"""Parse sweep outputs into structured Python objects.

Handles three data sources per run:

  * sweep CSV (per-trial: e2e_ms, walker_ms, tier counts, ...)
  * jac_server_*.log — one file per trial, containing:
      - [HIT-STATS-SERIES] ... a checkpoint list emitted at request end
      - [PREFETCH-WORKER-TIMES] ... per-worker prefetch durations (ms)
      - [TTG-COVERAGE] ... type breakdown of the prefetch list
"""

from __future__ import annotations

import ast
import csv as _csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


_HIT_STATS_MARKER = "[HIT-STATS-SERIES] "
_WORKER_TIMES_MARKER = "[PREFETCH-WORKER-TIMES] "
_TTG_COVERAGE_MARKER = "[TTG-COVERAGE] "
_FILE_RE = re.compile(r"limit(\d+)_trial(\d+)\.log$")
_COVERAGE_RE = re.compile(
    r"prefetched_by_type=(\{[^}]*\})\s+index_by_type=(\{[^}]*\})\s+max_length=(\d+)"
)


@dataclass
class TrialLog:
    """One walker call's diagnostic output."""

    limit: int
    trial: int
    source: Path
    hit_stats_series: list[tuple[str, dict[str, int]]] = field(default_factory=list)
    worker_times_ms: list[float] = field(default_factory=list)
    ttg_coverage_raw: str = ""
    prefetched_by_type: dict[str, int] = field(default_factory=dict)
    index_by_type: dict[str, int] = field(default_factory=dict)
    max_length: int | None = None
    distinct_ids_by_tier: dict[str, int] = field(default_factory=dict)
    # New extended access log (op,tier,n_in,n_out,type): per-op DB traffic.
    # {op: {"calls": N, "docs": sum(n_out), "db_docs": sum(n_out @ L3/DB)}}
    db_ops: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def plan_size(self) -> int:
        """Total UUIDs the runtime prefetched for this request."""
        return sum(self.prefetched_by_type.values())

    @property
    def distinct_covered(self) -> int:
        """Distinct anchor IDs the walker served from L1 or L2 (i.e. from
        the TTG-populated cache tiers).  Requires the sibling access_log
        CSV to have been picked up."""
        return self.distinct_ids_by_tier.get("L1", 0) + self.distinct_ids_by_tier.get("L2", 0)


def _parse_json_msg(line: str) -> str:
    try:
        return json.loads(line).get("msg", "")
    except Exception:
        return line


def _extract_after(msg: str, marker: str):
    i = msg.find(marker)
    if i < 0:
        return None
    payload = msg[i + len(marker):].rstrip("\"'} \n")
    try:
        return ast.literal_eval(payload)
    except Exception:
        return None


def parse_trial_log(path: Path) -> TrialLog | None:
    m = _FILE_RE.search(str(path))
    if not m:
        return None
    tl = TrialLog(limit=int(m.group(1)), trial=int(m.group(2)), source=path)
    # A concurrent sweep may `rm -rf logs` between glob() and read_text();
    # treat the file as gone and skip.
    try:
        text = path.read_text()
    except (FileNotFoundError, IsADirectoryError):
        return None
    for line in text.splitlines():
        msg = _parse_json_msg(line)
        if _HIT_STATS_MARKER in msg:
            series = _extract_after(msg, _HIT_STATS_MARKER)
            if series:
                tl.hit_stats_series = series
        elif _WORKER_TIMES_MARKER in msg:
            times = _extract_after(msg, _WORKER_TIMES_MARKER)
            if times is not None:
                tl.worker_times_ms = times
        elif _TTG_COVERAGE_MARKER in msg:
            # Multiple coverage lines can appear per log (login walker plus
            # the benchmark walker).  Overwrite so we always end up with
            # the last one — the benchmark call, which is what runs right
            # before the server is killed.
            tl.ttg_coverage_raw = msg[msg.find(_TTG_COVERAGE_MARKER):]
            match = _COVERAGE_RE.search(msg)
            if match:
                try:
                    tl.prefetched_by_type = ast.literal_eval(match.group(1))
                    tl.index_by_type = ast.literal_eval(match.group(2))
                    tl.max_length = int(match.group(3))
                except Exception:
                    pass
    return tl


def _load_access_log_distinct(logs_dir: Path, limit: int, trial: int) -> dict[str, int]:
    """Distinct anchor ID count per tier from the sibling access_log CSV.

    Filename patterns:
      - LinkedList: access_log_limit<X>_trial<Y>.csv
      - LittleX / Jacord: access_log_<walker>_limit<X>_trial<Y>.csv
    Glob catches both.  Returns {} if no file matches.
    """
    seen: dict[str, set[str]] = {}
    for path in logs_dir.glob(f"access_log*limit{limit}_trial{trial}.csv"):
        # Same race as parse_trial_log: a concurrent sweep may unlink the
        # file between glob() and open().  Skip missing files.
        try:
            fh = open(path)
        except FileNotFoundError:
            continue
        with fh:
            for row in _csv.DictReader(fh):
                # New schema (op,tier,n_in,n_out,type) has no per-id column;
                # this metric only applies to the old id,tier,type logs.
                if "id" not in row:
                    break
                seen.setdefault(row["tier"], set()).add(row["id"])
    return {tier: len(ids) for tier, ids in seen.items()}


_DB_OPS = [
    "node_pages", "hop_rows", "edge_endpoints", "existing_ids",
    "filter_ids", "batch_get", "get",
]


def _load_access_log_db_ops(
    logs_dir: Path, limit: int, trial: int
) -> dict[str, dict[str, int]]:
    """Per-op DB traffic from the sibling access_log (new schema:
    op,tier,n_in,n_out,type).

    Returns {op: {"calls": N, "docs": sum(n_out),
                  "db_docs": sum(n_out where tier in {L3, DB})}}.
    ``db_docs`` is the real DB read volume (L1/L2 are cache hits, excluded).
    Empty if the log is the old id,tier,type schema or missing.
    """
    agg: dict[str, dict[str, int]] = {}
    for path in logs_dir.glob(f"access_log*limit{limit}_trial{trial}.csv"):
        try:
            fh = open(path)
        except FileNotFoundError:
            continue
        with fh:
            reader = _csv.DictReader(fh)
            if reader.fieldnames is None or "op" not in reader.fieldnames:
                continue  # old schema — no per-op data
            for row in reader:
                op = row.get("op") or "?"
                tier = row.get("tier") or ""
                try:
                    n_out = int(row.get("n_out") or 0)
                except ValueError:
                    n_out = 0
                d = agg.setdefault(op, {"calls": 0, "docs": 0, "db_docs": 0})
                d["calls"] += 1
                d["docs"] += n_out
                if tier in ("L3", "DB"):
                    d["db_docs"] += n_out
    return agg


def parse_logs_dir(logs_dir: Path) -> list[TrialLog]:
    if not logs_dir.exists():
        return []
    out: list[TrialLog] = []
    for p in sorted(logs_dir.glob("jac_server_*.log")):
        tl = parse_trial_log(p)
        if tl is None:
            continue
        tl.distinct_ids_by_tier = _load_access_log_distinct(logs_dir, tl.limit, tl.trial)
        tl.db_ops = _load_access_log_db_ops(logs_dir, tl.limit, tl.trial)
        out.append(tl)
    return out


def load_csv(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv_path)
    for col in df.columns:
        if col in {"walker"}:
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

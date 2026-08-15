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

    @property
    def request_done_counts(self) -> dict[str, int]:
        """Tier counts at request end from [HIT-STATS-SERIES]."""
        for label, snap in reversed(self.hit_stats_series):
            if label == "request_done":
                return snap
        for label, snap in reversed(self.hit_stats_series):
            if label == "walker_done":
                return snap
        return {}


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


def apply_log_tier_counts(df: pd.DataFrame, logs: list[TrialLog]) -> pd.DataFrame:
    """Prefer request_done tier counts from logs over CSV tier columns.

    Some older app harnesses wrote placeholder zeros to l1_hit_rate/l1/l2/l3
    even though the Jac server log contains the real [HIT-STATS-SERIES]
    counters.  The Analyze tab should display observed runtime counters, so
    merge those log-derived values into the dataframe when available.
    """
    if df.empty or not logs:
        return df

    rows: list[dict[str, float | int]] = []
    for tl in logs:
        counts = tl.request_done_counts
        if not counts:
            continue
        l1 = int(counts.get("L1", 0))
        l2 = int(counts.get("L2", 0))
        l3 = int(counts.get("L3", 0))
        miss = int(counts.get("MISS", 0))
        total = l1 + l2 + l3 + miss
        rows.append({
            "prefetch_limit": tl.limit,
            "trial": tl.trial,
            "l1_hit_rate_log": (l1 * 100.0 / total) if total else 0.0,
            "l1_log": l1,
            "l2_log": l2,
            "l3_log": l3,
            "miss_log": miss,
        })
    if not rows:
        return df

    out = df.copy()
    for col in ("prefetch_limit", "trial"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")

    log_df = pd.DataFrame(rows)
    merged = out.merge(log_df, on=["prefetch_limit", "trial"], how="left")
    for base, log_col in [
        ("l1_hit_rate", "l1_hit_rate_log"),
        ("l1", "l1_log"),
        ("l2", "l2_log"),
        ("l3", "l3_log"),
        ("miss", "miss_log"),
    ]:
        if base in merged.columns and log_col in merged.columns:
            merged[base] = merged[log_col].combine_first(merged[base])
    return merged.drop(
        columns=[
            c for c in [
                "l1_hit_rate_log", "l1_log", "l2_log", "l3_log", "miss_log",
            ]
            if c in merged.columns
        ]
    )

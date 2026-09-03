"""OOP-only LinkedList traversal over Jac's Postgres anchors table.

This module deliberately avoids Jac walkers, visit, TTG, and the prefetch
policy interface. It models the persisted Jac graph as ordinary Python objects
backed by the same PgSQL schema as the LinkedList benchmark.
"""

from __future__ import annotations

import csv
import cProfile
import json
import os
import pstats
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11 compatibility.
    tomllib = None  # type: ignore[assignment]


DEFAULT_POSTGRES_URI = "postgresql://jac:jac@localhost:5432/jac_db"
CANONICAL_POLICIES = {
    "none",
    "capre",
}
POLICY_ALIASES = {
    "none": "none",
    "oop-none": "none",
    "capre": "capre",
    "oop-capre": "capre",
}
POLICIES = set(POLICY_ALIASES)

RESULT_COLUMNS = [
    "policy",
    "prefetch_limit",
    "trial",
    "start_id",
    "visited",
    "checksum",
    "first_value",
    "last_value",
    "e2e_ms",
    "db_ms",
    "cpu_ms",
    "prefetch_ms",
    "query_count",
    "l1",
    "l3",
    "actual_ids",
    "prefetched_ids",
    "covered_ids",
    "overfetch_ids",
    "undercoverage_ids",
    "coverage",
    "accuracy",
    "serialized_bytes",
    "access_log",
    "actual_file",
    "prefetch_file",
    "error",
]

PROFILE_COLUMNS = [
    "node_num",
    "edge_num",
    "tweet_num",
    "ttg_enabled",
    "ttg_total_ms",
    "topo_idx_ms",
    "ttg_ms",
    "prefetch_ms",
    "walker_ms",
    "resolve_total_ms",
]


@dataclass
class Item:
    id: str
    value: int
    index: int


@dataclass
class Edge:
    id: str
    src: str
    dst: str


@dataclass
class AccessRecord:
    phase: str
    op: str
    anchor_id: str
    anchor_kind: str
    arch_type: str
    tier: str
    query_ms: float


@dataclass
class TrialMetrics:
    policy: str
    prefetch_limit: int
    trial: int
    start_id: str
    visited: int
    checksum: int
    first_value: int | None
    last_value: int | None
    e2e_ms: float
    db_ms: float
    cpu_ms: float
    prefetch_ms: float
    query_count: int
    l1: int
    l3: int
    actual_ids: int
    prefetched_ids: int
    covered_ids: int
    overfetch_ids: int
    undercoverage_ids: int
    coverage: float
    accuracy: float
    serialized_bytes: int
    access_log: str = ""
    actual_file: str = ""
    prefetch_file: str = ""
    error: str = ""

    def as_row(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "prefetch_limit": self.prefetch_limit,
            "trial": self.trial,
            "start_id": self.start_id,
            "visited": self.visited,
            "checksum": self.checksum,
            "first_value": "" if self.first_value is None else self.first_value,
            "last_value": "" if self.last_value is None else self.last_value,
            "e2e_ms": f"{self.e2e_ms:.3f}",
            "db_ms": f"{self.db_ms:.3f}",
            "cpu_ms": f"{self.cpu_ms:.3f}",
            "prefetch_ms": f"{self.prefetch_ms:.3f}",
            "query_count": self.query_count,
            "l1": self.l1,
            "l3": self.l3,
            "actual_ids": self.actual_ids,
            "prefetched_ids": self.prefetched_ids,
            "covered_ids": self.covered_ids,
            "overfetch_ids": self.overfetch_ids,
            "undercoverage_ids": self.undercoverage_ids,
            "coverage": f"{self.coverage:.1f}",
            "accuracy": f"{self.accuracy:.1f}",
            "serialized_bytes": self.serialized_bytes,
            "access_log": self.access_log,
            "actual_file": self.actual_file,
            "prefetch_file": self.prefetch_file,
            "error": self.error,
        }


class PgLinkedListStore:
    """Object-store style adapter backed by Jac's anchors table."""

    def __init__(self, postgres_uri: str) -> None:
        self.postgres_uri = postgres_uri
        self.conn = _connect(postgres_uri)
        self.conn.autocommit = True
        self.items: dict[str, Item] = {}
        self.next_edges: dict[str, Edge | None] = {}
        self.prefetched_order: list[str] = []
        self.prefetched_seen: set[str] = set()
        self.actual_order: list[str] = []
        self.actual_seen: set[str] = set()
        self.records: list[AccessRecord] = []
        self.query_count = 0
        self.db_ms = 0.0
        self.l1 = 0
        self.l3 = 0

    def close(self) -> None:
        self.conn.close()

    def load_item(self, item_id: str, *, phase: str = "actual") -> Item | None:
        cached = self.items.get(item_id)
        if cached is not None:
            if phase == "actual":
                self._record_actual(item_id)
                self.l1 += 1
                self.records.append(
                    AccessRecord(phase, "load_item", item_id, "NodeAnchor", "Item", "L1", 0.0)
                )
            return cached

        rows, ms = self._query(
            """
            SELECT id::text AS id, props
            FROM anchors
            WHERE id = %s::uuid
              AND kind = 'NodeAnchor'
              AND arch_type = 'Item'
            """,
            (item_id,),
        )
        if not rows:
            if phase == "actual":
                self.records.append(
                    AccessRecord(phase, "load_item", item_id, "NodeAnchor", "Item", "MISS", ms)
                )
            return None

        item = _item_from_row(rows[0])
        self.items[item.id] = item
        if phase == "actual":
            self._record_actual(item.id)
            self.l3 += 1
            self.records.append(
                AccessRecord(phase, "load_item", item.id, "NodeAnchor", "Item", "L3", ms)
            )
        else:
            self._record_prefetched(item.id)
            self.records.append(
                AccessRecord(phase, "prefetch_item", item.id, "NodeAnchor", "Item", "L3", ms)
            )
        return item

    def load_next_edge(self, src_id: str, *, phase: str = "actual") -> Edge | None:
        if src_id in self.next_edges:
            cached = self.next_edges[src_id]
            if phase == "actual" and cached is not None:
                self._record_actual(cached.id)
                self.l1 += 1
                self.records.append(
                    AccessRecord(
                        phase, "load_next_edge", cached.id, "EdgeAnchor", "Next", "L1", 0.0
                    )
                )
            return cached

        rows, ms = self._query(
            """
            SELECT id::text AS id, src::text AS src, dst::text AS dst
            FROM anchors
            WHERE kind = 'EdgeAnchor'
              AND arch_type = 'Next'
              AND src = %s::uuid
            ORDER BY seq NULLS LAST, id
            LIMIT 1
            """,
            (src_id,),
        )
        edge = _edge_from_row(rows[0]) if rows else None

        if edge is not None or phase == "actual":
            self.next_edges[src_id] = edge
        if edge is not None:
            if phase == "actual":
                self._record_actual(edge.id)
                self.l3 += 1
                self.records.append(
                    AccessRecord(phase, "load_next_edge", edge.id, "EdgeAnchor", "Next", "L3", ms)
                )
            else:
                self._record_prefetched(edge.id)
                self.records.append(
                    AccessRecord(phase, "prefetch_next_edge", edge.id, "EdgeAnchor", "Next", "L3", ms)
                )
        return edge

    def next_item(self, current: Item) -> Item | None:
        edge = self.load_next_edge(current.id, phase="actual")
        if edge is None:
            return None
        return self.load_item(edge.dst, phase="actual")

    def prefetch_next(self, src_id: str, remaining_budget: int | None = None) -> int:
        """CAPRe-like one-hop association prefetch for one source object."""

        if remaining_budget is not None and remaining_budget <= 0:
            return 0
        before = len(self.prefetched_seen)
        edge = self.load_next_edge(src_id, phase="prefetch")
        if edge is None:
            return 0
        if remaining_budget is not None and len(self.prefetched_seen) - before >= remaining_budget:
            return len(self.prefetched_seen) - before
        self.load_item(edge.dst, phase="prefetch")
        return len(self.prefetched_seen) - before

    def write_access_log(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=[
                    "phase",
                    "op",
                    "anchor_id",
                    "anchor_kind",
                    "arch_type",
                    "tier",
                    "query_ms",
                ],
            )
            writer.writeheader()
            for rec in self.records:
                writer.writerow(
                    {
                        "phase": rec.phase,
                        "op": rec.op,
                        "anchor_id": rec.anchor_id,
                        "anchor_kind": rec.anchor_kind,
                        "arch_type": rec.arch_type,
                        "tier": rec.tier,
                        "query_ms": f"{rec.query_ms:.3f}",
                    }
                )

    def _record_actual(self, anchor_id: str) -> None:
        if anchor_id not in self.actual_seen:
            self.actual_seen.add(anchor_id)
            self.actual_order.append(anchor_id)

    def _record_prefetched(self, anchor_id: str) -> None:
        if anchor_id not in self.prefetched_seen:
            self.prefetched_seen.add(anchor_id)
            self.prefetched_order.append(anchor_id)

    def _query(self, sql: str, params: tuple[Any, ...]) -> tuple[list[dict[str, Any]], float]:
        start = time.perf_counter()
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = list(cur.fetchall())
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self.query_count += 1
        self.db_ms += elapsed_ms
        return rows, elapsed_ms


class OopTraversal:
    """Mutable state for one LinkedList OOP/CAPRe request."""

    def __init__(
        self,
        start_id: str,
        prefetch_limit: int = 0,
        visit_limit: int = 10000,
        policy: str = "none",
        postgres_uri: str = "",
        profile_dir: str = "",
        profile_csv: str = "",
    ) -> None:
        policy = canonical_policy(policy)
        if not start_id:
            raise ValueError(
                "LinkedList OOP traversal requires start_id from the Jac "
                "setup_graph request; DB discovery is intentionally disabled."
            )
        if visit_limit <= 0:
            raise ValueError("visit_limit must be positive")

        self.start_id = start_id
        self.prefetch_limit = 0
        self.visit_limit = visit_limit
        self.policy = policy
        self.profile_dir = _resolve_profile_dir(profile_dir, profile_csv)
        self.profile_csv = _resolve_profile_csv(self.profile_dir, profile_csv)
        self.profiler: cProfile.Profile | None = None
        if self.profile_dir is not None:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            self.profiler = cProfile.Profile()
            self.profiler.enable()
        self.store = PgLinkedListStore(resolve_postgres_uri(postgres_uri))
        self.trial_start = time.perf_counter()
        self.prefetch_ms = 0.0
        self.cpu_ms = 0.0
        self.prefetched_budget = 0
        self.visited = 0
        self.checksum = 0
        self.first_value: int | None = None
        self.last_value: int | None = None
        self.closed = False

        try:
            self.current = self.store.load_item(start_id)
            if self.current is None:
                raise RuntimeError(f"start Item not found: {start_id}")
        except Exception:
            self.close()
            raise

    def load_start(self) -> Item | None:
        return self.current

    def record_value(self, value: int) -> None:
        start = time.perf_counter()
        if self.first_value is None:
            self.first_value = value
        self.last_value = value
        self.checksum += value
        self.visited += 1
        self.cpu_ms += (time.perf_counter() - start) * 1000.0

    def maybe_prefetch(self, src_id: str) -> int:
        if self.policy != "capre":
            return 0
        start = time.perf_counter()
        added = self.store.prefetch_next(src_id)
        self.prefetch_ms += (time.perf_counter() - start) * 1000.0
        self.prefetched_budget += added
        return added

    def next_item(self, current: Item) -> Item | None:
        return self.store.next_item(current)

    def finish_metrics(self, reports: list[int]) -> TrialMetrics:
        if self.visited != len(reports):
            self._sync_report_values(reports)

        start = time.perf_counter()
        serialized = json.dumps(reports, separators=(",", ":"))
        self.cpu_ms += (time.perf_counter() - start) * 1000.0
        e2e_ms = (time.perf_counter() - self.trial_start) * 1000.0
        quality = _quality(self.store.actual_order, self.store.prefetched_order)
        return TrialMetrics(
            policy=self.policy,
            prefetch_limit=self.prefetch_limit,
            trial=0,
            start_id=self.start_id,
            visited=len(reports),
            checksum=self.checksum,
            first_value=self.first_value,
            last_value=self.last_value,
            e2e_ms=e2e_ms,
            db_ms=self.store.db_ms,
            cpu_ms=self.cpu_ms,
            prefetch_ms=self.prefetch_ms,
            query_count=self.store.query_count,
            l1=self.store.l1,
            l3=self.store.l3,
            actual_ids=len(self.store.actual_seen),
            prefetched_ids=len(self.store.prefetched_seen),
            covered_ids=quality["covered"],
            overfetch_ids=quality["overfetch"],
            undercoverage_ids=quality["undercoverage"],
            coverage=quality["coverage"],
            accuracy=quality["accuracy"],
            serialized_bytes=len(serialized.encode("utf-8")),
        )

    def finish_response(
        self,
        reports: list[int],
        access_log: str = "",
        actual_file: str = "",
        prefetch_file: str = "",
        include_metrics: bool = False,
    ) -> list[int] | dict[str, Any]:
        try:
            metrics = self.finish_metrics(reports)
            if access_log:
                self.store.write_access_log(Path(access_log))
                metrics.access_log = access_log
            if actual_file:
                write_uuid_list(Path(actual_file), self.store.actual_order)
                metrics.actual_file = actual_file
            if prefetch_file:
                write_uuid_list(Path(prefetch_file), self.store.prefetched_order)
                metrics.prefetch_file = prefetch_file
            self.write_profile(metrics)
            if include_metrics:
                return {
                    "reports": reports,
                    "metrics": metrics.as_row(),
                }
            return reports
        finally:
            self.close()

    def write_profile(self, metrics: TrialMetrics) -> None:
        if self.profile_dir is None or self.profile_csv is None:
            return

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        if self.profiler is not None:
            self.profiler.disable()
            prof_path = self.profile_dir / "jac_server.prof"
            txt_path = self.profile_dir / "jac_server.txt"
            self.profiler.dump_stats(str(prof_path))
            with txt_path.open("w") as fh:
                stats = pstats.Stats(self.profiler, stream=fh)
                stats.strip_dirs().sort_stats("cumulative").print_stats(200)
            self.profiler = None
        write_profile_csv(self.profile_csv, metrics)

    def close(self) -> None:
        if not self.closed:
            self.store.close()
            self.closed = True

    def _sync_report_values(self, reports: list[int]) -> None:
        self.visited = len(reports)
        self.checksum = sum(reports)
        self.first_value = reports[0] if reports else None
        self.last_value = reports[-1] if reports else None


def traverse_linked_list(
    postgres_uri: str = "",
    *,
    policy: str,
    prefetch_limit: int = 0,
    visit_limit: int,
    start_id: str = "",
    profile_dir: str = "",
    profile_csv: str = "",
) -> tuple[TrialMetrics, PgLinkedListStore, list[int]]:
    run = OopTraversal(
        start_id,
        prefetch_limit=prefetch_limit,
        visit_limit=visit_limit,
        policy=policy,
        postgres_uri=postgres_uri,
        profile_dir=profile_dir,
        profile_csv=profile_csv,
    )
    reports: list[int] = []

    try:
        current = run.load_start()
        while current is not None and len(reports) < run.visit_limit:
            value = current.value
            reports.append(value)
            run.record_value(value)
            if len(reports) >= run.visit_limit:
                break
            run.maybe_prefetch(current.id)
            current = run.next_item(current)
        metrics = run.finish_metrics(reports)
        run.write_profile(metrics)
        return metrics, run.store, reports
    except Exception:
        run.close()
        raise


def oop_traverse(
    start_id: str,
    prefetch_limit: int = 0,
    visit_limit: int = 10000,
    policy: str = "none",
    postgres_uri: str = "",
    access_log: str = "",
    actual_file: str = "",
    prefetch_file: str = "",
    profile_dir: str = "",
    profile_csv: str = "",
    include_metrics: bool = False,
) -> list[int] | dict[str, Any]:
    run = OopTraversal(
        start_id,
        prefetch_limit=prefetch_limit,
        visit_limit=visit_limit,
        policy=policy,
        postgres_uri=postgres_uri,
        profile_dir=profile_dir,
        profile_csv=profile_csv,
    )
    reports: list[int] = []
    try:
        current = run.load_start()
        while current is not None and len(reports) < run.visit_limit:
            value = current.value
            reports.append(value)
            run.record_value(value)
            if len(reports) >= run.visit_limit:
                break
            run.maybe_prefetch(current.id)
            current = run.next_item(current)
        return run.finish_response(
            reports,
            access_log=access_log,
            actual_file=actual_file,
            prefetch_file=prefetch_file,
            include_metrics=include_metrics,
        )
    except Exception:
        run.close()
        raise


def resolve_postgres_uri(postgres_uri: str = "") -> str:
    explicit = postgres_uri.strip()
    if explicit:
        return explicit

    for key in ("JAC_DB_URL", "POSTGRES_URL", "DATABASE_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            return value

    config_uri = _postgres_uri_from_jac_toml()
    if config_uri:
        return config_uri
    return DEFAULT_POSTGRES_URI


def jac_id(obj: Any) -> str:
    return str(obj.__jac__.id)


def canonical_policy(policy: str) -> str:
    key = policy.strip().lower()
    try:
        return POLICY_ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"unsupported LinkedList OOP policy: {policy}") from exc


def write_uuid_list(path: Path, ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{anchor_id}\n" for anchor_id in ids))


def write_results_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writeheader()


def write_profile_csv(path: Path, metrics: TrialMetrics) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "node_num": "",
        "edge_num": "",
        "tweet_num": "",
        "ttg_enabled": metrics.policy,
        "ttg_total_ms": f"{metrics.e2e_ms:.3f}",
        "topo_idx_ms": "0.000",
        "ttg_ms": "0.000",
        "prefetch_ms": f"{metrics.prefetch_ms:.3f}",
        "walker_ms": f"{metrics.cpu_ms:.3f}",
        "resolve_total_ms": "0.000",
    }
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=PROFILE_COLUMNS)
        writer.writeheader()
        writer.writerow(row)


def append_result(path: Path, metrics: TrialMetrics) -> None:
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writerow(metrics.as_row())


def _connect(postgres_uri: str) -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depends on runtime image.
        raise RuntimeError(
            "LinkedList OOP/CAPRe traversal requires psycopg in the Jac runtime."
        ) from exc
    return psycopg.connect(postgres_uri, row_factory=dict_row)


def _postgres_uri_from_jac_toml() -> str:
    if tomllib is None:
        return ""
    path = Path(__file__).with_name("jac.toml")
    if not path.exists():
        return ""
    try:
        data = tomllib.loads(path.read_text())
    except Exception:
        return ""
    scale = data.get("scale", {})
    if not isinstance(scale, dict):
        return ""
    database = scale.get("database", {})
    if not isinstance(database, dict):
        return ""
    return str(database.get("url", "")).strip()


def _item_from_row(row: dict[str, Any]) -> Item:
    props = row["props"]
    if isinstance(props, str):
        props = json.loads(props)
    arch = props.get("archetype", {}) if isinstance(props, dict) else {}
    return Item(
        id=str(row["id"]),
        value=int(arch.get("value", 0)),
        index=int(arch.get("index", 0)),
    )


def _edge_from_row(row: dict[str, Any]) -> Edge:
    return Edge(id=str(row["id"]), src=str(row["src"]), dst=str(row["dst"]))


def _quality(actual_order: list[str], prefetched_order: list[str]) -> dict[str, float | int]:
    actual = set(actual_order)
    prefetched = set(prefetched_order)
    covered = len(actual & prefetched)
    overfetch = len(prefetched - actual)
    undercoverage = len(actual - prefetched)
    coverage = (covered * 100.0 / len(actual)) if actual else 100.0
    accuracy = (covered * 100.0 / len(prefetched)) if prefetched else 100.0
    return {
        "covered": covered,
        "overfetch": overfetch,
        "undercoverage": undercoverage,
        "coverage": coverage,
        "accuracy": accuracy,
    }


def _resolve_profile_dir(profile_dir: str, profile_csv: str) -> Path | None:
    explicit_dir = profile_dir.strip()
    explicit_csv = profile_csv.strip()
    if explicit_dir:
        return Path(explicit_dir)
    if explicit_csv:
        return Path(explicit_csv).parent
    env_dir = os.environ.get("JAC_PROFILE_DIR", "").strip()
    env_csv = os.environ.get("JAC_PROFILE_CSV", "").strip()
    if env_dir:
        return Path(env_dir)
    if env_csv:
        return Path(env_csv).parent
    return None


def _resolve_profile_csv(profile_dir: Path | None, profile_csv: str) -> Path | None:
    explicit_csv = profile_csv.strip()
    if explicit_csv:
        return Path(explicit_csv)
    env_csv = os.environ.get("JAC_PROFILE_CSV", "").strip()
    if env_csv:
        return Path(env_csv)
    if profile_dir is not None:
        return profile_dir / "profile.csv"
    return None


__all__ = [
    "DEFAULT_POSTGRES_URI",
    "CANONICAL_POLICIES",
    "POLICY_ALIASES",
    "POLICIES",
    "PROFILE_COLUMNS",
    "RESULT_COLUMNS",
    "AccessRecord",
    "Edge",
    "Item",
    "OopTraversal",
    "PgLinkedListStore",
    "TrialMetrics",
    "append_result",
    "canonical_policy",
    "jac_id",
    "oop_traverse",
    "resolve_postgres_uri",
    "traverse_linked_list",
    "write_results_header",
    "write_profile_csv",
    "write_uuid_list",
    "_quality",
]

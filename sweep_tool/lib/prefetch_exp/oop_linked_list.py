"""OOP-only LinkedList traversal over Jac's Postgres anchors table.

This module is intentionally outside Jac's walker/prefetch-policy path.  It
uses the same persisted `anchors` schema as the Jac benchmark, but models the
application as ordinary Python objects whose methods issue storage reads.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError as exc:  # pragma: no cover - exercised by CLI environment.
    raise RuntimeError(
        "oop_linked_list requires psycopg. Run it with the experiment image's "
        "/opt/selep-venv/bin/python or install psycopg locally."
    ) from exc


POLICIES = {
    "oop-none",
    "oop-capre-sync",
    "oop-capre-async",
    "oop-plan-batch",
}

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


@dataclass
class Item:
    """Plain OOP representation of the benchmark Item node."""

    id: str
    value: int
    index: int


@dataclass
class Edge:
    """Plain OOP representation of a Next edge."""

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


@dataclass
class PrefetchBundle:
    nodes: dict[str, Item] = field(default_factory=dict)
    edges: dict[str, Edge | None] = field(default_factory=dict)
    prefetched_ids: list[str] = field(default_factory=list)
    records: list[AccessRecord] = field(default_factory=list)
    query_count: int = 0
    db_ms: float = 0.0
    prefetch_ms: float = 0.0


class PgLinkedListStore:
    """Object-store style adapter backed by the Jac `anchors` table."""

    def __init__(self, postgres_uri: str) -> None:
        self.postgres_uri = postgres_uri
        self.conn = psycopg.connect(postgres_uri, row_factory=dict_row)
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
        self._lock = threading.Lock()

    def close(self) -> None:
        self.conn.close()

    def find_start_id(self) -> str:
        rows, _ = self._query(
            """
            SELECT id::text AS id
            FROM anchors
            WHERE kind = 'NodeAnchor'
              AND arch_type = 'Item'
              AND (props->'archetype'->>'index')::int = 0
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (),
        )
        if not rows:
            raise RuntimeError(
                "no LinkedList start Item found: expected an Item with index=0"
            )
        return str(rows[0]["id"])

    def load_item(self, item_id: str, *, phase: str = "actual") -> Item | None:
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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

    def prefetch_next_sync(self, src_id: str, remaining_budget: int | None = None) -> int:
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

    def prefetch_plan_batch(self, start_id: str, prefetch_limit: int) -> None:
        """Request-level concrete plan reference for LinkedList.

        This is not CAPRe.  It is intentionally included to show what changes
        once the system has a request/topology-level view.
        """

        if prefetch_limit <= 0:
            return
        rows, ms = self._query(
            """
            WITH RECURSIVE walk(node_id, edge_id, depth, budget_used) AS (
                SELECT %s::uuid, NULL::uuid, 0, 1
              UNION ALL
                SELECT e.dst, e.id, walk.depth + 1, walk.budget_used + 2
                FROM walk
                JOIN anchors e
                  ON e.kind = 'EdgeAnchor'
                 AND e.arch_type = 'Next'
                 AND e.src = walk.node_id
                WHERE walk.budget_used + 2 <= %s
            )
            SELECT node_id::text AS node_id, edge_id::text AS edge_id, depth
            FROM walk
            ORDER BY depth
            """,
            (start_id, prefetch_limit),
        )
        self.records.append(
            AccessRecord(
                "prefetch",
                "plan_next_chain",
                start_id,
                "Plan",
                "LinkedList",
                "L3",
                ms,
            )
        )
        ids: list[str] = []
        for row in rows:
            edge_id = row.get("edge_id")
            if edge_id:
                ids.append(str(edge_id))
            node_id = row.get("node_id")
            if node_id:
                ids.append(str(node_id))
        ids = _dedupe(ids)[:prefetch_limit]
        if ids:
            self._batch_load_anchors(ids, phase="prefetch")

    def merge_prefetch_bundle(self, bundle: PrefetchBundle) -> None:
        with self._lock:
            self.items.update(bundle.nodes)
            self.next_edges.update(bundle.edges)
            for anchor_id in bundle.prefetched_ids:
                if anchor_id not in self.prefetched_seen:
                    self.prefetched_seen.add(anchor_id)
                    self.prefetched_order.append(anchor_id)
        self.query_count += bundle.query_count
        self.db_ms += bundle.db_ms
        self.records.extend(bundle.records)

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

    def _batch_load_anchors(self, ids: list[str], *, phase: str) -> None:
        rows, ms = self._query(
            """
            SELECT id::text AS id,
                   kind,
                   arch_type,
                   src::text AS src,
                   dst::text AS dst,
                   props
            FROM anchors
            WHERE id = ANY(%s::uuid[])
            """,
            (ids,),
        )
        by_id = {str(row["id"]): row for row in rows}
        for anchor_id in ids:
            row = by_id.get(anchor_id)
            if row is None:
                continue
            kind = str(row["kind"])
            arch_type = str(row["arch_type"])
            if kind == "NodeAnchor" and arch_type == "Item":
                item = _item_from_row(row)
                with self._lock:
                    self.items[item.id] = item
            elif kind == "EdgeAnchor" and arch_type == "Next":
                edge = _edge_from_row(row)
                with self._lock:
                    self.next_edges[edge.src] = edge
            self._record_prefetched(anchor_id)
            self.records.append(
                AccessRecord(phase, "batch_load_anchor", anchor_id, kind, arch_type, "L3", ms)
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


class PrefetchWorker:
    """Independent connection used by async CAPRe-style prefetch."""

    def __init__(self, postgres_uri: str) -> None:
        self.conn = psycopg.connect(postgres_uri, row_factory=dict_row)
        self.conn.autocommit = True

    def close(self) -> None:
        self.conn.close()

    def fetch_next_bundle(
        self, src_id: str, remaining_budget: int | None = None
    ) -> PrefetchBundle:
        bundle = PrefetchBundle()
        if remaining_budget is not None and remaining_budget <= 0:
            return bundle
        start_prefetch = time.perf_counter()
        edge_rows, edge_ms = self._query(
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
            bundle,
        )
        edge = _edge_from_row(edge_rows[0]) if edge_rows else None
        bundle.edges[src_id] = edge
        if edge is not None:
            bundle.prefetched_ids.append(edge.id)
            bundle.records.append(
                AccessRecord("prefetch", "prefetch_next_edge", edge.id, "EdgeAnchor", "Next", "L3", edge_ms)
            )
            if remaining_budget is not None and len(bundle.prefetched_ids) >= remaining_budget:
                bundle.prefetch_ms = (time.perf_counter() - start_prefetch) * 1000.0
                return bundle
            item_rows, item_ms = self._query(
                """
                SELECT id::text AS id, props
                FROM anchors
                WHERE id = %s::uuid
                  AND kind = 'NodeAnchor'
                  AND arch_type = 'Item'
                """,
                (edge.dst,),
                bundle,
            )
            if item_rows:
                item = _item_from_row(item_rows[0])
                bundle.nodes[item.id] = item
                bundle.prefetched_ids.append(item.id)
                bundle.records.append(
                    AccessRecord("prefetch", "prefetch_item", item.id, "NodeAnchor", "Item", "L3", item_ms)
                )
        bundle.prefetch_ms = (time.perf_counter() - start_prefetch) * 1000.0
        return bundle

    def _query(
        self, sql: str, params: tuple[Any, ...], bundle: PrefetchBundle
    ) -> tuple[list[dict[str, Any]], float]:
        start = time.perf_counter()
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            rows = list(cur.fetchall())
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        bundle.query_count += 1
        bundle.db_ms += elapsed_ms
        return rows, elapsed_ms


def traverse_linked_list(
    postgres_uri: str,
    *,
    policy: str,
    prefetch_limit: int,
    visit_limit: int,
    start_id: str = "",
) -> tuple[TrialMetrics, PgLinkedListStore]:
    if policy not in POLICIES:
        raise ValueError(f"unsupported LinkedList OOP policy: {policy}")
    store = PgLinkedListStore(postgres_uri)
    trial_start = time.perf_counter()
    prefetch_ms = 0.0
    reports: list[int] = []
    checksum = 0
    first_value: int | None = None
    last_value: int | None = None
    cpu_ms = 0.0

    try:
        if not start_id:
            start_id = store.find_start_id()
        if policy == "oop-plan-batch":
            prefetch_start = time.perf_counter()
            store.prefetch_plan_batch(start_id, prefetch_limit)
            prefetch_ms += (time.perf_counter() - prefetch_start) * 1000.0

        current = store.load_item(start_id)
        if current is None:
            raise RuntimeError(f"start Item not found: {start_id}")

        executor: ThreadPoolExecutor | None = None
        worker: PrefetchWorker | None = None
        future: Future[PrefetchBundle] | None = None
        prefetched_budget = 0
        if policy == "oop-capre-async":
            executor = ThreadPoolExecutor(max_workers=1)
            worker = PrefetchWorker(postgres_uri)

        try:
            while current is not None and len(reports) < visit_limit:
                if policy == "oop-capre-sync" and prefetched_budget < prefetch_limit:
                    remaining = prefetch_limit - prefetched_budget
                    prefetch_start = time.perf_counter()
                    added = store.prefetch_next_sync(current.id, remaining_budget=remaining)
                    prefetch_ms += (time.perf_counter() - prefetch_start) * 1000.0
                    prefetched_budget += added
                elif (
                    policy == "oop-capre-async"
                    and executor is not None
                    and worker is not None
                    and prefetched_budget < prefetch_limit
                ):
                    future = executor.submit(
                        worker.fetch_next_bundle,
                        current.id,
                        prefetch_limit - prefetched_budget,
                    )

                # Same application CPU work as LinkedList.Traverse: touch the
                # value and append it to the response report list.
                cpu_start = time.perf_counter()
                value = current.value
                if first_value is None:
                    first_value = value
                last_value = value
                checksum += value
                reports.append(value)
                cpu_ms += (time.perf_counter() - cpu_start) * 1000.0

                if future is not None:
                    bundle = future.result()
                    store.merge_prefetch_bundle(bundle)
                    prefetch_ms += bundle.prefetch_ms
                    prefetched_budget = len(store.prefetched_seen)
                    future = None

                if len(reports) >= visit_limit:
                    break
                current = store.next_item(current)
        finally:
            if future is not None:
                store.merge_prefetch_bundle(future.result())
            if executor is not None:
                executor.shutdown(wait=True)
            if worker is not None:
                worker.close()

        cpu_start = time.perf_counter()
        serialized = json.dumps(reports, separators=(",", ":"))
        cpu_ms += (time.perf_counter() - cpu_start) * 1000.0
        e2e_ms = (time.perf_counter() - trial_start) * 1000.0
        quality = _quality(store.actual_order, store.prefetched_order)
        metrics = TrialMetrics(
            policy=policy,
            prefetch_limit=prefetch_limit,
            trial=0,
            start_id=start_id,
            visited=len(reports),
            checksum=checksum,
            first_value=first_value,
            last_value=last_value,
            e2e_ms=e2e_ms,
            db_ms=store.db_ms,
            cpu_ms=cpu_ms,
            prefetch_ms=prefetch_ms,
            query_count=store.query_count,
            l1=store.l1,
            l3=store.l3,
            actual_ids=len(store.actual_seen),
            prefetched_ids=len(store.prefetched_seen),
            covered_ids=quality["covered"],
            overfetch_ids=quality["overfetch"],
            undercoverage_ids=quality["undercoverage"],
            coverage=quality["coverage"],
            accuracy=quality["accuracy"],
            serialized_bytes=len(serialized.encode("utf-8")),
        )
        return metrics, store
    except Exception:
        store.close()
        raise


def write_uuid_list(path: Path, ids: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{anchor_id}\n" for anchor_id in ids))


def write_results_header(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writeheader()


def append_result(path: Path, metrics: TrialMetrics) -> None:
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_COLUMNS)
        writer.writerow(metrics.as_row())


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


def _dedupe(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for anchor_id in ids:
        if anchor_id in seen:
            continue
        seen.add(anchor_id)
        out.append(anchor_id)
    return out

import cProfile;
import contextvars;
import json;
import os;
import time;
import from concurrent.futures { ThreadPoolExecutor }
import from http { HTTPMethod }
import from pathlib { Path }
import from typing { cast }
import from jaclang { JacRuntimeInterface as Jac }
import from jaclang.project.config { get_config }
import from jaclang.runtime.builtin { restspec }
import from jaclang.server.session {
    _access_log_reset_for_tests,
    hit_stats_reset,
    hit_stats_snapshot
}

node Item {
    has value: int;
    has index: int;
}

edge Next {}

glob _DBRIDGE_LIKE_EXECUTOR: any = ThreadPoolExecutor(
    max_workers=int(os.environ.get("JAC_DBRIDGE_LIKE_WORKERS", "4"))
);

# Traverse the list and report every value in order
walker Traverse {
    has visited: int = 0;

    can visit_item with Item entry {
        self.visited += 1;
        report here.value;
        if self.visited >= 10000 {
            disengage;
        }
        visit [->:Next:->];
    }
}

# Sum all values in the list
walker Sum {
    has total: int = 0;

    can visit_item with Item entry {
        self.total += here.value;
        visit [->:Next:->];
    }

    can done with Item exit {
        report self.total;
    }
}

# Find first item matching a value, report its index
walker Find {
    has target: int;
    has found: bool = False;

    can visit_item with Item entry {
        if here.value == self.target {
            self.found = True;
            report here;
            disengage;
        }
        visit [->:Next:->];
    }
}

def setup_graph() -> list[str] {
    LIST_SIZE = int(os.environ.get("JAC_LIST_SIZE", "100"));

    head: Item = Item(value=0, index=0);
    root ++> head;

    prev = head;
    items: list[Item] = [head];

    for i in range(1, LIST_SIZE) {
        curr = Item(value=i, index=i);
        prev +>: Next :+> curr;
        prev = curr;
        items.append(curr);

        if i % 1000 == 0 {
            print(f"Created {i} items...");
        }
    }

    print(f"Built linked list of {LIST_SIZE} items");
    print(f"root: {_jac_id(root)}");

    return [_jac_id(item) for item in items];
}

def _jac_id(value: any) -> str {
    return str(cast(any, value).__jac__.id);
}

def _write_uuid_list(path: str, ids: list[str]) -> None {
    if not path {
        return;
    }
    p = Path(path);
    p.parent.mkdir(parents=True, exist_ok=True);
    p.write_text("".join([f"{uid}\n" for uid in ids]));
}

def _quality(actual_order: list[str], prefetched_order: list[str]) -> dict {
    actual = set(actual_order);
    prefetched = set(prefetched_order);
    covered = len(actual & prefetched);
    overfetch = len(prefetched - actual);
    undercoverage = len(actual - prefetched);
    coverage = covered * 100.0 / len(actual) if actual else 100.0;
    accuracy = covered * 100.0 / len(prefetched) if prefetched else 100.0;
    return {
        "covered": covered,
        "overfetch": overfetch,
        "undercoverage": undercoverage,
        "coverage": coverage,
        "accuracy": accuracy
    };
}

def _next_item_id(current_id: str, next_cache: dict[str, str]) -> str {
    if current_id in next_cache {
        return next_cache[current_id];
    }
    ctx = Jac.get_context();
    mem = ctx.mem;
    if mem is None or mem.store is None {
        raise RuntimeError("LinkedList OOP traversal requires a persisted PgSQL store");
    }
    mem.read_barrier();
    rows = mem.store.rows(
        """
        SELECT e.dst::text
        FROM anchors e
        JOIN anchors dst ON dst.id = e.dst
        WHERE e.kind = 'EdgeAnchor'
          AND e.src = CAST(:src AS uuid)
          AND e.arch_type = 'Next'
          AND dst.kind = 'NodeAnchor'
          AND dst.arch_type = 'Item'
        ORDER BY e.seq NULLS LAST, e.id
        LIMIT 1
        """,
        {"src": current_id}
    );
    next_id = str(rows[0][0]) if rows else "";
    next_cache[current_id] = next_id;
    return next_id;
}

def _dbridge_like_prefetch_next(current_id: str, next_cache: dict[str, str]) -> dict[str, any] {
    started = time.perf_counter();
    edge_start = time.perf_counter();
    was_cached = current_id in next_cache;
    next_id = _next_item_id(current_id, next_cache);
    edge_ms = (time.perf_counter() - edge_start) * 1000.0;
    next_obj: (Item | None) = None;
    materialize_ms: float = 0.0;

    if next_id {
        materialize_start = time.perf_counter();
        next_obj = cast((Item | None), Jac.get_object(next_id));
        materialize_ms = (time.perf_counter() - materialize_start) * 1000.0;
        if next_obj is None {
            raise ValueError(f"prefetched Item not found: {next_id}");
        }
    }

    return {
        "next_id": next_id,
        "item": next_obj,
        "db_ms": edge_ms,
        "materialize_ms": materialize_ms,
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
        "queried": not was_cached
    };
}

def _submit_dbridge_like_prefetch(current_id: str, next_cache: dict[str, str]) -> any {
    ctx = contextvars.copy_context();
    return _DBRIDGE_LIKE_EXECUTOR.submit(
        ctx.run,
        _dbridge_like_prefetch_next,
        current_id,
        next_cache
    );
}

def _write_oop_profile(
    profile_dir: str,
    profile_csv: str,
    policy: str,
    profiler: any,
    e2e_ms: float,
    prefetch_ms: float,
    walker_ms: float,
    materialize_ms: float,
    prefetch_wait_ms: float
) -> None {
    out_dir = Path(profile_dir) if profile_dir else Path(profile_csv).parent if profile_csv else None;
    if out_dir is None {
        return;
    }
    out_dir.mkdir(parents=True, exist_ok=True);
    if profiler is not None {
        profiler.disable();
        prof_path = out_dir / "jac_server.prof";
        txt_path = out_dir / "jac_server.txt";
        profiler.dump_stats(str(prof_path));
        txt_path.write_text(f"Profile saved to {prof_path}\n");
    }
    csv_path = Path(profile_csv) if profile_csv else out_dir / "profile.csv";
    csv_path.parent.mkdir(parents=True, exist_ok=True);
    csv_path.write_text(
        "node_num,edge_num,tweet_num,ttg_enabled,ttg_total_ms,topo_idx_ms,ttg_ms,prefetch_ms,walker_ms,resolve_total_ms,materialize_ms,prefetch_wait_ms\n"
        + f",,,{policy},{e2e_ms:.3f},0.000,0.000,{prefetch_ms:.3f},{walker_ms:.3f},0.000,{materialize_ms:.3f},{prefetch_wait_ms:.3f}\n"
    );
}

@restspec(method=HTTPMethod.POST, path="/dbridge_like/Traverse/{start_id}")
def oop_traverse(start_id: str) -> any {
    access_log = os.environ.get("JAC_DBRIDGE_LIKE_ACCESS_LOG", "").strip();
    cfg = get_config();
    if not access_log and cfg is not None {
        access_log = str(cast(any, cfg).run.access_log or "");
    }
    actual_file = os.environ.get("JAC_DBRIDGE_LIKE_ACTUAL_FILE", "").strip();
    prefetch_file = os.environ.get("JAC_DBRIDGE_LIKE_PREFETCH_FILE", "").strip();
    profile_dir = (
        os.environ.get("JAC_DBRIDGE_LIKE_PROFILE_DIR", "").strip()
        or os.environ.get("JAC_PROFILE_DIR", "").strip()
    );
    profile_csv = (
        os.environ.get("JAC_DBRIDGE_LIKE_PROFILE_CSV", "").strip()
        or os.environ.get("JAC_PROFILE_CSV", "").strip()
    );

    if not actual_file {
        raise ValueError("JAC_DBRIDGE_LIKE_ACTUAL_FILE is required");
    }
    if not prefetch_file {
        raise ValueError("JAC_DBRIDGE_LIKE_PREFETCH_FILE is required");
    }
    if access_log {
        if cfg is not None {
            cast(any, cfg).run.access_log = access_log;
            _access_log_reset_for_tests();
        }
    }

    profile_out_dir = Path(profile_dir) if profile_dir else Path(profile_csv).parent if profile_csv else None;
    profiler: any = None;
    if profile_out_dir is not None {
        profile_out_dir.mkdir(parents=True, exist_ok=True);
        profiler = cProfile.Profile();
        profiler.enable();
    }

    hit_stats_reset();
    trial_start = time.perf_counter();
    prefetch_ms: float = 0.0;
    reports: list[int] = [];
    actual_order: list[str] = [];
    prefetched_order: list[str] = [];
    prefetched_seen: set[str] = set();
    next_cache: dict[str, str] = {};
    next_item: (Item | None) = None;
    db_ms: float = 0.0;
    materialize_ms: float = 0.0;
    prefetch_wait_ms: float = 0.0;
    query_count: int = 0;
    max_visits = 10000;
    current_id = start_id;

    for i in range(max_visits) {
        if not current_id {
            break;
        }
        current: (Item | None) = None;
        if next_item is not None and _jac_id(next_item) == current_id {
            current = next_item;
            next_item = None;
        } else {
            current = cast((Item | None), Jac.get_object(current_id));
        }
        if current is None {
            raise ValueError(f"Item not found during traversal: {current_id}");
        }

        current_id = _jac_id(current);
        actual_order.append(current_id);
        dbridge_like_future: any = None;
        if (len(reports) + 1) < max_visits {
            dbridge_like_future = _submit_dbridge_like_prefetch(current_id, next_cache);
        }

        value = current.value;
        reports.append(value);

        if len(reports) < max_visits {
            wait_start = time.perf_counter();
            prefetch_result = dbridge_like_future.result();
            prefetch_wait_ms += (time.perf_counter() - wait_start) * 1000.0;
            next_id = str(prefetch_result["next_id"]);
            db_ms += float(prefetch_result["db_ms"]);
            materialize_ms += float(prefetch_result["materialize_ms"]);
            prefetch_ms += float(prefetch_result["elapsed_ms"]);
            if bool(prefetch_result["queried"]) {
                query_count += 1;
            }
            if next_id {
                next_item = cast((Item | None), prefetch_result["item"]);
            }
            if not next_id {
                break;
            }
            if next_id not in prefetched_seen {
                prefetched_seen.add(next_id);
                prefetched_order.append(next_id);
            }
            current_id = next_id;
        }
    }

    e2e_ms = (time.perf_counter() - trial_start) * 1000.0;
    walker_ms = e2e_ms - prefetch_wait_ms;
    quality = _quality(actual_order, prefetched_order);
    hits = hit_stats_snapshot();
    l1 = int(hits.get("L1", 0));
    l2 = int(hits.get("L2", 0));
    l3 = int(hits.get("L3", 0));
    miss = int(hits.get("MISS", 0));
    serialized = json.dumps(reports, separators=(",", ":"));

    _write_uuid_list(actual_file, actual_order);
    _write_uuid_list(prefetch_file, prefetched_order);
    _write_oop_profile(
        profile_dir,
        profile_csv,
        "dbridge_like",
        profiler,
        e2e_ms,
        prefetch_ms,
        walker_ms,
        materialize_ms,
        prefetch_wait_ms
    );

    metrics = {
        "policy": "dbridge_like",
        "prefetch_limit": 0,
        "trial": 0,
        "start_id": start_id,
        "visited": len(reports),
        "checksum": sum(reports),
        "first_value": reports[0] if reports else "",
        "last_value": reports[-1] if reports else "",
        "e2e_ms": f"{e2e_ms:.3f}",
        "db_ms": f"{db_ms:.3f}",
        "materialize_ms": f"{materialize_ms:.3f}",
        "cpu_ms": f"{walker_ms:.3f}",
        "prefetch_ms": f"{prefetch_ms:.3f}",
        "prefetch_wait_ms": f"{prefetch_wait_ms:.3f}",
        "query_count": query_count,
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "miss": miss,
        "actual_ids": len(actual_order),
        "prefetched_ids": len(prefetched_order),
        "covered_ids": quality["covered"],
        "overfetch_ids": quality["overfetch"],
        "undercoverage_ids": quality["undercoverage"],
        "coverage": f"{quality['coverage']:.1f}",
        "accuracy": f"{quality['accuracy']:.1f}",
        "serialized_bytes": len(serialized.encode("utf-8")),
        "access_log": access_log,
        "actual_file": actual_file,
        "prefetch_file": prefetch_file,
        "error": ""
    };
    return {
        "reports": reports,
        "metrics": metrics
    };
}

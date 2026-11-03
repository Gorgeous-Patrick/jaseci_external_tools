"""JDrive backend - nodes, edges, and walker endpoints.

File bytes are stored on the server via the ambient `store()` builtin
(LocalStorage, local disk under ./blobs). Uploads use a native multipart
multipart file field; the File node keeps a `blob_key` = the storage path.

v1: a single global root owns the drive; walkers spawn on `root` (GetRoot) or
on a Folder/File anchor by id. Sharing is deferred; the schema is ready.
"""

import cProfile;
import contextvars;
import json;
import os;
import time;
import from concurrent.futures { ThreadPoolExecutor }
import from datetime { datetime }
import from http { HTTPMethod }
import from pathlib { Path }
import from uuid { UUID }
# local-disk object store (no cloud); create_dirs=True by default
import from typing { cast }
import from jaclang { JacRuntimeInterface as Jac }
import from jaclang.project.config { get_config }
import from jaclang.runtime.builtin { restspec }
import from jaclang.server.session {
    _access_log_reset_for_tests,
    hit_stats_reset,
    hit_stats_snapshot
}

glob storage: any = store(base_path="./blobs");
glob _DBRIDGE_LIKE_EXECUTOR: any = ThreadPoolExecutor(
    max_workers=int(os.environ.get("JAC_DBRIDGE_LIKE_WORKERS", "4"))
);

def now() -> str {
    return datetime.now().isoformat();
}

# --- nodes ------------------------------------------------------------------
node Drive {
    has created_at: str = "";
}

node Folder {
    has name: str = "";
    has created_at: str = "";
    has updated_at: str = "";
    has trashed: bool = False;
}

node File {
    has name: str = "";
    has mime: str = "application/octet-stream";
    has size: int = 0;
    has blob_key: str = "";       # storage path of the bytes
    has created_at: str = "";
    has updated_at: str = "";
    has trashed: bool = False;
}

# --- edges ------------------------------------------------------------------
edge Contains {}

# --- views ------------------------------------------------------------------
obj EntryView {
    has id: str = "",
        kind: str = "",       # "folder" | "file"
        name: str = "",
        size: int = 0,
        mime: str = "";
}

obj FolderView {
    has id: str = "",
        name: str = "",
        entries: list[EntryView] = [];
}

obj FolderTreeEntry {
    has id: str = "",
        name: str = "",
        depth: int = 0,
        path: str = "";
}

obj FolderTreeView {
    has id: str = "",
        entries: list[FolderTreeEntry] = [];
}

# --- walker endpoints -------------------------------------------------------

walker GetRoot {
    can run with Root entry;
}

walker ListFolder {
    can run with Folder entry;
}

walker VisibleFolderTree {
    has start_id: str = "",
        entries: list[FolderTreeEntry] = [],
        depths: dict[str, int] = {},
        paths: dict[str, str] = {},
        reports: list[FolderTreeView] = [];

    can walk with Folder entry;
    can done with Folder exit;
}

walker NewFolder {
    has name: str;
    can run with Folder entry;
}

walker TrashFolder {
    can run with Folder entry;
}

walker Upload {
    has file: any;                # native multipart file param
    can run with Folder entry;
}

walker Download {
    can run with File entry;      # reports {name, mime, size, content_b64}
}

def _dbridge_like_store() -> any {
    ctx = Jac.get_context();
    mem = ctx.mem;
    if mem is None or mem.store is None {
        raise RuntimeError("dbridge_like requires a persisted PgSQL store");
    }
    mem.read_barrier();
    return mem.store;
}

def _dbridge_like_jac_id(value: any) -> str {
    return jid(value);
}

def _dbridge_like_uuid_hex(value: any) -> str {
    return str(UUID(str(value))).replace("-", "");
}

def _dbridge_like_remember(order: list[str], seen: set[str], uid: str) -> None {
    if uid and uid not in seen {
        seen.add(uid);
        order.append(uid);
    }
}

def _dbridge_like_write_uuid_list(path: str, ids: list[str]) -> None {
    if not path {
        return;
    }
    p = Path(path);
    p.parent.mkdir(parents=True, exist_ok=True);
    p.write_text("".join([f"{uid}\n" for uid in ids]));
}

def _dbridge_like_quality(actual_order: list[str], prefetched_order: list[str]) -> dict {
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

def _dbridge_like_profile_paths -> dict[str, str] {
    return {
        "profile_dir": os.environ.get("JAC_DBRIDGE_LIKE_PROFILE_DIR", "").strip()
            or os.environ.get("JAC_PROFILE_DIR", "").strip(),
        "profile_csv": os.environ.get("JAC_DBRIDGE_LIKE_PROFILE_CSV", "").strip()
            or os.environ.get("JAC_PROFILE_CSV", "").strip()
    };
}

def _dbridge_like_write_profile(
    profile_dir: str,
    profile_csv: str,
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
        + f",,,dbridge_like,{e2e_ms:.3f},0.000,0.000,{prefetch_ms:.3f},{walker_ms:.3f},0.000,{materialize_ms:.3f},{prefetch_wait_ms:.3f}\n"
    );
}

def _dbridge_like_batch_get(ids: list[str]) -> dict[str, any] {
    if not ids {
        return {};
    }
    ctx = Jac.get_context();
    mem = ctx.mem;
    if mem is None {
        raise RuntimeError("dbridge_like requires an active Jac memory session");
    }
    uuid_ids: list[UUID] = [];
    seen: set[str] = set();
    for uid in ids {
        if uid and uid not in seen {
            seen.add(uid);
            uuid_ids.append(UUID(uid));
        }
    }
    anchors = mem.batch_get(uuid_ids);
    out: dict[str, any] = {};
    for uid in ids {
        if uid {
            anchor = anchors.get(UUID(uid));
            if anchor is not None and cast(any, anchor).archetype is not None {
                out[uid] = cast(any, anchor).archetype;
            }
        }
    }
    return out;
}

def _dbridge_like_batch_folders(ids: list[str], context: str) -> dict[str, Folder] {
    materialized = _dbridge_like_batch_get(ids);
    folders: dict[str, Folder] = {};
    for uid in ids {
        folder = cast((Folder | None), materialized.get(uid));
        if folder is None {
            raise ValueError(f"Folder not found during dbridge_like {context}: {uid}");
        }
        folders[uid] = folder;
    }
    return folders;
}

def _dbridge_like_child_folder_ids(parent_id: str) -> list[str] {
    canonical_parent_id = str(UUID(parent_id));
    rows = _dbridge_like_store().rows(
        """
        SELECT e.dst::text
        FROM anchors e
        JOIN anchors dst ON dst.id = e.dst
        WHERE e.src = :parent_id
          AND e.kind = 'EdgeAnchor'
          AND e.arch_type = 'Contains'
          AND dst.kind = 'NodeAnchor'
          AND dst.arch_type = 'Folder'
          AND COALESCE((dst.props->'archetype'->>'trashed')::boolean, false) = false
        ORDER BY e.seq NULLS LAST, e.id
        """,
        {"parent_id": canonical_parent_id}
    );
    out: list[str] = [];
    for r in rows {
        out.append(_dbridge_like_uuid_hex(r[0]));
    }
    return out;
}

def _dbridge_like_prefetch_jdrive_parent(parent_id: str) -> dict[str, any] {
    started = time.perf_counter();
    db_start = time.perf_counter();
    child_ids = _dbridge_like_child_folder_ids(parent_id);
    db_ms = (time.perf_counter() - db_start) * 1000.0;

    materialize_start = time.perf_counter();
    children_by_id = _dbridge_like_batch_folders(child_ids, "prefetch");
    materialize_ms = (time.perf_counter() - materialize_start) * 1000.0;
    return {
        "child_ids": child_ids,
        "children_by_id": children_by_id,
        "db_ms": db_ms,
        "materialize_ms": materialize_ms,
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
        "query_count": 1
    };
}

def _submit_dbridge_like_jdrive_parent(parent_id: str) -> any {
    ctx = contextvars.copy_context();
    return _DBRIDGE_LIKE_EXECUTOR.submit(
        ctx.run,
        _dbridge_like_prefetch_jdrive_parent,
        parent_id
    );
}

@restspec(method=HTTPMethod.POST, path="/dbridge_like/VisibleFolderTree/{folder_id}")
def dbridge_like_visible_folder_tree(folder_id: str) -> dict[str, any] {
    access_log = os.environ.get("JAC_DBRIDGE_LIKE_ACCESS_LOG", "").strip();
    cfg = get_config();
    if not access_log and cfg is not None {
        access_log = str(cfg.run.access_log or "");
    }
    actual_file = os.environ.get("JAC_DBRIDGE_LIKE_ACTUAL_FILE", "").strip();
    prefetch_file = os.environ.get("JAC_DBRIDGE_LIKE_PREFETCH_FILE", "").strip();
    paths = _dbridge_like_profile_paths();
    profile_dir = paths["profile_dir"];
    profile_csv = paths["profile_csv"];

    if not actual_file {
        raise ValueError("JAC_DBRIDGE_LIKE_ACTUAL_FILE is required");
    }
    if not prefetch_file {
        raise ValueError("JAC_DBRIDGE_LIKE_PREFETCH_FILE is required");
    }
    if access_log and cfg is not None {
        cfg.run.access_log = access_log;
        _access_log_reset_for_tests();
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
    actual_order: list[str] = [];
    actual_seen: set[str] = set();
    prefetched_order: list[str] = [];
    prefetched_seen: set[str] = set();
    entries: list[FolderTreeEntry] = [];
    db_ms: float = 0.0;
    materialize_ms: float = 0.0;
    prefetch_ms: float = 0.0;
    prefetch_wait_ms: float = 0.0;
    query_count: int = 0;

    materialize_start = time.perf_counter();
    start_folder = cast((Folder | None), _dbridge_like_batch_get([folder_id]).get(folder_id));
    materialize_ms += (time.perf_counter() - materialize_start) * 1000.0;
    if start_folder is None {
        raise ValueError(f"Folder not found during dbridge_like traversal: {folder_id}");
    }
    _dbridge_like_remember(actual_order, actual_seen, folder_id);

    pending: list[dict[str, any]] = [{
        "id": folder_id,
        "folder": start_folder,
        "depth": 0,
        "path": start_folder.name,
        "future": _submit_dbridge_like_jdrive_parent(folder_id)
    }];
    idx = 0;
    while idx < len(pending) {
        item = pending[idx];
        idx += 1;
        current_id = str(item["id"]);
        current = cast(Folder, item["folder"]);
        depth = int(item["depth"]);
        path = str(item["path"]);
        entries.append(
            FolderTreeEntry(id=current_id, name=current.name, depth=depth, path=path)
        );
        future = item["future"];
        wait_start = time.perf_counter();
        prefetch_result = future.result();
        prefetch_wait_ms += (time.perf_counter() - wait_start) * 1000.0;
        db_ms += float(prefetch_result["db_ms"]);
        materialize_ms += float(prefetch_result["materialize_ms"]);
        prefetch_ms += float(prefetch_result["elapsed_ms"]);
        query_count += int(prefetch_result["query_count"]);

        child_ids = cast(list[str], prefetch_result["child_ids"]);
        children_by_id = cast(dict[str, Folder], prefetch_result["children_by_id"]);
        for child_id in child_ids {
            child = children_by_id[child_id];
            _dbridge_like_remember(prefetched_order, prefetched_seen, child_id);
            _dbridge_like_remember(actual_order, actual_seen, child_id);
            pending.append({
                "id": child_id,
                "folder": child,
                "depth": depth + 1,
                "path": path + "/" + child.name,
                "future": _submit_dbridge_like_jdrive_parent(child_id)
            });
        }
    }

    entries.sort(key=lambda (e: FolderTreeEntry) { e.path; });
    reports = [FolderTreeView(id=folder_id, entries=entries)];
    e2e_ms = (time.perf_counter() - trial_start) * 1000.0;
    walker_ms = e2e_ms - prefetch_wait_ms;
    quality = _dbridge_like_quality(actual_order, prefetched_order);
    hits = hit_stats_snapshot();
    l1 = int(hits.get("L1", 0));
    l2 = int(hits.get("L2", 0));
    l3 = int(hits.get("L3", 0));
    miss = int(hits.get("MISS", 0));
    checksum = 0;
    for tree_entry in entries {
        checksum += len(tree_entry.path);
    }
    serialized = json.dumps(reports, separators=(",", ":"), `default=str);

    _dbridge_like_write_uuid_list(actual_file, actual_order);
    _dbridge_like_write_uuid_list(prefetch_file, prefetched_order);
    _dbridge_like_write_profile(
        profile_dir,
        profile_csv,
        profiler,
        e2e_ms,
        prefetch_ms,
        walker_ms,
        materialize_ms,
        prefetch_wait_ms
    );

    return {
        "reports": reports,
        "metrics": {
            "policy": "dbridge_like",
            "prefetch_limit": 0,
            "trial": 0,
            "start_id": folder_id,
            "visited": len(entries),
            "checksum": checksum,
            "first_value": entries[0].name if entries else "",
            "last_value": entries[-1].name if entries else "",
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
        }
    };
}

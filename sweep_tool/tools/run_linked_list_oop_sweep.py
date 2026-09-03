#!/usr/bin/env python3
"""Run an OOP-only LinkedList prefetch sweep over Jac's Postgres schema.

The measured workload deliberately avoids Jac walkers, spawn, visit, TTG, and
the Jac prefetch policy interface.  It treats the persisted Jac graph as a
plain object store and traverses Item.next through ordinary object methods.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SWEEP_TOOL_ROOT.parents[1]
APP_DIR = SWEEP_TOOL_ROOT.parent / "linked_list"
APP_NAME = "linked_list"
sys.path.insert(0, str(SWEEP_TOOL_ROOT))

from lib.prefetch_exp import oop_linked_list  # noqa: E402
from lib.prefetch_exp.db import load_db_settings  # noqa: E402


DEFAULT_MANIFEST = SWEEP_TOOL_ROOT / "manifests" / "linked_list.yaml"
DEFAULT_POLICIES = ["oop-none", "oop-capre-sync", "oop-capre-async", "oop-plan-batch"]
DEFAULT_LIMITS = [0, 250, 500, 1000]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--postgres-uri", default="")
    parser.add_argument("--start-id", default="")
    parser.add_argument("--policies", default=" ".join(DEFAULT_POLICIES))
    parser.add_argument("--prefetch-limits", default=" ".join(str(x) for x in DEFAULT_LIMITS))
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--visit-limit", type=int, default=10000)
    parser.add_argument(
        "--out-dir",
        default="",
        help="Defaults to analysis/linked_list_oop_capre_<timestamp> under the repo root.",
    )
    parser.add_argument(
        "--include-none-at-all-limits",
        action="store_true",
        help="By default oop-none runs only at limit 0.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    _validate_linked_list_manifest_hint(manifest_path)

    policies = _split_words(args.policies)
    unknown = [p for p in policies if p not in oop_linked_list.POLICIES]
    if unknown:
        raise ValueError(f"unknown OOP LinkedList policy: {', '.join(unknown)}")
    limits = _parse_ints(args.prefetch_limits)
    if args.trials <= 0:
        raise ValueError("--trials must be positive")
    if args.visit_limit <= 0:
        raise ValueError("--visit-limit must be positive")

    postgres_uri = args.postgres_uri or _postgres_uri_from_local_config()
    out_dir = Path(args.out_dir).expanduser() if args.out_dir else _default_out_dir()
    out_dir = out_dir.resolve()
    logs_dir = out_dir / "logs"
    plans_dir = out_dir / "plans"
    out_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    plans_dir.mkdir(parents=True, exist_ok=True)

    results_path = out_dir / "linked_list_oop_sweep.csv"
    oop_linked_list.write_results_header(results_path)

    metadata: dict[str, Any] = {
        "mode": "linked_list_oop_only",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "manifest": str(manifest_path),
        "app_dir": str(APP_DIR.resolve()),
        "postgres_uri": _redact_uri(postgres_uri),
        "policies": policies,
        "prefetch_limits": limits,
        "trials": args.trials,
        "visit_limit": args.visit_limit,
        "start_id": args.start_id,
        "notes": [
            "No Jac walker/spawn/visit execution is used by OOP policies.",
            "oop-capre-* performs one-hop Item.next prefetch at object-entry time.",
            "oop-plan-batch is a request-level concrete-plan reference, not CAPRe.",
        ],
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

    print("=== LinkedList OOP-only sweep ===")
    print(f"manifest : {manifest_path}")
    print(f"db       : {_redact_uri(postgres_uri)}")
    print(f"out_dir  : {out_dir}")
    print(f"policies : {' '.join(policies)}")
    print(f"limits   : {' '.join(str(x) for x in limits)}")
    print(f"trials   : {args.trials}")
    print("")

    for policy in policies:
        policy_limits = limits
        if policy == "oop-none" and not args.include_none_at_all_limits:
            policy_limits = [0]
        for limit in policy_limits:
            print("========================================")
            print(f"Case: policy={policy} prefetch_limit={limit}")
            print("========================================")
            for trial in range(1, args.trials + 1):
                store = None
                try:
                    metrics, store = oop_linked_list.traverse_linked_list(
                        postgres_uri,
                        policy=policy,
                        prefetch_limit=limit,
                        visit_limit=args.visit_limit,
                        start_id=args.start_id,
                    )
                    metrics.trial = trial
                    access_log = logs_dir / f"access_log_Traverse_policy{_safe(policy)}_limit{limit}_trial{trial}.csv"
                    actual_file = plans_dir / f"actual_policy{_safe(policy)}_limit{limit}_trial{trial}.uuids"
                    prefetch_file = plans_dir / f"prefetch_policy{_safe(policy)}_limit{limit}_trial{trial}.uuids"
                    store.write_access_log(access_log)
                    oop_linked_list.write_uuid_list(actual_file, store.actual_order)
                    oop_linked_list.write_uuid_list(prefetch_file, store.prefetched_order)
                    metrics.access_log = str(access_log)
                    metrics.actual_file = str(actual_file)
                    metrics.prefetch_file = str(prefetch_file)
                    oop_linked_list.append_result(results_path, metrics)
                    print(
                        f"  Trial {trial}: {metrics.e2e_ms:.3f}ms "
                        f"db={metrics.db_ms:.3f}ms q={metrics.query_count} "
                        f"L1={metrics.l1} L3={metrics.l3} "
                        f"coverage={metrics.coverage:.3f} "
                        f"accuracy={metrics.accuracy:.3f}"
                    )
                finally:
                    if store is not None:
                        store.close()

    print("")
    print("========================================")
    print("OOP sweep complete")
    print(f"Results saved to: {results_path}")
    print("========================================")
    print(results_path.read_text())
    return 0


def _postgres_uri_from_local_config() -> str:
    settings = load_db_settings(
        app_name=APP_NAME,
        default_postgres_uri="postgresql://jac:jac@localhost:5432/jac_db",
        default_postgres_container="postgres",
        env=os.environ,
    )
    return settings.postgres_uri


def _validate_linked_list_manifest_hint(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)
    # Avoid importing PyYAML in the experiment image; this runner is intentionally
    # LinkedList-only, so a cheap guard is enough.
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            name = stripped.split(":", 1)[1].strip().strip("'\"")
            if name != APP_NAME:
                raise ValueError(f"expected linked_list manifest, got {name!r}")
            return
    raise ValueError(f"manifest {path} does not declare name: linked_list")


def _default_out_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "analysis" / f"linked_list_oop_capre_{stamp}"


def _split_words(raw: str) -> list[str]:
    return [x.strip().lower() for x in raw.replace(",", " ").split() if x.strip()]


def _parse_ints(raw: str) -> list[int]:
    vals = [int(x) for x in raw.replace(",", " ").split() if x.strip()]
    return vals or list(DEFAULT_LIMITS)


def _safe(raw: str) -> str:
    out = []
    for ch in raw:
        out.append(ch if ch.isalnum() or ch in ("-", "_") else "_")
    return "".join(out)


def _redact_uri(uri: str) -> str:
    if "@" not in uri:
        return uri
    prefix, suffix = uri.rsplit("@", 1)
    scheme, _, rest = prefix.partition("://")
    if ":" not in rest:
        return uri
    user, _, _password = rest.partition(":")
    return f"{scheme}://{user}:***@{suffix}"


if __name__ == "__main__":
    raise SystemExit(main())

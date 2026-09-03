#!/usr/bin/env python3
"""Run an OOP-only LinkedList prefetch sweep over Jac's Postgres schema.

The measured workload deliberately avoids Jac walkers, spawn, visit, TTG, and
the Jac prefetch policy interface.  It treats the persisted Jac graph as a
plain object store plus an explicit SQL association resolver for Next edges.
The request target must still come from the same Jac setup_graph result that the
regular benchmark uses.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SWEEP_TOOL_ROOT.parents[1]
APP_DIR = SWEEP_TOOL_ROOT.parent / "linked_list"
APP_NAME = "linked_list"
sys.path.insert(0, str(SWEEP_TOOL_ROOT))

from lib.prefetch_exp import oop_linked_list, process  # noqa: E402
from lib.prefetch_exp.db import load_db_settings  # noqa: E402


DEFAULT_MANIFEST = SWEEP_TOOL_ROOT / "manifests" / "linked_list.yaml"
DEFAULT_POLICIES = ["none", "capre"]
BASELINE_LIMIT = 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--postgres-uri", default="")
    parser.add_argument("--start-id", default="")
    parser.add_argument(
        "--transport",
        choices=("http", "direct"),
        default=os.environ.get("LINKED_LIST_OOP_TRANSPORT", "http"),
        help="http runs the Jac /function/oop_traverse endpoint; direct raw-PgSQL mode is retired.",
    )
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "localhost:8000"))
    parser.add_argument("--jac-bin", default=os.environ.get("JAC_BIN", "jac"))
    parser.add_argument(
        "--reuse-server",
        action="store_true",
        help="Use an already-running Jac server at --base-url instead of starting one.",
    )
    parser.add_argument("--username", default=os.environ.get("TEST_USER", "oop_sweep"))
    parser.add_argument("--password", default=os.environ.get("TEST_PASSWORD", "password"))
    parser.add_argument(
        "--setup-nodes-file",
        default="",
        help=(
            "File containing the Jac /function/setup_graph response, a JSON "
            "node list, or newline-separated node UUIDs. The first node is "
            "used exactly like the Jac sweep adapter."
        ),
    )
    parser.add_argument("--policies", default=" ".join(DEFAULT_POLICIES))
    parser.add_argument(
        "--prefetch-limits",
        default="",
        help=(
            "Deprecated compatibility option. CAPRe is a baseline and does "
            "not consume TTG-style prefetch limits; rows use prefetch_limit=0."
        ),
    )
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument(
        "--out-dir",
        default="",
        help="Defaults to analysis/linked_list_oop_capre_<timestamp> under the repo root.",
    )
    parser.add_argument(
        "--include-none-at-all-limits",
        action="store_true",
        help="Deprecated compatibility flag; baseline policies always run once.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    _validate_linked_list_manifest_hint(manifest_path)

    policies = _canonical_policies(_split_words(args.policies))
    _ignored_limits = _parse_ints(args.prefetch_limits) if args.prefetch_limits.strip() else []
    if args.trials <= 0:
        raise ValueError("--trials must be positive")

    start_id = _resolve_start_id(args.start_id, args.setup_nodes_file)
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
        "mode": f"linked_list_oop_{args.transport}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "manifest": str(manifest_path),
        "app_dir": str(APP_DIR.resolve()),
        "postgres_uri": _redact_uri(postgres_uri),
        "transport": args.transport,
        "base_url": args.base_url,
        "jac_bin": args.jac_bin,
        "reuse_server": args.reuse_server,
        "policies": policies,
        "prefetch_limits": [BASELINE_LIMIT],
        "ignored_prefetch_limits": _ignored_limits,
        "trials": args.trials,
        "start_id": start_id,
        "setup_nodes_file": str(Path(args.setup_nodes_file).resolve()) if args.setup_nodes_file else "",
        "notes": [
            "No Jac walker/spawn/visit execution is used by OOP policies.",
            "The request target is the first node from Jac setup_graph, or an explicit matching start-id.",
            "Next edges are resolved by explicit SQL over Jac's persisted PgSQL schema, not by Jac spatial hop resolution.",
            "capre is an OOP baseline; it resolves and materializes the next Item after report and before the next object read.",
            "prefetch_limit is an OSP/TTG budget concept and is not applied to capre.",
        ],
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

    print("=== LinkedList OOP-only sweep ===")
    print(f"manifest : {manifest_path}")
    print(f"db       : {_redact_uri(postgres_uri)}")
    print(f"out_dir  : {out_dir}")
    print(f"transport: {args.transport}")
    print(f"baselines: {' '.join(policies)}")
    print(f"limits   : {BASELINE_LIMIT} (schema placeholder; not a CAPRe budget)")
    print(f"trials   : {args.trials}")
    print(f"start_id : {start_id}")
    print("")

    if args.transport == "http":
        _run_http_cases(args, policies, start_id, postgres_uri, results_path, logs_dir, plans_dir, out_dir)
    elif args.transport == "direct":
        raise RuntimeError("direct raw-PgSQL CAPRe mode was removed; use --transport http")
    else:
        _run_direct_cases(args, policies, start_id, postgres_uri, results_path, logs_dir, plans_dir)

    print("")
    print("========================================")
    print("OOP sweep complete")
    print(f"Results saved to: {results_path}")
    print("========================================")
    print(results_path.read_text())
    return 0


def _run_direct_cases(
    args: argparse.Namespace,
    policies: list[str],
    start_id: str,
    postgres_uri: str,
    results_path: Path,
    logs_dir: Path,
    plans_dir: Path,
) -> None:
    del args, policies, start_id, postgres_uri, results_path, logs_dir, plans_dir;
    raise RuntimeError("direct raw-PgSQL CAPRe mode was removed; use --transport http")


def _run_http_cases(
    args: argparse.Namespace,
    policies: list[str],
    start_id: str,
    postgres_uri: str,
    results_path: Path,
    logs_dir: Path,
    plans_dir: Path,
    out_dir: Path,
) -> None:
    proc = None
    profiles_dir = out_dir / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    try:
        if not args.reuse_server:
            server_log = logs_dir / "jac_server_oop_http.log"
            proc = process.start_server(
                _server_command(args),
                APP_DIR,
                {
                    "JAC_BIN": args.jac_bin,
                    "JAC_DB_URL": postgres_uri,
                    "POSTGRES_URL": postgres_uri,
                    "DATABASE_URL": postgres_uri,
                    "JAC_PROFILE_DIR": str(profiles_dir),
                },
                server_log,
            )
            process.wait_ready(args.base_url)
        process.register_user(args.base_url, args.username, args.password)
        token = process.login(args.base_url, args.username, args.password)

        for policy in policies:
            limit = BASELINE_LIMIT
            print("========================================")
            print(f"Case: baseline={policy}")
            print("========================================")
            for trial in range(1, args.trials + 1):
                access_log = logs_dir / f"access_log_Traverse_policy{_safe(policy)}_limit{limit}_trial{trial}.csv"
                actual_file = plans_dir / f"actual_policy{_safe(policy)}_limit{limit}_trial{trial}.uuids"
                prefetch_file = plans_dir / f"prefetch_policy{_safe(policy)}_limit{limit}_trial{trial}.uuids"
                profile_dir = (
                    profiles_dir
                    / f"policy_{_safe(policy)}"
                    / f"limit_{limit}"
                    / "Traverse"
                    / f"trial_{trial}"
                )
                response_file = logs_dir / f"http_response_policy{_safe(policy)}_limit{limit}_trial{trial}.json"
                resp = process.post_json(
                    args.base_url,
                    "/function/oop_traverse",
                    {
                        "start_id": start_id,
                        "policy": policy,
                        "postgres_uri": postgres_uri,
                        "access_log": str(access_log),
                        "actual_file": str(actual_file),
                        "prefetch_file": str(prefetch_file),
                        "profile_dir": str(profile_dir),
                        "profile_csv": str(profile_dir / "profile.csv"),
                        "include_metrics": True,
                    },
                    token=token,
                )
                payload = resp.json()
                response_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                _assert_profile_files(profile_dir)
                row = _row_from_http_payload(
                    payload,
                    trial=trial,
                    access_log=access_log,
                    actual_file=actual_file,
                    prefetch_file=prefetch_file,
                )
                _append_row(results_path, row)
                print(
                    f"  Trial {trial}: {_row_float(row, 'e2e_ms'):.3f}ms "
                    f"db={_row_float(row, 'db_ms'):.3f}ms q={row['query_count']} "
                    f"L1={row['l1']} L3={row['l3']} "
                    f"coverage={_row_float(row, 'coverage'):.3f} "
                    f"accuracy={_row_float(row, 'accuracy'):.3f}"
                )
    finally:
        if proc is not None:
            process.stop_process(proc)


def _postgres_uri_from_local_config() -> str:
    settings = load_db_settings(
        app_name=APP_NAME,
        default_postgres_uri="postgresql://jac:jac@localhost:5432/jac_db",
        default_postgres_container="postgres",
        env=os.environ,
    )
    return settings.postgres_uri


def _entry_point() -> str:
    try:
        import tomllib

        data = tomllib.loads((APP_DIR / "jac.toml").read_text())
        project = data.get("project", {})
        if isinstance(project, dict):
            entry = project.get("entry-point") or project.get("entry_point")
            if entry:
                return str(entry)
    except Exception:
        pass
    return "main.jac"


def _server_command(args: argparse.Namespace) -> list[str]:
    if _supports_jac_start(args.jac_bin):
        cmd = [args.jac_bin, "start", "--no_client"]
    else:
        cmd = [args.jac_bin, "run", "--serve", "--no-client"]
    cmd.extend(["--port", str(_port_from_base_url(args.base_url)), _entry_point()])
    return cmd


def _supports_jac_start(jac_bin: str) -> bool:
    try:
        result = subprocess.run(
            [jac_bin, "start", "--help"],
            cwd=str(APP_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def _port_from_base_url(base_url: str) -> int:
    parsed = urlsplit(base_url if "://" in base_url else f"http://{base_url}")
    return parsed.port or 8000


def _row_from_http_payload(
    payload: dict[str, Any],
    *,
    trial: int,
    access_log: Path,
    actual_file: Path,
    prefetch_file: Path,
) -> dict[str, Any]:
    if not payload.get("ok"):
        raise RuntimeError(f"oop_traverse failed: {json.dumps(payload, sort_keys=True)[:1000]}")
    data = payload.get("data")
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise RuntimeError(f"oop_traverse returned malformed payload: {payload!r}")
    reports = result.get("reports")
    metrics = result.get("metrics")
    if not isinstance(reports, list) or not isinstance(metrics, dict):
        raise RuntimeError(f"oop_traverse returned malformed result: {result!r}")

    row = {col: metrics.get(col, "") for col in oop_linked_list.RESULT_COLUMNS}
    row["trial"] = trial
    row["access_log"] = str(access_log)
    row["actual_file"] = str(actual_file)
    row["prefetch_file"] = str(prefetch_file)
    visited = int(row["visited"])
    if visited != len(reports):
        raise RuntimeError(f"visited mismatch: metrics={visited} reports={len(reports)}")
    return row


def _append_row(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=oop_linked_list.RESULT_COLUMNS)
        writer.writerow(row)


def _row_float(row: dict[str, Any], key: str) -> float:
    try:
        return float(row[key])
    except Exception:
        return 0.0


def _assert_profile_files(profile_dir: Path) -> None:
    missing = [
        str(path)
        for path in (profile_dir / "profile.csv", profile_dir / "jac_server.prof")
        if not path.exists()
    ]
    if missing:
        raise RuntimeError(f"OOP baseline profile output missing: {', '.join(missing)}")


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


def _resolve_start_id(raw_start_id: str, raw_setup_nodes_file: str) -> str:
    start_id = raw_start_id.strip()
    setup_start = ""
    if raw_setup_nodes_file:
        setup_start = _first_setup_node_from_file(Path(raw_setup_nodes_file).expanduser())
    if start_id and setup_start and start_id != setup_start:
        raise ValueError(
            "--start-id does not match the first node in --setup-nodes-file: "
            f"{start_id} != {setup_start}"
        )
    resolved = start_id or setup_start
    if not resolved:
        raise ValueError(
            "LinkedList OOP sweep requires --start-id or --setup-nodes-file. "
            "It intentionally does not scan PgSQL for Item(index=0), because "
            "the Jac benchmark target is nodes[0] returned by setup_graph."
        )
    return resolved


def _first_setup_node_from_file(path: Path) -> str:
    text = path.read_text().strip()
    if not text:
        raise ValueError(f"{path} is empty")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        nodes = [line.strip() for line in text.splitlines() if line.strip()]
    else:
        nodes = _nodes_from_setup_json(parsed)
    if not nodes:
        raise ValueError(f"{path} does not contain any setup_graph node ids")
    return str(nodes[0])


def _nodes_from_setup_json(parsed: Any) -> list[Any]:
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        data = parsed.get("data")
        if isinstance(data, dict) and isinstance(data.get("result"), list):
            return data["result"]
        result = parsed.get("result")
        if isinstance(result, list):
            return result
    raise ValueError("setup nodes JSON must be a list or contain data.result")


def _default_out_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "analysis" / f"linked_list_oop_capre_{stamp}"


def _split_words(raw: str) -> list[str]:
    return [x.strip().lower() for x in raw.replace(",", " ").split() if x.strip()]


def _parse_ints(raw: str) -> list[int]:
    vals = [int(x) for x in raw.replace(",", " ").split() if x.strip()]
    return vals


def _canonical_policies(raw_policies: list[str]) -> list[str]:
    policies = raw_policies or list(DEFAULT_POLICIES)
    out: list[str] = []
    seen: set[str] = set()
    for policy in policies:
        canonical = oop_linked_list.canonical_policy(policy)
        if canonical not in seen:
            seen.add(canonical)
            out.append(canonical)
    return out


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

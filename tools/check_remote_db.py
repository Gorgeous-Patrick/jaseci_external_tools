#!/usr/bin/env python3
"""Validate two-machine Postgres settings for sweep_tool remote_ssh mode."""

from __future__ import annotations

import argparse
import os
import shlex
import socket
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SWEEP_TOOL_ROOT = REPO_ROOT / "sweep_tool"
sys.path.insert(0, str(SWEEP_TOOL_ROOT))

from lib import manifest as mf  # noqa: E402
from lib.prefetch_exp.adapters import make_adapter  # noqa: E402
from lib.prefetch_exp.db import (  # noqa: E402
    COMPOSE_FILES,
    RemoteSshDockerDbManager,
    uri_host_port,
    uri_uses_localhost,
)
from lib.prefetch_exp.models import SweepOptions  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--app",
        action="append",
        default=[],
        help="App name to check. Repeat for multiple apps. Defaults to every prefetch_python manifest.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="TCP/SSH command timeout in seconds.",
    )
    parser.add_argument(
        "--allow-local-containers",
        action="store_true",
        help="Do not fail if local Docker has containers named like the benchmark Postgres containers.",
    )
    args = parser.parse_args()

    manifests = [
        m
        for m in mf.discover(SWEEP_TOOL_ROOT / "manifests")
        if m.runner == "prefetch_python" and (not args.app or m.name in args.app)
    ]
    missing = sorted(set(args.app) - {m.name for m in manifests})
    if missing:
        print(f"FAIL unknown or non-prefetch app(s): {', '.join(missing)}")
        return 1
    if not manifests:
        print("FAIL no prefetch_python manifests selected")
        return 1

    failures = 0
    local_container_names = _local_container_names(args.timeout)
    for manifest in manifests:
        failures += _check_manifest(manifest, local_container_names, args)

    if failures:
        print(f"\nremote DB check failed: {failures} issue(s)")
        return 1
    print("\nremote DB check passed")
    return 0


def _check_manifest(manifest: mf.Manifest, local_container_names: set[str] | None, args) -> int:
    print(f"\n=== {manifest.name} ===")
    failures = 0
    try:
        adapter = make_adapter(SweepOptions.from_env(manifest))
    except Exception as exc:
        print(f"FAIL load adapter/config: {exc}")
        return 1

    manager = adapter.db_manager
    if not isinstance(manager, RemoteSshDockerDbManager):
        print(f"FAIL db.mode is {manager.mode!r}; set sweep_tool/local.toml [db].mode = \"remote_ssh\"")
        return 1

    settings = manager.settings
    failures += _report(
        "ssh access",
        _run(["ssh", *settings.ssh_options, settings.ssh_target, "true"], args.timeout).returncode == 0,
        settings.ssh_target,
    )
    docker = _run(
        ["ssh", *settings.ssh_options, settings.ssh_target, "docker ps --format '{{.Names}}'"],
        args.timeout,
    )
    failures += _report("remote Docker", docker.returncode == 0, (docker.stdout or docker.stderr).strip())
    failures += _report(
        "remote compose file",
        _remote_compose_file_exists(settings, manager.remote_app_dir, args.timeout),
        manager.remote_app_dir,
    )

    for dump_name in _expected_dumps(adapter, manifest):
        exists = _remote_path_exists(settings, manager.remote_app_dir, dump_name, args.timeout)
        failures += _report(
            f"remote dump {dump_name}",
            exists,
            _remote_dump_description(settings, manager.remote_app_dir, dump_name, args.timeout),
        )

    failures += _check_uri_reachable("Postgres", manager.postgres_uri, 5432, args.timeout)
    failures += _report(
        "Postgres URI is remote",
        not uri_uses_localhost(manager.postgres_uri),
        manager.postgres_uri,
    )

    if local_container_names is None:
        print("OK   local Docker container check skipped: local Docker is not reachable")
    elif not args.allow_local_containers:
        accidental = sorted(local_container_names.intersection({adapter.postgres_container}))
        failures += _report(
            "no matching local DB containers",
            not accidental,
            ", ".join(accidental) if accidental else "none",
        )

    return failures


def _expected_dumps(adapter, manifest: mf.Manifest) -> list[str]:
    names: list[str] = []
    if hasattr(adapter, "_configured_dump"):
        names.append(adapter._configured_dump())
    elif manifest.name in {"jdrive", "jsearch"}:
        names.append("jac_db.pgdump")

    for param in manifest.parameters:
        if not param.name.endswith("_DUMP"):
            continue
        value = os.environ.get(param.name) or str(param.default or "")
        if value and value not in names:
            names.append(value)
    return names


def _check_uri_reachable(label: str, uri: str, default_port: int, timeout: float) -> int:
    host, port = uri_host_port(uri, default_port)
    if not host:
        return _report(f"{label} TCP connect", False, uri)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return _report(f"{label} TCP connect", True, f"{host}:{port}")
    except OSError as exc:
        return _report(f"{label} TCP connect", False, f"{host}:{port} ({exc})")


def _remote_compose_file_exists(settings, remote_app_dir: str, timeout: float) -> bool:
    joined = " || ".join(f"test -f {shlex.quote(name)}" for name in COMPOSE_FILES)
    return _remote(settings, remote_app_dir, f"( {joined} )", timeout).returncode == 0


def _remote_path_exists(settings, remote_app_dir: str, path: str, timeout: float) -> bool:
    return _remote(settings, remote_app_dir, f"test -e {shlex.quote(path)}", timeout).returncode == 0


def _remote_dump_description(settings, remote_app_dir: str, path: str, timeout: float) -> str:
    proc = _remote(settings, remote_app_dir, f"stat -Lc %s {shlex.quote(path)}", timeout)
    remote_path = f"{settings.ssh_target}:{remote_app_dir.rstrip('/')}/{path}"
    size = proc.stdout.strip()
    return f"{remote_path} ({size} bytes)" if proc.returncode == 0 and size else remote_path


def _remote(settings, remote_app_dir: str, command: str, timeout: float) -> subprocess.CompletedProcess:
    return _run(
        [
            "ssh",
            *settings.ssh_options,
            settings.ssh_target,
            f"cd {shlex.quote(remote_app_dir)} && {command}",
        ],
        timeout,
    )


def _local_container_names(timeout: float) -> set[str] | None:
    proc = _run(["docker", "ps", "--format", "{{.Names}}"], timeout)
    if proc.returncode != 0:
        return None
    return {line.strip() for line in proc.stdout.splitlines() if line.strip()}


def _run(cmd: list[str], timeout: float) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", exc.stderr or "timeout")


def _report(name: str, ok: bool, detail: str = "") -> int:
    status = "OK  " if ok else "FAIL"
    suffix = f": {detail}" if detail else ""
    print(f"{status} {name}{suffix}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

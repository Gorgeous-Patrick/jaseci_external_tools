"""Subprocess and HTTP helpers for benchmark runs."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class HttpResponse:
    status: int
    elapsed_ms: float
    body: bytes

    def json(self) -> dict[str, Any]:
        if not self.body:
            return {}
        return json.loads(self.body.decode("utf-8"))


def run(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
    stdout: int | None = None,
) -> subprocess.CompletedProcess:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        env=merged,
        check=check,
        text=True,
        stdout=stdout,
        stderr=subprocess.STDOUT if stdout == subprocess.PIPE else None,
    )


def start_server(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "w", buffering=1)
    try:
        return subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env={**os.environ.copy(), **env},
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_fh.close()


def stop_process(proc: subprocess.Popen | None, timeout_sec: float = 5.0) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + timeout_sec
    while time.time() < deadline and proc.poll() is None:
        time.sleep(0.1)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass


def wait_ready(base_url: str, timeout_sec: float = 60.0) -> None:
    url = _url(base_url, "/docs")
    deadline = time.time() + timeout_sec
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if 200 <= resp.status < 500:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(1.0)
    raise TimeoutError(f"server did not become ready at {url}: {last_error}")


def post_json(
    base_url: str,
    path: str,
    body: dict[str, Any],
    token: str = "",
    timeout_sec: float = 300.0,
) -> HttpResponse:
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        _url(base_url, path),
        data=data,
        headers=headers,
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            payload = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        status = exc.code
    elapsed_ms = (time.perf_counter() - start) * 1000
    return HttpResponse(status=status, elapsed_ms=elapsed_ms, body=payload)


def login(base_url: str, username: str, password: str) -> str:
    resp = post_json(
        base_url,
        "/user/login",
        {
            "identity": {"type": "username", "value": username},
            "credential": {"type": "password", "password": password},
        },
    )
    data = resp.json()
    payload = data.get("data")
    token = payload.get("token") if isinstance(payload, dict) else None
    if resp.status >= 400 or not token:
        body = resp.body.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"login failed for {username}: HTTP {resp.status} {body}")
    return str(token)


def register_user(base_url: str, username: str, password: str) -> None:
    post_json(
        base_url,
        "/user/register",
        {
            "identities": [{"type": "username", "value": username}],
            "credential": {"type": "password", "password": password},
        },
    )


def _url(base_url: str, path: str) -> str:
    base = base_url if base_url.startswith(("http://", "https://")) else f"http://{base_url}"
    return base.rstrip("/") + "/" + path.lstrip("/")

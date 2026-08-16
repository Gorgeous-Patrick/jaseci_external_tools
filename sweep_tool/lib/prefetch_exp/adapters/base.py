"""Base adapter contract for app-specific benchmark behavior."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from lib.prefetch_exp import process
from lib.prefetch_exp.models import CaseState, RequestSpec, SweepOptions


class BenchmarkAdapter(ABC):
    config_name = "jac.toml"
    mongo_container = "mongodb"
    redis_container = "redis"
    mongo_uri = "mongodb://localhost:27017"
    redis_url = "redis://localhost:6379"
    profile_name = ""
    default_user = "user"
    default_password = "password"
    credential_source = "adapter default"

    def __init__(self, options: SweepOptions):
        self.options = options

    @property
    def app_dir(self) -> Path:
        return self.options.manifest.app_dir

    @property
    def name(self) -> str:
        return self.options.manifest.name

    @property
    def base_url(self) -> str:
        return self.options.env.get("BASE_URL") or self.options.env.get("base_url") or "localhost:8000"

    @property
    def config_path(self) -> Path:
        return self.app_dir / self.config_name

    def clean_outputs(self) -> None:
        for rel in (self.options.manifest.logs_dir, self.options.manifest.profiles_dir):
            path = self.app_dir / rel
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)

    def prepare_sweep(self) -> None:
        """One-time preparation before all policy/limit cases."""

    def prepare_case(self, policy: str, limit: int) -> CaseState:
        """Prepare DB/cache state and return a stable request for this case."""
        self.reset_storage()
        return self.prepare_request(policy, limit)

    def reset_storage(self) -> None:
        self.compose_down()
        self.compose_up()
        time.sleep(5)
        self.restore_dump_if_present()
        self.flush_redis()
        self.stop_stale_servers()

    @abstractmethod
    def prepare_request(self, policy: str, limit: int) -> CaseState:
        """Return token and target walker request for measured trials."""

    def validate_response(self, spec: RequestSpec, payload: dict[str, Any]) -> None:
        if not payload:
            raise RuntimeError(f"{self.name}/{spec.walker} returned an empty response")

    def server_command(self) -> list[str]:
        cmd = [self.options.jac_bin, "start"]
        if self.profile_name:
            cmd.extend(["--profile", self.profile_name])
        return cmd

    def server_env(self, profile_dir: Path | None = None, profile_csv: Path | None = None) -> dict[str, str]:
        env = {
            **self.options.env,
            "JAC_BIN": self.options.jac_bin,
            "MONGODB_URI": self.mongo_uri,
            "REDIS_URL": self.redis_url,
        }
        if profile_dir is not None:
            env["JAC_PROFILE_DIR"] = str(profile_dir)
        if profile_csv is not None:
            env["JAC_PROFILE_CSV"] = str(profile_csv)
        return env

    def start_server(self, log_path: Path, profile_dir: Path | None = None, profile_csv: Path | None = None):
        proc = process.start_server(
            self.server_command(),
            self.app_dir,
            self.server_env(profile_dir=profile_dir, profile_csv=profile_csv),
            log_path,
        )
        try:
            process.wait_ready(self.base_url)
            self._assert_tiered_memory_connected(log_path)
        except Exception:
            process.stop_process(proc)
            raise
        return proc

    def login(self, username: str | None = None, password: str | None = None) -> str:
        return process.login(
            self.base_url,
            username or self.user_name(),
            password or self.password(),
        )

    def user_name(self) -> str:
        return self.options.env.get("TEST_USER") or self.default_user

    def password(self) -> str:
        return self.options.env.get("TEST_PASSWORD") or self.default_password

    def auth_summary(self) -> str:
        return f"user={self.user_name()} source={self.credential_source}"

    def compose_down(self) -> None:
        process.run(["docker", "compose", "down", "--remove-orphans"], self.app_dir, check=False)

    def compose_up(self) -> None:
        result = process.run(
            ["docker", "compose", "up", "-d"],
            self.app_dir,
            check=False,
            stdout=subprocess.PIPE,
        )
        if result.returncode == 0:
            return
        output = result.stdout or ""
        if "Conflict. The container name" in output:
            print("docker compose name conflict; removing stale benchmark containers")
            process.run(
                ["docker", "rm", "-f", self.mongo_container, self.redis_container],
                self.app_dir,
                check=False,
            )
            process.run(["docker", "compose", "up", "-d"], self.app_dir)
            return
        print(output)
        result.check_returncode()

    def flush_redis(self) -> None:
        process.run(
            ["docker", "exec", self.redis_container, "redis-cli", "FLUSHALL"],
            self.app_dir,
            check=False,
        )

    def restore_dump_if_present(self, dump_name: str = "jac_db.dump") -> None:
        dump_path = self.app_dir / dump_name
        if not dump_path.exists():
            print(f"=== No {dump_name} found for {self.name}; using current MongoDB state ===")
            return
        process.run(
            ["docker", "cp", "-L", dump_name, f"{self.mongo_container}:/tmp/jac_db.dump"],
            self.app_dir,
        )
        process.run(
            [
                "docker",
                "exec",
                self.mongo_container,
                "mongorestore",
                "--archive=/tmp/jac_db.dump",
                "--drop",
            ],
            self.app_dir,
            check=False,
        )

    def stop_stale_servers(self) -> None:
        basename = os.path.basename(self.options.jac_bin)
        process.run(["pkill", "-f", f"{basename} start"], self.app_dir, check=False)
        process.run(["pkill", "-f", "jac start"], self.app_dir, check=False)
        time.sleep(2)

    def setup_token(self, log_name: str = "jac_server_prepare.log") -> str:
        proc = None
        try:
            proc = self.start_server(self.app_dir / self.options.manifest.logs_dir / log_name)
            return self.login()
        finally:
            process.stop_process(proc)
            self.stop_stale_servers()

    def post(self, path: str, body: dict[str, Any], token: str = ""):
        return process.post_json(self.base_url, path, body, token=token)

    def json_file(self, rel: str) -> dict[str, Any]:
        return json.loads((self.app_dir / rel).read_text())

    def _assert_tiered_memory_connected(self, log_path: Path) -> None:
        try:
            text = log_path.read_text(errors="replace")
        except FileNotFoundError:
            return
        failures = [
            line.strip()
            for line in text.splitlines()
            if "MongoDB connection failed" in line or "Redis connection failed" in line
        ]
        if failures:
            raise RuntimeError(
                "Jac server did not connect to tiered memory; access logs would be invalid: "
                + " | ".join(failures[:2])
            )

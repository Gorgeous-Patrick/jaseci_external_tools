"""Base adapter contract for app-specific benchmark behavior."""

from __future__ import annotations

import json
import os
import shutil
import time
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from lib.prefetch_exp import process
from lib.prefetch_exp.db import make_db_manager
from lib.prefetch_exp.models import CaseState, RequestSpec, SweepOptions


class BenchmarkAdapter(ABC):
    config_name = "jac.toml"
    postgres_container = "postgres"
    postgres_uri = "postgresql://jac:jac@localhost:5432/jac_db"
    profile_name = ""
    default_user = "user"
    default_password = "password"
    credential_source = "adapter default"

    def __init__(self, options: SweepOptions):
        self.options = options
        self.db_manager = make_db_manager(
            app_name=self.name,
            app_dir=self.app_dir,
            default_postgres_uri=self.postgres_uri,
            postgres_container=self.postgres_container,
            env=self.options.env,
        )
        self.postgres_uri = self.db_manager.postgres_uri

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
        self.clear_runtime_cache()
        self.stop_stale_servers()

    @abstractmethod
    def prepare_request(self, policy: str, limit: int) -> CaseState:
        """Return token and target walker request for measured trials."""

    def spawn_pool(self, state: CaseState) -> list[RequestSpec]:
        """Return candidate requests for pooled predictor training/testing."""
        if state.request is None:
            return []
        return [state.request]

    def validate_response(self, spec: RequestSpec, payload: dict[str, Any]) -> None:
        if not payload:
            raise RuntimeError(f"{self.name}/{spec.walker} returned an empty response")

    def server_command(self) -> list[str]:
        cmd = [self.options.jac_bin, "run", "--serve", "--no-client"]
        if self.profile_name:
            cmd.extend(["--profile", self.profile_name])
        cmd.append(self.entry_point())
        return cmd

    def entry_point(self) -> str:
        for path in (self.config_path, self.app_dir / "jac.toml"):
            try:
                data = tomllib.loads(path.read_text())
            except FileNotFoundError:
                continue
            project = data.get("project", {})
            if isinstance(project, dict):
                entry = project.get("entry-point") or project.get("entry_point")
                if entry:
                    return str(entry)
        return "main.jac"

    def server_env(self, profile_dir: Path | None = None, profile_csv: Path | None = None) -> dict[str, str]:
        env = {
            **self.options.env,
            "JAC_BIN": self.options.jac_bin,
            "JAC_DB_URL": self.postgres_uri,
            "POSTGRES_URL": self.postgres_uri,
            "DATABASE_URL": self.postgres_uri,
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

    def db_summary(self) -> str:
        return self.db_manager.summary()

    def compose_down(self) -> None:
        self.db_manager.compose_down()

    def compose_up(self) -> None:
        self.db_manager.compose_up()

    def clear_runtime_cache(self) -> None:
        self.db_manager.clear_runtime_cache()

    def restore_dump_if_present(self, dump_name: str = "jac_db.pgdump") -> None:
        if not self.db_manager.dump_exists(dump_name):
            print(f"=== No {dump_name} found for {self.name}; using current database state ===")
            return
        self.db_manager.restore_dump(dump_name)

    def dump_exists(self, dump_name: str = "jac_db.pgdump") -> bool:
        return self.db_manager.dump_exists(dump_name)

    def dump_description(self, dump_name: str = "jac_db.pgdump") -> str:
        return self.db_manager.dump_description(dump_name)

    def drop_jac_db(self) -> None:
        self.db_manager.drop_jac_db()

    def drop_non_system_databases(self) -> None:
        self.db_manager.drop_non_system_databases()

    def dump_to_app(self, dump_name: str = "jac_db.pgdump") -> None:
        self.db_manager.dump_to_app(dump_name)

    def db_query_count(self) -> str:
        return self.db_manager.db_query_count()

    def stop_stale_servers(self) -> None:
        basename = os.path.basename(self.options.jac_bin)
        for pattern in (
            f"{basename} run --serve",
            "jac run --serve",
            f"{basename} start",
            "jac start",
        ):
            process.run(["pkill", "-f", pattern], self.app_dir, check=False)
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
            if "Postgres connection failed" in line
            or "PostgreSQL connection failed" in line
            or "database connection failed" in line
            or ("JAC_DB_URL" in line and "failed" in line.lower())
        ]
        if failures:
            raise RuntimeError(
                "Jac server did not connect to Postgres; access logs would be invalid: "
                + " | ".join(failures[:2])
            )

"""Docker-backed Postgres lifecycle helpers for prefetch sweeps."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import tomllib

from lib.prefetch_exp import process


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[2]
LOCAL_TOML = SWEEP_TOOL_ROOT / "local.toml"
COMPOSE_FILES = ("docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml")

DEFAULT_POSTGRES_URI = "postgresql://jac:jac@localhost:5432/jac_db"

POSTGRES_POST_RESTORE_SQL = """
CREATE INDEX IF NOT EXISTS idx_anchors_edge_src_type_order
    ON anchors (src, arch_type, seq, id)
    INCLUDE (dst, undirected)
    WHERE kind = 'EdgeAnchor' AND src IS NOT NULL AND dst IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_anchors_edge_dst_type_order
    ON anchors (dst, arch_type, seq, id)
    INCLUDE (src, undirected)
    WHERE kind = 'EdgeAnchor' AND src IS NOT NULL AND dst IS NOT NULL;
ANALYZE;
""".strip()


@dataclass(frozen=True)
class DbSettings:
    mode: str = "local_docker"
    host: str = ""
    ssh_user: str = ""
    remote_app_root: str = ""
    remote_app_dir: str = ""
    postgres_uri: str = DEFAULT_POSTGRES_URI
    postgres_container: str = "postgres"
    postgres_user: str = "jac"
    postgres_password: str = "jac"
    postgres_db: str = "jac_db"
    ssh_options: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.host}" if self.ssh_user else self.host


class DbManager:
    """Interface used by adapters for Postgres lifecycle work."""

    mode = "unknown"

    def __init__(
        self,
        *,
        settings: DbSettings,
        app_name: str,
        app_dir: Path,
        postgres_container: str,
    ):
        self.settings = settings
        self.app_name = app_name
        self.app_dir = app_dir
        self.postgres_container = settings.postgres_container or postgres_container
        self.postgres_uri = settings.postgres_uri
        self.postgres_user = settings.postgres_user
        self.postgres_password = settings.postgres_password
        self.postgres_db = settings.postgres_db

    def compose_down(self, remove_volumes: bool = False) -> None:
        raise NotImplementedError

    def compose_up(self) -> None:
        raise NotImplementedError

    def clear_runtime_cache(self) -> None:
        """Compatibility no-op; current Jac runtime is Postgres-only."""

    def restore_dump(self, dump_name: str) -> None:
        raise NotImplementedError

    def dump_exists(self, dump_name: str) -> bool:
        raise NotImplementedError

    def dump_description(self, dump_name: str) -> str:
        raise NotImplementedError

    def drop_jac_db(self) -> None:
        raise NotImplementedError

    def drop_non_system_databases(self) -> None:
        self.drop_jac_db()

    def dump_to_app(self, dump_name: str = "jac_db.pgdump") -> None:
        raise NotImplementedError

    def optimize_database(self) -> None:
        raise NotImplementedError

    def ensure_app_dir(self, rel_dir: str) -> None:
        raise NotImplementedError

    def db_query_count(self) -> str:
        return ""

    def compose_file_exists(self) -> bool:
        raise NotImplementedError

    def summary(self) -> str:
        return f"{self.mode} postgres={self.postgres_uri}"

    def _pg_env(self) -> list[str]:
        return ["-e", f"PGPASSWORD={self.postgres_password}"]


class LocalDockerDbManager(DbManager):
    mode = "local_docker"

    def compose_down(self, remove_volumes: bool = False) -> None:
        cmd = ["docker", "compose", "down", "--remove-orphans"]
        if remove_volumes:
            cmd.append("-v")
        process.run(cmd, self.app_dir, check=False)

    def compose_up(self) -> None:
        result = process.run(
            ["docker", "compose", "up", "-d"],
            self.app_dir,
            check=False,
            stdout=subprocess.PIPE,
        )
        if result.returncode == 0:
            self._wait_postgres_ready()
            return
        output = result.stdout or ""
        if "Conflict. The container name" in output:
            print("docker compose name conflict; removing stale benchmark Postgres container")
            process.run(
                ["docker", "rm", "-f", self.postgres_container],
                self.app_dir,
                check=False,
            )
            process.run(["docker", "compose", "up", "-d"], self.app_dir)
            self._wait_postgres_ready()
            return
        print(output)
        result.check_returncode()

    def restore_dump(self, dump_name: str) -> None:
        target = f"/tmp/{Path(dump_name).name}"
        process.run(
            ["docker", "cp", "-L", dump_name, f"{self.postgres_container}:{target}"],
            self.app_dir,
        )
        self._reset_database()
        self._restore_from_container_path(target)

    def dump_exists(self, dump_name: str) -> bool:
        return (self.app_dir / dump_name).exists()

    def dump_description(self, dump_name: str) -> str:
        dump_path = self.app_dir / dump_name
        if not dump_path.exists():
            return str(dump_path)
        return f"{dump_path.resolve()} ({dump_path.stat().st_size} bytes)"

    def drop_jac_db(self) -> None:
        self._reset_database()

    def dump_to_app(self, dump_name: str = "jac_db.pgdump") -> None:
        target = self.app_dir / dump_name
        target.parent.mkdir(parents=True, exist_ok=True)
        container_path = f"/tmp/{Path(dump_name).name}"
        process.run(
            [
                "docker",
                "exec",
                *self._pg_env(),
                self.postgres_container,
                "pg_dump",
                "-U",
                self.postgres_user,
                "-d",
                self.postgres_db,
                "--format=custom",
                "--no-owner",
                f"--file={container_path}",
            ],
            self.app_dir,
        )
        process.run(
            ["docker", "cp", f"{self.postgres_container}:{container_path}", dump_name],
            self.app_dir,
        )

    def ensure_app_dir(self, rel_dir: str) -> None:
        (self.app_dir / rel_dir).mkdir(parents=True, exist_ok=True)

    def compose_file_exists(self) -> bool:
        return any((self.app_dir / name).is_file() for name in COMPOSE_FILES)

    def _reset_database(self) -> None:
        process.run(
            [
                "docker",
                "exec",
                *self._pg_env(),
                self.postgres_container,
                "dropdb",
                "-U",
                self.postgres_user,
                "--if-exists",
                "--force",
                self.postgres_db,
            ],
            self.app_dir,
            check=False,
        )
        process.run(
            [
                "docker",
                "exec",
                *self._pg_env(),
                self.postgres_container,
                "createdb",
                "-U",
                self.postgres_user,
                self.postgres_db,
            ],
            self.app_dir,
        )

    def _restore_from_container_path(self, container_path: str) -> None:
        if container_path.endswith(".sql"):
            process.run(
                [
                    "docker",
                    "exec",
                    *self._pg_env(),
                    self.postgres_container,
                    "psql",
                    "-U",
                    self.postgres_user,
                    "-d",
                    self.postgres_db,
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-f",
                    container_path,
                ],
                self.app_dir,
            )
        else:
            process.run(
                [
                    "docker",
                    "exec",
                    *self._pg_env(),
                    self.postgres_container,
                    "pg_restore",
                    "-U",
                    self.postgres_user,
                    "-d",
                    self.postgres_db,
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    container_path,
                ],
                self.app_dir,
            )
        self.optimize_database()

    def optimize_database(self) -> None:
        print("Creating TTG Postgres indexes and analyzing planner stats")
        process.run(
            [
                "docker",
                "exec",
                *self._pg_env(),
                self.postgres_container,
                "psql",
                "-U",
                self.postgres_user,
                "-d",
                self.postgres_db,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                POSTGRES_POST_RESTORE_SQL,
            ],
            self.app_dir,
        )

    def _wait_postgres_ready(self, timeout_sec: float = 60.0) -> None:
        deadline = time.time() + timeout_sec
        last_output = ""
        while time.time() < deadline:
            result = process.run(
                [
                    "docker",
                    "exec",
                    *self._pg_env(),
                    self.postgres_container,
                    "pg_isready",
                    "-U",
                    self.postgres_user,
                    "-d",
                    self.postgres_db,
                ],
                self.app_dir,
                check=False,
                stdout=subprocess.PIPE,
            )
            last_output = result.stdout or ""
            if result.returncode == 0:
                return
            time.sleep(1.0)
        raise TimeoutError(
            f"Postgres did not become ready in container {self.postgres_container}: {last_output.strip()}"
        )


class RemoteSshDockerDbManager(DbManager):
    mode = "remote_ssh"

    @property
    def remote_app_dir(self) -> str:
        return self.settings.remote_app_dir

    def compose_down(self, remove_volumes: bool = False) -> None:
        cmd = "docker compose down --remove-orphans"
        if remove_volumes:
            cmd += " -v"
        self._ssh(self._cd(cmd), check=False)

    def compose_up(self) -> None:
        result = self._ssh(self._cd("docker compose up -d"), check=False, stdout=subprocess.PIPE)
        if result.returncode == 0:
            self._wait_postgres_ready()
            return
        output = result.stdout or ""
        if "Conflict. The container name" in output:
            print("remote docker compose name conflict; removing stale benchmark Postgres container")
            self._ssh(
                self._cd(f"docker rm -f {shlex.quote(self.postgres_container)}"),
                check=False,
            )
            self._ssh(self._cd("docker compose up -d"))
            self._wait_postgres_ready()
            return
        print(output)
        result.check_returncode()

    def restore_dump(self, dump_name: str) -> None:
        self._reset_database()
        if dump_name.endswith(".sql"):
            command = (
                f"docker exec -i {self._pg_exec_args()} "
                f"{shlex.quote(self.postgres_container)} psql "
                f"-U {shlex.quote(self.postgres_user)} "
                f"-d {shlex.quote(self.postgres_db)} "
                f"-v ON_ERROR_STOP=1 < {shlex.quote(dump_name)}"
            )
        else:
            command = (
                f"docker exec -i {self._pg_exec_args()} "
                f"{shlex.quote(self.postgres_container)} pg_restore "
                f"-U {shlex.quote(self.postgres_user)} "
                f"-d {shlex.quote(self.postgres_db)} "
                f"--clean --if-exists --no-owner < {shlex.quote(dump_name)}"
            )
        self._ssh(self._cd(command))
        self.optimize_database()

    def dump_exists(self, dump_name: str) -> bool:
        result = self._ssh(self._cd(f"test -e {shlex.quote(dump_name)}"), check=False)
        return result.returncode == 0

    def dump_description(self, dump_name: str) -> str:
        remote_path = f"{self.remote_app_dir.rstrip('/')}/{dump_name}"
        result = self._ssh(
            self._cd(f"stat -Lc %s {shlex.quote(dump_name)}"),
            check=False,
            stdout=subprocess.PIPE,
        )
        size = (result.stdout or "").strip()
        if result.returncode == 0 and size:
            return f"{self.settings.ssh_target}:{remote_path} ({size} bytes)"
        return f"{self.settings.ssh_target}:{remote_path}"

    def drop_jac_db(self) -> None:
        self._reset_database()

    def dump_to_app(self, dump_name: str = "jac_db.pgdump") -> None:
        parent = str(Path(dump_name).parent)
        if parent and parent != ".":
            self.ensure_app_dir(parent)
        self._ssh(
            self._cd(
                f"docker exec {self._pg_exec_args()} "
                f"{shlex.quote(self.postgres_container)} pg_dump "
                f"-U {shlex.quote(self.postgres_user)} "
                f"-d {shlex.quote(self.postgres_db)} "
                f"--format=custom --no-owner > {shlex.quote(dump_name)}"
            )
        )

    def ensure_app_dir(self, rel_dir: str) -> None:
        self._ssh(self._cd(f"mkdir -p {shlex.quote(rel_dir)}"))

    def compose_file_exists(self) -> bool:
        joined = " || ".join(f"test -f {shlex.quote(name)}" for name in COMPOSE_FILES)
        result = self._ssh(f"cd {shlex.quote(self.remote_app_dir)} && ( {joined} )", check=False)
        return result.returncode == 0

    def summary(self) -> str:
        return (
            f"{self.mode} ssh={self.settings.ssh_target} "
            f"remote_app_dir={self.remote_app_dir} "
            f"postgres={self.postgres_uri}"
        )

    def _reset_database(self) -> None:
        self._ssh(
            self._cd(
                f"docker exec {self._pg_exec_args()} "
                f"{shlex.quote(self.postgres_container)} dropdb "
                f"-U {shlex.quote(self.postgres_user)} "
                f"--if-exists --force {shlex.quote(self.postgres_db)}"
            ),
            check=False,
        )
        self._ssh(
            self._cd(
                f"docker exec {self._pg_exec_args()} "
                f"{shlex.quote(self.postgres_container)} createdb "
                f"-U {shlex.quote(self.postgres_user)} {shlex.quote(self.postgres_db)}"
            )
        )

    def _pg_exec_args(self) -> str:
        return f"-e PGPASSWORD={shlex.quote(self.postgres_password)}"

    def optimize_database(self) -> None:
        print("Creating remote TTG Postgres indexes and analyzing planner stats")
        command = (
            f"docker exec {self._pg_exec_args()} "
            f"{shlex.quote(self.postgres_container)} psql "
            f"-U {shlex.quote(self.postgres_user)} "
            f"-d {shlex.quote(self.postgres_db)} "
            f"-v ON_ERROR_STOP=1 "
            f"-c {shlex.quote(POSTGRES_POST_RESTORE_SQL)}"
        )
        self._ssh(self._cd(command))

    def _wait_postgres_ready(self, timeout_sec: float = 60.0) -> None:
        deadline = time.time() + timeout_sec
        last_output = ""
        command = (
            f"docker exec {self._pg_exec_args()} "
            f"{shlex.quote(self.postgres_container)} pg_isready "
            f"-U {shlex.quote(self.postgres_user)} "
            f"-d {shlex.quote(self.postgres_db)}"
        )
        while time.time() < deadline:
            result = self._ssh(self._cd(command), check=False, stdout=subprocess.PIPE)
            last_output = result.stdout or ""
            if result.returncode == 0:
                return
            time.sleep(1.0)
        raise TimeoutError(
            f"remote Postgres did not become ready in container {self.postgres_container}: "
            f"{last_output.strip()}"
        )

    def _cd(self, command: str) -> str:
        return f"cd {shlex.quote(self.remote_app_dir)} && {command}"

    def _ssh(
        self,
        command: str,
        *,
        check: bool = True,
        stdout: int | None = None,
    ) -> subprocess.CompletedProcess:
        return process.run(
            ["ssh", *self.settings.ssh_options, self.settings.ssh_target, command],
            self.app_dir,
            check=check,
            stdout=stdout,
        )


def make_db_manager(
    *,
    app_name: str,
    app_dir: Path,
    default_postgres_uri: str,
    postgres_container: str,
    env: dict[str, str] | None = None,
) -> DbManager:
    settings = load_db_settings(
        app_name=app_name,
        default_postgres_uri=default_postgres_uri,
        default_postgres_container=postgres_container,
        env=env,
    )
    cls: type[DbManager]
    if settings.mode == "remote_ssh":
        cls = RemoteSshDockerDbManager
    else:
        cls = LocalDockerDbManager
    return cls(
        settings=settings,
        app_name=app_name,
        app_dir=app_dir,
        postgres_container=postgres_container,
    )


def load_db_settings(
    *,
    app_name: str,
    default_postgres_uri: str = DEFAULT_POSTGRES_URI,
    default_postgres_container: str = "postgres",
    env: dict[str, str] | None = None,
    config_path: Path = LOCAL_TOML,
) -> DbSettings:
    env = env if env is not None else os.environ
    data = _load_local_toml(config_path)
    db_data = data.get("db", {})
    if not isinstance(db_data, dict):
        db_data = {}
    apps = db_data.get("apps", {})
    app_data = apps.get(app_name, {}) if isinstance(apps, dict) else {}
    if not isinstance(app_data, dict):
        app_data = {}

    backend = _setting(env, app_data, db_data, "backend", "SWEEP_DB_BACKEND", "postgres").strip().lower()
    if backend not in {"postgres", "postgresql", "pgsql"}:
        raise ValueError(f"unsupported sweep DB backend {backend!r}; this sweep tool expects Postgres")

    mode = _setting(env, app_data, db_data, "mode", "SWEEP_DB_MODE", "local_docker").strip()
    if mode not in {"local_docker", "remote_ssh"}:
        raise ValueError(f"unsupported sweep DB mode {mode!r}; use local_docker or remote_ssh")

    host = _setting(env, app_data, db_data, "host", "SWEEP_DB_HOST", "").strip()
    ssh_user = _setting(env, app_data, db_data, "ssh_user", "SWEEP_DB_SSH_USER", "").strip()
    remote_app_root = _setting(
        env,
        app_data,
        db_data,
        "remote_app_root",
        "SWEEP_DB_REMOTE_APP_ROOT",
        "",
    ).strip()
    remote_app_dir = _setting(
        env,
        app_data,
        db_data,
        "remote_app_dir",
        "SWEEP_DB_REMOTE_APP_DIR",
        "",
    ).strip()
    ssh_options = _ssh_options(env, app_data, db_data)

    postgres_uri = _uri_setting(
        env,
        app_data,
        db_data,
        "postgres_uri",
        ("SWEEP_DB_POSTGRES_URI", "JAC_DB_URL", "POSTGRES_URL", "DATABASE_URL"),
        "",
    )
    explicit_postgres_uri = _first_env(
        env, ("SWEEP_DB_POSTGRES_URI", "JAC_DB_URL", "POSTGRES_URL", "DATABASE_URL")
    )
    if (
        mode == "local_docker"
        and env.get("SWEEP_DB_MODE", "").strip() == "local_docker"
        and not explicit_postgres_uri
    ):
        postgres_uri = ""

    if mode == "remote_ssh":
        if not host:
            raise ValueError("remote_ssh DB mode requires db.host or SWEEP_DB_HOST")
        if not remote_app_dir:
            if not remote_app_root:
                raise ValueError(
                    "remote_ssh DB mode requires db.remote_app_root, "
                    "db.apps.<app>.remote_app_dir, or SWEEP_DB_REMOTE_APP_ROOT"
                )
            remote_app_dir = str(Path(remote_app_root) / app_name)
        if not postgres_uri and default_postgres_uri:
            postgres_uri = _replace_uri_host(default_postgres_uri, host)

    postgres_uri = postgres_uri or default_postgres_uri
    uri_user, uri_password, uri_db = _postgres_parts(postgres_uri)
    postgres_container = _setting(
        env,
        app_data,
        db_data,
        "postgres_container",
        "SWEEP_DB_POSTGRES_CONTAINER",
        default_postgres_container,
    ).strip()
    postgres_user = _setting(
        env,
        app_data,
        db_data,
        "postgres_user",
        "SWEEP_DB_POSTGRES_USER",
        uri_user or "jac",
    ).strip()
    postgres_password = _setting(
        env,
        app_data,
        db_data,
        "postgres_password",
        "SWEEP_DB_POSTGRES_PASSWORD",
        uri_password or "jac",
    )
    postgres_db = _setting(
        env,
        app_data,
        db_data,
        "postgres_db",
        "SWEEP_DB_POSTGRES_DB",
        uri_db or "jac_db",
    ).strip()

    return DbSettings(
        mode=mode,
        host=host,
        ssh_user=ssh_user,
        remote_app_root=remote_app_root,
        remote_app_dir=remote_app_dir,
        postgres_uri=postgres_uri,
        postgres_container=postgres_container,
        postgres_user=postgres_user,
        postgres_password=postgres_password,
        postgres_db=postgres_db,
        ssh_options=ssh_options,
    )


def run_all_teardown_shell(app_name: str, app_dir: Path, remove_volumes: bool = True) -> str:
    settings = load_db_settings(app_name=app_name)
    volume_arg = " -v" if remove_volumes else ""
    if settings.mode == "remote_ssh":
        remote_cmd = (
            f"cd {shlex.quote(settings.remote_app_dir)} && "
            f"docker compose down --remove-orphans{volume_arg} > /dev/null 2>&1 || true"
        )
        ssh_parts = ["ssh", *settings.ssh_options, settings.ssh_target, remote_cmd]
        return " ".join(shlex.quote(part) for part in ssh_parts)
    return (
        f"cd {shlex.quote(str(app_dir))} && "
        f"docker compose down --remove-orphans{volume_arg} > /dev/null 2>&1 || true"
    )


def uri_uses_localhost(uri: str) -> bool:
    host = (urlsplit(uri).hostname or "").lower()
    return host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("127.")


def uri_host_port(uri: str, default_port: int) -> tuple[str, int]:
    parsed = urlsplit(uri)
    return parsed.hostname or "", parsed.port or default_port


def _load_local_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def _setting(
    env: dict[str, str],
    app_data: dict[str, Any],
    db_data: dict[str, Any],
    key: str,
    env_key: str,
    default: str,
) -> str:
    if env.get(env_key, ""):
        return str(env[env_key])
    if key in app_data:
        return str(app_data[key])
    if key in db_data:
        return str(db_data[key])
    return default


def _uri_setting(
    env: dict[str, str],
    app_data: dict[str, Any],
    db_data: dict[str, Any],
    key: str,
    env_keys: tuple[str, ...],
    default: str,
) -> str:
    for env_key in env_keys:
        if env.get(env_key, ""):
            return str(env[env_key])
    if key in app_data:
        return str(app_data[key])
    if key in db_data:
        return str(db_data[key])
    return default


def _first_env(env: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        if env.get(key, ""):
            return str(env[key])
    return ""


def _ssh_options(env: dict[str, str], app_data: dict[str, Any], db_data: dict[str, Any]) -> tuple[str, ...]:
    raw = env.get("SWEEP_DB_SSH_OPTIONS", "")
    if raw:
        return tuple(shlex.split(raw))
    value = app_data.get("ssh_options", db_data.get("ssh_options", []))
    if isinstance(value, str):
        return tuple(shlex.split(value))
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _postgres_parts(uri: str) -> tuple[str, str, str]:
    parsed = urlsplit(uri)
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    database = parsed.path.lstrip("/").split("/", 1)[0] if parsed.path else ""
    return user, password, database


def _replace_uri_host(uri: str, host: str) -> str:
    parsed = urlsplit(uri)
    if not parsed.scheme or not parsed.netloc:
        return uri
    userinfo = ""
    hostport = parsed.netloc
    if "@" in hostport:
        userinfo, hostport = hostport.rsplit("@", 1)
        userinfo += "@"
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit((parsed.scheme, f"{userinfo}{host}{port}", parsed.path, parsed.query, parsed.fragment))

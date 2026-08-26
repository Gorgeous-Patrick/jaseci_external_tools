"""Docker-backed DB lifecycle helpers for prefetch sweeps."""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import tomllib

from lib.prefetch_exp import process


SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[2]
LOCAL_TOML = SWEEP_TOOL_ROOT / "local.toml"
COMPOSE_FILES = ("docker-compose.yaml", "docker-compose.yml", "compose.yaml", "compose.yml")


@dataclass(frozen=True)
class DbSettings:
    mode: str = "local_docker"
    host: str = ""
    ssh_user: str = ""
    remote_app_root: str = ""
    remote_app_dir: str = ""
    mongo_uri: str = ""
    redis_url: str = ""
    ssh_options: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ssh_target(self) -> str:
        return f"{self.ssh_user}@{self.host}" if self.ssh_user else self.host


class DbManager:
    """Interface used by adapters for MongoDB/Redis lifecycle work."""

    mode = "unknown"

    def __init__(
        self,
        *,
        settings: DbSettings,
        app_name: str,
        app_dir: Path,
        mongo_container: str,
        redis_container: str,
    ):
        self.settings = settings
        self.app_name = app_name
        self.app_dir = app_dir
        self.mongo_container = mongo_container
        self.redis_container = redis_container
        self.mongo_uri = settings.mongo_uri
        self.redis_url = settings.redis_url

    def compose_down(self, remove_volumes: bool = False) -> None:
        raise NotImplementedError

    def compose_up(self) -> None:
        raise NotImplementedError

    def flush_redis(self) -> None:
        raise NotImplementedError

    def restore_dump(self, dump_name: str) -> None:
        raise NotImplementedError

    def dump_exists(self, dump_name: str) -> bool:
        raise NotImplementedError

    def dump_description(self, dump_name: str) -> str:
        raise NotImplementedError

    def drop_jac_db(self) -> None:
        raise NotImplementedError

    def drop_non_system_databases(self) -> None:
        raise NotImplementedError

    def mongodump_to_app(self, dump_name: str = "jac_db.dump") -> None:
        raise NotImplementedError

    def ensure_app_dir(self, rel_dir: str) -> None:
        raise NotImplementedError

    def mongo_query_count(self) -> str:
        raise NotImplementedError

    def compose_file_exists(self) -> bool:
        raise NotImplementedError

    def summary(self) -> str:
        return f"{self.mode} mongo={self.mongo_uri} redis={self.redis_url}"


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

    def restore_dump(self, dump_name: str) -> None:
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

    def dump_exists(self, dump_name: str) -> bool:
        return (self.app_dir / dump_name).exists()

    def dump_description(self, dump_name: str) -> str:
        dump_path = self.app_dir / dump_name
        if not dump_path.exists():
            return str(dump_path)
        return f"{dump_path.resolve()} ({dump_path.stat().st_size} bytes)"

    def drop_jac_db(self) -> None:
        process.run(
            ["docker", "exec", self.mongo_container, "mongosh", "jac_db", "--quiet", "--eval", "db.dropDatabase()"],
            self.app_dir,
            check=False,
        )

    def drop_non_system_databases(self) -> None:
        process.run(
            [
                "docker",
                "exec",
                self.mongo_container,
                "mongosh",
                "--quiet",
                "--eval",
                _DROP_NON_SYSTEM_DATABASES_JS,
            ],
            self.app_dir,
            check=False,
        )

    def mongodump_to_app(self, dump_name: str = "jac_db.dump") -> None:
        target = self.app_dir / dump_name
        target.parent.mkdir(parents=True, exist_ok=True)
        process.run(
            ["docker", "exec", self.mongo_container, "mongodump", "--db", "jac_db", "--archive=/tmp/jac_db.dump"],
            self.app_dir,
        )
        process.run(
            ["docker", "cp", f"{self.mongo_container}:/tmp/jac_db.dump", dump_name],
            self.app_dir,
        )

    def ensure_app_dir(self, rel_dir: str) -> None:
        (self.app_dir / rel_dir).mkdir(parents=True, exist_ok=True)

    def mongo_query_count(self) -> str:
        try:
            proc = process.run(
                [
                    "docker",
                    "exec",
                    self.mongo_container,
                    "mongosh",
                    "jac_db",
                    "--quiet",
                    "--eval",
                    "print(Number(db.serverStatus().opcounters.query))",
                ],
                self.app_dir,
                stdout=subprocess.PIPE,
                check=False,
            )
            return (proc.stdout or "").strip().splitlines()[-1]
        except Exception:
            return ""

    def compose_file_exists(self) -> bool:
        return any((self.app_dir / name).is_file() for name in COMPOSE_FILES)


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
            return
        output = result.stdout or ""
        if "Conflict. The container name" in output:
            print("remote docker compose name conflict; removing stale benchmark containers")
            self._ssh(
                self._cd(
                    "docker rm -f "
                    f"{shlex.quote(self.mongo_container)} {shlex.quote(self.redis_container)}"
                ),
                check=False,
            )
            self._ssh(self._cd("docker compose up -d"))
            return
        print(output)
        result.check_returncode()

    def flush_redis(self) -> None:
        self._ssh(
            self._cd(f"docker exec {shlex.quote(self.redis_container)} redis-cli FLUSHALL"),
            check=False,
        )

    def restore_dump(self, dump_name: str) -> None:
        self._ssh(
            self._cd(
                f"docker exec -i {shlex.quote(self.mongo_container)} "
                f"mongorestore --archive --drop < {shlex.quote(dump_name)}"
            ),
            check=False,
        )

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
        self._ssh(
            self._cd(
                f"docker exec {shlex.quote(self.mongo_container)} "
                f"mongosh jac_db --quiet --eval {shlex.quote('db.dropDatabase()')}"
            ),
            check=False,
        )

    def drop_non_system_databases(self) -> None:
        self._ssh(
            self._cd(
                f"docker exec {shlex.quote(self.mongo_container)} "
                f"mongosh --quiet --eval {shlex.quote(_DROP_NON_SYSTEM_DATABASES_JS)}"
            ),
            check=False,
        )

    def mongodump_to_app(self, dump_name: str = "jac_db.dump") -> None:
        parent = str(Path(dump_name).parent)
        if parent and parent != ".":
            self.ensure_app_dir(parent)
        self._ssh(
            self._cd(
                f"docker exec {shlex.quote(self.mongo_container)} "
                f"mongodump --db jac_db --archive > {shlex.quote(dump_name)}"
            )
        )

    def ensure_app_dir(self, rel_dir: str) -> None:
        self._ssh(self._cd(f"mkdir -p {shlex.quote(rel_dir)}"))

    def mongo_query_count(self) -> str:
        try:
            proc = self._ssh(
                self._cd(
                    f"docker exec {shlex.quote(self.mongo_container)} "
                    "mongosh jac_db --quiet --eval "
                    f"{shlex.quote('print(Number(db.serverStatus().opcounters.query))')}"
                ),
                stdout=subprocess.PIPE,
                check=False,
            )
            return (proc.stdout or "").strip().splitlines()[-1]
        except Exception:
            return ""

    def compose_file_exists(self) -> bool:
        joined = " || ".join(f"test -f {shlex.quote(name)}" for name in COMPOSE_FILES)
        result = self._ssh(f"cd {shlex.quote(self.remote_app_dir)} && ( {joined} )", check=False)
        return result.returncode == 0

    def summary(self) -> str:
        return (
            f"{self.mode} ssh={self.settings.ssh_target} "
            f"remote_app_dir={self.remote_app_dir} "
            f"mongo={self.mongo_uri} redis={self.redis_url}"
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
    default_mongo_uri: str,
    default_redis_url: str,
    mongo_container: str,
    redis_container: str,
    env: dict[str, str] | None = None,
) -> DbManager:
    settings = load_db_settings(
        app_name=app_name,
        default_mongo_uri=default_mongo_uri,
        default_redis_url=default_redis_url,
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
        mongo_container=mongo_container,
        redis_container=redis_container,
    )


def load_db_settings(
    *,
    app_name: str,
    default_mongo_uri: str = "",
    default_redis_url: str = "",
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

    mongo_uri = _uri_setting(
        env,
        app_data,
        db_data,
        "mongo_uri",
        ("SWEEP_DB_MONGO_URI", "MONGODB_URI"),
        "",
    )
    redis_url = _uri_setting(
        env,
        app_data,
        db_data,
        "redis_url",
        ("SWEEP_DB_REDIS_URL", "REDIS_URL"),
        "",
    )

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
        if not mongo_uri and default_mongo_uri:
            mongo_uri = _replace_uri_host(default_mongo_uri, host)
        if not redis_url and default_redis_url:
            redis_url = _replace_uri_host(default_redis_url, host)

    return DbSettings(
        mode=mode,
        host=host,
        ssh_user=ssh_user,
        remote_app_root=remote_app_root,
        remote_app_dir=remote_app_dir,
        mongo_uri=mongo_uri or default_mongo_uri,
        redis_url=redis_url or default_redis_url,
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


_DROP_NON_SYSTEM_DATABASES_JS = (
    "db.getMongo().getDBNames().forEach(function(d){"
    'if(d!="admin"&&d!="local"&&d!="config"){'
    "db.getSiblingDB(d).dropDatabase()}})"
)

"""LittleX5 benchmark adapter."""

from __future__ import annotations

import shutil
from pathlib import Path

from lib.prefetch_exp import process
from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.models import CaseState, RequestSpec


class LittleX5Adapter(BenchmarkAdapter):
    config_name = "jac.sweep.toml"
    default_user = "sim_user_56"
    default_password = "password"
    credential_source = "backup.pgdump seeded sim_user benchmark target"
    default_dump = "backup.pgdump"

    def server_command(self) -> list[str]:
        return [self.options.jac_bin, "run", "--serve", "--no-client", "server.jac"]

    def start_server(
        self,
        log_path: Path,
        profile_dir: Path | None = None,
        profile_csv: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ):
        stage_dir = self._stage_backend_project()
        proc = process.start_server(
            self.server_command(),
            stage_dir,
            self.server_env(profile_dir=profile_dir, profile_csv=profile_csv, extra_env=extra_env),
            log_path,
        )
        try:
            process.wait_ready(self.base_url)
            self._assert_tiered_memory_connected(log_path)
        except Exception:
            process.stop_process(proc)
            raise
        return proc

    def _stage_backend_project(self) -> Path:
        stage_dir = Path(
            self.options.env.get("LITTLEX_SWEEP_STAGE_DIR")
            or "/tmp/jaseci_littlex5_sweep"
        )
        stage_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.app_dir / "server.jac", stage_dir / "server.jac")
        shutil.copy2(self.config_path, stage_dir / "jac.toml")
        for stale in ("jac.local.toml", "jac.sweep.toml"):
            try:
                (stage_dir / stale).unlink()
            except FileNotFoundError:
                pass
        return stage_dir

    def restore_dump_if_present(self, dump_name: str = "jac_db.pgdump") -> None:
        configured = self._configured_dump()
        self.options.env["LITTLEX_DUMP"] = configured
        if not self.dump_exists(configured):
            raise FileNotFoundError(
                "Configured LittleX dump does not exist: "
                f"{self.dump_description(configured)}. Set LITTLEX_DUMP to a valid dump; "
                "the LittleX sweep will not silently fall back to backup.pgdump."
            )
        print(
            "=== LittleX restoring configured dump: "
            f"{configured} -> {self.dump_description(configured)} ==="
        )
        super().restore_dump_if_present(configured)

    def prepare_request(self, policy: str, limit: int) -> CaseState:
        token = self.setup_token(f"jac_server_prepare_{policy}_limit{limit}.log")
        walker = self.options.env.get("WALKER") or "load_feed"
        return CaseState(
            token=token,
            request=RequestSpec(
                walker=walker,
                path=f"/walker/{walker}",
                body={},
                target_id=self.user_name(),
                request_id=self.user_name(),
            ),
        )

    def spawn_pool(self, state: CaseState) -> list[RequestSpec]:
        walker = self.options.env.get("WALKER") or "load_feed"
        users = self._pooled_users()
        proc = None
        try:
            proc = self.start_server(
                self.app_dir / self.options.manifest.logs_dir / "jac_server_markov_pool_auth.log"
            )
            tokens = {username: self.login(username, self.password()) for username in users}
        finally:
            process.stop_process(proc)
            self.stop_stale_servers()
        return [
            RequestSpec(
                walker=walker,
                path=f"/walker/{walker}",
                body={},
                target_id=username,
                request_id=username,
                token=tokens[username],
            )
            for username in users
        ]

    def _pooled_users(self) -> list[str]:
        raw = self.options.env.get("LITTLEX_USER_POOL", "").strip()
        if raw:
            return [item.strip() for item in raw.replace(",", " ").split() if item.strip()]
        desired = int(
            self.options.env.get("SWEEP_MARKOV_POOL_SIZE")
            or str(max(max(self.options.markov_train_ns), max(self.options.coaccess_train_ns)) + 1)
        )
        prefix = self.options.env.get("LITTLEX_USER_POOL_PREFIX") or "sim_user_"
        start = int(self.options.env.get("LITTLEX_USER_POOL_START") or "0")
        return [f"{prefix}{idx}" for idx in range(start, start + desired)]

    def _configured_dump(self) -> str:
        configured = (
            self.options.env.get("LITTLEX_DUMP")
            or self.options.env.get("LITTLEX5_DUMP")
            or self.default_dump
        ).strip()
        return configured or self.default_dump

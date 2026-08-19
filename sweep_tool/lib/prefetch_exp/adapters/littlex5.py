"""LittleX5 benchmark adapter."""

from __future__ import annotations

from lib.prefetch_exp import process
from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.models import CaseState, RequestSpec


class LittleX5Adapter(BenchmarkAdapter):
    default_user = "user56"
    default_password = "password"
    credential_source = "bootstrap.py users + quick_run.sh benchmark target"

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
        edge_dir = self.app_dir / "facebook"
        user_ids: set[int] = set()
        for path in sorted(edge_dir.glob("*.edges")):
            with open(path) as fh:
                for line in fh:
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    user_ids.add(int(parts[0]))
                    user_ids.add(int(parts[1]))
            if len(user_ids) >= desired:
                break
        return [f"user{uid}" for uid in sorted(user_ids)[:desired]]

"""Jacord benchmark adapter."""

from __future__ import annotations

from lib.prefetch_exp import process
from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.models import CaseState, RequestSpec


class JacordAdapter(BenchmarkAdapter):
    default_user = "user_0000"
    default_password = "password"
    credential_source = "bootstrap.py primary benchmark user"
    default_dump = "dumps/big.dump"

    def restore_dump_if_present(self, dump_name: str = "jac_db.dump") -> None:
        configured = self.options.env.get("JACORD_DUMP") or self.default_dump
        if (self.app_dir / configured).exists():
            super().restore_dump_if_present(configured)
            return
        super().restore_dump_if_present(dump_name)

    def prepare_request(self, policy: str, limit: int) -> CaseState:
        proc = None
        token = ""
        channel_id = ""
        try:
            proc = self.start_server(
                self.app_dir / self.options.manifest.logs_dir / f"jac_server_prepare_{policy}_limit{limit}.log"
            )
            token = self.login()
            resp = self.post("/walker/ListChannelIds", {"limit": 100}, token=token)
            reports = resp.json().get("data", {}).get("reports") or []
            ids = reports[0] if reports else []
            if not ids:
                raise RuntimeError("Jacord ListChannelIds returned no channel IDs")
            channel_id = sorted(str(x) for x in ids)[0]
        finally:
            process.stop_process(proc)
            self.stop_stale_servers()

        walker = self.options.env.get("WALKER") or "load_channel"
        return CaseState(
            token=token,
            request=RequestSpec(
                walker=walker,
                path=f"/walker/{walker}/{channel_id}",
                body={},
                target_id=channel_id,
            ),
        )

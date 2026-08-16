"""LittleX5 benchmark adapter."""

from __future__ import annotations

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
            ),
        )

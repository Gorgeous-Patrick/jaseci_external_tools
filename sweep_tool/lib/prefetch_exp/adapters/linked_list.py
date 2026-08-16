"""LinkedList benchmark adapter."""

from __future__ import annotations

import os
import subprocess
import time

from lib.prefetch_exp import process
from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.models import CaseState, RequestSpec


class LinkedListAdapter(BenchmarkAdapter):
    default_user = "user"
    default_password = "password"
    credential_source = "quick_run.sh live setup user"

    def server_env(self, profile_dir=None, profile_csv=None) -> dict[str, str]:
        env = super().server_env(profile_dir=profile_dir, profile_csv=profile_csv)
        env["JAC_LIST_SIZE"] = str(self.options.env.get("JAC_LIST_SIZE") or "1000")
        return env

    def reset_storage(self) -> None:
        self.compose_down()
        self.compose_up()
        time.sleep(5)
        self._jac_clean()
        self.flush_redis()
        process.run(
            [
                "docker",
                "exec",
                self.mongo_container,
                "mongosh",
                "--quiet",
                "--eval",
                (
                    "db.getMongo().getDBNames().forEach(function(d){"
                    'if(d!="admin"&&d!="local"&&d!="config"){'
                    "db.getSiblingDB(d).dropDatabase()}})"
                ),
            ],
            self.app_dir,
            check=False,
        )
        self.stop_stale_servers()

    def prepare_request(self, policy: str, limit: int) -> CaseState:
        proc = None
        try:
            proc = self.start_server(
                self.app_dir / self.options.manifest.logs_dir / f"jac_server_setup_{policy}_limit{limit}.log"
            )
            process.register_user(self.base_url, self.user_name(), self.password())
            token = self.login()
            resp = self.post("/function/setup_graph", {}, token=token)
            nodes = resp.json().get("data", {}).get("result") or []
            if not nodes:
                raise RuntimeError("LinkedList setup_graph returned no nodes")
            first_node = str(nodes[0])
            print(f"LinkedList setup_graph created {len(nodes)} node(s)")
            time.sleep(5)
        finally:
            process.stop_process(proc)
            self.stop_stale_servers()

        self.flush_redis()
        walker = self.options.env.get("WALKER") or "Traverse"
        return CaseState(
            token=token,
            request=RequestSpec(
                walker=walker,
                path=f"/walker/{walker}/{first_node}",
                body={},
                target_id=first_node,
            ),
        )

    def _jac_clean(self) -> None:
        env = {**os.environ.copy(), **self.options.env, "JAC_BIN": self.options.jac_bin}
        subprocess.run(
            [self.options.jac_bin, "clean"],
            cwd=str(self.app_dir),
            env=env,
            input="y\n",
            text=True,
            check=False,
        )

"""JSearch benchmark adapter."""

from __future__ import annotations

from lib.prefetch_exp import process
from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.models import CaseState, RequestSpec


class JSearchAdapter(BenchmarkAdapter):
    config_name = "jac.sweep.toml"
    mongo_container = "jsearch-mongodb"
    redis_container = "jsearch-redis"
    mongo_uri = "mongodb://localhost:27019"
    redis_url = "redis://localhost:6381"
    profile_name = "sweep"
    default_user = "sweep_user"
    default_password = "password"
    credential_source = "seed_sweep_db.py / sweep_seed.json"

    def prepare_sweep(self) -> None:
        self._assert_seed_credentials_match_env()
        if (
            self.options.env.get("SWEEP_RESEED") == "1"
            or not (self.app_dir / "jac_db.dump").exists()
            or not (self.app_dir / "sweep_seed.json").exists()
        ):
            self._prepare_seed_dump()

    def user_name(self) -> str:
        explicit = self.options.env.get("TEST_USER")
        if explicit:
            return explicit
        try:
            seeded = self.json_file("sweep_seed.json").get("username")
        except FileNotFoundError:
            seeded = ""
        return str(seeded or self.default_user)

    def prepare_request(self, policy: str, limit: int) -> CaseState:
        token = self.setup_token(f"jac_server_prepare_{policy}_limit{limit}.log")
        seed = self.json_file("sweep_seed.json")
        index_id = str(seed["index_id"])
        query = str(seed.get("query") or self.options.env.get("JSEARCH_QUERY") or "database latency cache")
        body = {
            "query": query,
            "max_results": int(self.options.env.get("JSEARCH_MAX_RESULTS") or "20"),
            "max_pages": int(self.options.env.get("JSEARCH_MAX_PAGES") or "300"),
            "cpu_rounds": int(self.options.env.get("JSEARCH_CPU_ROUNDS") or "500"),
        }
        return CaseState(
            token=token,
            request=RequestSpec(
                walker=self.options.env.get("WALKER") or "SearchIndex",
                path=f"/walker/{self.options.env.get('WALKER') or 'SearchIndex'}/{index_id}",
                body=body,
                target_id=index_id,
            ),
        )

    def validate_response(self, spec: RequestSpec, payload: dict) -> None:
        reports = payload.get("data", {}).get("reports") or []
        report = reports[0] if reports else {}
        if not report.get("results"):
            print("warning: JSearch returned no results")

    def _prepare_seed_dump(self) -> None:
        print("=== Preparing JSearch sweep seed dump ===")
        (self.app_dir / self.options.manifest.logs_dir).mkdir(parents=True, exist_ok=True)
        self.compose_down()
        self.compose_up()
        process.run(
            ["docker", "exec", self.mongo_container, "mongosh", "jac_db", "--quiet", "--eval", "db.dropDatabase()"],
            self.app_dir,
            check=False,
        )
        self.flush_redis()
        self.stop_stale_servers()

        proc = None
        try:
            proc = self.start_server(self.app_dir / self.options.manifest.logs_dir / "jac_server_seed.log")
            env = {
                **self.options.env,
                "BASE_URL": self.base_url,
                "TEST_USER": self.user_name(),
                "TEST_PASSWORD": self.password(),
                "MONGODB_URI": self.mongo_uri,
            }
            process.run([self.options.python_bin, "seed_sweep_db.py"], self.app_dir, env=env)
        finally:
            process.stop_process(proc)
            self.stop_stale_servers()

        self.flush_redis()
        process.run(
            ["docker", "exec", self.mongo_container, "mongodump", "--db", "jac_db", "--archive=/tmp/jac_db.dump"],
            self.app_dir,
        )
        process.run(
            ["docker", "cp", f"{self.mongo_container}:/tmp/jac_db.dump", "jac_db.dump"],
            self.app_dir,
        )
        print("=== Seed dump ready: jac_db.dump ===")

    def _assert_seed_credentials_match_env(self) -> None:
        explicit = self.options.env.get("TEST_USER")
        if not explicit or self.options.env.get("SWEEP_RESEED") == "1":
            return
        try:
            seeded = self.json_file("sweep_seed.json").get("username")
        except FileNotFoundError:
            return
        if seeded and seeded != explicit:
            raise RuntimeError(
                f"TEST_USER={explicit!r} does not match sweep_seed.json username={seeded!r}; "
                "set SWEEP_RESEED=1 to rebuild the dump for a different seeded user."
            )

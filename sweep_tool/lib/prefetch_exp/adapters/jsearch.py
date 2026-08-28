"""JSearch benchmark adapter."""

from __future__ import annotations

from lib.prefetch_exp import process
from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.models import CaseState, RequestSpec


class JSearchAdapter(BenchmarkAdapter):
    config_name = "jac.sweep.toml"
    postgres_container = "jsearch-postgres"
    postgres_uri = "postgresql://jac:jac@localhost:5434/jac_db"
    profile_name = "sweep"
    default_user = "sweep_user"
    default_password = "password"
    credential_source = "seed_sweep_db.py / sweep_seed.json"
    default_query_pool = [
        "database latency cache",
        "database query index",
        "database storage replica",
        "database document shard",
        "postgres query latency",
        "database row query",
        "compiler static analysis",
        "compiler runtime walker",
        "compiler optimizer bytecode",
        "typing source function",
        "program analysis call",
        "runtime walker optimizer",
        "cloud service request",
        "cloud endpoint container",
        "cloud deploy region",
        "autoscale network gateway",
        "trace worker service",
        "container request endpoint",
        "search ranking term",
        "search snippet corpus",
        "bm25 inverted index",
        "document phrase score",
        "ranking token page",
        "corpus search index",
        "security identity token",
        "security audit access",
        "permission session risk",
        "secret encryption policy",
        "login identity session",
        "audit access token",
        "analytics metric dashboard",
        "analytics trend forecast",
        "event segment report",
        "sample model signal",
        "pipeline metric trend",
        "dashboard event forecast",
        "database compiler runtime",
        "cloud security identity",
        "search analytics ranking",
        "cache service pipeline",
        "trace metric request",
        "storage document score",
    ]

    def prepare_sweep(self) -> None:
        self._assert_seed_credentials_match_env()
        if (
            self.options.env.get("SWEEP_RESEED") == "1"
            or not self.dump_exists("jac_db.pgdump")
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
        body = self._body_for_query(query)
        return CaseState(
            token=token,
            request=RequestSpec(
                walker=self.options.env.get("WALKER") or "SearchIndex",
                path=f"/walker/{self.options.env.get('WALKER') or 'SearchIndex'}/{index_id}",
                body=body,
                target_id=index_id,
                request_id=query,
            ),
        )

    def spawn_pool(self, state: CaseState) -> list[RequestSpec]:
        if state.request is None:
            return []
        walker = self.options.env.get("WALKER") or "SearchIndex"
        index_id = state.request.target_id
        return [
            RequestSpec(
                walker=walker,
                path=f"/walker/{walker}/{index_id}",
                body=self._body_for_query(query),
                target_id=index_id,
                request_id=query,
            )
            for query in self._query_pool()
        ]

    def validate_response(self, spec: RequestSpec, payload: dict) -> None:
        reports = payload.get("data", {}).get("reports") or []
        report = reports[0] if reports else {}
        if not report.get("results"):
            print("warning: JSearch returned no results")

    def _body_for_query(self, query: str) -> dict:
        return {
            "query": query,
            "max_results": int(self.options.env.get("JSEARCH_MAX_RESULTS") or "20"),
            "max_pages": int(self.options.env.get("JSEARCH_MAX_PAGES") or "300"),
            "cpu_rounds": int(self.options.env.get("JSEARCH_CPU_ROUNDS") or "500"),
        }

    def _query_pool(self) -> list[str]:
        raw = self.options.env.get("JSEARCH_QUERY_POOL", "").strip()
        if raw:
            queries = [item.strip() for item in raw.replace("\n", "|").split("|")]
            return [query for query in queries if query]
        try:
            seed_query = str(self.json_file("sweep_seed.json").get("query") or "").strip()
        except FileNotFoundError:
            seed_query = ""
        queries: list[str] = []
        for query in [seed_query, *self.default_query_pool]:
            if query and query not in queries:
                queries.append(query)
        return queries

    def _prepare_seed_dump(self) -> None:
        print("=== Preparing JSearch sweep seed dump ===")
        (self.app_dir / self.options.manifest.logs_dir).mkdir(parents=True, exist_ok=True)
        self.compose_down()
        self.compose_up()
        self.drop_jac_db()
        self.stop_stale_servers()

        proc = None
        try:
            proc = self.start_server(self.app_dir / self.options.manifest.logs_dir / "jac_server_seed.log")
            env = {
                **self.options.env,
                "BASE_URL": self.base_url,
                "TEST_USER": self.user_name(),
                "TEST_PASSWORD": self.password(),
                "JAC_DB_URL": self.postgres_uri,
                "POSTGRES_URL": self.postgres_uri,
                "DATABASE_URL": self.postgres_uri,
            }
            process.run([self.options.python_bin, "seed_sweep_db.py"], self.app_dir, env=env)
        finally:
            process.stop_process(proc)
            self.stop_stale_servers()

        self.dump_to_app("jac_db.pgdump")
        print(f"=== Seed dump ready: {self.dump_description('jac_db.pgdump')} ===")

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

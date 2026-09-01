"""JDrive benchmark adapter."""

from __future__ import annotations

import time

from lib.prefetch_exp import process
from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.models import CaseState, RequestSpec


class JDriveAdapter(BenchmarkAdapter):
    config_name = "jac.sweep.toml"
    postgres_container = "jdrive-postgres"
    postgres_uri = "postgresql://jac:jac@localhost:5433/jac_db"
    profile_name = "sweep"
    default_user = "sweep_user"
    default_password = "password"
    credential_source = "seed_sweep_db.py / sweep_seed.json"
    default_dump = "jac_db_50users_same_shape.pgdump"
    default_seed_file = "sweep_seed_50users_same_shape.json"

    def dump_name(self) -> str:
        return self.options.env.get("JDRIVE_DUMP", self.default_dump).strip() or self.default_dump

    def seed_file(self) -> str:
        return (
            self.options.env.get("JDRIVE_SEED_FILE", self.default_seed_file).strip()
            or self.default_seed_file
        )

    def entry_point(self) -> str:
        return "server.jac"

    def restore_dump_if_present(self, dump_name: str = "jac_db.pgdump") -> None:
        super().restore_dump_if_present(self.dump_name())

    def prepare_sweep(self) -> None:
        self._assert_seed_credentials_match_env()
        if (
            self.options.env.get("SWEEP_RESEED") == "1"
            or not self.dump_exists(self.dump_name())
            or not (self.app_dir / self.seed_file()).exists()
            or self._seed_training_root_count() < self._required_training_roots()
        ):
            self._prepare_seed_dump()

    def user_name(self) -> str:
        explicit = self.options.env.get("TEST_USER")
        if explicit:
            return explicit
        try:
            seeded = self.json_file(self.seed_file()).get("username")
        except FileNotFoundError:
            seeded = ""
        return str(seeded or self.default_user)

    def prepare_request(self, policy: str, limit: int) -> CaseState:
        token = self.setup_token(f"jac_server_prepare_{policy}_limit{limit}.log")
        seed = self.json_file(self.seed_file())
        root_id = str(seed["root_id"])
        walker = self.options.env.get("WALKER") or "VisibleFolderTree"
        return CaseState(
            token=token,
            request=RequestSpec(
                walker=walker,
                path=f"/walker/{walker}/{root_id}",
                body={},
                target_id=root_id,
                request_id=root_id,
            ),
            extra={"seed": seed},
        )

    def spawn_pool(self, state: CaseState) -> list[RequestSpec]:
        if state.request is None:
            return []
        seed = state.extra.get("seed") or self.json_file(self.seed_file())
        walker = self.options.env.get("WALKER") or "VisibleFolderTree"
        roots = [str(seed["root_id"])]
        for item in seed.get("training_roots") or []:
            root_id = str(item.get("root_id") or "")
            if root_id:
                roots.append(root_id)
        return [
            RequestSpec(
                walker=walker,
                path=f"/walker/{walker}/{root_id}",
                body={},
                target_id=root_id,
                request_id=root_id,
            )
            for root_id in roots
        ]

    def validate_response(self, spec: RequestSpec, payload: dict) -> None:
        reports = payload.get("data", {}).get("reports") or []
        if not reports:
            raise RuntimeError("JDrive VisibleFolderTree returned no reports")
        entries = reports[0].get("entries") or []

        try:
            seed = self.json_file(self.seed_file())
        except FileNotFoundError:
            return

        expected_by_root = {
            str(seed.get("root_id")): int(seed.get("expected_visible_entries") or 0)
        }
        for item in seed.get("training_roots") or []:
            root_id = str(item.get("root_id") or "")
            if root_id:
                expected_by_root[root_id] = int(item.get("expected_visible_entries") or 0)

        expected = expected_by_root.get(spec.target_id)
        if expected and len(entries) != expected:
            raise RuntimeError(
                f"JDrive VisibleFolderTree({spec.target_id}) returned {len(entries)} "
                f"entries, expected {expected}"
            )

    def _prepare_seed_dump(self) -> None:
        print("=== Preparing JDrive sweep seed dump ===")
        (self.app_dir / self.options.manifest.logs_dir).mkdir(parents=True, exist_ok=True)
        self.compose_down()
        self.compose_up()
        time.sleep(5)
        self.drop_jac_db()
        self.stop_stale_servers()

        proc = None
        try:
            proc = self.start_server(
                self.app_dir / self.options.manifest.logs_dir / "jac_server_seed.log"
            )
            env = {
                **self.options.env,
                "BASE_URL": self.base_url,
                "TEST_USER": self.user_name(),
                "TEST_PASSWORD": self.password(),
                "JAC_DB_URL": self.postgres_uri,
                "POSTGRES_URL": self.postgres_uri,
                "DATABASE_URL": self.postgres_uri,
                "SWEEP_SEED_TRAIN_ROOTS": str(self._seed_train_roots_to_create()),
            }
            process.run([self.options.python_bin, "seed_sweep_db.py"], self.app_dir, env=env)
        finally:
            process.stop_process(proc)
            self.stop_stale_servers()

        dump_name = self.dump_name()
        self.dump_to_app(dump_name)
        print(f"=== Seed dump ready: {self.dump_description(dump_name)} ===")

    def _assert_seed_credentials_match_env(self) -> None:
        explicit = self.options.env.get("TEST_USER")
        if not explicit or self.options.env.get("SWEEP_RESEED") == "1":
            return
        try:
            seeded = self.json_file(self.seed_file()).get("username")
        except FileNotFoundError:
            return
        if seeded and seeded != explicit:
            raise RuntimeError(
                f"TEST_USER={explicit!r} does not match {self.seed_file()} username={seeded!r}; "
                "set SWEEP_RESEED=1 to rebuild the dump for a different seeded user."
            )

    def _required_training_roots(self) -> int:
        requested = [0]
        if any(policy.startswith("markov1-pooled") for policy in self.options.policies):
            requested.extend(self.options.markov_train_ns)
        if any(policy.startswith("coaccess-pooled") for policy in self.options.policies):
            requested.extend(self.options.coaccess_train_ns)
        return max(requested)

    def _seed_train_roots_to_create(self) -> int:
        try:
            configured = int(self.options.env.get("SWEEP_SEED_TRAIN_ROOTS") or "0")
        except ValueError as exc:
            raise ValueError(
                "SWEEP_SEED_TRAIN_ROOTS must be an integer, got "
                f"{self.options.env.get('SWEEP_SEED_TRAIN_ROOTS')!r}"
            ) from exc
        return max(configured, self._required_training_roots())

    def _seed_training_root_count(self) -> int:
        try:
            seed = self.json_file(self.seed_file())
        except FileNotFoundError:
            return 0
        return len(seed.get("training_roots") or [])

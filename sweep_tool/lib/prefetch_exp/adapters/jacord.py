"""Jacord benchmark adapter."""

from __future__ import annotations

from lib.prefetch_exp import process
from lib.prefetch_exp.adapters.base import BenchmarkAdapter
from lib.prefetch_exp.models import CaseState, RequestSpec


class JacordAdapter(BenchmarkAdapter):
    default_user = "user_0000"
    default_password = "password"
    credential_source = "bootstrap.py primary benchmark user"
    default_dump = "jac_db.dump"
    legacy_dump_aliases = {"dumps/big.dump"}
    default_channel_scan_limit = 1000
    default_min_channel_messages = 1000

    def __init__(self, options):
        super().__init__(options)
        self._selected_channel_id = ""
        self._selected_channel_messages = -1
        self._restored_dump = ""

    def restore_dump_if_present(self, dump_name: str = "jac_db.dump") -> None:
        configured = self._configured_dump()
        self.options.env["JACORD_DUMP"] = configured
        if not self.dump_exists(configured):
            raise FileNotFoundError(
                "Configured Jacord dump does not exist: "
                f"{self.dump_description(configured)}. Set JACORD_DUMP to a valid dump; the Jacord "
                "sweep will not silently fall back to jac_db.dump."
            )

        resolved = self.dump_description(configured)
        if resolved != self._restored_dump:
            self._selected_channel_id = ""
            self._selected_channel_messages = -1
            self._restored_dump = resolved

        print(
            "=== Jacord restoring configured dump: "
            f"{configured} -> {resolved} ==="
        )
        super().restore_dump_if_present(configured)

    def prepare_request(self, policy: str, limit: int) -> CaseState:
        proc = None
        token = ""
        channel_id = ""
        try:
            proc = self.start_server(
                self.app_dir / self.options.manifest.logs_dir / f"jac_server_prepare_{policy}_limit{limit}.log"
            )
            token = self.login()
            if self._selected_channel_id:
                channel_id = self._selected_channel_id
                print(
                    "=== Jacord reusing selected channel: "
                    f"{channel_id} ({self._selected_channel_messages} messages) ==="
                )
            else:
                channel_id = self._select_channel(token)
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
                request_id=channel_id,
            ),
        )

    def spawn_pool(self, state: CaseState) -> list[RequestSpec]:
        walker = self.options.env.get("WALKER") or "load_channel"
        desired = self._int_env(
            "SWEEP_MARKOV_POOL_SIZE",
            max(max(self.options.markov_train_ns), max(self.options.coaccess_train_ns)) + 1,
        )
        scan_limit = max(self._int_env("JACORD_CHANNEL_SCAN_LIMIT", self.default_channel_scan_limit), desired)
        proc = None
        try:
            proc = self.start_server(
                self.app_dir / self.options.manifest.logs_dir / "jac_server_markov_pool_channels.log"
            )
            token = state.token or self.login()
            resp = self.post("/walker/ListChannelIds", {"limit": scan_limit}, token=token)
            reports = self._reports_or_raise(resp, "Jacord ListChannelIds")
            ids = [str(x) for x in (reports[0] if reports else [])]
            specs: list[RequestSpec] = []
            for channel_id in ids:
                if len(specs) >= desired:
                    break
                message_count = self._count_channel_messages(walker, channel_id, token)
                try:
                    self._validate_channel_size(channel_id, message_count)
                except RuntimeError:
                    continue
                specs.append(
                    RequestSpec(
                        walker=walker,
                        path=f"/walker/{walker}/{channel_id}",
                        body={},
                        target_id=channel_id,
                        request_id=channel_id,
                    )
                )
        finally:
            process.stop_process(proc)
            self.stop_stale_servers()
        return specs or super().spawn_pool(state)

    def _select_channel(self, token: str) -> str:
        explicit = self.options.env.get("JACORD_CHANNEL_ID", "").strip()
        walker = self.options.env.get("WALKER") or "load_channel"
        if explicit:
            message_count = self._count_channel_messages(walker, explicit, token)
            self._validate_channel_size(explicit, message_count)
            self._selected_channel_id = explicit
            self._selected_channel_messages = message_count
            print(
                "=== Jacord using configured channel: "
                f"{explicit} ({message_count} messages) ==="
            )
            return explicit

        scan_limit = self._int_env("JACORD_CHANNEL_SCAN_LIMIT", self.default_channel_scan_limit)
        resp = self.post("/walker/ListChannelIds", {"limit": scan_limit}, token=token)
        reports = self._reports_or_raise(resp, "Jacord ListChannelIds")
        ids = [str(x) for x in (reports[0] if reports else [])]
        if not ids:
            raise RuntimeError("Jacord ListChannelIds returned no channel IDs")

        pick_mode = (self.options.env.get("JACORD_CHANNEL_PICK") or "first").strip().lower()
        if pick_mode == "first":
            channel_id = ids[0]
            message_count = self._count_channel_messages(walker, channel_id, token)
        elif pick_mode == "lexicographic":
            channel_id = sorted(ids)[0]
            message_count = self._count_channel_messages(walker, channel_id, token)
        elif pick_mode == "largest":
            channel_id, message_count = self._largest_channel(walker, ids, token)
        else:
            raise ValueError(
                "Unsupported JACORD_CHANNEL_PICK="
                f"{pick_mode!r}; use 'largest' or 'first'."
            )

        self._validate_channel_size(channel_id, message_count)
        self._selected_channel_id = channel_id
        self._selected_channel_messages = message_count
        print(
            "=== Jacord selected channel: "
            f"{channel_id} ({message_count} messages, mode={pick_mode}, "
            f"candidates={len(ids)}) ==="
        )
        return channel_id

    def _largest_channel(self, walker: str, ids: list[str], token: str) -> tuple[str, int]:
        best_id = ""
        best_count = -1
        for channel_id in sorted(ids):
            count = self._count_channel_messages(walker, channel_id, token)
            if count > best_count:
                best_id = channel_id
                best_count = count
        return best_id, best_count

    def _count_channel_messages(self, walker: str, channel_id: str, token: str) -> int:
        resp = self.post(f"/walker/{walker}/{channel_id}", {}, token=token)
        reports = self._reports_or_raise(resp, f"Jacord {walker}({channel_id})")
        return len(reports)

    def _reports_or_raise(self, resp, context: str) -> list:
        body = resp.body.decode("utf-8", errors="replace")[:500]
        if resp.status >= 400:
            raise RuntimeError(f"{context} failed: HTTP {resp.status} {body}")
        try:
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"{context} returned non-JSON HTTP {resp.status}: {body}"
            ) from exc
        if data.get("error"):
            raise RuntimeError(f"{context} returned error: {data.get('error')}")
        payload = data.get("data")
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"{context} returned invalid payload HTTP {resp.status}: {body}"
            )
        return payload.get("reports") or []

    def _validate_channel_size(self, channel_id: str, message_count: int) -> None:
        min_messages = self._int_env(
            "JACORD_MIN_CHANNEL_MESSAGES", self.default_min_channel_messages
        )
        if min_messages <= 0 or message_count >= min_messages:
            return
        raise RuntimeError(
            "Jacord selected channel is too small for the Jacord benchmark: "
            f"{channel_id} has {message_count} messages, expected at least "
            f"{min_messages}. Confirm JACORD_DUMP={self.options.env.get('JACORD_DUMP') or self.default_dump!r} "
            "or set JACORD_CHANNEL_ID to the intended large channel."
        )

    def _int_env(self, name: str, default: int) -> int:
        raw = self.options.env.get(name, "")
        if raw == "":
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer, got {raw!r}") from exc

    def _configured_dump(self) -> str:
        configured = (self.options.env.get("JACORD_DUMP") or self.default_dump).strip()
        if not configured:
            return self.default_dump
        if configured in self.legacy_dump_aliases:
            print(
                "=== Jacord ignoring stale JACORD_DUMP="
                f"{configured}; using {self.default_dump} ==="
            )
            return self.default_dump
        return configured

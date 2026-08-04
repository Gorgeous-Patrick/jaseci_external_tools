"""HTTP client for the littlex5 Jac server."""

import sys

import requests


class LittlexAPI:
    def __init__(self, base_url: str = "localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"http://{self.base_url}{path}"

    @staticmethod
    def _reports(resp) -> list:
        """Extract data.reports from a walker response.

        Unlike a bare `.get(...).get(...)`, this does not throw on error
        envelopes ({"ok": false, "data": null}), non-JSON bodies, or timeouts
        -- but it does NOT swallow them silently: every bad/error response is
        logged to stderr (endpoint + HTTP status + error) so failures during a
        long unattended seed are visible. Returns [] so the run continues.
        """
        try:
            op = resp.request.path_url
        except Exception:
            op = "?"
        try:
            body = resp.json()
        except Exception as e:
            print(
                f"[api] {op}: non-JSON response (HTTP {resp.status_code}): "
                f"{resp.text[:200]!r} ({e})",
                file=sys.stderr,
            )
            return []
        if not isinstance(body, dict):
            print(
                f"[api] {op}: unexpected JSON {type(body).__name__}: "
                f"{str(body)[:200]}",
                file=sys.stderr,
            )
            return []
        data = body.get("data")
        if not isinstance(data, dict):
            print(
                f"[api] {op}: error response (HTTP {resp.status_code}): "
                f"data={data!r} error={body.get('error')}",
                file=sys.stderr,
            )
            return []
        reports = data.get("reports", [])
        return reports if isinstance(reports, list) else []

    def register(self, username: str, password: str) -> None:
        self.session.post(
            self._url("/user/register"),
            json={
                "identities": [{"type": "username", "value": username}],
                "credential": {"type": "password", "password": password},
            },
        )

    def login(self, username: str, password: str) -> str:
        resp = self.session.post(
            self._url("/user/login"),
            json={
                "identity": {"type": "username", "value": username},
                "credential": {"type": "password", "password": password},
            },
        )
        data = resp.json()
        token = data.get("data", {}).get("token", "")
        if not token:
            raise RuntimeError(f"Login failed for {username}: {data}")
        return token

    def setup_profile(self, token: str, username: str, bio: str) -> dict:
        resp = self.session.post(
            self._url("/walker/setup_profile"),
            json={"username": username, "bio": bio},
            headers={"Authorization": f"Bearer {token}"},
        )
        reports = self._reports(resp)
        return reports[0] if reports else {}

    def create_tweet(self, token: str, content: str) -> dict:
        resp = self.session.post(
            self._url("/walker/create_tweet"),
            json={"content": content},
            headers={"Authorization": f"Bearer {token}"},
        )
        reports = self._reports(resp)
        return reports[0] if reports else {}

    def follow_user(self, token: str, target_id: str) -> dict:
        resp = self.session.post(
            self._url("/walker/follow_user"),
            json={"target_id": target_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        reports = self._reports(resp)
        return reports[0] if reports else {}

    def get_all_profiles(self, token: str) -> list[dict]:
        resp = self.session.post(
            self._url("/walker/get_all_profiles"),
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        reports = self._reports(resp)
        return reports[0] if reports else []

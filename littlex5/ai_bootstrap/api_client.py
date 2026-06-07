"""HTTP client for the littlex5 Jac server."""

import requests


class LittlexAPI:
    def __init__(self, base_url: str = "localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"http://{self.base_url}{path}"

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
        reports = resp.json().get("data", {}).get("reports", [])
        return reports[0] if reports else {}

    def create_tweet(self, token: str, content: str) -> dict:
        resp = self.session.post(
            self._url("/walker/create_tweet"),
            json={"content": content},
            headers={"Authorization": f"Bearer {token}"},
        )
        reports = resp.json().get("data", {}).get("reports", [])
        return reports[0] if reports else {}

    def follow_user(self, token: str, target_id: str) -> dict:
        resp = self.session.post(
            self._url("/walker/follow_user"),
            json={"target_id": target_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        reports = resp.json().get("data", {}).get("reports", [])
        return reports[0] if reports else {}

    def get_all_profiles(self, token: str) -> list[dict]:
        resp = self.session.post(
            self._url("/walker/get_all_profiles"),
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        reports = resp.json().get("data", {}).get("reports", [])
        return reports[0] if reports else []

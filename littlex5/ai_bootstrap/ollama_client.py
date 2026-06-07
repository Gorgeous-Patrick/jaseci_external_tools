"""Thin wrapper around the Ollama HTTP API."""

import requests


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, temperature: float = 0.8, max_tokens: int = 256) -> str:
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()

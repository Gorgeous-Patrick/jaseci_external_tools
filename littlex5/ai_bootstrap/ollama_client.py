"""Thin wrapper around the Ollama HTTP API."""

import sys
import time

import requests

# Per-call resilience budget: retry with backoff on network errors for up to
# this many seconds, then give up and return "" so the caller's fallback
# (template bio / random follows) kicks in. Keeps an unattended seed alive
# across a flaky link without hanging for hours on a sustained outage.
_RETRY_BUDGET_S = 30.0


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def generate(self, prompt: str, temperature: float = 0.8, max_tokens: int = 256) -> str:
        start = time.monotonic()
        delay = 2.0
        attempt = 0
        while True:
            attempt += 1
            try:
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
            except Exception as e:
                elapsed = time.monotonic() - start
                if elapsed >= _RETRY_BUDGET_S:
                    # Logged, not swallowed: caller falls back and continues.
                    print(
                        f"[ollama] giving up after {attempt} attempt(s) / "
                        f"{elapsed:.0f}s ({type(e).__name__}: {e}); using fallback",
                        file=sys.stderr,
                    )
                    return ""
                print(
                    f"[ollama] attempt {attempt} failed ({type(e).__name__}: {e}); "
                    f"retrying in {delay:.0f}s",
                    file=sys.stderr,
                )
                time.sleep(delay)
                delay = min(delay * 2, 15.0)

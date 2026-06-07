"""Generate and manage a reusable pool of AI-generated tweets."""

import json
import random
import re
from pathlib import Path

from .ollama_client import OllamaClient

POOL_PROMPT = """\
Generate exactly {batch_size} unique, creative tweets for a Twitter-like social platform.
Each tweet should be max 280 characters. Cover diverse topics: tech, daily life, opinions, \
humor, observations, questions, announcements. Mix tones: casual, enthusiastic, reflective, witty.
{theme_hint}
Output each tweet on its own line, prefixed with a number and period (e.g. "1. tweet here").
No other text."""

THEMED_HINTS = [
    "Focus on: software development, coding, open source, debugging stories.",
    "Focus on: AI, machine learning, automation, future of work.",
    "Focus on: daily life, coffee, morning routines, productivity tips.",
    "Focus on: hot takes, unpopular opinions, controversial tech views.",
    "Focus on: gratitude, milestones, celebrations, community.",
    "Focus on: learning new things, book recommendations, courses, TILs.",
    "Focus on: fitness, health, work-life balance, mental wellness.",
    "Focus on: food, cooking, restaurants, travel experiences.",
    "Focus on: music, movies, games, creative hobbies.",
    "Focus on: startups, entrepreneurship, side projects, launches.",
    "Focus on: graphs, databases, distributed systems, infrastructure.",
    "Focus on: web development, frontend, design, UX opinions.",
    "Focus on: crypto, blockchain, decentralization, web3.",
    "Focus on: science, space, physics, nature, environment.",
    "Focus on: memes, internet culture, trending topics, humor.",
]


class TweetPool:
    def __init__(self, ollama: OllamaClient):
        self.ollama = ollama
        self.tweets: list[str] = []

    def generate(self, pool_size: int, batch_size: int = 20) -> list[str]:
        """Generate a pool of tweets via repeated batch calls to Ollama."""
        self.tweets = []
        batches_needed = (pool_size + batch_size - 1) // batch_size

        print(f"Generating tweet pool: {pool_size} tweets in {batches_needed} batches...")

        for i in range(batches_needed):
            theme = THEMED_HINTS[i % len(THEMED_HINTS)]
            prompt = POOL_PROMPT.format(batch_size=batch_size, theme_hint=theme)

            response = self.ollama.generate(
                prompt, temperature=1.0, max_tokens=batch_size * 80
            )

            batch = self._parse_tweets(response)
            self.tweets.extend(batch)
            print(f"  Batch {i+1}/{batches_needed}: got {len(batch)} tweets "
                  f"(pool total: {len(self.tweets)})")

            if len(self.tweets) >= pool_size:
                break

        self.tweets = self.tweets[:pool_size]
        print(f"Tweet pool ready: {len(self.tweets)} tweets")
        return self.tweets

    def _parse_tweets(self, response: str) -> list[str]:
        tweets = []
        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
            # Skip lines that look like meta-text rather than tweets
            if cleaned and len(cleaned) <= 280 and len(cleaned) > 10:
                tweets.append(cleaned)
        return tweets

    def sample(self, count: int) -> list[str]:
        """Randomly sample tweets from the pool (with replacement if needed)."""
        if not self.tweets:
            return [f"Hello world! #{random.randint(1,9999)}" for _ in range(count)]
        if count <= len(self.tweets):
            return random.sample(self.tweets, count)
        # With replacement for large counts
        return [random.choice(self.tweets) for _ in range(count)]

    def save(self, path: str) -> None:
        """Save pool to disk for reuse across runs."""
        Path(path).write_text(json.dumps(self.tweets, indent=2))
        print(f"Saved pool ({len(self.tweets)} tweets) to {path}")

    def load(self, path: str) -> bool:
        """Load pool from disk. Returns True if successful."""
        p = Path(path)
        if not p.exists():
            return False
        self.tweets = json.loads(p.read_text())
        print(f"Loaded pool ({len(self.tweets)} tweets) from {path}")
        return True

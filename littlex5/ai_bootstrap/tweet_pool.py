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
    def __init__(self, ollama: OllamaClient, save_path: str = "tweet_pool.json"):
        self.ollama = ollama
        self.tweets: list[str] = []
        self.save_path = save_path

    def generate(self, pool_size: int, batch_size: int = 20) -> list[str]:
        """Generate tweets until the pool has at least pool_size entries.

        - Never truncates or removes existing tweets.
        - Appends new tweets and saves after each batch.
        - If the file already has >= pool_size tweets, does nothing.
        """
        # Load existing pool (never discard anything)
        p = Path(self.save_path)
        if p.exists():
            self.tweets = json.loads(p.read_text())
            if len(self.tweets) >= pool_size:
                print(f"Pool already has {len(self.tweets)} tweets (>= {pool_size}) at {self.save_path}")
                return self.tweets
            print(f"Resuming pool generation from {len(self.tweets)}/{pool_size} tweets")
        else:
            self.tweets = []

        remaining = pool_size - len(self.tweets)
        batches_needed = (remaining + batch_size - 1) // batch_size

        print(f"Generating {remaining} more tweets in {batches_needed} batches...")

        for i in range(batches_needed):
            theme = THEMED_HINTS[(len(self.tweets) // batch_size) % len(THEMED_HINTS)]
            prompt = POOL_PROMPT.format(batch_size=batch_size, theme_hint=theme)

            response = self.ollama.generate(
                prompt, temperature=1.0, max_tokens=batch_size * 80
            )

            batch = self._parse_tweets(response)
            self.tweets.extend(batch)

            # Save after every batch (append-only, never truncate)
            self._save()

            print(f"  Batch {i+1}/{batches_needed}: got {len(batch)} tweets "
                  f"(pool total: {len(self.tweets)})")

            if len(self.tweets) >= pool_size:
                break

        print(f"Tweet pool ready: {len(self.tweets)} tweets")
        return self.tweets

    def _save(self) -> None:
        """Write current pool to disk. Only adds — never called after removals."""
        Path(self.save_path).write_text(json.dumps(self.tweets, indent=2))

    def _parse_tweets(self, response: str) -> list[str]:
        tweets = []
        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
            if not cleaned or len(cleaned) > 280 or len(cleaned) <= 10:
                continue
            # Skip only obvious preamble (exact patterns)
            if re.match(r"^here are .*\d+.*tweets", cleaned, re.IGNORECASE):
                continue
            tweets.append(cleaned)
        return tweets

    def clean(self) -> int:
        """Remove meta-lines from the pool. Only called via --clean-pool.

        Uses a narrow regex to only catch obvious LLM preamble like:
        "Here are the 20 unique tweets:" / "Here are 20 tweets for you:"
        """
        before = len(self.tweets)
        self.tweets = [
            t for t in self.tweets
            if not re.match(r"^here are .*\d+.*tweets", t, re.IGNORECASE)
        ]
        removed = before - len(self.tweets)
        if removed:
            self._save()
            print(f"Cleaned pool: removed {removed} meta-lines ({len(self.tweets)} remaining)")
        else:
            print("Nothing to clean.")
        return removed

    def sample(self, count: int) -> list[str]:
        """Randomly sample tweets from the pool (with replacement if needed)."""
        if not self.tweets:
            return [f"Hello world! #{random.randint(1,9999)}" for _ in range(count)]
        if count <= len(self.tweets):
            return random.sample(self.tweets, count)
        # With replacement for large counts
        return [random.choice(self.tweets) for _ in range(count)]


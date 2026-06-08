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
        """Generate a pool of tweets via repeated batch calls to Ollama.

        Saves incrementally after each batch so progress survives interruptions.
        If a partial pool file already exists, resumes from where it left off.
        """
        # Resume from partial pool if it exists
        p = Path(self.save_path)
        if p.exists():
            existing = json.loads(p.read_text())
            if len(existing) >= pool_size:
                self.tweets = existing[:pool_size]
                print(f"Pool already complete ({len(self.tweets)} tweets) at {self.save_path}")
                return self.tweets
            self.tweets = existing
            print(f"Resuming pool generation from {len(self.tweets)}/{pool_size} tweets")
        else:
            self.tweets = []

        remaining = pool_size - len(self.tweets)
        batches_needed = (remaining + batch_size - 1) // batch_size

        print(f"Generating tweet pool: {remaining} more tweets in {batches_needed} batches...")

        for i in range(batches_needed):
            theme = THEMED_HINTS[(len(self.tweets) // batch_size) % len(THEMED_HINTS)]
            prompt = POOL_PROMPT.format(batch_size=batch_size, theme_hint=theme)

            response = self.ollama.generate(
                prompt, temperature=1.0, max_tokens=batch_size * 80
            )

            batch = self._parse_tweets(response)
            self.tweets.extend(batch)

            # Save after every batch
            self._save_incremental()

            print(f"  Batch {i+1}/{batches_needed}: got {len(batch)} tweets "
                  f"(pool total: {len(self.tweets)})")

            if len(self.tweets) >= pool_size:
                break

        self.tweets = self.tweets[:pool_size]
        self._save_incremental()
        print(f"Tweet pool ready: {len(self.tweets)} tweets")
        return self.tweets

    def _save_incremental(self) -> None:
        Path(self.save_path).write_text(json.dumps(self.tweets, indent=2))

    def _is_meta_line(self, text: str) -> bool:
        """Detect preamble/meta lines the model outputs instead of actual tweets."""
        lower = text.lower()
        meta_patterns = [
            "here are",
            "here's",
            "sure,",
            "sure!",
            "certainly",
            "of course",
            "i'll",
            "i will",
            "below are",
            "the following",
            "unique tweets",
            "short tweets",
            "tweets for",
            "as requested",
            "let me",
        ]
        return any(lower.startswith(p) or p in lower[:50] for p in meta_patterns)

    def _parse_tweets(self, response: str) -> list[str]:
        tweets = []
        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
            if not cleaned or len(cleaned) > 280 or len(cleaned) <= 10:
                continue
            if self._is_meta_line(cleaned):
                continue
            tweets.append(cleaned)
        return tweets

    def clean(self) -> int:
        """Remove meta-lines from an already-generated pool. Returns count removed."""
        before = len(self.tweets)
        self.tweets = [t for t in self.tweets if not self._is_meta_line(t)]
        removed = before - len(self.tweets)
        if removed:
            self._save_incremental()
            print(f"Cleaned pool: removed {removed} meta-lines ({len(self.tweets)} remaining)")
        return removed

    def sample(self, count: int) -> list[str]:
        """Randomly sample tweets from the pool (with replacement if needed)."""
        if not self.tweets:
            return [f"Hello world! #{random.randint(1,9999)}" for _ in range(count)]
        if count <= len(self.tweets):
            return random.sample(self.tweets, count)
        # With replacement for large counts
        return [random.choice(self.tweets) for _ in range(count)]


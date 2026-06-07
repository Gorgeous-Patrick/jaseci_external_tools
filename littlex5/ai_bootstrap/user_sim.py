"""AI-driven user simulation logic."""

import random
import re

from .ollama_client import OllamaClient
from .api_client import LittlexAPI


PERSONA_PROMPT = """\
You are generating a short social media bio for a fictional user named "{username}".
The bio should be 1-2 sentences, creative, and reflect a unique personality.
Only output the bio text, nothing else."""

TWEET_PROMPT = """\
You are "{username}" (bio: "{bio}") posting on a Twitter-like platform.
Write a single short tweet (max 280 chars). Be creative, authentic to the persona.
{context}
Only output the tweet text, nothing else."""

TWEET_BATCH_PROMPT = """\
You are "{username}" (bio: "{bio}") posting on a Twitter-like platform.
Write exactly {batch_size} unique short tweets (each max 280 chars). Be creative, varied, \
and authentic to the persona. Cover different topics and moods.
{context}
Output each tweet on its own line, prefixed with a number and period (e.g. "1. tweet here").
No other text."""

FOLLOW_PROMPT = """\
You are "{username}" (bio: "{bio}").
Below is a list of other users on the platform. Pick exactly {k} users you'd most \
want to follow based on shared interests or complementary personas.

Users:
{user_list}

Reply with ONLY the usernames you want to follow, one per line. No numbering or explanation."""


class UserSimulator:
    def __init__(self, ollama: OllamaClient, api: LittlexAPI, password: str = "password"):
        self.ollama = ollama
        self.api = api
        self.password = password

    def generate_bio(self, username: str) -> str:
        prompt = PERSONA_PROMPT.format(username=username)
        bio = self.ollama.generate(prompt, temperature=0.9, max_tokens=100)
        # Truncate if too long
        return bio[:200] if bio else f"Hi, I'm {username}!"

    def generate_tweet(self, username: str, bio: str, previous_tweets: list[str]) -> str:
        context = ""
        if previous_tweets:
            recent = previous_tweets[-3:]
            context = "Your recent tweets for context (don't repeat):\n" + "\n".join(
                f"- {t}" for t in recent
            )
        prompt = TWEET_PROMPT.format(username=username, bio=bio, context=context)
        tweet = self.ollama.generate(prompt, temperature=0.9, max_tokens=100)
        # Ensure within tweet length
        return tweet[:280] if tweet else f"Hello from {username}!"

    def choose_follows(
        self, username: str, bio: str, candidates: list[dict], k: int
    ) -> list[str]:
        if not candidates or k <= 0:
            return []

        # Don't include self in candidates
        filtered = [u for u in candidates if u["username"] != username]
        if not filtered:
            return []

        # If fewer candidates than k, follow all
        if len(filtered) <= k:
            return [u["username"] for u in filtered]

        user_list = "\n".join(
            f"- {u['username']}: {u.get('bio', '')}" for u in filtered
        )
        prompt = FOLLOW_PROMPT.format(
            username=username, bio=bio, k=k, user_list=user_list
        )
        response = self.ollama.generate(prompt, temperature=0.3, max_tokens=200)

        # Parse usernames from response
        chosen = []
        valid_usernames = {u["username"] for u in filtered}
        for line in response.splitlines():
            name = line.strip().lstrip("-•* ").strip()
            if name in valid_usernames:
                chosen.append(name)

        # If AI didn't return enough valid names, fill randomly
        if len(chosen) < k:
            remaining = [u for u in valid_usernames if u not in chosen]
            needed = min(k - len(chosen), len(remaining))
            chosen.extend(random.sample(list(remaining), needed))

        return chosen[:k]

    def register_user(self, username: str) -> str:
        self.api.register(username, self.password)
        return self.api.login(username, self.password)

    def setup_user_profile(self, token: str, username: str) -> tuple[str, str]:
        bio = self.generate_bio(username)
        profile = self.api.setup_profile(token, username, bio)
        profile_id = profile.get("id", "")
        return profile_id, bio

    def generate_tweet_batch(self, username: str, bio: str, batch_size: int, previous_tweets: list[str]) -> list[str]:
        context = ""
        if previous_tweets:
            recent = previous_tweets[-5:]
            context = "Some of your previous tweets (don't repeat themes):\n" + "\n".join(
                f"- {t}" for t in recent
            )
        prompt = TWEET_BATCH_PROMPT.format(
            username=username, bio=bio, batch_size=batch_size, context=context
        )
        response = self.ollama.generate(prompt, temperature=0.9, max_tokens=batch_size * 80)

        tweets = []
        for line in response.splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip "1. ", "2. " etc. prefixes
            cleaned = re.sub(r"^\d+[\.\)]\s*", "", line)
            if cleaned and len(cleaned) <= 280:
                tweets.append(cleaned)
        return tweets

    def create_tweets(self, token: str, username: str, bio: str, count: int, batch_size: int = 10) -> list[str]:
        tweets = []
        remaining = count
        while remaining > 0:
            chunk = min(remaining, batch_size)
            if chunk >= 3:
                batch = self.generate_tweet_batch(username, bio, chunk, tweets)
                # If batch generation fails or returns too few, fall back one-by-one
                if len(batch) < chunk // 2:
                    for _ in range(chunk):
                        content = self.generate_tweet(username, bio, tweets)
                        self.api.create_tweet(token, content)
                        tweets.append(content)
                else:
                    for content in batch[:chunk]:
                        self.api.create_tweet(token, content)
                        tweets.append(content)
            else:
                for _ in range(chunk):
                    content = self.generate_tweet(username, bio, tweets)
                    self.api.create_tweet(token, content)
                    tweets.append(content)
            remaining -= chunk
        return tweets

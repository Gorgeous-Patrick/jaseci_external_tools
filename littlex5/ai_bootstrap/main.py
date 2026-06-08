#!/usr/bin/env python3
"""AI-driven bootstrap for littlex5.

Simulates N users, each creating M tweets and following K others.
Tweet content comes from a shared AI-generated pool (generated once, reused across users).
Follow decisions are AI-driven per user.

Usage:
    python -m ai_bootstrap \
        --users 5000 \
        --tweets-per-user 200 \
        --follows-per-user 50 \
        --pool-size 3000 \
        --ollama-url http://localhost:11434 \
        --ollama-model llama3 \
        --server-url localhost:8000
"""

import argparse
import random
import sys

from .ollama_client import OllamaClient
from .api_client import LittlexAPI
from .tweet_pool import TweetPool
from .user_sim import UserSimulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-driven littlex5 user simulator"
    )
    parser.add_argument("-n", "--users", type=int, default=10,
                        help="Number of users to simulate (default: 10)")
    parser.add_argument("-m", "--tweets-per-user", type=int, default=5,
                        help="Tweets per user (default: 5)")
    parser.add_argument("-k", "--follows-per-user", type=int, default=3,
                        help="Users to follow per user (default: 3)")
    parser.add_argument("--server-url", default="localhost:8000",
                        help="littlex5 server URL (default: localhost:8000)")
    parser.add_argument("--password", default="password",
                        help="Password for all simulated users (default: password)")
    # Ollama params
    parser.add_argument("--ollama-url", default="http://localhost:11434",
                        help="Ollama API base URL (default: http://localhost:11434)")
    parser.add_argument("--ollama-model", default="llama3",
                        help="Ollama model to use (default: llama3)")
    # Pool params
    parser.add_argument("--pool-size", type=int, default=2000,
                        help="Number of tweets in the shared pool (default: 2000)")
    parser.add_argument("--pool-batch-size", type=int, default=20,
                        help="Tweets generated per Ollama call for pool (default: 20)")
    parser.add_argument("--pool-file", default="tweet_pool.json",
                        help="Path to save/load tweet pool JSON (default: tweet_pool.json)")
    parser.add_argument("--generate-pool-only", action="store_true",
                        help="Only generate the tweet pool and exit (no user simulation)")
    parser.add_argument("--clean-pool", action="store_true",
                        help="Remove meta-lines (e.g. 'Here are 20 tweets:') from pool and exit")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    ollama = OllamaClient(base_url=args.ollama_url, model=args.ollama_model)
    api = LittlexAPI(base_url=args.server_url)
    sim = UserSimulator(ollama=ollama, api=api, password=args.password)
    pool = TweetPool(ollama=ollama, save_path=args.pool_file)

    n_users = args.users
    m_tweets = args.tweets_per_user
    k_follows = args.follows_per_user

    pool_calls = (args.pool_size + args.pool_batch_size - 1) // args.pool_batch_size
    follow_calls = n_users
    bio_calls = n_users

    print(f"Config: {n_users} users, {m_tweets} tweets/user, {k_follows} follows/user")
    print(f"Ollama: {args.ollama_url} model={args.ollama_model}")
    print(f"Server: {args.server_url}")
    print(f"Pool: {args.pool_size} tweets ({pool_calls} Ollama calls to generate)")
    print(f"Estimated total Ollama calls: ~{pool_calls + bio_calls + follow_calls}")
    print()

    # Clean existing pool if requested (the ONLY way to remove tweets)
    if args.clean_pool:
        pool.generate(args.pool_size, batch_size=args.pool_batch_size)
        pool.clean()
        return

    # Phase 0: Generate or load/resume tweet pool (never removes anything)
    pool.generate(args.pool_size, batch_size=args.pool_batch_size)
    print()

    if args.generate_pool_only:
        print("Pool generated. Exiting (--generate-pool-only).")
        return

    # Phase 1: Register users, set up profiles, assign tweets from pool
    users: list[dict] = []

    for i in range(n_users):
        username = f"sim_user_{i}"
        if (i + 1) % 100 == 0 or i == 0:
            print(f"[{i+1}/{n_users}] Creating users...")

        try:
            token = sim.register_user(username)
        except RuntimeError as e:
            print(f"  ERROR registering {username}: {e}", file=sys.stderr)
            continue

        profile_id, bio = sim.setup_user_profile(token, username)

        # Sample tweets from pool and post them
        tweet_texts = pool.sample(m_tweets)
        for content in tweet_texts:
            api.create_tweet(token, content)

        users.append({
            "username": username,
            "token": token,
            "profile_id": profile_id,
            "bio": bio,
        })

        if (i + 1) % 100 == 0:
            print(f"  ...{i+1}/{n_users} users done ({len(users)} successful)")

    print(f"\nPhase 1 complete: {len(users)} users with {m_tweets} tweets each\n")

    if len(users) < 2:
        print("Not enough users to establish follow relationships.")
        return

    # Phase 2: AI-driven follow decisions
    print("Phase 2: Establishing follow relationships...")

    candidates = [{"username": u["username"], "bio": u["bio"]} for u in users]
    profile_map = {u["username"]: u["profile_id"] for u in users}
    total_follows = 0

    for i, user in enumerate(users):
        chosen = sim.choose_follows(
            user["username"], user["bio"], candidates, k_follows
        )

        if (i + 1) % 100 == 0 or i == 0:
            print(f"  [{i+1}/{len(users)}] {user['username']} -> {len(chosen)} follows")

        for target_name in chosen:
            target_id = profile_map.get(target_name)
            if target_id:
                api.follow_user(user["token"], target_id)
                total_follows += 1

    total_tweets = len(users) * m_tweets
    print(f"\nDone! {len(users)} users, {total_tweets} tweets, {total_follows} follows")


if __name__ == "__main__":
    main()

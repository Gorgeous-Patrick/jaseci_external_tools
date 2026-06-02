#!/usr/bin/env python3
"""Bootstrap the littlex5 database from edges.txt.

Creates users, sets up profiles, generates tweets, and establishes
follow relationships. Talks to the running jac server via HTTP.

Usage:
    # Start the server first:
    #   docker compose up -d && jac start
    # Then:
    python bootstrap.py [--base-url localhost:8000] [--tweets-per-user 5]
"""

import argparse
import random
import requests

SAMPLE_TWEETS = [
    "Just discovered #jac and it's amazing!",
    "Building graphs is so much easier with object-spatial programming",
    "Hot take: walkers > REST endpoints #osp",
    "Anyone else exploring #jaseci? The architecture is wild",
    "Shipped a new feature today, feeling great #dev",
    "The weather is perfect for coding outside",
    "Reading about distributed systems tonight #learning",
    "Coffee + code = productivity #devlife",
    "Just hit 100 followers! Thanks everyone",
    "Working on something exciting, stay tuned #building",
    "Graphs are the natural way to model social networks #graphdb",
    "Can't believe how fast #jac compiles now",
    "Object-spatial is the future of programming #osp #jac",
    "Late night debugging session... found it! #coding",
    "New blog post about walker patterns coming soon",
    "The topology index is a game changer for query perf",
    "Who else is at the #jaseci meetup today?",
    "Refactored my entire backend into walkers #cleancode",
    "This linked list benchmark is blowing my mind #perf",
    "Happy Friday! Time to push to prod #yolo",
    "Learning about TTG prefetching, very cool stuff",
    "Just deployed my first #jac app to production!",
    "The future is data-spatial #osp #jaseci",
    "Pair programming with AI is the new normal #dev",
    "Graph databases + walkers = unlimited power",
    "Morning run done, now time to code #balance",
    "Open source is beautiful #community",
    "Debugging is just detective work for nerds #coding",
    "Serverless walkers when? #jac #wishlist",
    "TIL about edge filtering in jac, so elegant",
]


def make_session(base_url: str) -> requests.Session:
    s = requests.Session()
    s.base_url = base_url  # type: ignore[attr-defined]
    return s


def url(session: requests.Session, path: str) -> str:
    return f"http://{session.base_url}{path}"  # type: ignore[attr-defined]


def register_and_login(session: requests.Session, username: str, password: str) -> str:
    """Register a user and return the auth token."""
    session.post(
        url(session, "/user/register"),
        json={
            "identities": [{"type": "username", "value": username}],
            "credential": {"type": "password", "password": password},
        },
    )
    resp = session.post(
        url(session, "/user/login"),
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


def setup_profile(session: requests.Session, token: str, username: str, bio: str) -> dict:
    resp = session.post(
        url(session, "/walker/setup_profile"),
        json={"username": username, "bio": bio},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    reports = data.get("data", {}).get("reports", [])
    return reports[0] if reports else {}


def create_tweet(session: requests.Session, token: str, content: str) -> dict:
    resp = session.post(
        url(session, "/walker/create_tweet"),
        json={"content": content},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    reports = data.get("data", {}).get("reports", [])
    return reports[0] if reports else {}


def follow_user(session: requests.Session, token: str, target_id: str) -> dict:
    resp = session.post(
        url(session, "/walker/follow_user"),
        json={"target_id": target_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    reports = data.get("data", {}).get("reports", [])
    return reports[0] if reports else {}


def load_edges(path: str) -> list[tuple[int, int]]:
    edges = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                edges.append((int(parts[0]), int(parts[1])))
    return edges


def main():
    parser = argparse.ArgumentParser(description="Bootstrap littlex5 database")
    parser.add_argument("--base-url", default="localhost:8000")
    parser.add_argument("--tweets-per-user", type=int, default=5)
    parser.add_argument("--edges-file", default="edges.txt")
    parser.add_argument("--password", default="password")
    args = parser.parse_args()

    random.seed(42)

    # Load edges and discover unique user IDs
    edges = load_edges(args.edges_file)
    user_ids = sorted({uid for src, dst in edges for uid in (src, dst)})
    print(f"Loaded {len(edges)} edges, {len(user_ids)} unique users from {args.edges_file}")

    session = make_session(args.base_url)

    # Phase 1: Register users, set up profiles, create tweets
    tokens: dict[int, str] = {}
    profile_ids: dict[int, str] = {}  # user_id -> profile jid

    for i, uid in enumerate(user_ids):
        username = f"user{uid}"
        token = register_and_login(session, username, args.password)
        tokens[uid] = token

        profile = setup_profile(
            session, token, username, bio=f"Hi, I'm {username}!"
        )
        profile_ids[uid] = profile.get("id", "")

        # Create tweets
        for _ in range(args.tweets_per_user):
            content = random.choice(SAMPLE_TWEETS)
            # Add user-specific flavor
            if random.random() < 0.3:
                content = f"@user{random.choice(user_ids)} {content}"
            create_tweet(session, token, content)

        if (i + 1) % 50 == 0:
            print(f"  Created {i + 1}/{len(user_ids)} users with profiles and tweets")

    print(f"Created {len(user_ids)} users, each with {args.tweets_per_user} tweets")

    # Phase 2: Establish follow relationships
    follow_count = 0
    for i, (src, dst) in enumerate(edges):
        if src in tokens and dst in profile_ids:
            follow_user(session, tokens[src], profile_ids[dst])
            follow_count += 1
            if (follow_count) % 500 == 0:
                print(f"  Created {follow_count}/{len(edges)} follow edges")

    print(f"Created {follow_count} follow edges")
    print(f"\nBootstrap complete: {len(user_ids)} users, "
          f"{len(user_ids) * args.tweets_per_user} tweets, {follow_count} follows")


if __name__ == "__main__":
    main()

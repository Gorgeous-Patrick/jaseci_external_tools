"""Little X - Social graph backend in idiomatic object-spatial style.

The graph holds the data: `Profile` / `Tweet` / `Channel` nodes wired by
typed edges. Walkers are the mobile agents the client spawns - each one
declares where it starts (`with Root entry`) and what to do at every node
type it lands on (`with Tweet entry`, ...). Traversal is `visit`, never a
hand-rolled loop, and shared fan-out lives in small base walkers.
"""

import cProfile;
import contextvars;
import datetime;
import json;
import os;
import time;
import from concurrent.futures { ThreadPoolExecutor }
import from http { HTTPMethod }
import from pathlib { Path }
import from typing { cast }
import from jaclang { JacRuntimeInterface as Jac }
import from jaclang.project.config { get_config }
import from jaclang.runtime.archetype { AccessLevel }
import from jaclang.runtime.builtin { restspec }
import from jaclang.server.session {
    _access_log_reset_for_tests,
    hit_stats_reset,
    hit_stats_snapshot
}

glob _DBRIDGE_LIKE_EXECUTOR: any = ThreadPoolExecutor(
    max_workers=int(os.environ.get("JAC_DBRIDGE_LIKE_WORKERS", "4"))
);

def _now -> str {
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat() + "Z";
}

# --- View models: the typed contract returned to the client ---
obj UserView {
    has id: str,
        username: str,
        bio: str = "";
}

obj TweetView {
    has id: str,
        content: str,
        author_username: str,
        created_at: str,
        likes: list[str],
        comments: list[dict[str, str]],
        is_mine: bool = False;
}

obj ProfileView {
    has id: str,
        username: str,
        bio: str,
        followers: list[UserView],
        following: list[UserView],
        tweets: list[TweetView];
}

obj ChannelView {
    has id: str,
        name: str,
        description: str,
        creator_username: str,
        created_at: str,
        member_count: int,
        is_member: bool,
        posts: list[TweetView] = [];
}

obj TrendingTag {
    has tag: str,
        count: int;
}

# --- Edges: the relationships in the social graph ---
edge Follow {}
edge Post {}
edge Member {}
edge ChannelPost {}

# --- Graph nodes: data, plus the methods that present it as a view.
#     A node knows how to describe itself; walkers decide when to ask. ---
node Profile {
    has username: str = "",
        bio: str = "",
        created_at: str = "";

    def to_user_view -> UserView {
        return UserView(id=jid(self), username=self.username, bio=self.bio);
    }

    # Followers / following fall straight out of the edges - no graph scan.
    def to_profile_view -> ProfileView {
        followers = [p.to_user_view() for p in [self<-:Follow:<-[?:Profile]]];
        following = [p.to_user_view() for p in [self->:Follow:->[?:Profile]]];
        tweets = [t.to_view() for t in [self-->[?:Tweet]]];
        tweets.sort(key=lambda (t: TweetView) { t.created_at; }, reverse=True);
        return ProfileView(
            id=jid(self),
            username=self.username,
            bio=self.bio,
            followers=followers,
            following=following,
            tweets=tweets
        );
    }
}

node Tweet {
    has content: str = "",
        author_username: str = "",
        created_at: str = "",
        likes: list[str] = [],
        comments: list[dict[str, str]] = [];

    def to_view -> TweetView {
        mine = [root-->[?:Profile]];
        is_mine: bool = len(mine) > 0 and self.author_username == mine[0].username;
        return TweetView(
            id=jid(self),
            content=self.content,
            author_username=self.author_username,
            created_at=self.created_at,
            likes=self.likes,
            comments=self.comments,
            is_mine=is_mine
        );
    }
}

node Channel {
    has name: str = "",
        description: str = "",
        creator_username: str = "",
        created_at: str = "";

    def to_view(with_posts: bool) -> ChannelView {
        mine = [root-->[?:Profile]];
        is_member: bool = len(mine) > 0 and len([edge mine[0]->:Member:->self]) > 0;
        posts: list[TweetView] = [];
        if with_posts {
            posts = [t.to_view() for t in [self-->[?:Tweet]]];
            posts.sort(key=lambda (t: TweetView) { t.created_at; }, reverse=True);
        }
        return ChannelView(
            id=jid(self),
            name=self.name,
            description=self.description,
            creator_username=self.creator_username,
            created_at=self.created_at,
            member_count=len([self<-:Member:<-[?:Profile]]),
            is_member=is_member,
            posts=posts
        );
    }
}

# --- Profile walkers: spawn at the caller's root, act on their profile ---
walker setup_profile {
    has username: str = "",
        bio: str = "",
        reports: list[ProfileView] = [];

    can run with Root entry {
        existing = [-->[?:Profile]];
        if existing {
            visit existing;
        } else {
            fresh = here ++> Profile(created_at=_now());
            grant(fresh, level=AccessLevel.CONNECT);
            visit fresh;
        }
    }

    can apply with Profile entry {
        if self.username {
            here.username = self.username;
        }
        if self.bio {
            here.bio = self.bio;
        }
        report here.to_profile_view();
    }
}

walker get_profile {
    has reports: list[ProfileView] = [];

    can run with Root entry {
        visit [-->[?:Profile]];
    }

    can give with Profile entry {
        report here.to_profile_view();
    }
}

# --- Accumulator walkers: fan out, gather at each node, report once at exit ---
walker:pub get_all_profiles {
    has results: list[UserView] = [],
        reports: list[list[UserView]] = [];

    can run with Root entry {
        for r in allroots() {
            visit [r-->[?:Profile]];
        }
    }

    can gather with Profile entry {
        self.results.append(here.to_user_view());
    }

    can deliver with Root exit {
        report self.results;
    }
}

walker get_trending {
    # `allroots()` can surface the same Tweet through more than one
    # path (e.g. via the system root and the user's own root), so a
    # bare per-visit tally would double-count. Dedupe by tweet jid.
    has counts: dict[str, int] = {},
        seen: dict[str, bool] = {},
        reports: list[list[TrendingTag]] = [];

    can run with Root entry {
        for r in allroots() {
            visit [r-->[?:Profile]-->[?:Tweet]];
        }
    }

    can tally with Tweet entry {
        tid = jid(here);
        if tid in self.seen {
            return;
        }
        self.seen[tid] = True;
        for word in here.content.split() {
            if word.startswith("#") and len(word) > 1 {
                tag = word.lower().rstrip(".,!?;:");
                self.counts[tag] = self.counts.get(tag, 0) + 1;
            }
        }
    }

    can deliver with Root exit {
        tags = [TrendingTag(tag=t, count=self.counts[t]) for t in self.counts];
        tags.sort(key=lambda (x: TrendingTag) { x.count; }, reverse=True);
        report tags[:8];
    }
}

walker load_feed {
    has search_query: str = "",
        feed: list[TweetView] = [],
        reports: list[list[TweetView]] = [];

    can run with Root entry {
        visit [-->[?:Profile]];
    }

    can collect with Profile entry {
        # TEMPORARY: typed Post edges so the TTG planner can include Tweets
        # in the prefetch plan. Real fix is runtime-side (planner should
        # handle generic out-edges too, with cardinality guards).
        visit [->:Post:->[?:Tweet]];
        visit [->:Follow:->[?:Profile]->:Post:->[?:Tweet]];
    }

    can gather with Tweet entry {
        self.feed.append(here.to_view());
    }

    can deliver with Root exit {
        result = self.feed;
        if self.search_query {
            q = self.search_query.lower().strip();
            result = [
                t
                for t in result
                if q in t.content.lower()
            ];
        }
        result.sort(key=lambda (t: TweetView) { t.created_at; }, reverse=True);
        report result;
    }
}

walker load_feed_stepwise {
    has search_query: str = "",
        root_profile_id: str = "",
        seen_profiles: dict[str, bool] = {},
        seen_tweets: dict[str, bool] = {},
        feed: list[TweetView] = [],
        reports: list[list[TweetView]] = [];

    can run with Root entry {
        visit [-->[?:Profile]];
    }

    can collect with Profile entry {
        pid = jid(here);
        if pid in self.seen_profiles {
            return;
        }
        self.seen_profiles[pid] = True;

        visit [->:Post:->[?:Tweet]];
        if not self.root_profile_id {
            self.root_profile_id = pid;
            visit [->:Follow:->[?:Profile]];
        }
    }

    can gather with Tweet entry {
        tid = jid(here);
        if tid in self.seen_tweets {
            return;
        }
        self.seen_tweets[tid] = True;
        self.feed.append(here.to_view());
    }

    can deliver with Root exit {
        result = self.feed;
        if self.search_query {
            q = self.search_query.lower().strip();
            result = [
                t
                for t in result
                if q in t.content.lower()
            ];
        }
        result.sort(key=lambda (t: TweetView) { t.created_at; }, reverse=True);
        report result;
    }
}

walker get_channels {
    has seen: dict[str, bool] = {},
        results: list[ChannelView] = [],
        reports: list[list[ChannelView]] = [];

    can run with Root entry {
        for r in allroots() {
            visit [r-->[?:Profile]-->[?:Channel]];
        }
    }

    # A channel links to every member, so it can be reached more than once.
    can gather with Channel entry {
        cid = jid(here);
        if cid not in self.seen {
            self.seen[cid] = True;
            self.results.append(here.to_view(False));
        }
    }

    can deliver with Root exit {
        self.results.sort(key=lambda (c: ChannelView) { c.created_at; }, reverse=True);
        report self.results;
    }
}

# --- Create walkers: navigate to the caller's profile, then attach a node ---
walker create_tweet {
    has content: str;

    can run with Root entry {
        visit [-->[?:Profile]];
    }

    can make with Profile entry {
        new_tweet = here +>: Post() :+> Tweet(
            content=self.content, author_username=here.username, created_at=_now()
        );
        grant(new_tweet, level=AccessLevel.WRITE);
        report new_tweet.to_view();
    }
}

walker create_channel {
    has name: str,
        description: str = "";

    can run with Root entry {
        visit [-->[?:Profile]];
    }

    can make with Profile entry {
        new_channel = here +>: Member() :+> Channel(
            name=self.name,
            description=self.description,
            creator_username=here.username,
            created_at=_now()
        );
        grant(new_channel, level=AccessLevel.CONNECT);
        report new_channel.to_view(False);
    }
}

# --- Lookup base walkers: resolve the target node by jid via `& (id)`
#     and visit it directly. Action subclasses just react on entry. ---
walker find_profile {
    has target_id: str = "";

    can run with Root entry {
        if self.target_id {
            target = jobj(self.target_id);
            if isinstance(target, Profile) {
                visit [target];
            }
        }
    }
}

walker follow_user(find_profile) {
    can act with Profile entry {
        if jid(here) == self.target_id {
            me = [root-->[?:Profile]][0];
            me +>: Follow() :+> here;
            report {"success": True};
            disengage;
        }
    }
}

walker unfollow_user(find_profile) {
    can act with Profile entry {
        if jid(here) == self.target_id {
            me = [root-->[?:Profile]][0];
            edges = [edge me->:Follow:->here];
            if edges {
                del edges[0];
            }
            report {"success": True};
            disengage;
        }
    }
}

# `actor` is resolved once on entry so Tweet abilities need no extra lookup.
walker find_tweet {
    has tweet_id: str = "",
        actor: str = "";

    can run with Root entry {
        mine = [-->[?:Profile]];
        if mine {
            self.actor = mine[0].username;
        }
        if self.tweet_id {
            target = jobj(self.tweet_id);
            if isinstance(target, Tweet) {
                visit [target];
            }
        }
    }
}

walker like_tweet(find_tweet) {
    can act with Tweet entry {
        if jid(here) == self.tweet_id {
            if self.actor in here.likes {
                here.likes = [
                    u
                    for u in here.likes
                    if u != self.actor
                ];
                report {"liked": False, "likes": here.likes};
            } else {
                here.likes = here.likes + [self.actor];
                report {"liked": True, "likes": here.likes};
            }
            disengage;
        }
    }
}

walker delete_tweet(find_tweet) {
    can act with Tweet entry {
        if jid(here) == self.tweet_id and here.author_username == self.actor {
            del here;
            report {"success": True};
            disengage;
        }
    }
}

walker add_comment(find_tweet) {
    has content: str = "";

    can act with Tweet entry {
        if jid(here) == self.tweet_id {
            comment = {
                "username": self.actor,
                "content": self.content,
                "created_at": _now()
            };
            here.comments = here.comments + [comment];
            report {"success": True, "comment": comment};
            disengage;
        }
    }
}

walker find_channel {
    has channel_id: str = "";

    can run with Root entry {
        if self.channel_id {
            target = jobj(self.channel_id);
            if isinstance(target, Channel) {
                visit [target];
            }
        }
    }
}

walker join_channel(find_channel) {
    can act with Channel entry {
        if jid(here) == self.channel_id {
            me = [root-->[?:Profile]][0];
            if not [edge me->:Member:->here] {
                me +>: Member() :+> here;
            }
            report {"success": True};
            disengage;
        }
    }
}

walker leave_channel(find_channel) {
    can act with Channel entry {
        if jid(here) == self.channel_id {
            me = [root-->[?:Profile]][0];
            edges = [edge me->:Member:->here];
            if edges {
                del edges[0];
            }
            report {"success": True};
            disengage;
        }
    }
}

walker get_channel_detail(find_channel) {
    has reports: list[ChannelView] = [];

    can act with Channel entry {
        if jid(here) == self.channel_id {
            report here.to_view(True);
            disengage;
        }
    }
}

walker create_channel_tweet(find_channel) {
    has content: str = "";

    can act with Channel entry {
        if jid(here) == self.channel_id {
            me = [root-->[?:Profile]][0];
            if [edge me->:Member:->here] {
                new_tweet = here +>: ChannelPost() :+> Tweet(
                    content=self.content, author_username=me.username, created_at=_now()
                );
                grant(new_tweet, level=AccessLevel.WRITE);
                report new_tweet.to_view();
            }
            disengage;
        }
    }
}

def _dbridge_like_store() -> any {
    ctx = Jac.get_context();
    mem = ctx.mem;
    if mem is None or mem.store is None {
        raise RuntimeError("dbridge_like requires a persisted PgSQL store");
    }
    mem.read_barrier();
    return mem.store;
}

def _dbridge_like_jac_id(value: any) -> str {
    return str(cast(any, value).__jac__.id);
}

def _dbridge_like_remember(order: list[str], seen: set[str], uid: str) -> None {
    if uid and uid not in seen {
        seen.add(uid);
        order.append(uid);
    }
}

def _dbridge_like_write_uuid_list(path: str, ids: list[str]) -> None {
    if not path {
        return;
    }
    p = Path(path);
    p.parent.mkdir(parents=True, exist_ok=True);
    p.write_text("".join([f"{uid}\n" for uid in ids]));
}

def _dbridge_like_quality(actual_order: list[str], prefetched_order: list[str]) -> dict {
    actual = set(actual_order);
    prefetched = set(prefetched_order);
    covered = len(actual & prefetched);
    overfetch = len(prefetched - actual);
    undercoverage = len(actual - prefetched);
    coverage = covered * 100.0 / len(actual) if actual else 100.0;
    accuracy = covered * 100.0 / len(prefetched) if prefetched else 100.0;
    return {
        "covered": covered,
        "overfetch": overfetch,
        "undercoverage": undercoverage,
        "coverage": coverage,
        "accuracy": accuracy
    };
}

def _dbridge_like_profile_paths -> dict[str, str] {
    return {
        "profile_dir": os.environ.get("JAC_DBRIDGE_LIKE_PROFILE_DIR", "").strip()
            or os.environ.get("JAC_PROFILE_DIR", "").strip(),
        "profile_csv": os.environ.get("JAC_DBRIDGE_LIKE_PROFILE_CSV", "").strip()
            or os.environ.get("JAC_PROFILE_CSV", "").strip()
    };
}

def _dbridge_like_write_profile(
    profile_dir: str,
    profile_csv: str,
    profiler: any,
    e2e_ms: float,
    prefetch_ms: float,
    walker_ms: float,
    materialize_ms: float,
    prefetch_wait_ms: float
) -> None {
    out_dir = Path(profile_dir) if profile_dir else Path(profile_csv).parent if profile_csv else None;
    if out_dir is None {
        return;
    }
    out_dir.mkdir(parents=True, exist_ok=True);
    if profiler is not None {
        profiler.disable();
        prof_path = out_dir / "jac_server.prof";
        txt_path = out_dir / "jac_server.txt";
        profiler.dump_stats(str(prof_path));
        txt_path.write_text(f"Profile saved to {prof_path}\n");
    }
    csv_path = Path(profile_csv) if profile_csv else out_dir / "profile.csv";
    csv_path.parent.mkdir(parents=True, exist_ok=True);
    csv_path.write_text(
        "node_num,edge_num,tweet_num,ttg_enabled,ttg_total_ms,topo_idx_ms,ttg_ms,prefetch_ms,walker_ms,resolve_total_ms,materialize_ms,prefetch_wait_ms\n"
        + f",,,dbridge_like,{e2e_ms:.3f},0.000,0.000,{prefetch_ms:.3f},{walker_ms:.3f},0.000,{materialize_ms:.3f},{prefetch_wait_ms:.3f}\n"
    );
}

def _dbridge_like_empty_feed_result(
    root_id: str,
    e2e_ms: float,
    db_ms: float,
    access_log: str,
    actual_file: str,
    prefetch_file: str,
    query_count: int
) -> dict[str, any] {
    reports: list[list[TweetView]] = [[]];
    return {
        "reports": reports,
        "metrics": {
            "policy": "dbridge_like",
            "prefetch_limit": 0,
            "trial": 0,
            "start_id": root_id,
            "visited": 0,
            "checksum": 0,
            "first_value": "",
            "last_value": "",
            "e2e_ms": f"{e2e_ms:.3f}",
            "db_ms": f"{db_ms:.3f}",
            "materialize_ms": "0.000",
            "cpu_ms": f"{e2e_ms:.3f}",
            "prefetch_ms": "0.000",
            "prefetch_wait_ms": "0.000",
            "query_count": query_count,
            "l1": 0,
            "l2": 0,
            "l3": 0,
            "miss": 0,
            "actual_ids": 0,
            "prefetched_ids": 0,
            "covered_ids": 0,
            "overfetch_ids": 0,
            "undercoverage_ids": 0,
            "coverage": "100.0",
            "accuracy": "100.0",
            "serialized_bytes": 2,
            "access_log": access_log,
            "actual_file": actual_file,
            "prefetch_file": prefetch_file,
            "error": ""
        }
    };
}

def _dbridge_like_root_profile_id(root_id: str) -> str {
    rows = _dbridge_like_store().rows(
        """
        SELECT e.dst::text
        FROM anchors e
        JOIN anchors dst ON dst.id = e.dst
        WHERE e.kind = 'EdgeAnchor'
          AND e.src = CAST(:src AS uuid)
          AND dst.kind = 'NodeAnchor'
          AND dst.arch_type = 'Profile'
        ORDER BY e.seq NULLS LAST, e.id
        LIMIT 1
        """,
        {"src": root_id}
    );
    return str(rows[0][0]) if rows else "";
}

def _dbridge_like_own_tweet_ids(profile_id: str) -> list[str] {
    rows = _dbridge_like_store().rows(
        """
        SELECT e.dst::text
        FROM anchors e
        JOIN anchors dst ON dst.id = e.dst
        WHERE e.kind = 'EdgeAnchor'
          AND e.src = CAST(:src AS uuid)
          AND e.arch_type = 'Post'
          AND dst.kind = 'NodeAnchor'
          AND dst.arch_type = 'Tweet'
        ORDER BY e.seq NULLS LAST, e.id
        """,
        {"src": profile_id}
    );
    return [str(r[0]) for r in rows];
}

def _dbridge_like_followed_tweet_ids(profile_id: str) -> list[str] {
    rows = _dbridge_like_store().rows(
        """
        SELECT post.dst::text
        FROM anchors follow
        JOIN anchors followed ON followed.id = follow.dst
        JOIN anchors post ON post.src = follow.dst
        JOIN anchors tweet ON tweet.id = post.dst
        WHERE follow.kind = 'EdgeAnchor'
          AND follow.src = CAST(:src AS uuid)
          AND follow.arch_type = 'Follow'
          AND followed.kind = 'NodeAnchor'
          AND followed.arch_type = 'Profile'
          AND post.kind = 'EdgeAnchor'
          AND post.arch_type = 'Post'
          AND tweet.kind = 'NodeAnchor'
          AND tweet.arch_type = 'Tweet'
        ORDER BY follow.seq NULLS LAST, follow.id, post.seq NULLS LAST, post.id
        """,
        {"src": profile_id}
    );
    return [str(r[0]) for r in rows];
}

def _dbridge_like_prefetch_feed_tweets(profile_id: str) -> dict[str, any] {
    started = time.perf_counter();
    db_start = time.perf_counter();
    tweet_ids = _dbridge_like_own_tweet_ids(profile_id);
    tweet_ids += _dbridge_like_followed_tweet_ids(profile_id);
    db_ms = (time.perf_counter() - db_start) * 1000.0;

    materialize_start = time.perf_counter();
    tweets: list[Tweet] = [];
    for tweet_id in tweet_ids {
        tweet = cast((Tweet | None), Jac.get_object(tweet_id));
        if tweet is None {
            raise ValueError(f"Tweet not found during dbridge_like prefetch: {tweet_id}");
        }
        tweets.append(tweet);
    }
    materialize_ms = (time.perf_counter() - materialize_start) * 1000.0;

    return {
        "tweet_ids": tweet_ids,
        "tweets": tweets,
        "db_ms": db_ms,
        "materialize_ms": materialize_ms,
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
        "query_count": 2
    };
}

def _submit_dbridge_like_feed_tweets(profile_id: str) -> any {
    ctx = contextvars.copy_context();
    return _DBRIDGE_LIKE_EXECUTOR.submit(
        ctx.run,
        _dbridge_like_prefetch_feed_tweets,
        profile_id
    );
}

@restspec(method=HTTPMethod.POST, path="/dbridge_like/load_feed")
def dbridge_like_load_feed(search_query: str = "") -> dict[str, any] {
    access_log = os.environ.get("JAC_DBRIDGE_LIKE_ACCESS_LOG", "").strip();
    cfg = get_config();
    if not access_log and cfg is not None {
        access_log = str(cast(any, cfg).run.access_log or "");
    }
    actual_file = os.environ.get("JAC_DBRIDGE_LIKE_ACTUAL_FILE", "").strip();
    prefetch_file = os.environ.get("JAC_DBRIDGE_LIKE_PREFETCH_FILE", "").strip();
    paths = _dbridge_like_profile_paths();
    profile_dir = paths["profile_dir"];
    profile_csv = paths["profile_csv"];

    if not actual_file {
        raise ValueError("JAC_DBRIDGE_LIKE_ACTUAL_FILE is required");
    }
    if not prefetch_file {
        raise ValueError("JAC_DBRIDGE_LIKE_PREFETCH_FILE is required");
    }
    if access_log and cfg is not None {
        cast(any, cfg).run.access_log = access_log;
        _access_log_reset_for_tests();
    }

    profile_out_dir = Path(profile_dir) if profile_dir else Path(profile_csv).parent if profile_csv else None;
    profiler: any = None;
    if profile_out_dir is not None {
        profile_out_dir.mkdir(parents=True, exist_ok=True);
        profiler = cProfile.Profile();
        profiler.enable();
    }

    hit_stats_reset();
    trial_start = time.perf_counter();
    actual_order: list[str] = [];
    actual_seen: set[str] = set();
    prefetched_order: list[str] = [];
    prefetched_seen: set[str] = set();
    feed: list[TweetView] = [];
    db_ms: float = 0.0;
    materialize_ms: float = 0.0;
    prefetch_ms: float = 0.0;
    prefetch_wait_ms: float = 0.0;
    query_count: int = 0;

    root_id = _dbridge_like_jac_id(Jac.root());
    db_start = time.perf_counter();
    profile_id = _dbridge_like_root_profile_id(root_id);
    db_ms += (time.perf_counter() - db_start) * 1000.0;
    query_count += 1;
    if not profile_id {
        e2e_ms = (time.perf_counter() - trial_start) * 1000.0;
        _dbridge_like_write_uuid_list(actual_file, actual_order);
        _dbridge_like_write_uuid_list(prefetch_file, prefetched_order);
        _dbridge_like_write_profile(profile_dir, profile_csv, profiler, e2e_ms, prefetch_ms, e2e_ms, materialize_ms, prefetch_wait_ms);
        return _dbridge_like_empty_feed_result(
            root_id,
            e2e_ms,
            db_ms,
            access_log,
            actual_file,
            prefetch_file,
            query_count
        );
    }

    materialize_start = time.perf_counter();
    profile = cast((Profile | None), Jac.get_object(profile_id));
    materialize_ms += (time.perf_counter() - materialize_start) * 1000.0;
    if profile is None {
        raise ValueError(f"Profile not found during dbridge_like traversal: {profile_id}");
    }
    _dbridge_like_remember(actual_order, actual_seen, profile_id);
    my_username = profile.username;

    feed_future = _submit_dbridge_like_feed_tweets(profile_id);
    wait_start = time.perf_counter();
    feed_prefetch = feed_future.result();
    prefetch_wait_ms += (time.perf_counter() - wait_start) * 1000.0;
    db_ms += float(feed_prefetch["db_ms"]);
    materialize_ms += float(feed_prefetch["materialize_ms"]);
    prefetch_ms += float(feed_prefetch["elapsed_ms"]);
    query_count += int(feed_prefetch["query_count"]);

    tweet_ids = cast(list[str], feed_prefetch["tweet_ids"]);
    tweets = cast(list[Tweet], feed_prefetch["tweets"]);
    for idx in range(len(tweet_ids)) {
        tweet_id = tweet_ids[idx];
        tweet = tweets[idx];
        _dbridge_like_remember(prefetched_order, prefetched_seen, tweet_id);
        _dbridge_like_remember(actual_order, actual_seen, tweet_id);
        feed.append(
            TweetView(
                id=tweet_id,
                content=tweet.content,
                author_username=tweet.author_username,
                created_at=tweet.created_at,
                likes=tweet.likes,
                comments=tweet.comments,
                is_mine=tweet.author_username == my_username
            )
        );
    }

    result = feed;
    if search_query {
        q = search_query.lower().strip();
        result = [t for t in result if q in t.content.lower()];
    }
    result.sort(key=lambda (t: TweetView) { t.created_at; }, reverse=True);
    reports = [result];

    e2e_ms = (time.perf_counter() - trial_start) * 1000.0;
    walker_ms = e2e_ms - prefetch_wait_ms;
    quality = _dbridge_like_quality(actual_order, prefetched_order);
    hits = hit_stats_snapshot();
    l1 = int(hits.get("L1", 0));
    l2 = int(hits.get("L2", 0));
    l3 = int(hits.get("L3", 0));
    miss = int(hits.get("MISS", 0));
    checksum = 0;
    for view in result {
        checksum += len(view.content);
    }
    serialized = json.dumps(reports, separators=(",", ":"), `default=str);

    _dbridge_like_write_uuid_list(actual_file, actual_order);
    _dbridge_like_write_uuid_list(prefetch_file, prefetched_order);
    _dbridge_like_write_profile(
        profile_dir,
        profile_csv,
        profiler,
        e2e_ms,
        prefetch_ms,
        walker_ms,
        materialize_ms,
        prefetch_wait_ms
    );

    return {
        "reports": reports,
        "metrics": {
            "policy": "dbridge_like",
            "prefetch_limit": 0,
            "trial": 0,
            "start_id": root_id,
            "visited": len(result),
            "checksum": checksum,
            "first_value": result[0].id if result else "",
            "last_value": result[-1].id if result else "",
            "e2e_ms": f"{e2e_ms:.3f}",
            "db_ms": f"{db_ms:.3f}",
            "materialize_ms": f"{materialize_ms:.3f}",
            "cpu_ms": f"{walker_ms:.3f}",
            "prefetch_ms": f"{prefetch_ms:.3f}",
            "prefetch_wait_ms": f"{prefetch_wait_ms:.3f}",
            "query_count": query_count,
            "l1": l1,
            "l2": l2,
            "l3": l3,
            "miss": miss,
            "actual_ids": len(actual_order),
            "prefetched_ids": len(prefetched_order),
            "covered_ids": quality["covered"],
            "overfetch_ids": quality["overfetch"],
            "undercoverage_ids": quality["undercoverage"],
            "coverage": f"{quality['coverage']:.1f}",
            "accuracy": f"{quality['accuracy']:.1f}",
            "serialized_bytes": len(serialized.encode("utf-8")),
            "access_log": access_log,
            "actual_file": actual_file,
            "prefetch_file": prefetch_file,
            "error": ""
        }
    };
}

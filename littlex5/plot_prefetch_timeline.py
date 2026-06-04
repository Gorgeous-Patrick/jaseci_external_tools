#!/usr/bin/env python3
"""Visualize the per-anchor cost breakdown during prefetch and walker runtime.

Reads a yappi .prof file and produces a timeline showing where time is spent
per anchor: deserialization, _compute_hash, _snapshot_field_hashes, Redis,
MongoDB, and other overhead.

Usage:
    python plot_prefetch_timeline.py [path/to/jac_server.prof]
"""

import pstats
import sys

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def load_stats(prof_path):
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    result = {}
    callers = {}
    for (filename, lineno, funcname), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
        key = funcname
        if key not in result:
            result[key] = {"nc": 0, "tt": 0.0, "ct": 0.0}
            callers[key] = {}
        result[key]["nc"] += nc
        result[key]["tt"] += tt
        result[key]["ct"] += ct
        for (cf, cl, cfn), (ccc, cnc, ctt, cct) in caller_dict.items():
            if cfn not in callers[key]:
                callers[key][cfn] = {"nc": 0, "ct": 0.0}
            callers[key][cfn]["nc"] += cnc
            callers[key][cfn]["ct"] += cct
    return result, callers


def safe_ct(s, fn):
    return s.get(fn, {"ct": 0})["ct"] * 1000


def safe_tt(s, fn):
    return s.get(fn, {"tt": 0})["tt"] * 1000


def safe_nc(s, fn):
    return s.get(fn, {"nc": 0})["nc"]


def caller_ct(cal, fn, caller):
    return cal.get(fn, {}).get(caller, {"ct": 0})["ct"] * 1000


def main():
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_1000/trial_1/get_profile/trial_1/jac_server.prof"
    s, cal = load_stats(prof_path)

    # Total times
    total_prefetch = safe_ct(s, "ScaleTieredMemory.prefetch") or safe_ct(s, "prefetch")
    total_walker = safe_ct(s, "osp_spawn")
    total_spawn = safe_ct(s, "_jac_walker_execute") or safe_ct(s, "spawn_call")

    # Prefetch breakdown
    super_prefetch = safe_ct(s, "TieredMemory.prefetch") or caller_ct(cal, "prefetch", "ScaleTieredMemory.prefetch")
    snapshot_hashes = safe_ct(s, "_snapshot_field_hashes")

    # Inside super.prefetch (TieredMemory.prefetch)
    find_raw_ct = safe_ct(s, "find_raw")
    bulk_put_raw_ct = safe_ct(s, "bulk_put_raw")
    bulk_exists_ct = safe_ct(s, "bulk_exists")

    # Deserialization (happens in both prefetch and walker)
    deser_total = safe_ct(s, "deserialize")
    compute_hash_total = safe_ct(s, "_compute_hash")
    get_field_types = safe_ct(s, "_get_field_types")
    deser_archetype = safe_ct(s, "_deserialize_archetype")

    # Walker breakdown
    refs_ct = safe_ct(s, "refs") or safe_ct(s, "execute_path")
    resolve_chain = safe_ct(s, "resolve_chain_ordered") or safe_ct(s, "resolve_chain")

    # Redis individual puts (during walker batch_get write-back)
    redis_put = safe_ct(s, "RedisBackend.put") or safe_ct(s, "put")
    redis_batch_get = safe_ct(s, "RedisBackend.batch_get") or safe_ct(s, "batch_get")
    mongo_batch_get = safe_ct(s, "MongoBackend.batch_get")

    # Counts
    n_deser = safe_nc(s, "deserialize")
    n_snapshot = safe_nc(s, "_snapshot_field_hashes")
    n_compute_hash = safe_nc(s, "_compute_hash")

    # ─── Build the figure ───
    fig, axes = plt.subplots(1, 3, figsize=(18, 7))

    # ─── Panel 1: Prefetch pipeline ───
    ax1 = axes[0]
    prefetch_steps = []
    if bulk_exists_ct > 0:
        prefetch_steps.append(("Redis\nbulk_exists", bulk_exists_ct, "#76b7b2"))
    if find_raw_ct > 0:
        prefetch_steps.append(("MongoDB\nfind_raw", find_raw_ct, "#4e79a7"))
    if bulk_put_raw_ct > 0:
        prefetch_steps.append(("Redis\nbulk_put_raw", bulk_put_raw_ct, "#f28e2b"))

    # Deserialize within prefetch (approximate from counts)
    if n_deser > 0 and total_prefetch > 0:
        # Fraction of deserialize calls that happen during prefetch vs walker
        prefetch_deser = deser_total * 0.5 if n_snapshot > 0 else deser_total
        prefetch_steps.append(("Deserialize\n(in prefetch)", prefetch_deser, "#59a14f"))

    if snapshot_hashes > 0:
        prefetch_steps.append(("_snapshot_\nfield_hashes", snapshot_hashes, "#e15759"))

    prefetch_other = max(0, total_prefetch - sum(v for _, v, _ in prefetch_steps))
    if prefetch_other > 1:
        prefetch_steps.append(("Other", prefetch_other, "#bab0ac"))

    y_pos = range(len(prefetch_steps))
    bars = ax1.barh(
        y_pos,
        [v for _, v, _ in prefetch_steps],
        color=[c for _, _, c in prefetch_steps],
        height=0.6,
        edgecolor="white",
    )
    ax1.set_yticks(list(y_pos))
    ax1.set_yticklabels([l for l, _, _ in prefetch_steps], fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlabel("Time (ms)")
    ax1.set_title(f"Prefetch Pipeline ({total_prefetch:.0f}ms total)")
    for bar, (_, v, _) in zip(bars, prefetch_steps):
        if v > 1:
            ax1.text(
                bar.get_x() + bar.get_width() + 1,
                bar.get_y() + bar.get_height() / 2,
                f"{v:.1f}ms",
                ha="left", va="center", fontsize=8,
            )

    # ─── Panel 2: Per-anchor cost comparison ───
    ax2 = axes[1]
    categories = []

    # Prefetch per-anchor
    if n_snapshot > 0:
        per_deser = deser_total / n_deser if n_deser else 0
        per_hash_in_deser = compute_hash_total / n_compute_hash if n_compute_hash else 0
        per_snapshot = snapshot_hashes / n_snapshot if n_snapshot else 0
        per_typing = get_field_types / safe_nc(s, "_get_field_types") if safe_nc(s, "_get_field_types") else 0

        categories.append((
            "Prefetch\n(per anchor)",
            [
                ("deserialize", per_deser - per_hash_in_deser, "#59a14f"),
                ("_compute_hash\n(re-serialize)", per_hash_in_deser, "#e15759"),
                ("_snapshot_\nfield_hashes", per_snapshot, "#ff9d9a"),
            ],
        ))

    # Walker per-anchor (batch_get path)
    if mongo_batch_get > 0:
        n_mongo = safe_nc(s, "MongoBackend.batch_get") or 1
        per_mongo = mongo_batch_get / n_mongo
        per_redis_get = redis_batch_get / (safe_nc(s, "RedisBackend.batch_get") or 1)
        per_redis_put_val = redis_put / (safe_nc(s, "RedisBackend.put") or 1)
        per_deser_walker = deser_total / n_deser if n_deser else 0
        per_hash_walker = compute_hash_total / n_compute_hash if n_compute_hash else 0

        categories.append((
            "Walker fetch\n(per anchor)",
            [
                ("Redis MGET", per_redis_get, "#76b7b2"),
                ("MongoDB query", per_mongo, "#4e79a7"),
                ("deserialize", per_deser_walker - per_hash_walker, "#59a14f"),
                ("_compute_hash", per_hash_walker, "#e15759"),
                ("Redis PUT", per_redis_put_val, "#f28e2b"),
            ],
        ))

    x_pos = 0
    x_ticks = []
    x_labels = []
    for cat_label, parts in categories:
        bottom = 0
        for part_label, val, color in parts:
            ax2.bar(x_pos, val, bottom=bottom, color=color, width=0.5, edgecolor="white")
            if val > 0.01:
                ax2.text(
                    x_pos, bottom + val / 2,
                    f"{val:.3f}ms",
                    ha="center", va="center", fontsize=7, fontweight="bold",
                )
            bottom += val
        ax2.text(x_pos, bottom + 0.005, f"{bottom:.3f}ms", ha="center", fontsize=9, fontweight="bold")
        x_ticks.append(x_pos)
        x_labels.append(cat_label)
        x_pos += 1

    ax2.set_xticks(x_ticks)
    ax2.set_xticklabels(x_labels, fontsize=9)
    ax2.set_ylabel("Time (ms)")
    ax2.set_title("Per-Anchor Cost")

    # ─── Panel 3: Overall time split ───
    ax3 = axes[2]
    overall = []
    if total_prefetch > 0:
        overall.append(("Prefetch", total_prefetch, "#f28e2b"))
    if total_walker > 0:
        overall.append(("Walker\n(osp_spawn)", total_walker, "#4e79a7"))
    commit_ct = safe_ct(s, "ScaleTieredMemory.commit") or safe_ct(s, "commit")
    if commit_ct > 0:
        overall.append(("Commit", commit_ct, "#59a14f"))
    overall_other = max(0, total_spawn - sum(v for _, v, _ in overall))
    if overall_other > 1:
        overall.append(("Other", overall_other, "#bab0ac"))

    if overall:
        labels = [l for l, _, _ in overall]
        sizes = [v for _, v, _ in overall]
        colors = [c for _, _, c in overall]
        wedges, texts, autotexts = ax3.pie(
            sizes, labels=labels, colors=colors, autopct="%1.0f%%",
            startangle=90, textprops={"fontsize": 9},
        )
        for at in autotexts:
            at.set_fontsize(8)
            at.set_fontweight("bold")
        ax3.set_title(f"Total Spawn ({total_spawn:.0f}ms)")

    # Legend
    legend_patches = [
        mpatches.Patch(color="#4e79a7", label="MongoDB"),
        mpatches.Patch(color="#f28e2b", label="Redis write"),
        mpatches.Patch(color="#76b7b2", label="Redis read"),
        mpatches.Patch(color="#59a14f", label="Deserialize"),
        mpatches.Patch(color="#e15759", label="_compute_hash"),
        mpatches.Patch(color="#ff9d9a", label="_snapshot_field_hashes"),
        mpatches.Patch(color="#bab0ac", label="Other"),
    ]
    fig.legend(handles=legend_patches, loc="lower center", ncol=4, fontsize=8)

    plt.suptitle(
        f"Prefetch & Walker Cost Breakdown\n"
        f"(deserialize: {n_deser} calls, snapshot: {n_snapshot} calls, "
        f"compute_hash: {n_compute_hash} calls)",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout(rect=[0, 0.06, 1, 0.93])

    out = prof_path.rsplit("/", 1)[0] + "/prefetch_timeline.png" if "/" in prof_path else "prefetch_timeline.png"
    plt.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()

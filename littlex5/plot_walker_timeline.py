#!/usr/bin/env python3
"""Visualize the walker runtime as a timeline (waterfall) chart.

Each step starts where the previous one ends, showing the sequential
flow of time through the walker execution.

Steps:
  1. User code (walker abilities)
  2. Plan building (_build_plan_from_path)
  3. Filter analysis (_filter_has_predicates + _filter_type_name + getclosurevars)
  4. Topology index resolution (plan_chain_ordered)
  5. Materialize from L1 (_materialize_ids)
  6. Commit (_sv_on_complete)

Usage:
    python plot_walker_timeline.py [path/to/jac_server.prof]
"""

import pstats
import sys

import matplotlib.pyplot as plt


def load_stats(prof_path):
    stats = pstats.Stats(prof_path, stream=open("/dev/null", "w"))
    result = {}
    for (filename, lineno, funcname), (cc, nc, tt, ct, caller_dict) in stats.stats.items():
        if funcname not in result:
            result[funcname] = {"nc": 0, "tt": 0.0, "ct": 0.0}
        result[funcname]["nc"] += nc
        result[funcname]["tt"] += tt
        result[funcname]["ct"] += ct
    return result


def ct(s, fn):
    return s.get(fn, {"ct": 0})["ct"] * 1000


def tt(s, fn):
    return s.get(fn, {"tt": 0})["tt"] * 1000


def nc(s, fn):
    return s.get(fn, {"nc": 0})["nc"]


# Walker ability names for littlex5 walkers
WALKER_ABILITIES = [
    "run", "give", "apply", "gather", "deliver", "tally",
    "act", "make", "greet", "process", "compute",
]


def main():
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_5000/get_profile/trial_1/jac_server.prof"
    s = load_stats(prof_path)

    total_walker = ct(s, "osp_spawn")

    # Step 1: User code — sum self-time of all walker abilities
    user_ms = 0
    for ability in WALKER_ABILITIES:
        user_ms += tt(s, ability)
    # Also check for common node methods called from walkers
    for method in ["to_profile_view", "to_user_view", "to_view"]:
        user_ms += tt(s, method)

    # Step 2: Plan building
    plan_ms = ct(s, "_build_plan_from_path")

    # Step 3: Filter analysis (sub-calls of plan building)
    filter_predicates = ct(s, "_filter_has_predicates")
    filter_type = ct(s, "_filter_type_name")
    closure_vars = ct(s, "getclosurevars")
    filter_total = filter_predicates + filter_type + closure_vars
    plan_pure = max(0, plan_ms - filter_total)

    # Step 4: Topology index resolution
    topo_ms = ct(s, "plan_chain_ordered")

    # Step 5: Materialize from L1
    materialize_ms = ct(s, "_materialize_ids")

    # Step 6: L3 (MongoDB) fetch time
    mongo_ms = ct(s, "MongoBackend.batch_get") or ct(s, "MongoBackend.get")

    # Step 7: Deserialization
    deser_ms = ct(s, "deserialize")

    # Step 8: L2 (Redis) write-back
    redis_put_ms = ct(s, "RedisBackend.put") or ct(s, "bulk_put_raw")

    # Step 9: Commit
    commit_ms = ct(s, "_sv_on_complete")

    # Build timeline
    steps = [
        ("User code\n(abilities)", user_ms, "#59a14f"),
        ("Plan building\n(pure)", plan_pure, "#4e79a7"),
        ("Filter analysis\n(bytecode+inspect)", filter_total, "#b07aa1"),
        ("Topology index\nresolution", topo_ms, "#f28e2b"),
        ("Materialize\nfrom L1", materialize_ms, "#76b7b2"),
        ("L3 fetch\n(MongoDB)", mongo_ms, "#4e79a7"),
        ("Deserialize", deser_ms, "#ff9d9a"),
        ("L2 write-back\n(Redis)", redis_put_ms, "#f28e2b"),
        ("Commit", commit_ms, "#e15759"),
    ]

    accounted = sum(w for _, w, _ in steps)
    other = max(0, total_walker - accounted)
    if other > 1:
        steps.append(("Other", other, "#bab0ac"))

    # Filter out zero-width steps
    steps = [(l, w, c) for l, w, c in steps if w > 0.01]

    n_visits = nc(s, "_visit_recursive") or nc(s, "run_typed")

    # Draw waterfall
    fig, ax = plt.subplots(figsize=(16, 5))

    bar_y = 2.0
    offset = 0.0
    small_labels = []
    for label, width, color in steps:
        ax.barh(bar_y, width, left=offset, height=0.6, color=color, edgecolor="white", linewidth=0.5)
        if width > total_walker * 0.06:
            ax.text(
                offset + width / 2, bar_y,
                f"{label}\n{width:.0f}ms",
                ha="center", va="center", fontsize=8, fontweight="bold",
            )
        else:
            small_labels.append((offset, width, label, color))
        offset += width

    for i, (x, w, label, color) in enumerate(small_labels):
        mid = x + w / 2
        y_text = 0.8 - (i % 3) * 0.7
        ax.annotate(
            f"{label} ({w:.0f}ms)",
            xy=(mid, bar_y - 0.3), xytext=(mid, y_text),
            ha="center", va="top", fontsize=7,
            arrowprops=dict(arrowstyle="-", color=color, lw=0.8),
        )

    ax.set_ylim(-1.5, bar_y + 0.8)
    ax.set_xlim(0, offset * 1.02)
    ax.set_yticks([])
    ax.set_xlabel("Time (ms)")
    ax.set_title(
        f"Walker Runtime Timeline ({total_walker:.0f}ms total, {n_visits} visits)",
        fontsize=11, fontweight="bold",
    )
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()

    out = prof_path.rsplit("/", 1)[0] + "/walker_timeline.png" if "/" in prof_path else "walker_timeline.png"
    plt.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()

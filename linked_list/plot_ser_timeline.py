#!/usr/bin/env python3
"""Visualize per-anchor cost breakdown for prefetch and walker runtime paths.

Left panel:  Prefetch path (MongoDB bulk → deserialize → L1)
Right panel: Walker runtime path (L2 miss → L3 fetch → deserialize → L2 write → L1)

Usage:
    python plot_ser_timeline.py [path/to/jac_server.prof]
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
        if funcname not in result:
            result[funcname] = {"nc": 0, "tt": 0.0, "ct": 0.0}
            callers[funcname] = {}
        result[funcname]["nc"] += nc
        result[funcname]["tt"] += tt
        result[funcname]["ct"] += ct
        for (cf, cl, cfn), (ccc, cnc, ctt, cct) in caller_dict.items():
            if cfn not in callers[funcname]:
                callers[funcname][cfn] = {"nc": 0, "ct": 0.0}
            callers[funcname][cfn]["nc"] += cnc
            callers[funcname][cfn]["ct"] += cct
    return result, callers


def main():
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_0/trial_1/jac_server.prof"
    s, cal = load_stats(prof_path)

    n_anchors = s.get("deserialize", {"nc": 1})["nc"]

    # Per-anchor times (ms)
    def ct(fn):
        return s.get(fn, {"ct": 0})["ct"] * 1000 / n_anchors

    def tt(fn):
        return s.get(fn, {"tt": 0})["tt"] * 1000 / n_anchors

    # --- Deserialize breakdown (per anchor) ---
    total_deser = ct("deserialize")
    compute_hash = ct("_compute_hash") * (n_anchors / s.get("_compute_hash", {"nc": 1})["nc"])
    get_type_hints = ct("get_type_hints") * (n_anchors / s.get("get_type_hints", {"nc": 1})["nc"])
    uuid_total = tt("UUID.__init__")
    permission = ct("_deserialize_permission")
    stub = ct("_id_to_stub")
    arch_self = tt("_deserialize_archetype")
    anchor_self = tt("_deserialize_anchor")

    # Compute get_type_hints by subtraction for accuracy
    non_typing = compute_hash + uuid_total + permission + stub + arch_self + anchor_self
    typing_in_deser = max(0, total_deser - non_typing)

    # --- Redis write per anchor (during walker batch_get miss path) ---
    redis_put_total = s.get("RedisBackend.put", {"ct": 0})["ct"] * 1000
    redis_put_nc = s.get("RedisBackend.put", {"nc": 1})["nc"]
    redis_put_per = redis_put_total / redis_put_nc if redis_put_nc > 0 else 0

    # --- MongoDB per anchor (during walker batch_get miss path) ---
    mongo_batch = s.get("MongoBackend.batch_get", {"ct": 0})["ct"] * 1000
    mongo_nc = s.get("MongoBackend.batch_get", {"nc": 1})["nc"]
    mongo_per = mongo_batch / mongo_nc if mongo_nc > 0 else 0

    # --- Redis MGET per anchor (during walker batch_get) ---
    redis_mget = s.get("RedisBackend.batch_get", {"ct": 0})["ct"] * 1000
    redis_mget_nc = s.get("RedisBackend.batch_get", {"nc": 1})["nc"]
    redis_mget_per = redis_mget / redis_mget_nc if redis_mget_nc > 0 else 0

    # --- Snapshot per anchor ---
    snapshot_total = s.get("_snapshot_field_hashes", {"ct": 0})["ct"] * 1000
    snapshot_nc = s.get("_snapshot_field_hashes", {"nc": 1})["nc"]
    snapshot_per = snapshot_total / snapshot_nc if snapshot_nc > 0 else 0

    # ─── Figure ───
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # ─── Left: Prefetch per-anchor ───
    ax1 = axes[0]
    prefetch_parts = [
        ("get_type_hints\n(typing reflection)", typing_in_deser, "#b07aa1"),
        ("_compute_hash\n(re-serialize+hash)", compute_hash, "#e15759"),
        ("UUID construction", uuid_total, "#f28e2b"),
        ("Permission", permission, "#76b7b2"),
        ("Edge stubs", stub, "#edc948"),
        ("Archetype recon.", arch_self, "#59a14f"),
        ("Anchor setup", anchor_self, "#4e79a7"),
    ]

    bottom = 0
    for label, val, color in prefetch_parts:
        ax1.bar(0, val, bottom=bottom, color=color, width=0.5, edgecolor="white")
        if val > total_deser * 0.03:
            ax1.text(0, bottom + val / 2, f"{val:.3f}ms", ha="center", va="center", fontsize=8, fontweight="bold")
        bottom += val
    ax1.text(0, bottom + 0.005, f"{bottom:.3f}ms", ha="center", fontsize=9, fontweight="bold")
    ax1.set_xticks([0])
    ax1.set_xticklabels(["Prefetch\n(per anchor)"], fontsize=9)
    ax1.set_ylabel("Time (ms)")
    ax1.set_title("Prefetch: Deserialize 1 anchor")

    # ─── Right: Walker runtime per-anchor (L2 miss path) ───
    ax2 = axes[1]
    walker_parts = [
        ("Redis MGET", redis_mget_per, "#76b7b2"),
        ("MongoDB query", mongo_per, "#4e79a7"),
        ("get_type_hints", typing_in_deser, "#b07aa1"),
        ("_compute_hash", compute_hash, "#e15759"),
        ("Other deser", uuid_total + permission + stub + arch_self + anchor_self, "#59a14f"),
        ("_snapshot_field_hashes", snapshot_per, "#ff9d9a"),
        ("Redis PUT\n(write-back)", redis_put_per, "#f28e2b"),
    ]
    # Filter zero values
    walker_parts = [(l, v, c) for l, v, c in walker_parts if v > 0.001]

    bottom = 0
    for label, val, color in walker_parts:
        ax2.bar(0, val, bottom=bottom, color=color, width=0.5, edgecolor="white")
        if val > 0.01:
            ax2.text(0, bottom + val / 2, f"{val:.3f}ms", ha="center", va="center", fontsize=8, fontweight="bold")
        bottom += val
    ax2.text(0, bottom + 0.01, f"{bottom:.3f}ms", ha="center", fontsize=9, fontweight="bold")
    ax2.set_xticks([0])
    ax2.set_xticklabels(["Walker fetch\n(per anchor, L2 miss)"], fontsize=9)
    ax2.set_ylabel("Time (ms)")
    ax2.set_title("Walker: Fetch 1 anchor (no prefetch)")

    # Legend
    legend_patches = [
        mpatches.Patch(color="#4e79a7", label="MongoDB"),
        mpatches.Patch(color="#76b7b2", label="Redis read"),
        mpatches.Patch(color="#f28e2b", label="Redis write"),
        mpatches.Patch(color="#b07aa1", label="get_type_hints"),
        mpatches.Patch(color="#e15759", label="_compute_hash"),
        mpatches.Patch(color="#ff9d9a", label="_snapshot_field_hashes"),
        mpatches.Patch(color="#59a14f", label="Other deser work"),
        mpatches.Patch(color="#edc948", label="Edge stubs"),
    ]
    fig.legend(handles=legend_patches, loc="lower center", ncol=4, fontsize=8)

    plt.suptitle(
        f"Per-Anchor Cost: Prefetch vs Walker Runtime\n({n_anchors} anchors)",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout(rect=[0, 0.08, 1, 0.93])
    out = "ser_deser_timeline.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()

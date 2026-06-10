#!/usr/bin/env python3
"""Visualize cross-root resolution as a timeline (waterfall) chart.

Breaks down TopologyIndex.resolve_chain_cross_root into:
  1. mem.get (load foreign root anchors from L1/L2/L3)
  2. TopologyIndex.decode (deserialize binary topology index blobs)
     - UUID construction
     - _get_col (bucket fan-out during edge replay)
     - struct unpacking + other decode overhead
  3. resolve_chain (actual chain resolution on foreign indices)
  4. get_cross_root_ids (identify foreign nodes)

Usage:
    python plot_cross_root_timeline.py [path/to/jac_server.prof]
"""

import pstats
import sys

import matplotlib.pyplot as plt


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


def ct(s, fn):
    return s.get(fn, {"ct": 0})["ct"] * 1000


def nc(s, fn):
    return s.get(fn, {"nc": 0})["nc"]


def caller_ct(cal, fn, caller):
    return cal.get(fn, {}).get(caller, {"ct": 0})["ct"] * 1000


def main():
    prof_path = sys.argv[1] if len(sys.argv) > 1 else "profiles/limit_5000/load_feed/trial_1/jac_server.prof"
    s, cal = load_stats(prof_path)

    total_ms = ct(s, "TopologyIndex.resolve_chain_cross_root")
    n_calls = nc(s, "TopologyIndex.resolve_chain_cross_root")

    if total_ms < 0.01:
        print(f"No cross-root resolution data found in {prof_path}")
        return

    # Sub-calls of resolve_chain_cross_root
    mem_get_ms = caller_ct(cal, "ScaleTieredMemory.get", "TopologyIndex.resolve_chain_cross_root") \
        or caller_ct(cal, "TieredMemory.get", "TopologyIndex.resolve_chain_cross_root")
    topo_get_ms = caller_ct(cal, "NodeAnchor.get_topology_index", "TopologyIndex.resolve_chain_cross_root")
    resolve_ms = caller_ct(cal, "TopologyIndex.resolve_chain", "TopologyIndex.resolve_chain_cross_root")
    cross_ids_ms = caller_ct(cal, "TopologyIndex.get_cross_root_ids", "TopologyIndex.resolve_chain_cross_root")

    # decode breakdown (called by get_topology_index)
    decode_total = caller_ct(cal, "decode", "NodeAnchor.get_topology_index")
    decode_uuid = caller_ct(cal, "UUID.__init__", "decode")
    decode_get_col = caller_ct(cal, "_get_col", "decode")
    decode_keys = caller_ct(cal, "_n_key", "decode") + caller_ct(cal, "_e_key", "decode")
    decode_hash = caller_ct(cal, "UUID.__hash__", "decode")
    decode_other = max(0, decode_total - decode_uuid - decode_get_col - decode_keys - decode_hash)

    n_foreign = nc(s, "NodeAnchor.get_topology_index") - 1  # subtract local root
    n_decode = caller_ct(cal, "decode", "NodeAnchor.get_topology_index")

    # Build timeline
    steps = [
        ("mem.get\n(root anchors)", mem_get_ms, "#76b7b2"),
        ("decode: _get_col\n(bucket fan-out)", decode_get_col, "#e15759"),
        ("decode: UUID\nconstruction", decode_uuid, "#f28e2b"),
        ("decode: hash +\nkey gen", decode_hash + decode_keys, "#ff9d9a"),
        ("decode: struct\n+ overhead", decode_other, "#9c755f"),
        ("resolve_chain\n(query)", resolve_ms, "#4e79a7"),
        ("get_cross_root_ids", cross_ids_ms, "#59a14f"),
    ]

    total_display = sum(w for _, w, _ in steps)
    other = max(0, total_ms - total_display)
    if other > total_ms * 0.02:
        steps.append(("Other", other, "#bab0ac"))

    # Filter out zero-width steps
    steps = [(l, w, c) for l, w, c in steps if w > 0.01]

    if not steps:
        print(f"No meaningful data in {prof_path}")
        return

    total_display = sum(w for _, w, _ in steps)

    # Draw waterfall
    fig, ax = plt.subplots(figsize=(16, 5))

    bar_y = 2.0
    offset = 0.0
    small_labels = []
    for label, width, color in steps:
        ax.barh(bar_y, width, left=offset, height=0.6, color=color, edgecolor="white", linewidth=0.5)
        if width > total_display * 0.06:
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
        f"Cross-Root Resolution Timeline ({total_ms:.0f}ms total, "
        f"{n_calls} calls, ~{n_foreign} foreign roots decoded)",
        fontsize=11, fontweight="bold",
    )
    ax.grid(axis="x", alpha=0.3)

    plt.tight_layout()

    out = prof_path.rsplit("/", 1)[0] + "/cross_root_timeline.png" if "/" in prof_path else "cross_root_timeline.png"
    plt.savefig(out, dpi=200, bbox_inches="tight")
    print(f"Saved to {out}")
    plt.close()


if __name__ == "__main__":
    main()

"""Shared data structures for the prefetch policy sweep runner."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lib.manifest import Manifest


@dataclass
class RequestSpec:
    """One measured walker request."""

    walker: str
    path: str
    body: dict[str, Any] = field(default_factory=dict)
    target_id: str = ""
    request_id: str = ""
    token: str = ""


@dataclass
class CaseState:
    """Stable state prepared once per app/policy/limit case."""

    token: str = ""
    request: RequestSpec | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SweepOptions:
    """Resolved CLI/env options for one manifest run."""

    manifest: "Manifest"
    jac_bin: str
    python_bin: str
    policies: list[str]
    limits: list[int]
    trials: int
    oracle_mode: str
    oracle_dir: Path
    markov_mode: str
    markov_dir: Path
    markov_train_ns: list[int]
    markov_pool_seed: int
    coaccess_mode: str
    coaccess_dir: Path
    coaccess_train_ns: list[int]
    coaccess_pool_seed: int
    coaccess_cluster_threshold: float
    count_mongo: bool
    env: dict[str, str]

    @classmethod
    def from_env(cls, manifest: "Manifest", jac_bin: str | None = None) -> "SweepOptions":
        env = os.environ.copy()
        resolved_jac = jac_bin or env.get("JAC_BIN") or _default_jac_bin()
        python_bin = env.get("PYTHON_BIN") or _sibling_python(resolved_jac) or "python3"
        return cls(
            manifest=manifest,
            jac_bin=resolved_jac,
            python_bin=python_bin,
            policies=_split_words(env.get("SWEEP_POLICIES") or "ttg"),
            limits=_parse_int_list(env.get("SWEEP_PREFETCH_LIMITS"), [0, 1000]),
            trials=int(
                env.get("JAC_TRIALS")
                or env.get("SWEEP_TRIALS")
                or "30"
            ),
            oracle_mode=(env.get("SWEEP_ORACLE_MODE") or "auto").strip().lower(),
            oracle_dir=Path(env.get("SWEEP_ORACLE_DIR") or (manifest.app_dir / "oracle_plans")),
            markov_mode=(env.get("SWEEP_MARKOV_MODE") or "auto").strip().lower(),
            markov_dir=Path(env.get("SWEEP_MARKOV_DIR") or (manifest.app_dir / "markov_models")),
            markov_train_ns=_parse_int_list(env.get("SWEEP_MARKOV_TRAIN_NS"), [5]),
            markov_pool_seed=int(env.get("SWEEP_MARKOV_POOL_SEED") or "42"),
            coaccess_mode=(env.get("SWEEP_COACCESS_MODE") or "auto").strip().lower(),
            coaccess_dir=Path(env.get("SWEEP_COACCESS_DIR") or (manifest.app_dir / "coaccess_models")),
            coaccess_train_ns=_parse_int_list(
                env.get("SWEEP_COACCESS_TRAIN_NS") or env.get("SWEEP_MARKOV_TRAIN_NS"),
                [5],
            ),
            coaccess_pool_seed=int(
                env.get("SWEEP_COACCESS_POOL_SEED")
                or env.get("SWEEP_MARKOV_POOL_SEED")
                or "42"
            ),
            coaccess_cluster_threshold=float(env.get("SWEEP_COACCESS_CLUSTER_THRESHOLD") or "0.05"),
            count_mongo=bool(env.get("JAC_COUNT_MONGO")),
            env=env,
        )


@dataclass
class TrialResult:
    policy: str
    walker: str
    prefetch_limit: int
    trial: int
    e2e_ms: float
    request_id: str = ""
    train_n: str = ""
    trial_count: str = ""
    pool_seed: str = ""
    coverage: str = ""
    accuracy: str = ""
    actual_ids: str = ""
    plan_ids: str = ""
    covered_ids: str = ""
    overfetch_ids: str = ""
    undercoverage_ids: str = ""
    topo_idx_ms: str = ""
    ttg_ms: str = ""
    prefetch_ms: str = ""
    walker_ms: str = ""
    l1_hit_rate: str = ""
    l1: str = ""
    l2: str = ""
    l3: str = ""
    miss: str = ""
    mongo_q: str = ""
    oracle_file: str = ""
    model_file: str = ""


def _split_words(raw: str) -> list[str]:
    return [x.strip().lower() for x in raw.replace(",", " ").split() if x.strip()]


def _parse_int_list(raw: str | None, default: list[int]) -> list[int]:
    if not raw:
        return list(default)
    out: list[int] = []
    for item in raw.replace(",", " ").split():
        if item.strip():
            out.append(int(item))
    return out or list(default)


def _sibling_python(jac_bin: str) -> str:
    path = Path(jac_bin).expanduser()
    if "/" not in jac_bin:
        return ""
    candidate = path.parent / "python"
    return str(candidate) if candidate.exists() else ""


def _default_jac_bin() -> str:
    candidates = [
        Path.home() / "Space" / "jaseci_env" / "jaseci" / ".venv" / "bin" / "jac",
        Path.home() / "Space" / "jaseci" / "jac" / "zig-out" / "bin" / "jac",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "jac"

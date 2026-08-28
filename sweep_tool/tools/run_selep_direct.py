"""Run the original SeLeP SQL/block-level baseline from sweep_tool.

This wrapper does not translate SeLeP predictions into Jac UUIDs.  It
validates the files the original SeLeP pipeline expects, then calls
``selep_main.main`` inside the SeLeP checkout.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SWEEP_TOOL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SWEEP_TOOL_ROOT))

from lib import selep_direct  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-env", action="store_true", help="read SELEP_* settings from the environment")
    parser.add_argument("--check", action="store_true", help="only validate files/configuration")
    parser.add_argument("--repo", default=str(selep_direct.DEFAULT_SELEP_REPO))
    parser.add_argument("--python", default=str(selep_direct.DEFAULT_SELEP_PYTHON))
    parser.add_argument("--mode", choices=["test", "train-test"], default="train-test")
    parser.add_argument("--db-name", default="sdss_1")
    parser.add_argument("--db-user", default="user")
    parser.add_argument("--db-password", default="pass")
    parser.add_argument("--db-host", default="127.0.0.1")
    parser.add_argument("--db-port", default="5432")
    parser.add_argument("--model-name", default="binary_cross_entropy2")
    parser.add_argument("--result-name", default="binary_lstm2")
    parser.add_argument("--config-suffix", default="")
    parser.add_argument("--test-repeat", type=int, default=1)
    parser.add_argument("--total-repeat", type=int, default=1)
    parser.add_argument("--cache-size", type=int, default=66000)
    parser.add_argument("--prefetching-k", type=int, default=42)
    parser.add_argument("--max-partition-size", type=int, default=128)
    parser.add_argument("--logical-block-size", type=int, default=8)
    parser.add_argument("--look-back", type=int, default=4)
    parser.add_argument("--measure-time", action="store_true")
    parser.add_argument("--optimize", action="store_true")
    parser.add_argument("--read-table-manager", action="store_true")
    parser.add_argument("--read-partition-manager", action="store_true")
    parser.add_argument("--read-affinity-matrix", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    return parser


def _config_from_args(args: argparse.Namespace) -> selep_direct.SelepDirectConfig:
    if args.from_env:
        return selep_direct.config_from_env()
    return selep_direct.SelepDirectConfig(
        repo=Path(args.repo).expanduser().resolve(),
        python=Path(args.python).expanduser().resolve(),
        mode=args.mode,
        db_name=args.db_name,
        db_user=args.db_user,
        db_password=args.db_password,
        db_host=args.db_host,
        db_port=args.db_port,
        model_name=args.model_name,
        result_name=args.result_name,
        config_suffix=args.config_suffix,
        test_repeat=args.test_repeat,
        total_repeat=args.total_repeat,
        cache_size=args.cache_size,
        prefetching_k=args.prefetching_k,
        max_partition_size=args.max_partition_size,
        logical_block_size=args.logical_block_size,
        look_back=args.look_back,
        measure_time=args.measure_time,
        optimize=args.optimize,
        read_table_manager=args.read_table_manager,
        read_partition_manager=args.read_partition_manager,
        read_affinity_matrix=args.read_affinity_matrix,
        save_to_file=not args.no_save,
    )


def _ensure_output_dirs(repo: Path) -> None:
    for rel in (
        "Results",
        "SavedFiles/Models",
        "SavedFiles/TableManagers",
        "SavedFiles/PartitionManagers",
        "SavedFiles/PartitionManager",
        "SavedFiles/AffinityMatrices",
    ):
        (repo / rel).mkdir(parents=True, exist_ok=True)


def _run(config: selep_direct.SelepDirectConfig) -> None:
    sys.path.insert(0, str(config.repo))
    os.chdir(config.repo)
    _ensure_output_dirs(config.repo)

    from Configuration.config import Config, alter_config
    import selep_main
    from main import get_tables_actual_bid_range, get_tables_bid_range

    Config.db_name = config.db_name
    Config.db_user = config.db_user
    Config.db_password = config.db_password
    Config.db_host = config.db_host
    Config.db_port = config.db_port
    Config.logical_block_size = config.logical_block_size
    Config.max_partition_size = config.max_partition_size
    Config.look_back = config.look_back
    Config.prefetching_k = config.prefetching_k
    alter_config(config.db_name, config.max_partition_size)

    selep_main.cache_size = config.cache_size
    selep_main.read_tb_manager = 1 if config.read_table_manager else 0
    selep_main.read_par_manager = 1 if config.read_partition_manager else 0
    selep_main.read_aff_matrix = 1 if config.read_affinity_matrix else 0
    selep_main.result_base_path = "./Results"
    selep_main.base_model_file_dir = "./SavedFiles/Models/"

    print("=== direct SeLeP SQL/block baseline ===", flush=True)
    print(f"repo={config.repo}", flush=True)
    print(f"mode={config.mode}", flush=True)
    print(f"db={config.db_name}@{config.db_host}:{config.db_port}", flush=True)
    print(
        "WB="
        f"{Config.logical_block_size} WP={Config.max_partition_size} "
        f"k={Config.prefetching_k} cache_size={selep_main.cache_size}",
        flush=True,
    )

    Config.tb_bid_range = get_tables_bid_range()
    Config.actual_tb_bid_range = get_tables_actual_bid_range()
    selep_main.main(
        config.model_name,
        config.result_name,
        do_train=1 if config.do_train else 0,
        config_suffix=config.config_suffix,
        test_repeat=config.test_repeat,
        total_repeat=config.total_repeat,
        measure_time=config.measure_time,
        do_optimize=1 if config.optimize else 0,
        save_to_file=config.save_to_file,
    )


def main() -> int:
    args = _parser().parse_args()
    config = _config_from_args(args)
    problems = selep_direct.validate(config)
    if problems:
        selep_direct.write_metadata(config, "blocked", problems)
        print("Direct SeLeP baseline is not ready:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 2

    if args.check:
        selep_direct.write_metadata(config, "ready")
        print("Direct SeLeP baseline is ready.")
        for path in selep_direct.expected_workload_files(config):
            print(f"workload: {path}")
        return 0

    selep_direct.write_metadata(config, "running")
    try:
        _run(config)
    except Exception as exc:
        selep_direct.write_metadata(config, "failed", [repr(exc)])
        raise
    selep_direct.write_metadata(config, "done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

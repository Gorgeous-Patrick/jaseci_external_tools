"""Streamlit entry point for the sweep tool.

Six tabs, all backed by the app's live output directory on disk:

  1. Run — kick off a sweep for a chosen app.  Fire-and-forget subprocess.
  2. Random paired — compare policies on the same random request set.
  3. Analyze — read the app's current CSV + logs, render interactive charts.
  4. Raw data — the CSV as a downloadable dataframe.
  5. Churn — run/analyze the Jacord same-spawn churn experiment.
  6. SeLeP — run the LinkedList SQL/block LSTM smoke experiment.

Archiving isn't the tool's job; commit interesting runs to git.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import streamlit as st

from lib import manifest as mf
from lib import parsers, charts, sweep_runner
from lib import selep_sweep

APP_ROOT = Path(__file__).resolve().parent
MANIFEST_DIR = APP_ROOT / "manifests"
DEFAULT_PAIR_APPS = ("linked_list", "jacord")


st.set_page_config(page_title="Sweep tool", layout="wide")


@st.cache_data
def load_manifests(_cache_key: tuple[tuple[str, int], ...]) -> list[mf.Manifest]:
    return mf.discover(MANIFEST_DIR)


manifest_cache_key = tuple(
    sorted((p.name, p.stat().st_mtime_ns) for p in MANIFEST_DIR.glob("*.yaml"))
)
manifests = load_manifests(manifest_cache_key)
if not manifests:
    st.error(f"No manifests found in {MANIFEST_DIR}. Add one and rerun.")
    st.stop()
manifest_by_name = {m.name: m for m in manifests}
default_run_all_manifests = [
    manifest_by_name[name] for name in mf.DEFAULT_APP_ORDER if name in manifest_by_name
]


def _parse_int_list(text: str) -> list[int]:
    return [int(x) for x in text.split() if x.strip()]


def _random_paired_values(
    n: int,
    train_k: int,
    seed: int,
    policies: str,
    limits: list[int] | None,
    selep_values: dict[str, object] | None = None,
) -> dict:
    values = {
        "SWEEP_POLICIES": "random-paired",
        "SWEEP_RANDOM_N": n,
        "SWEEP_RANDOM_TRAIN_K": train_k,
        "SWEEP_RANDOM_SEED": seed,
        "SWEEP_RANDOM_POLICIES": policies,
        "SWEEP_MARKOV_POOL_SIZE": n + train_k,
    }
    if "selep" in {part.strip().lower() for part in policies.split()} and selep_values:
        values.update(selep_values)
    if limits is not None:
        values["SWEEP_PREFETCH_LIMITS"] = limits
    return values


def _manifest_param_default(manifest: mf.Manifest, name: str, fallback: object = "") -> object:
    for param in manifest.parameters:
        if param.name == name:
            return param.default
    return fallback


def _format_int_list(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(str(x) for x in value)
    return str(value or "")


def _render_log_tail(
    path: Path,
    *,
    refresh_key: str,
    missing_label: str,
    max_bytes: int = 15_000,
    clear_cache: bool = False,
) -> None:
    label_col, refresh_col = st.columns([5, 1])
    with label_col:
        st.caption(f"tail of `{path}`")
    with refresh_col:
        if st.button("Refresh", key=refresh_key, use_container_width=True):
            if clear_cache:
                st.cache_data.clear()
            st.rerun()
    if path.exists():
        text = path.read_text()
        if len(text) > max_bytes:
            text = "(truncated head)\n" + text[-max_bytes:]
        st.code(text or "(empty)", language="text")
    else:
        st.info(f"No {missing_label} at `{path}` yet.")


tab_run, tab_random, tab_analyze, tab_raw, tab_churn, tab_selep = st.tabs(
    ["Run", "Random paired", "Analyze", "Raw data", "Churn", "SeLeP"]
)


# ---------------------------------------------------------------------------
# TAB 1 — Run sweep
# ---------------------------------------------------------------------------
with tab_run:
    st.header("Run a sweep")

    # ---- jac binary (applies to every sweep launched from this tab) ----
    jac_bin = st.text_input(
        "jac binary (JAC_BIN)",
        value=sweep_runner.DEFAULT_JAC_BIN,
        key="jac_bin",
        help=(
            "Path to the jac binary every sweep runs against. Defaults to the "
            "locally-built zig `jac`. Exported as JAC_BIN and honoured by each "
            "sweep script via ${JAC_BIN:-jac}. Applies to both per-app and "
            "Run-all sweeps."
        ),
    ).strip()
    jac_bin = str(Path(jac_bin).expanduser()) if jac_bin else "jac"
    if "/" in jac_bin and not Path(jac_bin).exists():
        st.warning(f"JAC_BIN path does not exist: `{jac_bin}`")

    # ---- Run all (shepherd over the default benchmark manifests, sequential) ----
    st.subheader("Run all sweeps")
    st.caption(
        "Kicks off the default benchmark sweeps sequentially with each app's "
        "default parameters. Presets use the same default-parameter path. "
        "Some apps share Postgres container "
        "names, so parallel isn't safe."
    )
    all_running, all_pid = sweep_runner.is_run_all_running()
    ra_status, ra_kill, ra_launch, ra_pair = st.columns([3, 1, 1, 2])
    with ra_status:
        if all_running:
            st.warning(f"⏳ Run-all is in progress (shepherd pid={all_pid}).")
        else:
            st.info("No run-all sweep is currently in progress.")
    with ra_kill:
        if all_running and st.button("Stop all", type="secondary", key="run_all_kill"):
            msg = sweep_runner.kill_run_all()
            st.success(msg)
            st.rerun()
    with ra_launch:
        if not all_running and st.button("Run all", type="primary", key="run_all_go"):
            info = sweep_runner.kickoff_all(default_run_all_manifests, jac_bin=jac_bin)
            st.success(
                f"Launched shepherd (pid={info.pid}) over "
                f"{len(default_run_all_manifests)} manifest(s).  Watch progress in "
                f"`{info.stdout_log}` or the Analyze tab per app."
            )
            st.rerun()
    with ra_pair:
        pair_manifests = [
            manifest_by_name[name] for name in DEFAULT_PAIR_APPS if name in manifest_by_name
        ]
        missing_pair = [name for name in DEFAULT_PAIR_APPS if name not in manifest_by_name]
        if missing_pair:
            st.warning(f"Missing preset manifest(s): {', '.join(missing_pair)}")
        elif (
            not all_running
            and st.button(
                "Run LinkedList + Jacord",
                type="primary",
                key="run_linked_jacord_defaults",
                help="Runs linked_list and jacord sequentially with manifest default values.",
            )
        ):
            info = sweep_runner.kickoff_all(pair_manifests, jac_bin=jac_bin)
            app_list = ", ".join(m.name for m in pair_manifests)
            st.success(
                f"Launched default sweeps for {app_list} "
                f"(shepherd pid={info.pid}). Watch progress in `{info.stdout_log}`."
            )
            st.rerun()
    if sweep_runner.run_all_log_path().exists():
        with st.expander("Tail of run_all.log", expanded=False):
            _render_log_tail(
                sweep_runner.run_all_log_path(),
                refresh_key="run_all_refresh_log",
                missing_label="run-all output",
            )

    st.divider()

    # ---- Per-app sweep (existing single-manifest form) ----
    app_name = st.selectbox(
        "App",
        [m.name for m in manifests],
        key="run_app",
    )
    m = manifest_by_name[app_name]
    st.caption(m.description)
    st.write(
        f"**app_dir**: `{m.app_dir}`  ·  **runner**: `{m.runner}`"
        f"  ·  **script**: `{m.sweep_script}`"
    )

    # Status + kill controls.  Detected via the PID file the runner
    # writes; robust across Streamlit restarts.
    running, live_pid = sweep_runner.is_running(m)
    col_status, col_kill = st.columns([3, 1])
    with col_status:
        if running:
            st.warning(f"⏳ Sweep is running (pid={live_pid}).")
        else:
            st.info("No sweep is currently running for this app.")
    with col_kill:
        if running and st.button("Stop sweep", type="secondary", key="run_kill"):
            msg = sweep_runner.kill(m)
            st.success(msg)
            st.rerun()

    with st.form("sweep_form"):
        form_values: dict = {}
        for p in m.parameters:
            if p.kind == "int_list":
                default_txt = " ".join(str(x) for x in (p.default or []))
                txt = st.text_input(p.label, value=default_txt, help=p.help)
                form_values[p.name] = [int(x) for x in txt.split() if x.strip()]
            elif p.kind == "int":
                form_values[p.name] = st.number_input(
                    p.label, value=int(p.default or 0), step=1, help=p.help
                )
            elif p.kind == "enum":
                form_values[p.name] = st.selectbox(
                    p.label,
                    p.choices,
                    index=(p.choices.index(p.default) if p.default in p.choices else 0),
                    help=p.help,
                )
            else:
                form_values[p.name] = st.text_input(
                    p.label, value=str(p.default or ""), help=p.help
                )
        submitted = st.form_submit_button("Run sweep")

    if submitted:
        info = sweep_runner.kickoff(m, form_values, jac_bin=jac_bin)
        st.success(
            f"Started sweep for **{app_name}** (pid={info.pid}). "
            f"Fire-and-forget — switch to the Analyze tab when it's done."
        )
        with st.expander("Env vars passed to the sweep", expanded=False):
            st.code(
                "\n".join(f"{k}={v}" for k, v in sorted(info.env_overrides.items()))
            )

    # Sweep output viewer.  Always visible (independent of whether we
    # just submitted) so the user can come back to the tab and check on
    # a long-running sweep.
    st.divider()
    st.subheader("Sweep output")
    log_path = sweep_runner.stdout_log_path(m)
    _render_log_tail(
        log_path,
        refresh_key="run_refresh_log",
        missing_label="sweep output",
    )


# ---------------------------------------------------------------------------
# TAB 2 — Random paired sweep
# ---------------------------------------------------------------------------
with tab_random:
    st.header("Random paired")
    st.caption(
        "Trains predictors on K sampled requests, then runs the same N-request "
        "stream across policies without resetting DB state between requests. "
        "Trials is ignored in this mode."
    )

    random_jac_bin = st.text_input(
        "jac binary (JAC_BIN)",
        value=sweep_runner.DEFAULT_JAC_BIN,
        key="random_jac_bin",
    ).strip()
    random_jac_bin = str(Path(random_jac_bin).expanduser()) if random_jac_bin else "jac"
    if "/" in random_jac_bin and not Path(random_jac_bin).exists():
        st.warning(f"JAC_BIN path does not exist: `{random_jac_bin}`")

    random_app_options = [m.name for m in default_run_all_manifests]
    selected_random_apps = st.multiselect(
        "Apps",
        random_app_options,
        default=random_app_options,
        key="random_apps",
    )
    random_defaults_manifest = (
        manifest_by_name[selected_random_apps[0]]
        if selected_random_apps and selected_random_apps[0] in manifest_by_name
        else default_run_all_manifests[0]
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        random_n = st.number_input(
            "Measured N",
            value=int(_manifest_param_default(random_defaults_manifest, "SWEEP_RANDOM_N", 20)),
            min_value=1,
            step=1,
            key="random_n",
        )
    with c2:
        random_seed = st.number_input(
            "Random paired seed",
            value=int(_manifest_param_default(random_defaults_manifest, "SWEEP_RANDOM_SEED", 42)),
            step=1,
            key="random_seed",
        )
    with c3:
        random_policies = st.text_input(
            "Random paired policies",
            value=str(_manifest_param_default(random_defaults_manifest, "SWEEP_RANDOM_POLICIES", "none dbridge_like ttg selep")),
            help="Supported in stream mode: none, dbridge_like, ttg, selep, history, manual.",
            key="random_policies",
        )

    st.caption(
        "Random-paired runs the same measured stream across policies. "
        "Train K and TTG limits are app-specific below. SeLeP settings shown here are passed to every selected app."
    )

    with st.expander("SeLeP settings", expanded=True):
        model_choices = ["faithful", "lstm", "frequency", "original"]
        default_model_kind = str(
            _manifest_param_default(random_defaults_manifest, "SELEP_MODEL_KIND", "faithful")
        )
        if default_model_kind not in model_choices:
            default_model_kind = "faithful"
        block_source_choices = ["jac-ctid", "pg-buffercache", "hash"]
        default_block_source = str(
            _manifest_param_default(random_defaults_manifest, "SELEP_BLOCK_SOURCE", "jac-ctid")
        )
        if default_block_source not in block_source_choices:
            default_block_source = "jac-ctid"
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            selep_model_kind = st.selectbox(
                "SeLeP model",
                model_choices,
                index=model_choices.index(default_model_kind),
                key="random_selep_model_kind",
            )
            selep_top_k = st.number_input(
                "SeLeP top-k partitions",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_TOP_K", 42)),
                min_value=1,
                step=1,
                key="random_selep_top_k",
            )
        with sc2:
            selep_look_back = st.number_input(
                "SeLeP lookback",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_LOOK_BACK", 4)),
                min_value=1,
                step=1,
                key="random_selep_look_back",
            )
            selep_partition_size = st.number_input(
                "SeLeP partition size",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_PARTITION_SIZE", 128)),
                min_value=1,
                step=1,
                key="random_selep_partition_size",
            )
        with sc3:
            selep_block_limit = st.number_input(
                "SeLeP block cap",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_BLOCK_LIMIT", 0)),
                min_value=0,
                step=1,
                key="random_selep_block_limit",
            )
            selep_max_block_selects = st.number_input(
                "SeLeP max SELECTs",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_MAX_BLOCK_SELECTS", 0)),
                min_value=0,
                step=1,
                key="random_selep_max_block_selects",
            )
        with sc4:
            selep_lstm_epochs = st.number_input(
                "SeLeP epochs",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_LSTM_EPOCHS", 75)),
                min_value=1,
                step=1,
                key="random_selep_lstm_epochs",
            )
            selep_lstm_batch_size = st.number_input(
                "SeLeP batch size",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_LSTM_BATCH_SIZE", 32)),
                min_value=1,
                step=1,
                key="random_selep_lstm_batch_size",
            )
        vf1, vf2, vf3, vf4 = st.columns(4)
        with vf1:
            selep_test_fraction = st.text_input(
                "SeLeP test fraction",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_TEST_FRACTION", "0.10")),
                key="random_selep_test_fraction",
            )
        with vf2:
            selep_validation_fraction = st.text_input(
                "SeLeP validation fraction",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_LSTM_VALIDATION_FRACTION", "0.10")),
                key="random_selep_validation_fraction",
            )
        with vf3:
            selep_encoding_epochs = st.number_input(
                "SeLeP encoding epochs",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_ENCODING_EPOCHS", 100)),
                min_value=1,
                step=1,
                key="random_selep_encoding_epochs",
            )
        with vf4:
            selep_rows_per_block = st.number_input(
                "Rows per block",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_SEMANTIC_ROWS_PER_BLOCK", 64)),
                min_value=1,
                step=1,
                key="random_selep_rows_per_block",
            )
        ec1, ec2 = st.columns([1, 1])
        with ec1:
            selep_encoding_length = st.number_input(
                "SeLeP encoding length",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_ENCODING_LENGTH", 32)),
                min_value=1,
                step=1,
                key="random_selep_encoding_length",
            )
        with ec2:
            selep_table_encoding_method = st.text_input(
                "SeLeP table encoder",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_TABLE_ENCODING_METHOD", "AutoEncoder_1")),
                key="random_selep_table_encoding_method",
            )
        clay1, clay2, clay3, clay4 = st.columns(4)
        with clay1:
            selep_clay_repartition_threshold = st.number_input(
                "Clay repartition threshold",
                value=int(_manifest_param_default(random_defaults_manifest, "SELEP_CLAY_REPARTITION_THRESHOLD", 2500)),
                min_value=1,
                step=1,
                key="random_selep_clay_repartition_threshold",
            )
        with clay2:
            selep_clay_initial_fill = st.text_input(
                "Clay initial fill",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_CLAY_INITIAL_FILL", "0.90")),
                key="random_selep_clay_initial_fill",
            )
        with clay3:
            selep_clay_empty_fraction = st.text_input(
                "Clay empty fraction",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_CLAY_EMPTY_FRACTION", "0.10")),
                key="random_selep_clay_empty_fraction",
            )
        with clay4:
            selep_clay_max_load = st.text_input(
                "Clay max load",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_CLAY_MAX_LOAD", "1.0")),
                key="random_selep_clay_max_load",
            )
            selep_clay_weight_reset = st.text_input(
                "Clay weight reset",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_CLAY_WEIGHT_RESET", "0.10")),
                key="random_selep_clay_weight_reset",
            )
        dc1, dc2, dc3 = st.columns([1, 2, 1])
        with dc1:
            selep_block_source = st.selectbox(
                "SeLeP block source",
                block_source_choices,
                index=block_source_choices.index(default_block_source),
                key="random_selep_block_source",
            )
        with dc2:
            selep_relation_allowlist = st.text_input(
                "SeLeP relations",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_RELATION_ALLOWLIST", "anchors,graph_types")),
                key="random_selep_relation_allowlist",
            )
        with dc3:
            selep_relation_kinds = st.text_input(
                "SeLeP relation kinds",
                value=str(_manifest_param_default(random_defaults_manifest, "SELEP_RELATION_KINDS", "r")),
                key="random_selep_relation_kinds",
            )
    random_selep_values = {
        "SELEP_MODEL_KIND": selep_model_kind,
        "SELEP_TOP_K": int(selep_top_k),
        "SELEP_LOOK_BACK": int(selep_look_back),
        "SELEP_PARTITION_SIZE": int(selep_partition_size),
        "SELEP_BLOCK_LIMIT": int(selep_block_limit),
        "SELEP_BLOCK_SOURCE": selep_block_source,
        "SELEP_RELATION_ALLOWLIST": selep_relation_allowlist,
        "SELEP_RELATION_KINDS": selep_relation_kinds,
        "SELEP_MAX_BLOCK_SELECTS": int(selep_max_block_selects),
        "SELEP_CLAY_REPARTITION_THRESHOLD": int(selep_clay_repartition_threshold),
        "SELEP_CLAY_INITIAL_FILL": selep_clay_initial_fill,
        "SELEP_CLAY_EMPTY_FRACTION": selep_clay_empty_fraction,
        "SELEP_CLAY_MAX_LOAD": selep_clay_max_load,
        "SELEP_CLAY_WEIGHT_RESET": selep_clay_weight_reset,
        "SELEP_TEST_FRACTION": selep_test_fraction,
        "SELEP_ENCODING_LENGTH": int(selep_encoding_length),
        "SELEP_ENCODING_EPOCHS": int(selep_encoding_epochs),
        "SELEP_TABLE_ENCODING_METHOD": selep_table_encoding_method,
        "SELEP_SEMANTIC_ROWS_PER_BLOCK": int(selep_rows_per_block),
        "SELEP_LSTM_EPOCHS": int(selep_lstm_epochs),
        "SELEP_LSTM_BATCH_SIZE": int(selep_lstm_batch_size),
        "SELEP_LSTM_VALIDATION_FRACTION": selep_validation_fraction,
    }

    random_limits_by_name: dict[str, str] = {}
    random_train_k_by_name: dict[str, int] = {}
    for name in selected_random_apps:
        m_for_limits = manifest_by_name.get(name)
        if m_for_limits is None:
            continue
        default_limits = _format_int_list(
            _manifest_param_default(m_for_limits, "SWEEP_PREFETCH_LIMITS", "")
        )
        default_train_k = int(_manifest_param_default(m_for_limits, "SWEEP_RANDOM_TRAIN_K", 20))
        tc, lc = st.columns([1, 3])
        with tc:
            random_train_k_by_name[name] = int(
                st.number_input(
                    f"{name} Train K",
                    value=default_train_k,
                    min_value=0,
                    step=1,
                    key=f"random_train_k_{name}",
                )
            )
        with lc:
            random_limits_by_name[name] = st.text_input(
                f"{name} TTG limits",
                value=default_limits,
                key=f"random_limits_{name}",
            )

    random_running, random_pid = sweep_runner.is_run_all_running()
    rr_status, rr_kill, rr_launch = st.columns([3, 1, 1])
    with rr_status:
        if random_running:
            st.warning(f"Run-all is in progress (shepherd pid={random_pid}).")
        else:
            st.info("No run-all sweep is currently in progress.")
    with rr_kill:
        if random_running and st.button("Stop all", type="secondary", key="random_kill"):
            msg = sweep_runner.kill_run_all()
            st.success(msg)
            st.rerun()
    with rr_launch:
        if not random_running and st.button("Run all", type="primary", key="random_run_all"):
            random_manifests = [
                manifest_by_name[name]
                for name in selected_random_apps
                if name in manifest_by_name
            ]
            if not random_manifests:
                st.error("Select at least one app.")
                st.stop()
            form_values_by_name = {}
            for manifest in random_manifests:
                raw_limits = random_limits_by_name.get(manifest.name, "").strip()
                try:
                    limits = _parse_int_list(raw_limits) if raw_limits else None
                except ValueError as e:
                    st.error(
                        f"{manifest.name} TTG limits must be space-separated integers: {e}"
                    )
                    st.stop()
                form_values_by_name[manifest.name] = _random_paired_values(
                    int(random_n),
                    int(random_train_k_by_name.get(manifest.name, 20)),
                    int(random_seed),
                    random_policies,
                    limits,
                    random_selep_values,
                )
            info = sweep_runner.kickoff_all(
                random_manifests,
                form_values_by_name=form_values_by_name,
                jac_bin=random_jac_bin,
            )
            st.success(
                f"Launched random-paired run-all (pid={info.pid}) over "
                f"{len(random_manifests)} app(s). Watch `{info.stdout_log}`."
            )
            st.rerun()

    if sweep_runner.run_all_log_path().exists():
        with st.expander("Tail of run_all.log", expanded=False):
            _render_log_tail(
                sweep_runner.run_all_log_path(),
                refresh_key="random_run_all_refresh_log",
                missing_label="run-all output",
            )

    summary_rows = []
    for name in selected_random_apps:
        m = manifest_by_name.get(name)
        if m is None:
            continue
        logs_dir = m.app_dir / m.logs_dir
        for path in sorted(logs_dir.glob("random_paired_stream_*_summary.json"))[-20:]:
            try:
                row = json.loads(path.read_text())
            except Exception:
                continue
            summary_rows.append(
                {
                    "app": name,
                    "policy": row.get("policy", ""),
                    "limit": row.get("prefetch_limit", ""),
                    "N": row.get("measured_n", ""),
                    "K": row.get("train_k", ""),
                    "sum_e2e_ms": row.get("sum_request_e2e_ms", ""),
                    "stream_wall_ms": row.get("stream_wall_ms", ""),
                    "train_ms": row.get("train_ms", ""),
                    "l1_hit_rate": row.get("l1_hit_rate", ""),
                    "summary": row.get("summary_path", str(path)),
                }
            )
    if summary_rows:
        st.subheader("Recent stream summaries")
        st.dataframe(summary_rows, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# TAB 3 — Analyze
# ---------------------------------------------------------------------------
with tab_analyze:
    st.header("Analyze")
    app_name = st.selectbox(
        "App",
        [m.name for m in manifests],
        key="analyze_app",
    )
    m = manifest_by_name[app_name]
    st.caption(f"csv: `{m.app_dir / m.results_csv}`  ·  logs: `{m.app_dir / m.logs_dir}`")

    if st.button("Reload", key="analyze_reload"):
        st.cache_data.clear()
        st.rerun()

    df = parsers.load_csv(m.app_dir / m.results_csv)
    logs = parsers.parse_logs_dir(m.app_dir / m.logs_dir)
    df = parsers.apply_log_tier_counts(df, logs)

    if df.empty and not logs:
        st.warning(
            f"Nothing to analyze.  Either kick off a sweep, or drop "
            f"`{m.results_csv}` and/or `{m.logs_dir}/` under `{m.app_dir}`."
        )
    else:
        summary = charts.hit_rate_summary(df)
        if not summary.empty:
            st.subheader("Hit-rate summary")
            st.dataframe(summary, use_container_width=True, hide_index=True)

        # Render each chart only if it has data; otherwise the panel is
        # a blank axes block, which is confusing.  Older sweeps predate
        # the [HIT-STATS-SERIES] / [PREFETCH-WORKER-TIMES] markers, so
        # log-based charts come back empty for them.
        chart_specs = [
            ("chart_l1_hit_rate_by_policy", charts.l1_hit_rate_by_policy, (df,)),
            ("chart_cache_tier_mix", charts.cache_tier_mix, (df,)),
            ("chart_e2e_stack", charts.e2e_stack, (df,)),
            ("chart_memory_time_reduction", charts.memory_time_reduction, (df, m.app_dir / m.profiles_dir)),
            ("chart_db_request_count", charts.db_request_count, (df, logs)),
            ("chart_db_access_by_op", charts.db_access_by_op, (logs,)),
            ("chart_coverage", charts.coverage, (df, logs)),
            ("chart_hit_counts_request_done", charts.hit_counts_request_done, (logs,)),
            ("chart_hit_counts_pw_phase", charts.hit_counts_pw_phase, (logs,)),
            ("chart_worker_times", charts.worker_times, (logs,)),
        ]
        rendered_any = False
        for key, fn, args in chart_specs:
            fig = fn(*args)
            if not fig.data:  # empty figure — skip
                continue
            st.plotly_chart(fig, use_container_width=True, key=key)
            rendered_any = True
        if not rendered_any:
            st.info(
                "The data on disk is missing the log markers this "
                "tool visualizes.  Re-run the sweep with the current "
                "jaclang runtime to see the hit-stats / worker-times "
                "charts."
            )


# ---------------------------------------------------------------------------
# TAB 4 — Sweep data
# ---------------------------------------------------------------------------
with tab_raw:
    st.header("Sweep data")
    app_name = st.selectbox(
        "App",
        [m.name for m in manifests],
        key="raw_app",
    )
    m = manifest_by_name[app_name]
    csv_path = m.app_dir / m.results_csv
    st.caption(
        f"path: `{csv_path}`"
        "  ·  tier columns prefer request_done counters from logs when available"
    )

    df = parsers.load_csv(csv_path)
    logs = parsers.parse_logs_dir(m.app_dir / m.logs_dir)
    df = parsers.apply_log_tier_counts(df, logs)
    if df.empty:
        st.warning(f"No CSV found at `{csv_path}`.")
    else:
        st.dataframe(charts.csv_raw(df), use_container_width=True)
        st.download_button(
            "Download CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=csv_path.name,
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# TAB 5 — Jacord churn experiment
# ---------------------------------------------------------------------------
with tab_churn:
    st.header("Jacord churn")
    jacord_manifest = manifest_by_name.get("jacord")
    if jacord_manifest is None:
        st.error("The jacord manifest is not available.")
    else:
        st.caption(
            "Same-spawn stale-history experiment. Generates deterministic "
            "churn dumps by mutating Jacord through Jac walkers, restarts "
            "the full DB stack after mutation, then measures cold runs."
        )

        running, live_pid = sweep_runner.is_jacord_churn_running(jacord_manifest)
        col_status, col_kill = st.columns([3, 1])
        with col_status:
            if running:
                st.warning(f"Jacord churn is running (pid={live_pid}).")
            else:
                st.info("No Jacord churn experiment is currently running.")
        with col_kill:
            if running and st.button("Stop churn", type="secondary", key="churn_kill"):
                msg = sweep_runner.kill_jacord_churn(jacord_manifest)
                st.success(msg)
                st.rerun()

        with st.form("jacord_churn_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                churn_rates = st.text_input("Churn rates (%)", value="0 5 10 25 50")
                limit = st.number_input("Prefetch limit", value=12000, step=500)
                trials = st.number_input("Trials", value=5, min_value=1, step=1)
            with c2:
                policies = st.text_input(
                    "Policies",
                    value="oracle ttg history markov coaccess none",
                )
                seed = st.number_input("Mutation seed", value=42, step=1)
                reply_fraction = st.number_input(
                    "Reply fraction",
                    value=0.0,
                    min_value=0.0,
                    max_value=1.0,
                    step=0.05,
                )
            with c3:
                base_dump = st.text_input("Base dump", value="jac_db.pgdump")
                channel_id = st.text_input("Fixed channel ID", value="")
                restore_scope = st.selectbox(
                    "Restore scope",
                    ["trial", "case"],
                    index=0,
                    help="trial restores the churn dump before every measured trial.",
                )
            force_dumps = st.checkbox(
                "Regenerate churn dumps",
                value=False,
                help="Leave off to reuse existing jacord/churn_dumps files.",
            )
            keep_outputs = st.checkbox(
                "Keep previous churn logs/models",
                value=False,
                help="Leave off for a clean churn_logs/churn_profiles/churn_models run.",
            )
            submitted = st.form_submit_button("Run Jacord churn")

        if submitted:
            info = sweep_runner.kickoff_jacord_churn(
                jacord_manifest,
                {
                    "JACORD_CHURN_RATES": churn_rates,
                    "JACORD_CHURN_LIMIT": int(limit),
                    "JACORD_CHURN_TRIALS": int(trials),
                    "JACORD_CHURN_POLICIES": policies,
                    "JACORD_CHURN_SEED": int(seed),
                    "JACORD_CHURN_REPLY_FRACTION": float(reply_fraction),
                    "JACORD_CHURN_BASE_DUMP": base_dump,
                    "JACORD_CHURN_CHANNEL_ID": channel_id,
                    "JACORD_CHURN_RESTORE_SCOPE": restore_scope,
                    "JACORD_CHURN_FORCE_DUMPS": "1" if force_dumps else "0",
                    "JACORD_CHURN_KEEP_OUTPUTS": "1" if keep_outputs else "0",
                },
                jac_bin=jac_bin,
            )
            st.success(
                f"Started Jacord churn experiment (pid={info.pid}). "
                f"Watch progress in `{info.stdout_log}`."
            )
            with st.expander("Env vars passed to the churn run", expanded=False):
                st.code("\n".join(f"{k}={v}" for k, v in sorted(info.env_overrides.items())))
            st.rerun()

        st.divider()
        log_path = sweep_runner.jacord_churn_stdout_log_path(jacord_manifest)
        st.subheader("Churn output")
        _render_log_tail(
            log_path,
            refresh_key="churn_refresh_log",
            missing_label="churn output",
            clear_cache=True,
        )

        churn_csv = jacord_manifest.app_dir / "churn_results.csv"
        churn_df = parsers.load_csv(churn_csv)
        if churn_df.empty:
            st.warning(f"No churn CSV found at `{churn_csv}`.")
        else:
            for key, fig in (
                ("chart_jacord_churn_coverage", charts.churn_coverage(churn_df)),
                ("chart_jacord_churn_hit_rate", charts.churn_hit_rate(churn_df)),
                ("chart_jacord_churn_e2e", charts.churn_e2e(churn_df)),
            ):
                if fig.data:
                    st.plotly_chart(fig, use_container_width=True, key=key)
            st.dataframe(charts.csv_raw(churn_df), use_container_width=True)
            st.download_button(
                "Download churn CSV",
                data=churn_df.to_csv(index=False).encode("utf-8"),
                file_name=churn_csv.name,
                mime="text/csv",
            )


# ---------------------------------------------------------------------------
# TAB 6 — LinkedList SeLeP SQL/block LSTM smoke
# ---------------------------------------------------------------------------
with tab_selep:
    st.header("LinkedList SeLeP LSTM")
    st.caption(
        "Collects a Jac LinkedList SQL trace, converts SQL touches to block "
        "partitions, then trains/tests SeLeP's LSTM predictor."
    )

    running, live_pid = selep_sweep.is_running()
    col_status, col_kill = st.columns([3, 1])
    with col_status:
        if running:
            st.warning(f"SeLeP LSTM experiment is running (pid={live_pid}).")
        else:
            st.info("No SeLeP LSTM experiment is currently running.")
    with col_kill:
        if running and st.button("Stop SeLeP", type="secondary", key="selep_kill"):
            msg = selep_sweep.kill()
            st.success(msg)
            st.rerun()

    st.subheader("Configuration")
    c1, c2, c3 = st.columns(3)
    with c1:
        selep_repo = Path(
            st.text_input(
                "SeLeP repo",
                value=str(selep_sweep.DEFAULT_SELEP_REPO),
                key="selep_repo",
            )
        ).expanduser()
        selep_python = Path(
            st.text_input(
                "SeLeP LSTM python",
                value=str(selep_sweep.DEFAULT_SELEP_PYTHON),
                key="selep_python",
            )
        ).expanduser()
        sweep_python = Path(
            st.text_input(
                "Sweep python",
                value=str(selep_sweep.DEFAULT_SWEEP_PYTHON),
                key="selep_sweep_python",
            )
        ).expanduser()
        jac_bin_selep = Path(
            st.text_input(
                "jac binary",
                value=str(selep_sweep.DEFAULT_JAC_BIN),
                key="selep_jac_bin",
            )
        ).expanduser()
    with c2:
        input_mode = st.selectbox(
            "Input mode",
            ["fresh collect + LSTM", "existing workload + LSTM", "fresh collect + frequency"],
            index=0,
            key="selep_input_mode",
        )
        out_dir = Path(
            st.text_input(
                "Output directory",
                value=str(selep_sweep.DEFAULT_OUT_DIR),
                key="selep_out_dir",
            )
        ).expanduser()
        list_size = st.number_input("LinkedList size", value=24, min_value=1, step=1)
        trials = st.number_input("Collect trials", value=1, min_value=1, step=1)
    with c3:
        look_back = st.number_input("Look back", value=2, min_value=1, step=1)
        top_k = st.number_input("Top-k partitions", value=4, min_value=1, step=1)
        test_fraction = st.number_input(
            "Held-out fraction",
            value=0.30,
            min_value=0.0,
            max_value=0.95,
            step=0.05,
        )
        lstm_epochs = st.number_input("LSTM epochs", value=20, min_value=1, step=1)

    c4, c5, c6 = st.columns(3)
    with c4:
        block_source = st.selectbox(
            "Block source",
            ["pg-buffercache", "hash"],
            index=0,
            key="selep_block_source",
        )
        max_block_selects = st.number_input(
            "Max block SELECTs",
            value=20,
            min_value=1,
            step=1,
        )
        sql_contains = st.text_input("SQL filter", value="", key="selep_sql_filter")
    with c5:
        partition_size = st.number_input(
            "Blocks per partition",
            value=8,
            min_value=1,
            step=1,
        )
        partitions = st.number_input("Hash partitions", value=64, min_value=1, step=1)
        lstm_batch_size = st.number_input("LSTM batch size", value=4, min_value=1, step=1)
    with c6:
        ssh_target = st.text_input("SSH target", value="clarity2", key="selep_ssh_target")
        ssh_options = st.text_input(
            "SSH options",
            value=selep_sweep.DEFAULT_SSH_OPTIONS,
            key="selep_ssh_options",
        )
        postgres_container = st.text_input(
            "Postgres container",
            value="postgres",
            key="selep_postgres_container",
        )

    model_kind = "frequency" if input_mode.endswith("frequency") else "lstm"
    skip_collect = input_mode.startswith("existing workload")
    skip_workload_rebuild = input_mode.startswith("existing workload")
    selep_config = selep_sweep.SelepSweepConfig(
        selep_repo=selep_repo.resolve(),
        selep_python=selep_python,
        sweep_python=sweep_python,
        jac_bin=jac_bin_selep,
        out_dir=out_dir.resolve(),
        model_kind=model_kind,
        list_size=int(list_size),
        trials=int(trials),
        look_back=int(look_back),
        top_k=int(top_k),
        test_fraction=float(test_fraction),
        lstm_epochs=int(lstm_epochs),
        lstm_batch_size=int(lstm_batch_size),
        partitions=int(partitions),
        block_source=block_source,
        max_block_selects=int(max_block_selects),
        sql_contains=sql_contains,
        ssh_target=ssh_target,
        ssh_options=ssh_options,
        postgres_container=postgres_container,
        partition_size=int(partition_size),
        skip_collect=skip_collect,
        skip_workload_rebuild=skip_workload_rebuild,
    )
    problems = selep_sweep.validate(selep_config)

    st.subheader("Prerequisite check")
    if problems:
        st.error("SeLeP LSTM experiment is not ready.")
        for problem in problems:
            st.write(f"- {problem}")
    else:
        st.success("SeLeP LSTM inputs are present.")
        with st.expander("Command", expanded=False):
            st.code(
                " ".join(shlex.quote(part) for part in selep_sweep.command_from_config(selep_config)),
                language="bash",
            )

    c_run, c_check = st.columns([1, 1])
    with c_run:
        run_clicked = st.button(
            "Run SeLeP LSTM",
            type="primary",
            disabled=running or bool(problems),
            key="selep_run",
        )
    with c_check:
        if st.button("Refresh SeLeP", key="selep_refresh"):
            st.rerun()

    if run_clicked:
        try:
            info = selep_sweep.kickoff(selep_config)
        except RuntimeError as exc:
            st.error(str(exc))
        else:
            st.success(f"Started SeLeP LSTM experiment (pid={info.pid}). Watch `{info.stdout_log}`.")
            with st.expander("Env vars passed to SeLeP", expanded=False):
                st.code("\n".join(f"{k}={v}" for k, v in sorted(info.env_overrides.items())))
            st.rerun()

    st.divider()
    st.subheader("SeLeP output")
    _render_log_tail(
        selep_sweep.LOG_PATH,
        refresh_key="selep_refresh_log",
        missing_label="SeLeP LSTM output",
    )

    if selep_config.summary_path.exists():
        with st.expander("Last SeLeP summary", expanded=True):
            try:
                st.json(json.loads(selep_config.summary_path.read_text()))
            except json.JSONDecodeError:
                st.code(selep_config.summary_path.read_text(), language="json")
    if selep_sweep.METADATA_PATH.exists():
        with st.expander("Last SeLeP metadata", expanded=False):
            st.code(selep_sweep.METADATA_PATH.read_text(), language="json")

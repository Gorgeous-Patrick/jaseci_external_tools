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
) -> dict:
    values = {
        "SWEEP_POLICIES": "random-paired",
        "SWEEP_RANDOM_N": n,
        "SWEEP_RANDOM_TRAIN_K": train_k,
        "SWEEP_RANDOM_SEED": seed,
        "SWEEP_RANDOM_POLICIES": policies,
        "SWEEP_MARKOV_POOL_SIZE": n + train_k,
    }
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
            text = sweep_runner.run_all_log_path().read_text()
            max_bytes = 15_000
            if len(text) > max_bytes:
                text = "…(truncated head)…\n" + text[-max_bytes:]
            st.code(text or "(empty)", language="text")

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
    st.caption(f"tail of `{log_path}`")
    if st.button("Refresh", key="run_refresh_log"):
        st.rerun()
    if log_path.exists():
        text = log_path.read_text()
        # Show only the last ~15KB so a giant log doesn't slow the tab.
        max_bytes = 15_000
        if len(text) > max_bytes:
            text = "…(truncated head)…\n" + text[-max_bytes:]
        st.code(text or "(empty)", language="text")
    else:
        st.info(f"No sweep has produced output at `{log_path}` yet.")


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

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        random_n = st.number_input(
            "Measured N",
            value=20,
            min_value=1,
            step=1,
            key="random_n",
        )
    with c2:
        random_train_k = st.number_input(
            "Train K",
            value=5,
            min_value=0,
            step=1,
            key="random_train_k",
        )
    with c3:
        random_seed = st.number_input(
            "Random paired seed",
            value=42,
            step=1,
            key="random_seed",
        )
    with c4:
        random_policies = st.text_input(
            "Random paired policies",
            value="none ttg",
            help="Supported in stream mode: none, ttg, selep, history, manual.",
            key="random_policies",
        )
    st.caption(
        "TTG limits are app-specific. Defaults below come from each app's manifest. "
        "SeLeP can still be selected explicitly and runs once with SELEP_TOP_K/SELEP_BLOCK_LIMIT."
    )
    random_limits_by_name: dict[str, str] = {}
    for name in selected_random_apps:
        m_for_limits = manifest_by_name.get(name)
        if m_for_limits is None:
            continue
        default_limits = _format_int_list(
            _manifest_param_default(m_for_limits, "SWEEP_PREFETCH_LIMITS", "")
        )
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
                    int(random_train_k),
                    int(random_seed),
                    random_policies,
                    limits,
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
            text = sweep_runner.run_all_log_path().read_text()
            max_bytes = 15_000
            if len(text) > max_bytes:
                text = "…(truncated head)…\n" + text[-max_bytes:]
            st.code(text or "(empty)", language="text")

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
        st.caption(f"tail of `{log_path}`")
        if st.button("Refresh churn", key="churn_refresh"):
            st.cache_data.clear()
            st.rerun()
        if log_path.exists():
            text = log_path.read_text()
            max_bytes = 15_000
            if len(text) > max_bytes:
                text = "(truncated head)\n" + text[-max_bytes:]
            st.code(text or "(empty)", language="text")
        else:
            st.info(f"No churn output at `{log_path}` yet.")

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
    st.caption(f"tail of `{selep_sweep.LOG_PATH}`")
    if selep_sweep.LOG_PATH.exists():
        text = selep_sweep.LOG_PATH.read_text()
        max_bytes = 15_000
        if len(text) > max_bytes:
            text = "(truncated head)\n" + text[-max_bytes:]
        st.code(text or "(empty)", language="text")
    else:
        st.info(f"No SeLeP LSTM output at `{selep_sweep.LOG_PATH}` yet.")

    if selep_config.summary_path.exists():
        with st.expander("Last SeLeP summary", expanded=True):
            try:
                st.json(json.loads(selep_config.summary_path.read_text()))
            except json.JSONDecodeError:
                st.code(selep_config.summary_path.read_text(), language="json")
    if selep_sweep.METADATA_PATH.exists():
        with st.expander("Last SeLeP metadata", expanded=False):
            st.code(selep_sweep.METADATA_PATH.read_text(), language="json")

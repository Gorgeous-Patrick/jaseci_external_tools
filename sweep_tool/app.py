"""Streamlit entry point for the sweep tool.

Three tabs, all backed by the app's live output directory on disk:

  1. Run — kick off a sweep for a chosen app.  Fire-and-forget subprocess.
  2. Analyze — read the app's current CSV + logs, render interactive charts.
  3. Raw data — the CSV as a downloadable dataframe.

Archiving isn't the tool's job; commit interesting runs to git.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from lib import manifest as mf
from lib import parsers, charts, sweep_runner

APP_ROOT = Path(__file__).resolve().parent
MANIFEST_DIR = APP_ROOT / "manifests"


st.set_page_config(page_title="Sweep tool", layout="wide")


@st.cache_data
def load_manifests() -> list[mf.Manifest]:
    return mf.discover(MANIFEST_DIR)


manifests = load_manifests()
if not manifests:
    st.error(f"No manifests found in {MANIFEST_DIR}. Add one and rerun.")
    st.stop()
manifest_by_name = {m.name: m for m in manifests}


tab_run, tab_analyze, tab_raw = st.tabs(["Run", "Analyze", "Raw data"])


# ---------------------------------------------------------------------------
# TAB 1 — Run sweep
# ---------------------------------------------------------------------------
with tab_run:
    st.header("Run a sweep")

    # ---- Run all (shepherd over every manifest, sequential) ----
    st.subheader("Run all sweeps")
    st.caption(
        "Kicks off every manifest's sweep sequentially with each app's "
        "default parameters.  All apps share MongoDB/Redis container "
        "names, so parallel isn't safe."
    )
    all_running, all_pid = sweep_runner.is_run_all_running()
    ra_status, ra_kill, ra_launch = st.columns([3, 1, 1])
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
            info = sweep_runner.kickoff_all(manifests)
            st.success(
                f"Launched shepherd (pid={info.pid}) over "
                f"{len(manifests)} manifest(s).  Watch progress in "
                f"`{info.stdout_log}` or the Analyze tab per app."
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
    st.write(f"**app_dir**: `{m.app_dir}`  ·  **script**: `{m.sweep_script}`")

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
        info = sweep_runner.kickoff(m, form_values)
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
# TAB 2 — Analyze
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

    if df.empty and not logs:
        st.warning(
            f"Nothing to analyze.  Either kick off a sweep, or drop "
            f"`{m.results_csv}` and/or `{m.logs_dir}/` under `{m.app_dir}`."
        )
    else:
        # Render each chart only if it has data; otherwise the panel is
        # a blank axes block, which is confusing.  Older sweeps predate
        # the [HIT-STATS-SERIES] / [PREFETCH-WORKER-TIMES] markers, so
        # log-based charts come back empty for them.
        chart_specs = [
            ("chart_e2e_stack", charts.e2e_stack, (df,)),
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
# TAB 3 — Raw data
# ---------------------------------------------------------------------------
with tab_raw:
    st.header("Raw sweep CSV")
    app_name = st.selectbox(
        "App",
        [m.name for m in manifests],
        key="raw_app",
    )
    m = manifest_by_name[app_name]
    csv_path = m.app_dir / m.results_csv
    st.caption(f"path: `{csv_path}`")

    df = parsers.load_csv(csv_path)
    if df.empty:
        st.warning(f"No CSV found at `{csv_path}`.")
    else:
        st.dataframe(charts.csv_raw(df), use_container_width=True)
        st.download_button(
            "Download CSV",
            data=csv_path.read_bytes(),
            file_name=csv_path.name,
            mime="text/csv",
        )

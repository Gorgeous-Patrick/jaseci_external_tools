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
    app_name = st.selectbox(
        "App",
        [m.name for m in manifests],
        key="run_app",
    )
    m = manifest_by_name[app_name]
    st.caption(m.description)
    st.write(f"**app_dir**: `{m.app_dir}`  ·  **script**: `{m.sweep_script}`")

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
        if not df.empty:
            st.plotly_chart(
                charts.e2e_stack(df),
                use_container_width=True,
                key="chart_e2e_stack",
            )
        if logs:
            st.plotly_chart(
                charts.hit_counts_request_done(logs),
                use_container_width=True,
                key="chart_hit_counts_request_done",
            )
            st.plotly_chart(
                charts.hit_counts_pw_phase(logs),
                use_container_width=True,
                key="chart_hit_counts_pw_phase",
            )
            st.plotly_chart(
                charts.worker_times(logs),
                use_container_width=True,
                key="chart_worker_times",
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

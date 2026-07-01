# Sweep tool

Local single-user Streamlit tool for driving Jac benchmark sweeps.

## Structure

```
sweep_tool/
├── app.py                 # Streamlit entry point
├── manifests/*.yaml       # one per benchmarkable app
├── lib/
│   ├── manifest.py        # loader
│   ├── sweep_runner.py    # subprocess + archiving
│   ├── parsers.py         # CSV + jac server log parsers
│   └── charts.py          # Plotly chart builders
├── results/<app>/<ts>/    # sweep outputs archived per run
└── requirements.txt
```

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Add a new app

1. Make sure the app's sweep script honours env-var overrides for the
   parameters you want to expose (e.g. `SWEEP_PREFETCH_LIMITS`).
2. Drop a YAML into `manifests/` with:
   - `name`, `description`
   - `app_dir` (relative to the manifest file)
   - `scripts.sweep` (relative to `app_dir`)
   - `outputs.results_csv`, `outputs.logs_dir`, `outputs.profiles_dir`
   - `parameters` — list of form fields.  `kind` is one of
     `int`, `int_list`, `enum`, `str`.
3. Reload the tab — it'll appear in every dropdown.

## Tabs

- **Run sweep**: pick an app, edit params, hit Run.  Sweep runs as a
  detached bash subprocess; the tool doesn't wait.  Results archived
  under `results/<app>/<yyyymmdd-hhmmss>/`.
- **Analyze**: pick a completed run, see interactive Plotly charts
  (e2e stack, hit-count breakdown, prefetch-phase snapshots, worker
  time distribution).
- **Raw data**: the results CSV as a table, downloadable.

## Notes

- Sweep runs can take minutes; the tool is fire-and-forget.  The Analyze
  tab has a Reload button; hit it after you expect the run to finish.
- The `STATUS` file inside a run dir is written by the wrapper on exit
  (`done` or `failed rc=N`).  Absence = still running.

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
│   ├── prefetch_exp/      # Python prefetch policy sweep backend
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
   - optional `runner: prefetch_python` for the Python TTG/policy runner;
     omit it to keep launching `scripts.sweep` as a shell script
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
- **Churn**: runs the Jacord same-spawn churn experiment and plots
  coverage and L1 hit rate across churn rates.

## Python prefetch policy runner

The manifests for JSearch, Jacord, LittleX5, and LinkedList use
`runner: prefetch_python`.  The Streamlit launcher runs:

```bash
python -m lib.prefetch_exp.cli --manifest manifests/<app>.yaml
```

The backend accepts the same manifest parameters as environment variables.
Useful knobs:

- `SWEEP_POLICIES="oracle none ttg"` — space-separated policy list. Supported
  values include `none`, `ttg`, `oracle`, `markov`, `markov1-pooled`,
  `coaccess`, `coaccess-pooled`, `selep-adapted`,
  `selep-adapted-pooled`, `history`, and `manual`.
- `SWEEP_PREFETCH_LIMITS="500 1000 2000"` — positive limits for predictive
  policies; `none` runs once at limit 0.
- `SWEEP_ORACLE_MODE=auto` — run a non-counted `prefetching="none"` request,
  extract first-touch UUIDs from its access log, then replay with
  `prefetching="oracle"`.
- `SWEEP_ORACLE_MODE=file` — read existing UUID files from
  `SWEEP_ORACLE_DIR` or `SWEEP_ORACLE_FILE`.
- `SWEEP_MARKOV_MODE=auto` — run a non-counted `prefetching="none"` request,
  train a first-order UUID Markov model from its access log, then replay with
  `prefetching="markov"`.
- `SWEEP_MARKOV_MODE=file` — read existing model JSON files from
  `SWEEP_MARKOV_DIR` or `SWEEP_MARKOV_FILE`.
- `SWEEP_COACCESS_MODE=auto` — run no-prefetch training requests, cluster
  each request's first-touch UUID set with the standalone co-access policy,
  then replay with `prefetching="coaccess"`.
- `SWEEP_SELEP_MODE=auto` — run no-prefetch training requests, reuse the same
  co-access clustering code path for partitions, train the local SeLeP
  encoder-decoder LSTM over request partition-access sequences, then replay
  with `prefetching="selep-adapted"`.
- `SWEEP_SELEP_MODE=file` — read existing SeLeP-adapted model JSON files from
  `SWEEP_SELEP_DIR` or `SWEEP_SELEP_FILE`.
- `SWEEP_SELEP_TRAIN_NS="10"` — training request counts swept by
  `selep-adapted-pooled`; explicit policy names such as
  `selep-adapted-pooled-N10` override this.
- `SWEEP_SELEP_REPO=/path/to/SeLeP` — local checkout containing the authors'
  `Backend.Models.LSTM` code. Defaults to the sibling `SeLeP` repo.
- `SWEEP_SELEP_LOOK_BACK=4`, `SWEEP_SELEP_EPOCHS=25`, and
  `SWEEP_SELEP_BATCH_SIZE=16` tune only the offline LSTM training phase.
  `SWEEP_COACCESS_CLUSTER_THRESHOLD` remains the shared partitioning
  threshold for both `coaccess-pooled` and `selep-adapted-pooled`.
- SeLeP cold start is honest: if there is not enough preceding history to
  create supervised LSTM windows, the generated plan is empty. Single-request
  self-labeling is disabled unless `SWEEP_SELEP_ALLOW_SELF_LABEL=1`.

The result CSV keeps the old timing/tier columns and adds `policy` and
`oracle_file` / `model_file`.

## Jacord churn experiment

The Churn tab runs `tools/run_jacord_churn.py`.  It answers how each
policy behaves between perfect same-request repetition and fully disjoint
spawn history:

1. Restore the Jacord base dump and select one `load_channel` spawn.
2. Record a pre-churn no-prefetch trace on that same channel.
3. Build stale history, Markov, and co-access plans from that trace. If
   `selep-adapted` is requested, also record repeated pre-churn no-prefetch
   traces and train the offline SeLeP-adapted file model before measurement.
4. For each churn rate, restore the base dump, post deterministic new
   messages through Jacord walkers, restart the full Mongo/Redis stack,
   verify the same channel survives, then dump Mongo to `churn_dumps/`.
5. Measure cold post-churn runs from each dump for `oracle`, `ttg`,
   `history`, `markov`, `coaccess`, optional `selep-adapted`, and `none`.

The default churn rates are `0 5 10 25 50`, the default budget is
`12000`, and the default trial count is `5`.  Churn outputs are isolated
from the normal sweep:

```text
jacord/churn_results.csv
jacord/churn_metadata.json
jacord/churn_logs/
jacord/churn_profiles/
jacord/churn_models/
jacord/churn_dumps/
```

The CLI equivalent of the Streamlit button is:

```bash
python tools/run_jacord_churn.py --manifest manifests/jacord.yaml
```

The SeLeP-adapted p=0 gate is explicit because it needs TensorFlow only in
the offline trainer process:

```bash
JACORD_CHURN_POLICIES="selep-adapted" JACORD_CHURN_RATES="0" \
python tools/run_jacord_churn.py --manifest manifests/jacord.yaml
```

`JACORD_CHURN_SELEP_TRAIN_REPEATS` overrides the pre-churn repeat count;
the default is `max(12, SWEEP_SELEP_LOOK_BACK + 8)`.

To regenerate paper-ready churn coverage and hit-rate PDFs:

```bash
python tools/plot_jacord_churn.py --csv ../../../jacord/churn_results.csv
```

## Two-machine DB mode

By default, sweeps use local Docker for MongoDB and Redis:

```toml
[db]
mode = "local_docker"
```

To run Streamlit/Jac on Machine 1 and MongoDB/Redis on Machine 2, edit
`sweep_tool/local.toml`:

```toml
[db]
mode = "remote_ssh"
host = "MACHINE2_HOST_OR_IP"
ssh_user = "patrickli"
remote_app_root = "/abs/path/to/benchmark/apps/on/machine2"
```

In remote mode, the Python prefetch runner SSHes to Machine 2 for
`docker compose up/down`, Mongo restore/drop/dump, and Redis flush. Jac
still starts on Machine 1, with `MONGODB_URI` and `REDIS_URL` pointed at
Machine 2. If `mongo_uri` / `redis_url` are omitted, each app keeps its
local port and replaces `localhost` with `db.host`.

Copy dump files to Machine 2 once before the sweep, under the matching
remote app directory, for example `jacord/jac_db.dump` or
`littlex5/jac_db.dump`. Then run the dry checker from the
`jaseci_external_tools` repo root:

```bash
python tools/check_remote_db.py --app jacord
```

## Notes

- Sweep runs can take minutes; the tool is fire-and-forget.  The Analyze
  tab has a Reload button; hit it after you expect the run to finish.
- The `STATUS` file inside a run dir is written by the wrapper on exit
  (`done` or `failed rc=N`).  Absence = still running.

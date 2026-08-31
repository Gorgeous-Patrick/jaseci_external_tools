# Experiment Runner Container

This image compiles and packages the Jac binary, the sweep tool, and the
benchmark app code so the prefetch experiments can move to a stable machine.

Build from the `jaseci_env` root, using the intended Jac checkout as an
additional build context:

```bash
JASECI_SRC=/home/patrickli/Space/jaseci \
IMAGE=jac-prefetch-experiment:free-threaded \
jaseci_external_tools/docker/build_experiment_image.sh
```

Build and push the GHCR image:

```bash
JASECI_SRC=/home/patrickli/Space/jaseci \
IMAGE=ghcr.io/gorgeous-patrick/jaseci_external_tools:free-threaded \
jaseci_external_tools/docker/build_experiment_image.sh --push
```

Run the Streamlit UI:

```bash
docker run --rm -it \
  -p 8501:8501 \
  -v "$PWD/jacord:/workspace/jacord" \
  -v "$PWD/jdrive:/workspace/jdrive" \
  -v "$PWD/jsearch:/workspace/jsearch" \
  -v "$PWD/jaseci_external_tools/linked_list:/workspace/jaseci_external_tools/linked_list" \
  -v "$PWD/jaseci_external_tools/littlex5:/workspace/jaseci_external_tools/littlex5" \
  -v "$HOME/.ssh:/root/.ssh:ro" \
  -e SWEEP_DB_MODE=remote_ssh \
  -e SWEEP_DB_HOST=clarity2 \
  -e SWEEP_DB_REMOTE_APP_ROOT=/home/baichuan/jaseci_remote_apps \
  -e SWEEP_DB_SSH_OPTIONS="-F /root/.ssh/config" \
  jac-prefetch-experiment:free-threaded streamlit
```

Run one foreground sweep:

```bash
docker run --rm -it \
  -v "$PWD/jacord:/workspace/jacord" \
  -v "$HOME/.ssh:/root/.ssh:ro" \
  -e SWEEP_DB_MODE=remote_ssh \
  -e SWEEP_DB_HOST=clarity2 \
  -e SWEEP_DB_REMOTE_APP_ROOT=/home/baichuan/jaseci_remote_apps \
  -e SWEEP_DB_SSH_OPTIONS="-F /root/.ssh/config" \
  jac-prefetch-experiment:free-threaded sweep jacord
```

Run all manifests sequentially:

```bash
docker run --rm -it \
  -v "$PWD:/workspace-host" \
  -v "$PWD/jacord:/workspace/jacord" \
  -v "$PWD/jdrive:/workspace/jdrive" \
  -v "$PWD/jsearch:/workspace/jsearch" \
  -v "$PWD/jaseci_external_tools/linked_list:/workspace/jaseci_external_tools/linked_list" \
  -v "$PWD/jaseci_external_tools/littlex5:/workspace/jaseci_external_tools/littlex5" \
  -v "$HOME/.ssh:/root/.ssh:ro" \
  -e SWEEP_DB_MODE=remote_ssh \
  -e SWEEP_DB_HOST=clarity2 \
  -e SWEEP_DB_REMOTE_APP_ROOT=/home/baichuan/jaseci_remote_apps \
  -e SWEEP_DB_SSH_OPTIONS="-F /root/.ssh/config" \
  jac-prefetch-experiment:free-threaded run-all linked_list jacord littlex5 jdrive
```

Run the published image on a remote machine:

```bash
mkdir -p ~/jac-prefetch-experiment
cd ~/jac-prefetch-experiment
curl -fsSLO https://raw.githubusercontent.com/Gorgeous-Patrick/jaseci_external_tools/new-main/docker-compose.remote.yaml
docker login ghcr.io
docker compose pull
docker compose up -d
```

If port 8501 is not directly reachable, tunnel it from your laptop:

```bash
ssh -L 8501:localhost:8501 clarity1
```

Then open `http://localhost:8501`.

To verify the remote container is using free-threaded Python:

```bash
docker compose exec sweep jac-info
```

`JASECI_SOURCE_LABEL` should point at the Jac checkout used for the build.
The sweep Python lines should show `sweep_Py_GIL_DISABLED=1` and
`sweep_gil_enabled=False`.  The same command also verifies the packaged
SeLeP LSTM runtime:

```text
SELEP_REPO=/workspace/SeLeP
SELEP_PYTHON=/opt/selep-venv/bin/python
selep_tensorflow=2.13.0
selep_keras=2.13.1
```

Export remote results:

```bash
docker compose --profile tools run --rm export-results
scp clarity1:~/jac-prefetch-experiment/exports/sweep-results.tar.gz .
```

Notes:

- The image keeps seed dump files, but excludes old logs/profiles/results from
  the build context.
- Mount app directories if you want new CSVs, logs, profiles, oracle plans, and
  model JSON files to persist on the host.
- For `local_docker` mode, mount `/var/run/docker.sock` and make sure the host
  allows the container to use Docker.
- For `remote_ssh` mode, mount SSH credentials and set `SWEEP_DB_SSH_OPTIONS`
  to point at the mounted config.

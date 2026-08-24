# Experiment Runner Container

This image packages the Jac runtime, `jac_scale`, the sweep tool, and the
benchmark app code so the prefetch experiments can move to a stable machine.

Build from the `jaseci_env` root:

```bash
docker build \
  -f jaseci_external_tools/Dockerfile.experiment \
  -t jac-prefetch-experiment:free-threaded \
  .
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
  jac-prefetch-experiment:free-threaded run-all jacord jdrive jsearch linked_list littlex5
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
docker compose exec sweep python -c \
  'import sys, sysconfig; print(sys.version); print(sysconfig.get_config_var("Py_GIL_DISABLED")); print(sys._is_gil_enabled())'
```

The second line should be `1`; the third line should be `False`.

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

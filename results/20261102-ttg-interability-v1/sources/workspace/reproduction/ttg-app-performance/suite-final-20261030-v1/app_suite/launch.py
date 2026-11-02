#!/usr/bin/env python3
"""Resume a validated suite application's persisted graph and interactive UI."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit

from native import NativeServer, SUITE, free_port, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True, help='Evidence directory containing postgres/ and app subdirectories')
    parser.add_argument('--app', required=True)
    parser.add_argument('--port', type=int, default=0, help='Frontend port; zero selects an unused port')
    args = parser.parse_args()
    state = args.state.resolve()
    if not (state / 'manifest.json').exists() and not (state / 'run-manifest.json').exists():
        parser.error('The state directory must contain a suite run manifest')
    directory = state / args.app
    summary = json.loads((directory / 'summary.json').read_text())
    if summary.get('native', summary.get('native_replay')) != 'passed':
        parser.error('The application must pass native validation before launch')
    data = state / 'postgres' / 'data'
    if (data / 'postmaster.pid').exists():
        parser.error('This suite cluster is already running; choose a stopped suite state directory')
    pg_bin = Path(os.environ.get('JAC_PG_DIST', '/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0')) / 'bin'
    pg_port = free_port()
    original = urlsplit(json.loads((directory / 'connection.json').read_text())['database_url'])
    database_url = urlunsplit((original.scheme, f'ttgsuite@127.0.0.1:{pg_port}', original.path, '', ''))
    subprocess.run([str(pg_bin / 'pg_ctl'), '-D', str(data), '-l', str(state / 'postgres' / 'server.log'),
                    '-o', f'-h 127.0.0.1 -p {pg_port} -k {state / "postgres"}', '-w', 'start'], check=True)
    backend = NativeServer(directory, database_url, free_port())
    frontend = None
    try:
        backend.start()
        config = directory / 'ui-config.json'
        write_json(config, {})
        port = args.port or free_port()
        frontend = subprocess.Popen([sys.executable, str(SUITE / 'ui_server.py'), '--app', args.app,
                                     '--backend', f'http://127.0.0.1:{backend.port}', '--config', str(config),
                                     '--port', str(port)])
        print(f'Open http://127.0.0.1:{port}', flush=True)
        print('Username: user_0000; password: isolated-suite-seed-password', flush=True)
        print('Press Ctrl-C to stop this application and its owned PostgreSQL cluster.', flush=True)
        frontend.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if frontend is not None:
            frontend.terminate()
            frontend.wait(timeout=10)
        backend.stop()
        subprocess.run([str(pg_bin / 'pg_ctl'), '-D', str(data), '-m', 'fast', '-w', 'stop'], check=True)


if __name__ == '__main__':
    main()

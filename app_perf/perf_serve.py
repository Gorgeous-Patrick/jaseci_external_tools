"""Isolated server entrypoint with optional driver instrumentation."""
import os
import sys
import jaclang
from driver_probe import install
observed = os.environ.get('TTG_PERF_OBSERVER', '1') == '1'
if observed:
    install()
from control_server import start
control = start(int(os.environ['TTG_PERF_CONTROL_PORT']), observed=observed)
from jaclang.scale.server.native_server import NativeJServer
from jaclang.cli.cli_boot import start_cli
original = NativeJServer.run_server
def loopback(self, *args, **kwargs):
    kwargs['host'] = '127.0.0.1'
    return original(self, *args, **kwargs)
NativeJServer.run_server = loopback
sys.argv = ['jac', 'run', '--serve', '--no-client', '--port', os.environ['TTG_HTTP_PORT'], 'server.jac']
start_cli()

"""Run the native Jac server on an explicitly assigned loopback port."""
import os
import sys

import jaclang
from jaclang.scale.server.native_server import NativeJServer
from jaclang.cli.cli_boot import start_cli

original_run_server = NativeJServer.run_server


def run_loopback(self, *args, **kwargs):
    kwargs['host'] = '127.0.0.1'
    return original_run_server(self, *args, **kwargs)


NativeJServer.run_server = run_loopback
sys.argv = ['jac', 'run', '--serve', '--no-client', '--port',
            os.environ['TTG_HTTP_PORT'], 'server.jac']
start_cli()

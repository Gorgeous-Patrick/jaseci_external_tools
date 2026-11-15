"""Explicit instrumented native server entry; run only after stage approval."""
import os
import sys
import jaclang
from http_observer import install
from control_server import start
install()
control=start(int(os.environ['TTG_PERF_CONTROL_PORT']))
from jaclang.scale.server.native_server import NativeJServer
from jaclang.cli.cli_boot import start_cli
original=NativeJServer.run_server
def loopback(self,*args,**kwargs):
    kwargs['host']='127.0.0.1'
    return original(self,*args,**kwargs)
NativeJServer.run_server=loopback
sys.argv=['jac','run','--serve','--no-client','--port',os.environ['TTG_HTTP_PORT'],'server.jac']
start_cli()

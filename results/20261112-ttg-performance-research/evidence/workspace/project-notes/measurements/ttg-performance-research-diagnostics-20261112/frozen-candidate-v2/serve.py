"""Thin diagnostic entry: unchanged compact observer and native HTTP server."""
import json
import os
from pathlib import Path
import sys
OWN=Path(__file__).resolve().parent
PRIMARY=OWN.parent/'ttg-performance-research-20261112'
sys.path.insert(0,str(PRIMARY))
import jaclang
from compact_observer import install
from control_server import start
install()
from cpu_profile import install as install_cpu
install_cpu(json.loads(os.environ['TTG_CPU_TARGETS']),
            Path(os.environ['TTG_CPU_OUTPUT'])/('generation-'+os.environ['TTG_PERF_SERVER_GENERATION']))
control=start(int(os.environ['TTG_PERF_CONTROL_PORT']))
from jaclang.scale.server.native_server import NativeJServer
from jaclang.cli.cli_boot import start_cli
old=NativeJServer.run_server
def loopback(self,*args,**kwargs):
    kwargs['host']='127.0.0.1'
    return old(self,*args,**kwargs)
NativeJServer.run_server=loopback
sys.argv=['jac','run','--serve','--no-client','--port',os.environ['TTG_HTTP_PORT'],'server.jac']
start_cli()

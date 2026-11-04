"""NEW compact observer entry; no runtime/core/ability replacement."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import jaclang
from compact_observer import install
from control_server import start
install()
if os.environ.get('TTG_CPU_OUTPUT'):
    import cpu_profile
    cpu_profile.install()
control=start(int(os.environ['TTG_PERF_CONTROL_PORT']))
from jaclang.scale.server.native_server import NativeJServer
from jaclang.cli.cli_boot import start_cli
old=NativeJServer.run_server
def loopback(self,*args,**kwargs):
    kwargs['host']='127.0.0.1';return old(self,*args,**kwargs)
NativeJServer.run_server=loopback
sys.argv=['jac','run','--serve','--no-client','--port',os.environ['TTG_HTTP_PORT'],'server.jac']
start_cli()

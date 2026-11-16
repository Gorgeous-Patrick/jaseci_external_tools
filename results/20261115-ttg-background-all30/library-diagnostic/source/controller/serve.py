"""NEW compact observer entry; no runtime/core/ability replacement."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ttg-background-pushdown-portfolio-performance-20261115'))
import jaclang
from compact_observer import install
from background_observer import install as install_background
from control_server import start
install()
background_observer=install_background()
if os.environ.get('TTG_RESEARCH_CAPTURE')=='precision':
    from precision_observer import install as install_precision
    install_precision()
if os.environ.get('TTG_LIBRARY_TRACE')=='1':
    import importlib.util
    observer_path=Path(os.environ['TTG_LIBRARY_OBSERVER'])
    spec=importlib.util.spec_from_file_location('_library_timeliness_observer',observer_path)
    observer=importlib.util.module_from_spec(spec);sys.modules[spec.name]=observer
    spec.loader.exec_module(observer);observer.install(Path(os.environ['TTG_PERF_DIR']))
control=start(int(os.environ['TTG_PERF_CONTROL_PORT']))
from jaclang.scale.server.native_server import NativeJServer
from jaclang.cli.cli_boot import start_cli
old=NativeJServer.run_server
def loopback(self,*args,**kwargs):
    kwargs['host']='127.0.0.1';return old(self,*args,**kwargs)
NativeJServer.run_server=loopback
sys.argv=['jac','run','--serve','--no-client','--port',os.environ['TTG_HTTP_PORT'],'server.jac']
start_cli()

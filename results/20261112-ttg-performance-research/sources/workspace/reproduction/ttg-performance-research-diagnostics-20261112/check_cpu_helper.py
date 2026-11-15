"""Released DB-free helper import/source-binding and direct-clock preflight."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys
import sysconfig
import threading
from cpu_profile import HOOKS, FORBIDDEN, clock_controls


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('New preflight output required')
    args.output.mkdir(parents=True)
    result=dict(passed=False,stage='DB-free import/clock controls only',bindings=[])
    try:
        if sysconfig.get_config_var('Py_GIL_DISABLED')!=1 or sys._is_gil_enabled():
            raise AssertionError('Actual GIL-off interpreter required')
        import jaclang
        from jaclang.server.serving.app import ServingApp
        from jaclang.runtime.runtime import JacRuntimeInterface
        for module,names in HOOKS.items():
            loaded=importlib.import_module(module)
            for name in names:
                if name in FORBIDDEN:raise AssertionError('Forbidden caller-frame hook')
                fn=getattr(loaded,name)
                if not callable(fn) or isinstance(fn,type):raise AssertionError('Unexpected hook binding')
                code=getattr(fn,'__code__',None)
                if code is None:raise AssertionError('Unresolved Python phase implementation')
                if set(code.co_names)&{'_getframe','currentframe'}:
                    raise AssertionError('Direct caller-frame-sensitive phase rejected')
                aliases=[]
                for value in list(sys.modules.values()):
                    if value is None:continue
                    ns=vars(value);label=ns.get('__name__','')
                    if not label.startswith('jaclang'):continue
                    aliases.extend(label+'.'+key for key,candidate in list(ns.items()) if candidate is fn)
                result['bindings'].append(dict(module=module,name=name,module_file=getattr(loaded,'__file__',None),
                    callable_module=fn.__module__,callable_name=fn.__qualname__,code_file=code.co_filename,
                    code_first_line=code.co_firstlineno,loaded_aliases=sorted(aliases),
                    direct_frame_intrinsic=False))
        controls=clock_controls()
        (args.output/'clock-controls.json').write_text(json.dumps(controls,indent=2)+'\n')
        result.update(passed=True,GIL_enabled=False,Py_GIL_DISABLED=1,
            python=sys.executable,main_thread=threading.get_ident(),
            helper_sha256=hashlib.sha256(Path(__file__).with_name('cpu_profile.py').read_bytes()).hexdigest(),
            no_hooks_installed=True,no_DB_or_native_workflow=True)
    except BaseException as error:
        result['error']=type(error).__name__+': '+str(error)
        raise
    finally:
        (args.output/'outcome.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,bindings=len(result['bindings']),output=str(args.output))))


if __name__=='__main__':main()

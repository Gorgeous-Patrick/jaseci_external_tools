"""Import-only check of immutable runtime+DIRECT; no constructors/services/SQL."""
import importlib,json,os,sys
from pathlib import Path
import jaclang
root=Path(os.environ['TTG_RUNTIME_SOURCE']).resolve()
assert Path(jaclang.__file__).resolve().is_relative_to(root)
names=('jaclang.runtime.ttg_templates','jaclang.runtime.ttg_fusion_sql',
 'jaclang.runtime.ttg_dependency_prefetch','jaclang.data.pgwire',
 'jaclang.runtime.ttg_process_reader','jaclang.compiler.driver.program')
modules={name:str(importlib.import_module(name).__file__) for name in names}
print(json.dumps(dict(passed=True,stage='Import-only; no SQL/server',runtime=str(root),Python=sys.version,
 GIL_enabled=sys._is_gil_enabled() if hasattr(sys,'_is_gil_enabled') else None,modules=modules)))

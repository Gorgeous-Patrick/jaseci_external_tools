"""Exact accepted transport/scoping/SQL/semantic primitives, loaded by unique path."""
import importlib.util
from pathlib import Path
import sys
NEXT=Path(__file__).resolve().parents[1]/'ttg-next-performance'
spec=importlib.util.spec_from_file_location('_interability_borrowed_primitives',NEXT/'next_interop.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
for name in ('require','read_json','sha256','verify_case','load_jsonl','reference','checked_ref',
 'payload_errors','scope_calls','totals','concurrency','executor_evidence','Applications','BasePostgres'):
 globals()[name]=getattr(module,name)

# Restore owned prefixed module/observer lookup after borrowed imports.
sys.path.insert(0,str(Path(__file__).resolve().parent))

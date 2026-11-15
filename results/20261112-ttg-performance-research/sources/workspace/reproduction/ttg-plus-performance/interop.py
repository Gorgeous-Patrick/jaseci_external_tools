"""Read-only reuse of published observer/protocol/oracle primitives."""
from pathlib import Path
import sys
from plus_config import PREVIOUS
sys.path.insert(0,str(PREVIOUS))
from evidence import read_json,sha256,checked_ref,verify_case,load_jsonl
from gate import check_tree,payload_errors
from app_tier_adapter import Applications,OLD,OLD_SUITE
from owned_postgres import OwnedPostgres as BasePostgres
from small_metrics_v1 import scope_calls,totals
from intervals import concurrency,executor_evidence


def require(value,message):
    if not value:raise ValueError(message)


def reference(path):
    path=Path(path).resolve();return dict(path=str(path),sha256=sha256(path))

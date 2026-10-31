"""Predeclared six-cell architecture/model/executor controls, no tuning."""
import hashlib
import json
from pathlib import Path
import re

COMMON=dict(topology_index=True,prefetch_limit=256,prefetch_workers=1,cross_root_resolve=True)
CELLS={
    'none':dict(prefetching='none',ttg_prefetch_model='always',async_prefetch='thread'),
    'legacy_ttg_thread':dict(prefetching='ttg',ttg_prefetch_model='always',async_prefetch='thread'),
    'continuation_always_thread':dict(prefetching='ttg_dependency',ttg_prefetch_model='always',async_prefetch='thread'),
    'continuation_always_process':dict(prefetching='ttg_dependency',ttg_prefetch_model='always',async_prefetch='process'),
    'continuation_expected_benefit_thread':dict(prefetching='ttg_dependency',ttg_prefetch_model='expected_benefit',async_prefetch='thread'),
    'continuation_expected_benefit_process':dict(prefetching='ttg_dependency',ttg_prefetch_model='expected_benefit',async_prefetch='process')}
EXPECTED_BENEFIT_DEFAULTS=dict(min_samples=3,margin_ms=0.0,unused_weight=1.0,cold_start_prefetch=True,probe_every=20)
HISTORY_REGIME='Fresh process-local profile per independent workflow trial; natural learning within ordered workflow; excluded warmup has separate state and is not transferred'


def run_config(cell):return {**COMMON,**CELLS[cell]}


def signature(cell):
    return hashlib.sha256(json.dumps(run_config(cell),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def write(directory,case_id,cell):
    values=run_config(cell)
    name='continuation-'+re.sub(r'[^a-zA-Z0-9_-]','-',case_id)
    lines=['[project]',f'name = "{name}"','entry-point = "server.jac"','[run]']
    for key,value in values.items():lines.append(key+' = '+json.dumps(value))
    lines+=['[serve]','profile = false','[scale.jwt]',
        'secret = "isolated-ttg-suite-development-secret"','algorithm = "HS256"','exp_delta_days = 1']
    (Path(directory)/'jac.toml').write_text('\n'.join(lines)+'\n')
    return dict(cell_id=cell,run=values,effective_config_sha256=signature(cell),
        expected_benefit_defaults=EXPECTED_BENEFIT_DEFAULTS if values['ttg_prefetch_model']=='expected_benefit' else None,
        history_regime=HISTORY_REGIME,
        off_executor_note='async_prefetch setting is inactive because prefetching=none' if cell=='none' else None)

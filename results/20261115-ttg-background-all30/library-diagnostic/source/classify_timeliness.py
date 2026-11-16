"""Offline exact-key classification; source preparation, no data collection.

Consumers supply exact accepted business request IDs. SQL strings are compared
only to SQL already present in observed cache keys; no SQL/key is generated.
"""
from collections import Counter
import json


def decoded(value):
    tag=value[0]
    if tag=='none':return None
    if tag in ('str','bytes','uuid','float'):return value[1]
    if tag=='int':return int(value[1])
    if tag=='bool':return value[1]
    if tag=='type':return ('process_local_type',value[1],tuple(sorted(value[2].items())))
    if tag in ('list','tuple'):return tuple(decoded(v)for v in value[1])
    if tag=='dict':return tuple((decoded(k),decoded(v))for k,v in value[1])
    raise ValueError('Unknown typed key tag')


def request(row):
    binding=row.get('binding')
    return binding[0] if binding else None


def _job_state(lookup,jid):
    before=next((x for x in lookup['futures_before']if x['job_id']==jid),None)
    after=next((x for x in lookup['futures_after']if x['job_id']==jid),None)
    if not before or not after:return 'exact_coverage_readiness_unknown'
    if any(x['lease_cancelled'] or x['owner_closed'] or not x['epoch_equal'] or not x['snapshot_equal'] for x in (before,after)):
        return 'exact_coverage_invalidated_or_closed'
    if before['done'] is True and before['cancelled'] is False:
        return 'future_ready_before_lookup_unpublished'
    if before['done'] is False and after['done'] is False:
        return 'future_pending_through_lookup'
    return 'readiness_boundary_or_unknown'


def classify_access(begin,lookups,jobs,returns):
    if not lookups:return 'no_cache_attempt_observed',[]
    hits=[x for x in lookups if x['hit']]
    if hits:
        source=hits[0].get('write_source') or {}
        kind=source.get('kind')
        return ('hit_background_publication' if kind=='background' else
                'hit_native_access_cache' if kind=='native_access' else
                'hit_other_or_unattributed_cache'),[]
    candidates=[];unknown=False;materialized=0
    for jid,job in jobs.items():
        if job['session']!=lookups[0]['session'] or request(job)!=request(begin):continue
        if job['ns']>max(x['lookup_end_ns']for x in lookups):continue
        result=returns.get(jid)
        if not result or not result['coverage_materialized']:
            unknown=True;continue
        materialized+=1
        for lookup in lookups:
            if job['ns']>lookup['lookup_start_ns']:continue
            if lookup['key_id'] not in result['key_ids']:continue
            # Epoch identity is not erased by matching SQL/origin operands.
            state=('exact_coverage_invalidated_or_closed' if job['epoch']!=lookup['epoch']
                   else _job_state(lookup,jid))
            candidates.append(dict(job_id=jid,key_id=lookup['key_id'],lookup_seq=lookup['seq'],state=state))
    if candidates:
        priority=['future_ready_before_lookup_unpublished','future_pending_through_lookup',
                  'readiness_boundary_or_unknown','exact_coverage_readiness_unknown',
                  'exact_coverage_invalidated_or_closed']
        return next(s for s in priority if any(c['state']==s for c in candidates)),candidates
    if unknown:return 'unknown_job_coverage',[]
    return ('uncovered_by_observed_materialized_jobs' if materialized else
            'no_preexisting_observed_job'),[]


def summarize(rows,business_request_ids):
    """Return one denominator per native logical resolution, not cache attempt."""
    selected=set(business_request_ids);definitions={}
    # IDs are process-local; include PID everywhere.
    jobs={};returns={};phases={};accesses={};lookups={};sql={};sqlend={}
    for r in rows:
        pid=r.get('pid');kind=r['kind']
        if kind=='key_definition':definitions[pid,r['key_id']]=r['key']
        if kind=='job_capture':jobs[pid,r['job_id']]=r
        if kind=='worker_return':returns[pid,r['job_id']]=r
        if kind=='job_phase':phases.setdefault((pid,r['native_event'].get('job_id')),[]).append(r)
        if kind=='access_begin'and request(r)in selected:accesses[pid,r['seq']]=r
        if kind=='cache_lookup'and r.get('access_id')is not None:
            lookups.setdefault((pid,r['access_id']),[]).append(r)
        if kind=='sql_begin':sql[pid,r['seq']]=r
        if kind=='sql_end':sqlend[pid,r['sql_id']]=r
    outcomes=[]
    for (pid,aid),begin in accesses.items():
        attempts=lookups.get((pid,aid),[])
        outcome,candidates=classify_access(begin,attempts,
            {j:r for (p,j),r in jobs.items()if p==pid},
            {j:r for (p,j),r in returns.items()if p==pid})
        observed_sql=set()
        for attempt in attempts:
            key=decoded(definitions[pid,attempt['key_id']])
            if len(key)>=4 and key[0]in ('pairs','count','ttg_path') and type(key[2])is str:
                observed_sql.add(key[2])
        exact_native_sql=[dict(begin=r,end=sqlend.get((pid,sid))) for (p,sid),r in sql.items()
                          if p==pid and r.get('access_id')==aid and r.get('sql')in observed_sql]
        outcomes.append(dict(pid=pid,access_id=aid,request_id=request(begin),
            from_visit=begin.get('from_visit'),outcome=outcome,begin=begin,
            lookups=attempts,candidates=candidates,exact_native_sql=exact_native_sql))
    ordinary=[r for r in outcomes if r['from_visit']is False]
    visits=[r for r in outcomes if r['from_visit']is True]
    unknown=[r for r in outcomes if r['from_visit']is None]
    counts=lambda values:dict(Counter(r['outcome']for r in values))
    # Payload denominator is (logical get/batch call, requested UID), separate
    # from graph-path resolutions and unique demanded identities.
    payload=[];promotion_index={};load_index={}
    for p in rows:
        if p['kind']=='payload_promotion' and p['served']:
            promotion_index.setdefault((p['pid'],p.get('payload_id'),p['uid']),[]).append(p)
        if p['kind']=='payload_load' and p.get('job_id')is None:
            for uid in p.get('loaded_ids')or []:
                load_index.setdefault((p['pid'],p.get('payload_id'),uid),[]).append(p)
    for r in rows:
        if r['kind']!='payload_begin' or request(r)not in selected:continue
        for uid in dict.fromkeys(r.get('ids')or []):
            promotions=promotion_index.get((r['pid'],r['seq'],uid),[])
            loads=load_index.get((r['pid'],r['seq'],uid),[])
            bg=[p for p in promotions if (p.get('raw_source')or {}).get('kind')=='background']
            state=('background_raw_promotion' if bg else 'other_raw_promotion' if promotions else
                   'native_payload_load' if loads else 'memory_or_unclassified')
            payload.append(dict(pid=r['pid'],payload_id=r['seq'],uid=uid,outcome=state))
    timeline=None
    for r in ordinary:
        if not r['candidates'] or not r['exact_native_sql']:continue
        candidate=next((c for c in r['candidates']if c['state']=='future_pending_through_lookup'),r['candidates'][0])
        jid=candidate['job_id'];pid=r['pid']
        timeline=dict(access=r,job_capture=jobs[pid,jid],worker_return=returns.get((pid,jid)),
            phases=phases.get((pid,jid),[]),future_observations=[e for e in rows if e.get('pid')==pid
                and e.get('job_id')==jid and e['kind']in ('future_attached','future_done_observed')],
            publication=[e for e in rows if e.get('pid')==pid and e['kind']=='cache_write'
                and (e.get('source')or {}).get('job_id')==jid],
            key_definitions={a['key_id']:definitions[pid,a['key_id']]for a in r['lookups']})
        break
    return dict(scope='Selected accepted business HTTP only; logical native resolver denominators',
        business_request_ids=list(business_request_ids),logical_path_resolutions=len(outcomes),
        ordinary_access=dict(n=len(ordinary),outcomes=counts(ordinary)),
        visit_backed=dict(n=len(visits),outcomes=counts(visits)),
        unknown_operation=dict(n=len(unknown),outcomes=counts(unknown)),
        nested_cache_attempts=sum(len(r['lookups'])for r in outcomes),
        payload=dict(n=len(payload),outcomes=counts(payload),denominator='(get/batch call, requested UID); not unique nodes'),
        timeline_available=timeline is not None,timeline=timeline,outcomes=outcomes,
        limits=['Future false→true bracket is readiness boundary/unknown.',
                'No materialized exact keys means unknown coverage, never inferred lateness.',
                'Validity flags are observed owner lease/epoch state; no causal hook-placement test.',
                'Native cache hits and raw promotion are separate from prefetch timing/business necessity.',
                'Instrumentation changes scheduling; three traced repeats are not primary n5.'])

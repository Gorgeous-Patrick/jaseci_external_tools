"""Offline extraction of the five accepted captures; no runtime/DB imports."""
from pathlib import Path
import hashlib,json,os

ROOT=Path(__file__).resolve().parents[2]
M=ROOT/'project-notes/measurements/ttg-plus-diagnostics-20261031'
RUN=M/'recapture-v1'
def sha(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def ref(p):return dict(path=str(p),sha256=sha(p))
def walk(node,path='/Plan'):
    yield node,path
    for i,child in enumerate(node.get('Plans',[])):
        yield from walk(child,path+'/Plans/'+str(i))

rows=[];bindings=[];known=set()
launch=json.loads((M/'recapture-v1-launch.json').read_text())
known.update((launch['creator_pid'],launch['launcher_pid']))
life=json.loads((RUN/'lifecycle.json').read_text())
known.update(s['pid'] for s in life['services'])
for cell in ('off','ttg_plus'):
    directory=RUN/('littlex-'+cell)
    acceptance_path=directory/'diagnostic-acceptance.json'
    acceptance=json.loads(acceptance_path.read_text());assert acceptance['passed']
    bindings.append(ref(acceptance_path))
    for entry in acceptance['selected']:
        p=Path(entry['capture']['path']);assert sha(p)==entry['capture']['sha256']
        capture=json.loads(p.read_text());target=capture['target']
        assert entry['plans_accepted_after_oracle']
        for rep in capture['explain']['repetitions']:
            plan=rep['full_plan'][0]['Plan'];nodes=[]
            for node,path in walk(plan):
                if node.get('Actual Loops',0)>0:
                    item={k:node[k] for k in ('Node Type','Index Name','Relation Name','Alias','Index Cond','Filter','Rows Removed by Filter','Actual Rows','Actual Loops','Actual Startup Time','Actual Total Time') if k in node}
                    item['plan_pointer']='/explain/repetitions/'+str(rep['repetition'])+'/full_plan/0'+path
                    item['buffers']={k:v for k,v in node.items() if k.endswith(' Blocks')}
                    nodes.append(item)
            rows.append(dict(target_id=target['target_id'],semantic_region=target['semantic_region'],
                repetition=rep['repetition'],capture=ref(p),actual_selected_rows=entry['actual_call']['returned_rows'],
                planning_ms=rep['planning_ms'],execution_ms=rep['execution_ms'],
                server_plan_plus_execution_ms=round(rep['planning_ms']+rep['execution_ms'],9),
                root_node=plan['Node Type'],root_actual_rows=plan['Actual Rows'],
                root_buffers={k:v for k,v in plan.items() if k.endswith(' Blocks')},executed_nodes=nodes,
                context=capture['state']['context'],settings=capture['state']['settings']))
    for p in directory.glob('server-*.events.jsonl'):
        with p.open() as stream:
            for line in stream:
                if '"worker_process_pids"' in line:
                    d=json.loads(line);known.update(d.get('summary',{}).get('worker_process_pids',[]))
                elif '"kind":"process_reader_ready"' in line:
                    known.add(json.loads(line)['child_process_pid'])
assert len(rows)==10 and len({(r['target_id'],r['repetition']) for r in rows})==10
comparisons=[]
for rep in (0,1):
    indexed={r['target_id']:r for r in rows if r['repetition']==rep}
    for label,native,fused in [('root_profile',['native-root'],'fused-root'),('collect',['native-post','native-follow'],'fused-batch')]:
        n=[indexed[key] for key in native];f=indexed[fused]
        comparisons.append(dict(region=label,repetition=rep,native_targets=native,fused_target=fused,
            native_planning_ms=round(sum(r['planning_ms'] for r in n),9),fused_planning_ms=f['planning_ms'],
            native_execution_ms=round(sum(r['execution_ms'] for r in n),9),fused_execution_ms=f['execution_ms'],
            native_rows=sum(r['root_actual_rows'] for r in n),fused_rows=f['root_actual_rows'],
            native_root_shared_hits=sum(r['root_buffers']['Shared Hit Blocks'] for r in n),
            fused_root_shared_hits=f['root_buffers']['Shared Hit Blocks'],
            native_root_shared_reads=sum(r['root_buffers']['Shared Read Blocks'] for r in n),
            fused_root_shared_reads=f['root_buffers']['Shared Read Blocks']))
processes=[]
for pid in sorted(known):
    try:os.kill(pid,0);alive=True
    except ProcessLookupError:alive=False
    processes.append(dict(pid=pid,alive=alive))
stopped=dict(passed=life['services_stopped'] and life['pg_ctl_status']==3 and not life['pidfile']
    and life['retained_databases']==[] and not any(p['alive'] for p in processes),
    original_lifecycle=ref(RUN/'lifecycle.json'),known_processes=processes,pg_ctl_status=3,
    pidfile=False,retained_databases=[],source_guard_before_after=True)
assert stopped['passed'];(M/'stopped-proof-v1.json').write_text(json.dumps(stopped,indent=2)+'\n')
result=dict(passed=True,kind='bounded_matched_littlex_explain',accepted_recaptures=bindings,
    selection=ref(M/'selection-v1.json'),source_binding=ref(RUN/'sources.json'),
    summarizer=ref(Path(__file__).resolve()),primary_measurement=False,plans=rows,comparisons=comparisons,
    definitions=dict(times='Server-reported EXPLAIN planning/execution milliseconds; first and repeated shown separately',
        buffers='Root counters inclusive; only independent native statement roots are added',
        regime='Same recapture connection/transaction, isolation captured; controlled unchanged graph; census/EXPLAIN warmed',
        limitation='One matched diagnostic instance per configuration; does not decompose primary n3 wall time or measure server CPU'))
(M/'explain-summary-v1.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(summary=ref(M/'explain-summary-v1.json'),stopped_proof=ref(M/'stopped-proof-v1.json'),comparisons=comparisons),indent=2))

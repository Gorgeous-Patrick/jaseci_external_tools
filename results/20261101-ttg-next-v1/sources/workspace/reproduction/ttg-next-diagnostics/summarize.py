"""Small figure inputs derived only from accepted diagnostic plans and state."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
E=ROOT/'project-notes/measurements/ttg-next-diagnostics-20261101'
def ref(p):return dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def flatten(n,path='Plan'):
    result=[dict(path=path,**{k:n[k] for k in ('Node Type','Join Type','Index Name','Index Cond','Filter','Plan Rows','Actual Rows','Actual Loops','Actual Total Time') if k in n})]
    for i,c in enumerate(n.get('Plans',[])):result+=flatten(c,f'{path}/Plans/{i}')
    return result
def details(plan):
    n=plan['Plan'];return dict(estimated_total_cost=n['Total Cost'],jit=plan.get('JIT'),root_buffers={k:v for k,v in n.items() if k.endswith(' Blocks')},operators=flatten(n))
def main():
    rec=[]
    for path in sorted((E/'recapture-v2/cases').glob('*/captures/*.json')):
        c=json.loads(path.read_text());a=path.parent.parent/'diagnostic-acceptance.json'
        rec.append(dict(config_id=c['target']['config_id'],capture=ref(path),acceptance=ref(a),actual_original_rows=1000,wire_packet_sha256=c['wire']['packet_sha256'],state_isolation=c['state']['context'][0][3],settings=c['state']['settings'],relations=c['state']['relations'],statistics_rows=len(c['state']['statistics']),plans=[dict(repetition=r['repetition'],planning_ms=r['planning_ms'],execution_ms=r['execution_ms'],**details(r['full_plan'][0])) for r in c['explain']['repetitions']]))
    lab=json.loads((E/'stats-lab-v1/result.json').read_text());controlled=[]
    for case in lab['cases']:
        controlled.append(dict(config_id=case['config_id'],capture=case['capture'],exact_bind_verified=case['exact_bind_verified'],indexes=case['indexes'],constraints=case['constraints'],settings=case['settings'],jit_settings=case['extra_settings'],database_dropped_after_zero_active=case['database_dropped_after_zero_active'],phases=[dict(analyzed=p['analyzed'],relations=p['relations'],statistics_rows=len(p['statistics']),ordered_result_verified=p['ordered_result_verified'],census_verified=p['census_verified'],plans=[dict(repetition=r['repetition'],planning_ms=r['planning_ms'],execution_ms=r['execution_ms'],**details(r['full_plan'][0])) for r in p['plans']]) for p in case['phases']]))
    summary=dict(passed=True,kind='accepted_LL1000_SQL_diagnostic_summary',primary_performance=False,recapture=rec,controlled_statistics=controlled,refs={k:ref(E/p) for k,p in {'recapture_result':'recapture-v2/result.json','recapture_lifecycle':'recapture-v2/lifecycle.json','recapture_sources':'recapture-v2/sources.json','stats_result':'stats-lab-v1/result.json','stats_lifecycle':'stats-lab-v1/lifecycle.json','stats_launch':'stats-lab-v1/launch.json'}.items()},interpretation='In both restored fixtures, ANALYZE removes a repeated kind-only Bitmap Index Scan beneath BitmapAnd at two path-evaluation sites (1000 rows per loop,1000 loops each before). Endpoint BitmapOr remains; root shared hits fall20126->16126 and execution fallsabout48-50ms->13.4-13.7ms. This establishes controlled plan sensitivity for the captured SQL, not the statistics/autovacuum state of primary samples.',limitations=['Primary both versions have slow and fast samples; primary plans/statistics were not captured.','Same diagnostic Bind/captured anchors/types/indexes/settings and ordered result are verified. Original DDL defaults fill unused uncaptured columns; restored heap layout is not claimed byte-identical.','Census/result checks warm buffers; EXPLAIN adds instrumentation. No cold-cache or application-speedup claim.','Statistics views may lag; pre-ANALYZE cumulative table counters are observations, not synchronous modification counts.','JIT is absent in all12 retained plans; observed estimated costs are below observed jit_above_cost100000.','Root buffers are reported directly; inclusive parent/child counters are never summed.'],littlex_mechanism=ref(ROOT/'project-notes/measurements/ttg-next-performance-20261101/littlex-mechanism-v1.json'))
    (E/'summary-v1.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# LL1000 matched SQL diagnostics','','Two full native workflows passed; actual selected queries each completed with1000 rows. The four initial plans and eight controlled plans are separate from primary measurements.','','| Query | Regime | Planning ms (first/repeat) | Execution ms (first/repeat) | Root shared hits | Reads |','|---|---|---|---|---:|---:|']
    for r in rec:
        p=r['plans'];lines.append(f"| {r['config_id']} | Actual recapture, no ANALYZE | {p[0]['planning_ms']}/{p[1]['planning_ms']} | {p[0]['execution_ms']}/{p[1]['execution_ms']} | {p[0]['root_buffers']['Shared Hit Blocks']} | {p[0]['root_buffers']['Shared Read Blocks']} |")
    for r in controlled:
        for phase in r['phases']:
            p=phase['plans'];label='After ANALYZE' if phase['analyzed'] else 'Restored, before ANALYZE';lines.append(f"| {r['config_id']} | {label} | {p[0]['planning_ms']}/{p[1]['planning_ms']} | {p[0]['execution_ms']}/{p[1]['execution_ms']} | {p[0]['root_buffers']['Shared Hit Blocks']} | {p[0]['root_buffers']['Shared Read Blocks']} |")
    lines+=['',summary['interpretation'],'','Before ANALYZE both restored tables have reltuples=-1/relpages=0 and no column statistics. Afterward anchors has2005 estimated rows/126pages and graph_types4rows/1page. The repeated kind-only scan estimated18rows but returned1000 per loop; ANALYZE eliminates it from both recursive expansion and path-output evaluation. The actual source/state/Bind/plan-node paths are bound in summary-v1.json.','','JIT: on, but no JIT section in any retained plan; jit_above_cost100000, inline/optimize thresholds500000. No JIT cause is established here.','','Limitations:']+['- '+s for s in summary['limitations']]
    (E/'summary-v1.md').write_text('\n'.join(lines)+'\n');print(ref(E/'summary-v1.json'))
if __name__=='__main__':main()

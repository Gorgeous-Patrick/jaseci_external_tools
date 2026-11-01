"""Numeric presentation supplement from the sealed LittleX attribution only."""
import hashlib,json,statistics
from pathlib import Path

E=Path(__file__).resolve().parent
def ref(p):return dict(path=str(Path(p).resolve()),sha256=hashlib.sha256(Path(p).read_bytes()).hexdigest())
p=E/'littlex-attribution-v1/results.json'
d=json.loads(p.read_text())
def category(g):
    if g['kind']=='control':return 'Control'
    if g['fingerprint'].startswith('b0075df9'):return 'Payload loading'
    if g['sql'].lstrip().startswith(('SELECT n1.id, e1.id','SELECT n2.id, e2.id','SELECT * FROM (SELECT * FROM (SELECT CAST','WITH RECURSIVE')):return 'Path discovery'
    return 'Other data'
rows=[]
for mode in ('off','prefusion','ttg_plus'):
    trials=[t for t in d['trials'] if t['config']==mode]
    summaries=[]
    for name in ('Path discovery','Payload loading','Control','Other data'):
        values=[]
        for t in trials:
            gs=[g for g in t['fingerprints'] if category(g)==name]
            values.append(dict(repeat=t['repeat'],SQL=sum(g['sql_dispatches'] for g in gs),
                protocol_ns=sum(g['protocol_sum_ns'] for g in gs),rows=sum(g['data_rows'] for g in gs),
                bytes=sum(g['data_row_payload_bytes'] for g in gs)))
        summaries.append(dict(category=name,trials=values,mean_SQL=statistics.mean(x['SQL'] for x in values),
            mean_protocol_ms=statistics.mean(x['protocol_ns']/1e6 for x in values)))
    for t in trials:
        assert sum(s['trials'][trials.index(t)]['SQL'] for s in summaries)==t['primary']['sql_dispatches']
    rows.append(dict(config=mode,categories=summaries))
t=next(t for t in d['trials'] if t['config']=='ttg_plus' and t['repeat']==0)
rpc=[g for g in t['per_RPC'] if g['request']=='2:20']
timeline=[dict(**c,role=g['role'],fingerprint=g['fingerprint']) for g in rpc for c in g['observed_calls']]
assert len(timeline)==15
payload=[]
for t in d['trials']:
    gs=[g for g in t['fingerprints'] if g['fingerprint'].startswith('b0075df9')]
    payload.append(dict(config=t['config'],repeat=t['repeat'],calls=sum(g['sql_dispatches'] for g in gs),
        rows=sum(g['data_rows'] for g in gs),bytes=sum(g['data_row_payload_bytes'] for g in gs),
        roles=[dict(role=g['role'],calls=g['sql_dispatches'],rows=g['data_rows'],bytes=g['data_row_payload_bytes']) for g in gs]))
out=E/'presentation-data-v1';out.mkdir(exist_ok=False)
result=dict(passed=True,source=ref(__file__),attribution=ref(p),n=3,
    classification='Control uses reviewed SQL kind; payload exact b0075 fingerprint from PgStore.load_full; paths are explicit native n1/n2 path or certified fused SQL; remainder Other data.',
    LittleX_mean_categories=rows,LittleX_payload=payload,
    targets=d['diagnostic_targets'],timeline=dict(trial=t['trial'],request='2:20',path='/walker/load_feed',
        calls=timeline,definition='Actual send-to-Z intervals; separate OS/backend IDs; wall clock includes client decode progress.'))
# The t loop above is payload inventory; timeline identity is explicitly the selected sample.
result['timeline']['trial']='littlex-ttg_plus-measured-0'
(out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
(out/'artifacts.json').write_text(json.dumps(dict(passed=True,outputs=[ref(out/'results.json')]),indent=2)+'\n')
print(json.dumps(ref(out/'results.json')))

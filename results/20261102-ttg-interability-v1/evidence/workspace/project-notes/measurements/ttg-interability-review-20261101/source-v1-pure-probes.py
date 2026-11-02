"""Tiny source-backed Python witnesses. No Jac import/compiler/runtime/DB/test runner."""
import hashlib,json
from functools import cached_property
from pathlib import Path
R=Path('/home/baichuan/jaseci');D=R/'project-notes/measurements/ttg-interability-20261101/source-v1';O=R/'project-notes/measurements/ttg-interability-review-20261101'
def ref(p):return {'path':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
m=json.loads((D/'manifest.json').read_text())
for name,h in m['files'].items():assert ref(D/name)['sha256']==h
# Same primitive-value/descriptor distinction as known_node_fields, without imports.
class Item:
    value=1
    def __init__(self):self.value=1
    @cached_property
    def __jac__(self):return object()
i=Item();anchor=i.__jac__
facts={}
for name,value in vars(i).items():
    descriptor=any(name in vars(b) and any('__get__' in vars(c) for c in type(vars(b)[name]).__mro__) for b in type(i).__mro__)
    facts[name if not descriptor and type(value) in (bool,int,float,str,type(None)) else name+'::unsafe']=value if not descriptor and type(value) in (bool,int,float,str,type(None)) else True
assert facts['__jac__::unsafe'] is True
# Write-only destination is absent from the read-key set passed at regions297.
class SetterWalker:
    def __init__(self):self.effects=[]
    @property
    def sink(self):raise AssertionError('getter must not run')
    @sink.setter
    def sink(self,v):self.effects.append(v)
reads=set();writes={'self.sink'}
read_only_checked=[k for k in reads if k.startswith('self.')]
assert not read_only_checked
w=SetterWalker();object.__setattr__(w,'sink',1);assert w.effects==[1]
# Walker exit callback triggers refer to node class; node exit triggers to walker class.
class Node:pass
class Walker:pass
wrong_node_exit_applicability=issubclass(Node,Walker)
actual_node_exit_applicability=issubclass(Walker,Walker)
assert not wrong_node_exit_applicability and actual_node_exit_applicability
# Fast payload list not sliced to remaining; legacy branch slices at518.
maximum=4;submitted={'old1','old2','old3'};new=['new1','new2','new3']
fast_count=len(submitted|set(new));bounded_count=len(submitted|set(new[:maximum-len(submitted)]))
assert fast_count==6 and bounded_count==4
errors={}
for label,left,right,op in [('wrong_total',None,1,'+'),('valid_typed_zero_divisor',1,0,'/')]:
    try:result=left+right if op=='+' else left/right
    except Exception as e:errors[label]=type(e).__name__
assert errors=={'wrong_total':'TypeError','valid_typed_zero_divisor':'ZeroDivisionError'}
result=dict(scope='Source-condition witnesses only; not execution of the Jac implementation or native regression tests.',source_manifest=ref(D/'manifest.json'),copied_hashes_verified=len(m['files']),witnesses={'internal_metadata':{'fact_keys':list(facts),'v1_declines':any(k.endswith('::unsafe') for k in facts)},'write_only_descriptor':{'read_keys':sorted(reads),'omitted_write_keys':sorted(writes),'setter_effects':w.effects},'typed_node_exit':{'v1_applicable':wrong_node_exit_applicability,'native_trigger_type_applicable':actual_node_exit_applicability},'submission_budget':{'maximum':maximum,'prior':len(submitted),'new':len(new),'v1_total':fast_count,'bounded_total':bounded_count},'output_arithmetic':{'both_state_values_pass_v1_allowed_type_set':all(type(v) in (bool,int,float,str,list,type(None)) for v in [None,1]),'exceptions':errors}},probe_source=ref(Path(__file__)))
(O/'source-v1-pure-probes.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

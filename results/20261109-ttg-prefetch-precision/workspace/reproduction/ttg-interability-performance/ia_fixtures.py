"""DB-free finite fixtures/oracles; original graph generator/source stay immutable."""
import copy,hashlib,importlib.util,json,random,shutil
from pathlib import Path
from ia_config import OWN,APP_SNAPSHOT,digest,write_config
ROOT=APP_SNAPSHOT.parent

def corpus():
 spec=importlib.util.spec_from_file_location('_ia_original_corpus',ROOT/'datasets/ttg/build.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def fixture(case):
 c=corpus()
 if case['app']=='linked_list':
  config=copy.deepcopy(c.SCALES[case['scale']]);g=c.make_graph('linked_list',config,random.Random(42))
  proof=prove_chain(g,case['length']);walker='Traverse';reports=list(range(case['length']));visited=case['length'];types=(['Item'],['Next'])
 elif case['app']=='region_chain':
  config=dict(nodes=3,guard=case.get('guard',True));g=c.Graph();g.node('item:0','A',value=10)
  g.node('item:1','B',value=20,active=case.get('guard',True));g.node('item:2','C',value=30)
  g.edge('item:0','AB','item:1');g.edge('item:1','BC','item:2')
  reports=[10,20]+([30] if config['guard'] else []);visited=len(reports);walker='RegionChain';types=(['A','B','C'],['AB','BC'])
  proof=dict(passed=True,acyclic=True,successors={'item:0':['item:1'],'item:1':['item:2'],'item:2':[]},
   guard_type='bool',guard=config['guard'],expected_entered=['A','B']+(['C'] if config['guard'] else []))
 else:raise ValueError('Custom traversal fixture only')
 return dict(graph=g,config=config,shape_proof=proof,walker=walker,reports=reports,visited=visited,types=types)

def prove_chain(g,n):
 assert len(g.nodes)==n and all(v['type']=='Item' for v in g.nodes.values())
 assert len(g.edges)==n-1 and all(e['type']=='Next' for e in g.edges)
 successors={key:[] for key in g.nodes};incoming={key:0 for key in g.nodes}
 for e in g.edges:successors[e['source']].append(e['target']);incoming[e['target']]+=1
 assert all(len(v)<=1 for v in successors.values())
 assert incoming['item:0']==0 and all(v==1 for k,v in incoming.items() if k!='item:0')
 seen=[];cur='item:0'
 while cur is not None:
  assert cur not in seen,'Cycle in finite traversal fixture';seen.append(cur)
  cur=successors[cur][0] if successors[cur] else None
 assert seen==['item:'+str(i) for i in range(n)] and set(seen)==set(g.nodes)
 return dict(passed=True,all_nodes_type='Item',node_count=n,typed_edges=n-1,maximum_successors=1,
  all_nodes_reachable_from_head=True,acyclic=True,ordered_identity_sha256=digest(seen),
  interpretation='Fixture successor/cardinality/reachability proof; visited is TOTAL output, never used as depth.')

def prepare(directory,case,mode):
 directory=Path(directory);directory.mkdir();f=fixture(case);dataset=directory/'dataset';dataset.mkdir()
 for name,rows in [('nodes.jsonl',f['graph'].nodes.values()),('edges.jsonl',f['graph'].edges)]:
  (dataset/name).write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows))
 action=dict(op='traverse' if case['app']=='linked_list' else 'guard_chain',target='item:0',walker=f['walker'])
 (dataset/'operations.jsonl').write_text(json.dumps(action)+'\n');(dataset/'expected.jsonl').write_text(json.dumps(dict(reports=f['reports'],visited=f['visited']))+'\n')
 files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dataset.iterdir()}
 (dataset/'manifest.json').write_text(json.dumps(dict(app=case['app'],scale=case['scale'],seed=42,config=f['config'],files=files),indent=2)+'\n')
 (directory/'fixture-shape-proof.json').write_text(json.dumps(f['shape_proof'],indent=2)+'\n')
 source=OWN/('apps/linked_list/main.jac' if case['app']=='linked_list' else 'apps/region_chain/server.jac')
 nodes,edges=f['types'];node_map='{'+','.join('"'+n+'":'+n for n in nodes)+'}';edge_map='{'+','.join('"'+n+'":'+n for n in edges)+'}'
 extension='''
import from native_seed { import_graph, inspect_graph }
walker SuiteRoot { can identify with Root entry { report jid(root); } }
walker SuiteImport {
 has roots: dict;
 can load with Root entry { report import_graph(NODE_MAP, EDGE_MAP, self.roots, None); }
}
walker SuiteInspect {
 has mapping: dict;
 can inspect with Root entry { report inspect_graph(self.mapping); }
}
'''.replace('NODE_MAP',node_map).replace('EDGE_MAP',edge_map)
 (directory/'server.jac').write_text(source.read_text()+extension)
 shutil.copyfile(ROOT/'app_suite/native_seed.py',directory/'native_seed.py')
 (directory/'source-adaptation.json').write_text(json.dumps(dict(owned_source=str(source),owned_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
  changes=['Append unchanged native import/inspect adapters'],core_source_unchanged=True),indent=2)+'\n')
 write_config(directory,mode);return f

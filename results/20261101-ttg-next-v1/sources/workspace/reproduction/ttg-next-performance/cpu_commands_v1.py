"""Record exact completed CPU commands and reproducible environment; does not run them."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OWN=ROOT/'reproduction/ttg-next-performance';E=ROOT/'project-notes/measurements/ttg-next-performance-20261101'
def ref(p):return dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
commands=[]
for stage in ['compile','runtime']:
 for mode in ['next','baseline850']:
  runtime=OWN/'runtime-direct-9282-v1' if mode=='next' else ROOT/'reproduction/ttg-plus-performance/runtime-direct-final-v2'
  for case in ['linked_list32','littlex']:
   output=E/('cpu-'+stage+'-'+mode+'-'+case+'-v1')
   command=['bash',str(ROOT/'reproduction/ttg-continuation-performance/runtime.sh'),'-B',str(OWN/'cpu_driver.py'),'--implementation',mode,'--runtime-manifest',str(runtime)+'-overlay/manifest.json']
   if stage=='compile':command+=['--module',str(E/'cpu-inputs-v1'/case/'server.jac')]
   else:command+=['--plans',str(E/('cpu-compile-next-'+case+'-v1')/'emitted-checkpoint-plans.json'),'--spec',str(E/'cpu-inputs-v1'/case/'runtime-shapes.json')]
   command+=['--output',str(output)]
   result=json.loads((output/'result.json').read_text());assert result['passed'] and result['driver']==ref(OWN/'cpu_driver.py')
   commands.append(dict(stage=stage,implementation=mode,case=case,argv=command,
    environment=dict(TTG_RUNTIME_SOURCE=str(runtime),TTG_RUNTIME_CACHE=str(OWN/('cache-'+runtime.name+'-runtime')),TTG_CACHE_DIR=str(OWN/('cache-'+runtime.name+'-compiler'))),
    output=ref(output/'result.json'),log=ref(E/('cpu-'+stage+'-'+mode+'-'+case+'-v1.log')),exit_code=0))
result=dict(passed=True,source=ref(Path(__file__)),driver=ref(OWN/'cpu_driver.py'),commands=commands,
 executor='Sequential subprocess.run; compiler group session31234 exit0, runtime group session31549 exit0; no services/database started.',
 defaults=dict(repeats=3,runtime_iterations=100,compiler_iterations=1),
 order='next LL /next LittleX /baseline LL /baseline LittleX, compiler then runtime; fixed order disclosed as diagnostic limitation.',
 cache='Reused per-runtime primary compiler/JIT cache directories; new JacProgram or same-program regimes explicitly labelled; first compiler/dependency initialization and no OS flush retained.',
 reexecution='Use NEW output paths; modules/input specs/emitted plans preserved. No primary artifact may be overwritten.')
p=E/'cpu-commands-v1.json';assert not p.exists();p.write_text(json.dumps(result,indent=2)+'\n');print(ref(p))

from pathlib import Path
import os,subprocess,json,time,hashlib,shutil,shlex
ROOT=Path('/home/baichuan/jaseci');CORE=ROOT/'jac-ttg';OUT=ROOT/'project-notes/measurements/ttg-interability-20261101/regression-final-v2'
CACHE=Path('/tmp/ttg-interability-regression-db-v1');DATA=CACHE/'pg/main';BIN=Path('/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin')
assert not OUT.exists() and CACHE.exists();OUT.mkdir();assert subprocess.run([str(BIN/'pg_ctl'),'-D',str(DATA),'status'],capture_output=True).returncode==3
cli=Path('/tmp/jac-ttg-interability-regression-cli');body=Path('/tmp/jac-ttg-cli').read_text().replace('export JAC_CACHE_HOME=/tmp/jac-ttg-db','export JAC_CACHE_HOME=/tmp/ttg-interability-regression-db-v1\nunset JAC_DB_URL');cli.write_text(body);cli.chmod(0o755)
paths=subprocess.check_output(['git','diff','--name-only'],cwd=CORE,text=True).splitlines()+['jac/jaclang/runtime/ttg_regions.jac','jac/tests/runtimelib/fixtures/ttg_region_walkers.jac','jac/tests/runtimelib/test_ttg_regions.jac','jac/tests/runtimelib/test_ttg_regions_native.jac']
def hashes():return {p:hashlib.sha256((CORE/p).read_bytes()).hexdigest() for p in paths}
(OUT/'source-start.json').write_text(json.dumps(hashes(),indent=2));(OUT/'launcher.py').write_bytes(Path(__file__).read_bytes());(OUT/'runtime-cli.sh').write_text(body)
opts=shlex.split((DATA/'postmaster.opts').read_text());assert opts[1:3]==['-D',str(DATA)]
(OUT/'previous-postmaster-options.json').write_text(json.dumps(opts,indent=2))
old=json.loads((ROOT/'project-notes/measurements/ttg-next-20261101/regression-final-v1/outcome.json').read_text())['command']
cmd=[str(cli),*old[1:],'jac/tests/runtimelib/test_ttg_regions.jac','jac/tests/runtimelib/test_ttg_regions_native.jac']
env={**os.environ,'TTG_INTERABILITY_EVIDENCE':str(OUT/'regions.jsonl'),'TTG_PLUS_NATIVE_EVIDENCE':str(OUT/'fusion.jsonl'),'TTG_ACL_TEST_EVIDENCE':str(OUT/'acl.jsonl'),'TTG_NEXT_NATIVE_EVIDENCE':str(OUT/'frontier.jsonl')};env.pop('JAC_DB_URL',None)
owner={'creator_pid':os.getpid(),'command':cmd,'cache_home':str(CACHE),'data':str(DATA),'routing':'Standard embedded PgRuntime with private hashed Unix socket; JAC_DB_URL unset; project databases stay isolated','min_wal_size':'32MB','max_wal_size':'64MB','source_start':hashes(),'free_before':shutil.disk_usage(ROOT).free,'started':time.time()}
records={}
def record(pid):
 try:
  p=Path('/proc')/str(pid);records[pid]={'pid':pid,'stat':(p/'stat').read_text(),'cmdline':(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')}
 except (FileNotFoundError,PermissionError):return
 try:
  for c in (p/'task'/str(pid)/'children').read_text().split():record(int(c))
 except (FileNotFoundError,PermissionError):pass
child=None;code=1
try:
 subprocess.run([str(BIN/'pg_ctl'),'-D',str(DATA),'-l',str(OUT/'postgres.log'),'-o',shlex.join(opts[3:]),'-w','start'],check=True)
 with (OUT/'tests.log').open('w') as log:
  child=subprocess.Popen(cmd,env=env,cwd=CORE,stdout=log,stderr=subprocess.STDOUT);owner['test_pid']=child.pid;(OUT/'owner.json').write_text(json.dumps(owner,indent=2))
  deadline=time.monotonic()+900
  while True:
   record(child.pid)
   if (DATA/'postmaster.pid').exists():
    try:record(int((DATA/'postmaster.pid').read_text().splitlines()[0]))
    except (ValueError,FileNotFoundError):pass
   try:code=child.wait(timeout=.5);break
   except subprocess.TimeoutExpired:
    assert time.monotonic()<deadline,'bounded regression timed out'
finally:
 if child is not None and child.poll() is None:child.terminate();child.wait(timeout=30)
 status_before=subprocess.run([str(BIN/'pg_ctl'),'-D',str(DATA),'status'],capture_output=True)
 stop=subprocess.run([str(BIN/'pg_ctl'),'-D',str(DATA),'-w','stop','-m','fast'],capture_output=True,text=True) if status_before.returncode==0 else None
 status=subprocess.run([str(BIN/'pg_ctl'),'-D',str(DATA),'status'],capture_output=True)
 (OUT/'source-end.json').write_text(json.dumps(hashes(),indent=2));(OUT/'recorded-processes.json').write_text(json.dumps(list(records.values()),indent=2))
 lifecycle={'test_pid':child.pid if child else None,'test_exit':child.poll() if child else None,'pg_status':status.returncode,'has_pid':(DATA/'postmaster.pid').exists(),'stop_exit':stop.returncode if stop else None,'free_after':shutil.disk_usage(ROOT).free,'finished':time.time()}
 (OUT/'lifecycle.json').write_text(json.dumps(lifecycle,indent=2));(OUT/'outcome.json').write_text(json.dumps({'passed':code==0,'exit':code,'source_unchanged':owner['source_start']==hashes()},indent=2))
print('REGRESSION OUTCOME',OUT,code);raise SystemExit(code)

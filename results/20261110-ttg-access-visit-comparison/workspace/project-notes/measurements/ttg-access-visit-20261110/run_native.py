from pathlib import Path
import os,json,socket,subprocess,time,shutil,sys,hashlib
ROOT=Path('/home/baichuan/jaseci');OUT=ROOT/'project-notes/measurements/ttg-access-visit-20261110'/sys.argv[1]
PG=ROOT/'reproduction/ttg-access-visit-20261110/pg-native-v1';BIN=Path('/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin')
assert not OUT.exists();OUT.mkdir();PG.mkdir(parents=True,exist_ok=True)
source_paths=sorted(set(subprocess.check_output(['git','diff','--name-only'],cwd=ROOT/'jac-ttg',text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT/'jac-ttg',text=True).splitlines()))
def source_hashes():return {p:hashlib.sha256((ROOT/'jac-ttg'/p).read_bytes()).hexdigest() for p in source_paths}
(OUT/'source-start.json').write_text(json.dumps(source_hashes(),indent=2))
(OUT/'launcher.py').write_bytes(Path(__file__).read_bytes())
if (PG/'data/PG_VERSION').exists():
 assert subprocess.run([str(BIN/'pg_ctl'),'-D',str(PG/'data'),'status'],capture_output=True).returncode==3
else:
 assert not (PG/'data/postmaster.pid').exists()
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
owner=dict(creator_pid=os.getpid(),data=str(PG/'data'),port=port,source_root=str(ROOT/'jac-ttg'),out=str(OUT),started=time.time(),free_bytes=shutil.disk_usage(ROOT).free)
(OUT/'owner.json').write_text(json.dumps(owner,indent=2))
code=1;started=False;child=None
try:
 if not (PG/'data/PG_VERSION').exists():
  with (OUT/'init.log').open('w') as log:subprocess.run([str(BIN/'initdb'),'-D',str(PG/'data'),'-U','ttginterability','-A','trust','--no-locale','--encoding=UTF8'],stdout=log,stderr=subprocess.STDOUT,check=True)
  with (PG/'data/postgresql.conf').open('a') as f:f.write("\nshared_buffers='32MB'\nmax_connections=12\nmin_wal_size='32MB'\nmax_wal_size='64MB'\nlog_statement='none'\nunix_socket_directories=''\n")
 subprocess.run([str(BIN/'pg_ctl'),'-D',str(PG/'data'),'-l',str(OUT/'postgres.log'),'-o',f'-h127.0.0.1 -p{port}','-w','start'],check=True);started=True
 env={**os.environ,'PYTHONNOUSERSITE':'1','PYTHONPATH':'/tmp/jac-ttg-metadata:'+str(ROOT/'jac-ttg/jac'),'XDG_CACHE_HOME':'/tmp/jac-ttg-cache','JAC_CACHE_HOME':str(ROOT/'reproduction/ttg-access-visit-20261110/native-cache'),'JAC_DB_URL':f'postgresql://ttginterability@127.0.0.1:{port}/postgres','TTG_ACCESS_EVIDENCE':str(OUT/'native.jsonl')}
 cmd=[str(ROOT/'reproduction/runtime/pbs314/python/install/bin/python3.14'),'-s','-m','jaclang','test','-x',*sys.argv[2:]]
 (OUT/'command.json').write_text(json.dumps(dict(command=cmd,env={k:env[k] for k in ('JAC_DB_URL','TTG_ACCESS_EVIDENCE')}),indent=2))
 with (OUT/'native.log').open('w') as log:
  child=subprocess.Popen(cmd,env=env,cwd=ROOT/'jac-ttg',stdout=log,stderr=subprocess.STDOUT)
  owner['child_pid']=child.pid;(OUT/'owner.json').write_text(json.dumps(owner,indent=2))
  code=child.wait(timeout=900)
finally:
 if child is not None and child.poll() is None:
  child.terminate();child.wait(timeout=30)
 stop=subprocess.run([str(BIN/'pg_ctl'),'-D',str(PG/'data'),'-w','stop','-m','fast'],capture_output=True,text=True) if started else None
 status=subprocess.run([str(BIN/'pg_ctl'),'-D',str(PG/'data'),'status'],capture_output=True)
 (OUT/'lifecycle.json').write_text(json.dumps(dict(child_pid=child.pid if child else None,child_exit=child.poll() if child else None,stop_exit=stop.returncode if stop else None,pg_status=status.returncode,has_pid=(PG/'data/postmaster.pid').exists(),free_bytes=shutil.disk_usage(ROOT).free,finished=time.time()),indent=2))
 (OUT/'source-end.json').write_text(json.dumps(source_hashes(),indent=2))
 (OUT/'outcome.json').write_text(json.dumps(dict(exit=code,passed=code==0),indent=2))
print('NATIVE OUTCOME',OUT,code);sys.exit(code)

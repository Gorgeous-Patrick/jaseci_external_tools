from pathlib import Path
import os,json,socket,subprocess,time,shutil,sys,hashlib
ROOT=Path('/home/baichuan/jaseci');OUT=ROOT/'project-notes/measurements/ttg-jdrive-access-20261103'/sys.argv[1]
PG=ROOT/'project-notes/measurements/ttg-jdrive-access-20261103/pg-native-v1';BIN=Path('/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin')
assert not OUT.exists();OUT.mkdir();PG.mkdir(exist_ok=True)
source_paths=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT/'jac-ttg',text=True).splitlines()+['jac/jaclang/runtime/ttg_access_slice.py','jac/jaclang/runtime/ttg_output_tree.py','jac/tests/runtimelib/test_ttg_output_tree.jac']+['jac/jaclang/runtime/ttg_regions.jac','jac/tests/runtimelib/fixtures/ttg_region_walkers.jac','jac/tests/runtimelib/test_ttg_regions.jac','jac/tests/runtimelib/test_ttg_regions_native.jac']
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
 def query(database, sql):
  import struct
  with socket.create_connection(('127.0.0.1',port),timeout=10) as sock:
   params=b'user\0ttginterability\0database\0'+database.encode()+b'\0\0'
   sock.sendall(struct.pack('!II',len(params)+8,196608)+params)
   def take(n):
    buf=b''
    while len(buf)<n:
     part=sock.recv(n-len(buf));assert part;buf+=part
    return buf
   def ready():
    while True:
     kind=take(1);size=struct.unpack('!I',take(4))[0];data=take(size-4)
     if kind==b'E':raise RuntimeError(data.decode(errors='replace'))
     if kind==b'Z':return
   ready();body=sql.encode()+b'\0';sock.sendall(b'Q'+struct.pack('!I',len(body)+4)+body);ready()
   sock.sendall(b'X'+struct.pack('!I',4))
 owner['databases']=[]
 code=0
 for i,module in enumerate(sys.argv[2:]):
  database='dag_'+str(os.getpid())+'_'+str(i)
  query('postgres','CREATE DATABASE '+database)
  owner['databases'].append(database)
  env={**os.environ,'JAC_DB_URL':f'postgresql://ttginterability@127.0.0.1:{port}/{database}','TTG_INTERABILITY_EVIDENCE':str(OUT/'native.jsonl')}
  parts=module.split('::',1)
  cmd=['/tmp/jac-ttg-access-slice-cli','test','-x',*(['-t',parts[1]] if len(parts)>1 else []),parts[0]]
  with (OUT/('native-'+str(i)+'.log')).open('w') as log:
   child=subprocess.Popen(cmd,env=env,cwd=ROOT/'jac-ttg',stdout=log,stderr=subprocess.STDOUT)
   owner['child_pid']=child.pid;(OUT/'owner.json').write_text(json.dumps(owner,indent=2))
   code=child.wait(timeout=900)
  if code:break

finally:
 if child is not None and child.poll() is None:
  child.terminate();child.wait(timeout=30)
 stop=subprocess.run([str(BIN/'pg_ctl'),'-D',str(PG/'data'),'-w','stop','-m','fast'],capture_output=True,text=True) if started else None
 status=subprocess.run([str(BIN/'pg_ctl'),'-D',str(PG/'data'),'status'],capture_output=True)
 (OUT/'lifecycle.json').write_text(json.dumps(dict(child_pid=child.pid if child else None,child_exit=child.poll() if child else None,stop_exit=stop.returncode if stop else None,pg_status=status.returncode,has_pid=(PG/'data/postmaster.pid').exists(),free_bytes=shutil.disk_usage(ROOT).free,finished=time.time()),indent=2))
 (OUT/'source-end.json').write_text(json.dumps(source_hashes(),indent=2))
 (OUT/'outcome.json').write_text(json.dumps(dict(exit=code,passed=code==0),indent=2))
print('NATIVE OUTCOME',OUT,code);sys.exit(code)

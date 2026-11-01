"""Fresh-process regression for exact new release binding and actual export call."""
import hashlib,json,subprocess,sys
from pathlib import Path

PROBE=r'''
import inspect,json,runpy,sys
from pathlib import Path
own=Path(sys.argv[1]).resolve();sys.path.insert(0,str(own))
ns=runpy.run_path(str(own/'export_v2.py'),run_name='binding_probe')
release=ns['release'];assert Path(inspect.getsourcefile(release)).resolve()==own/'runner.py'
assert len(inspect.signature(release).parameters)==2
class ReachedCorrectRelease(Exception):pass
seen=[]
def release_read(path):seen.append(str(path));raise ReachedCorrectRelease()
release.__globals__['read_json']=release_read
export=ns['export'];g=export.__globals__
rows=ns['schedule'](True)
index=dict(passed=True,status='complete',stage='formal',rows=rows,
    plan=dict(path='/unused-plan'),postgres_settings=dict(path='/unused-settings'),authorization={})
plan=dict(postgres=dict(min_wal_size='32MB',max_wal_size='64MB'))
def metadata(path):
    if str(path)=='/unused-index':return index
    if str(path)=='/unused-plan':return plan
    if str(path)=='/unused-settings':return dict(passed=True,settings=plan['postgres'])
    raise AssertionError('Unexpected file read: '+str(path))
g['read_json']=metadata;g['checked_ref']=lambda value,parent:Path(value['path'])
try:export(Path('/unused-index'),Path('/never-created-output'))
except ReachedCorrectRelease:pass
else:raise AssertionError('Actual export did not invoke intended release')
assert len(seen)==1 and seen[0].endswith('/ttg-next-performance-20261101/formal-run-authorization.json')
print(json.dumps(dict(passed=True,release_module=release.__module__,release_source=inspect.getsourcefile(release),
    release_parameters=list(inspect.signature(release).parameters),actual_export_reached_release=True,
    authorization_path=seen[0],raw_or_DB_reads=0,synthetic_index_used_only_to_reach_release=True)))
'''

if __name__=='__main__':
    own=Path(__file__).resolve().parent
    result=subprocess.run([sys.executable,'-B','-c',PROBE,str(own)],capture_output=True,text=True)
    if result.returncode:print(result.stdout);print(result.stderr,file=sys.stderr);raise SystemExit(result.returncode)
    print(result.stdout,end='')

"""One bounded statistics control on two accepted captured fixtures; no app runs."""
import argparse,base64,hashlib,json,os,re,socket,subprocess,sys,time,uuid
from pathlib import Path
OWN=Path(__file__).resolve().parent
ROOT=OWN.parent.parent
M=ROOT/'project-notes/measurements/ttg-next-diagnostics-20261101'
BIN=Path('/home/baichuan/.cache/jac/pg/dist/linux-amd64-18.6.0/bin')

def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ref(path):return dict(path=str(path),sha256=sha(path))
def check(value,message):
    if not value:raise ValueError(message)
def normalized(rows):return [list(r[:9])+[json.loads(r[9]) if isinstance(r[9],str) else r[9]] for r in rows]
def chain_expected(capture):
    anchors=capture['state']['anchors'];nodes={r[0]:r for r in anchors if r[2]=='NodeAnchor'}
    items={r[0]:r for r in nodes.values() if r[3]=='Item'}
    start=next(r[0] for r in items.values() if json.loads(r[9])['archetype']['index']==0)
    result=[];seen=set();current=start
    for depth in range(1000):
        check(current not in seen,'Fixture cycle');seen.add(current)
        check(json.loads(items[current][9])['archetype']['index']==depth,'Fixture order')
        edges=sorted([r for r in anchors if r[2]=='EdgeAnchor' and r[3]=='Next' and (r[6]==current or (r[8] and r[7]==current))],key=lambda r:(r[1],r[0]))
        if not edges:
            check(depth==999,'Early fixture terminal');result.append([0,depth,current,None,None,None,None,None,None]);break
        check(len(edges)==1,'Fixture fanout');edge=edges[0];target=edge[7] if edge[6]==current else edge[6];node=nodes[target]
        result.append([0,depth,current,target,edge[0],node[3],node[4],1,1]);current=target
    check(len(result)==1000,'Fixture count');return result

def child(args):
    import jaclang
    from jaclang.data.pgwire import PgWireConnection,_named_to_positional,_encode_param
    from capture import ANCHORS,GRAPH_TYPES,INDEXES,SETTINGS,STATISTICS,RELATIONS
    from explain import plan_nodes
    output=args.output;result=dict(passed=False,kind='controlled_statistics_SQL_only',primary_measurement=False,cases=[])
    admin=PgWireConnection(user='ttgperf',host='127.0.0.1',port=args.port,database='postgres',application_name='ttg-stats-control-admin')
    schema=args.schema.read_text().split('impl ConnInfo.dsn')[0]
    ddl=[s for s in re.findall(r'"""(.*?)"""',schema,re.S) if re.search(r'CREATE TABLE IF NOT EXISTS (anchors|graph_types)\b|ON anchors\b',s)]
    extra_settings="SELECT name,setting FROM pg_settings WHERE name IN ('jit_above_cost','jit_inline_above_cost','jit_optimize_above_cost','jit_provider','default_statistics_target') ORDER BY name"
    for capture_path in args.captures:
        cap=json.loads(capture_path.read_text());mode=cap['target']['config_id'];folder=output/mode;folder.mkdir()
        acceptance=capture_path.parent.parent/'diagnostic-acceptance.json';check(json.loads(acceptance.read_text())['passed'],'Native capture not accepted')
        database='continuation_'+uuid.uuid4().hex;admin.run('CREATE DATABASE '+database)
        entry=dict(config_id=mode,capture=ref(capture_path),native_acceptance=ref(acceptance),database=database,schema_source=ref(args.schema),phases=[]);result['cases'].append(entry);write(output/'result.json',result)
        c=PgWireConnection(user='ttgperf',host='127.0.0.1',port=args.port,database=database,application_name='ttg-stats-control')
        try:
            for sql in ddl:c.run(sql)
            c.run('BEGIN')
            for row in cap['state']['anchors']:
                c.run('INSERT INTO anchors(id,seq,kind,arch_type,arch_module,root_id,src,dst,undirected,props) VALUES(CAST(:v0 AS uuid),CAST(:v1 AS bigint),:v2,:v3,:v4,CAST(:v5 AS uuid),CAST(:v6 AS uuid),CAST(:v7 AS uuid),CAST(:v8 AS boolean),CAST(:v9 AS jsonb))',**{f'v{i}':value for i,value in enumerate(row)})
            for name,ancestor in cap['state']['graph_types']:c.run('INSERT INTO graph_types VALUES(:name,:ancestor)',name=name,ancestor=ancestor)
            c.run('COMMIT')
            check(normalized(c.run(ANCHORS))==normalized(cap['state']['anchors']),'Restored census differs')
            check([list(r) for r in c.run(GRAPH_TYPES)]==cap['state']['graph_types'],'Restored types differ')
            indexes=[list(r) for r in c.run(INDEXES) if r[1] in ('anchors','graph_types')]
            check(indexes==[r for r in cap['state']['indexes'] if r[1] in ('anchors','graph_types')],'Restored indexes differ')
            constraints=c.run("SELECT conrelid::regclass::text,conname,contype,pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid IN ('anchors'::regclass,'graph_types'::regclass) ORDER BY conrelid::regclass::text,conname")
            check({r[1] for r in constraints if r[2]=='p'}=={'anchors_pkey','graph_types_pkey'} and all(r[2] in ('p','n') for r in constraints),'Original DDL constraints differ')
            for name,value in cap['state']['settings']:
                if name!='server_version_num':c.run('SELECT set_config(:name,:value,false)',name=name,value=value)
            check([list(r) for r in c.run(SETTINGS)]==cap['state']['settings'],'Original planner/session settings differ')
            params={name:None if value is None else base64.b64decode(value).decode('utf-8') for name,value in zip(cap['parameter_names'],cap['wire']['parameters_base64'])}
            positional,values=_named_to_positional(cap['original_sql'],params)
            check(positional==cap['wire']['positional_sql'],'Selected SQL changed')
            check([None if v is None else base64.b64encode(_encode_param(v)).decode() for v in values]==cap['wire']['parameters_base64'],'Selected Bind changed')
            expected=chain_expected(cap);entry.update(exact_captured_projection=True,unselected_columns='Original DDL defaults; not referenced by selected SQL',indexes=indexes,constraints=constraints,exact_bind_verified=True,settings=c.run(SETTINGS),extra_settings=c.run(extra_settings),expected_result_sha256=hashlib.sha256(json.dumps(expected,separators=(',',':')).encode()).hexdigest())
            for analyzed in (False,True):
                if analyzed:c.run('ANALYZE anchors');c.run('ANALYZE graph_types')
                c.run('BEGIN ISOLATION LEVEL SERIALIZABLE READ ONLY');c.run("SET LOCAL statement_timeout='30s'")
                try:
                    actual=[list(r) for r in c.run(cap['original_sql'],**params)];check(actual==expected,'Ordered SQL result differs from independent captured chain')
                    phase=dict(analyzed=analyzed,context=c.run("SELECT current_database(),pg_backend_pid(),current_setting('transaction_isolation'),txid_current_snapshot()::text"),statistics=c.run(STATISTICS),relations=c.run(RELATIONS),plans=[])
                    for repeat in (0,1):
                        rows=c.run('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+cap['original_sql'],**params);value=json.loads(rows[0][0]) if isinstance(rows[0][0],str) else rows[0][0]
                        plan=value[0];phase['plans'].append(dict(repetition=repeat,planning_ms=plan['Planning Time'],execution_ms=plan['Execution Time'],estimated_total_cost=plan['Plan']['Total Cost'],jit=plan.get('JIT'),nodes=plan_nodes(plan['Plan']),full_plan=value))
                    check(normalized(c.run(ANCHORS))==normalized(cap['state']['anchors']),'Census changed after plans')
                    check([list(r) for r in c.run(cap['original_sql'],**params)]==expected,'Ordered query changed after plans')
                    phase['ordered_result_verified']=True;phase['census_verified']=True;entry['phases'].append(phase)
                finally:c.run('ROLLBACK')
            write(folder/'result.json',entry);write(folder/'ordered-result.json',expected)
        finally:c.close()
        active=admin.run('SELECT count(*) FROM pg_stat_activity WHERE datname=:name',name=database)[0][0];check(active==0,'Controlled DB remains active');admin.run('DROP DATABASE '+database);entry['database_dropped_after_zero_active']=True;write(output/'result.json',result)
    admin.close();result.update(passed=True,scope='Two exact accepted captured projections, original DDL/indexes/settings and real Bind; 8 before/after first/repeat plans; no application rerun',limitations='Census/verification/query warmups disclosed; restores captured relevant columns with original defaults for unused columns. Controlled sensitivity does not label primary samples or prove their autovacuum state. EXPLAIN instrumentation is separate from primary protocol wall.');write(output/'result.json',result)

def controller(args):
    cluster=OWN/'pg-rec-v2';data=cluster/'data';prior=M/'recapture-v2/lifecycle.json';check(json.loads(prior.read_text())['pg_ctl_status']==3,'Recapture not stopped')
    check(not (data/'postmaster.pid').exists(),'Owned PG active');owner=cluster/'owner.json';owner_hash=sha(owner)
    args.output.mkdir();s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
    captures=sorted((M/'recapture-v2/cases').glob('*/captures/*.json'));check(len(captures)==2,'Exact two accepted captures')
    plan=json.loads((ROOT/'project-notes/measurements/ttg-next-performance-20261101/correctness-plan-v2/plan.json').read_text());runtime=Path(json.loads(Path(plan['runtimes']['baseline850']['clean']['path']).read_text())['root']);schema=runtime/'jac/jaclang/data/impl/store.impl.jac'
    cmd=['bash',str(ROOT/'reproduction/ttg-continuation-performance/runtime.sh'),str(Path(__file__).resolve()),'--child','--port',str(port),'--schema',str(schema),'--output',str(args.output),*[str(p) for p in captures]]
    write(args.output/'launch.json',dict(creator_pid=os.getpid(),source=ref(__file__),owner=ref(owner),prior_lifecycle=ref(prior),command=cmd,captures=[ref(p) for p in captures],primary_measurement=False))
    rc=None
    try:
        subprocess.run([str(BIN/'pg_ctl'),'start','-D',str(data),'-l',str(args.output/'postgres.log'),'-o',f"-h127.0.0.1 -p{port} -c unix_socket_directories=''",'-w'],check=True)
        env={**os.environ,'TTG_RUNTIME_SOURCE':str(runtime),'TTG_RUNTIME_CACHE':str(OWN/'cache-admin-runtime'),'TTG_CACHE_DIR':str(OWN/'cache-admin-compiler')}
        with (args.output/'child.log').open('w') as log:
            p=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT);launch=json.loads((args.output/'launch.json').read_text());launch['child_pid']=p.pid;write(args.output/'launch.json',launch);rc=p.wait(timeout=180)
        check(rc==0,'Controlled child failed; preserve DB and evidence')
    finally:
        stop=subprocess.run([str(BIN/'pg_ctl'),'stop','-D',str(data),'-m','fast','-w','-t','30'],capture_output=True,text=True)
        status=subprocess.run([str(BIN/'pg_ctl'),'status','-D',str(data)],capture_output=True,text=True)
        write(args.output/'lifecycle.json',dict(passed=rc==0 and stop.returncode==0 and status.returncode==3 and not(data/'postmaster.pid').exists(),child_exit_code=rc,stop_returncode=stop.returncode,pg_ctl_status=status.returncode,pidfile=(data/'postmaster.pid').exists(),owner_unchanged=sha(owner)==owner_hash,failed_v1_not_started=not(OWN/'pg-rec-v1/data/postmaster.pid').exists(),completed_at_ns=time.time_ns()))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--child',action='store_true');p.add_argument('--port',type=int);p.add_argument('--schema',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('captures',nargs='*',type=Path);a=p.parse_args();child(a) if a.child else controller(a)

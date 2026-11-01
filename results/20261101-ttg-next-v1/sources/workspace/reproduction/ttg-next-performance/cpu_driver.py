"""Separate DB-free compiler/artifact and runtime-construction diagnostic.

Run under the selected immutable runtime's Python3.14 environment, in a quiet
window AFTER native acceptance. No ability or request method is wrapped.
"""
import argparse,ast,copy,hashlib,json,marshal,os,threading,time,types
from pathlib import Path
from uuid import UUID

def ref(path):return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
def block(fn,n=1):
    tid=threading.get_ident();w=time.perf_counter_ns();t=time.thread_time_ns();p=time.process_time_ns()
    result=None
    for _ in range(n):result=fn()
    end_p=time.process_time_ns();end_t=time.thread_time_ns();end_w=time.perf_counter_ns()
    assert threading.get_ident()==tid
    return result,dict(iterations=n,wall_ns=end_w-w,thread_cpu_ns=end_t-t,process_cpu_ns=end_p-p,thread_id=tid)

def clock_controls():
    _,sleep=block(lambda:time.sleep(.02))
    _,busy=block(lambda:sum(i*i for i in range(50000)))
    assert min(sleep['thread_cpu_ns'],busy['thread_cpu_ns'])>=0
    assert sleep['thread_cpu_ns']<sleep['wall_ns']/2 and busy['thread_cpu_ns']>0
    return dict(passed=True,blocking=sleep,busy=busy,
        meaning='Same-thread/process CPU clock controls; no server CPU inference')

def checkpoint_plans(gen):
    found={}
    def inspect(value):
        if isinstance(value,types.CodeType):
            for item in value.co_consts:inspect(item)
        elif isinstance(value,(tuple,list)):
            for item in value:inspect(item)
        elif isinstance(value,str) and '"walker_name"' in value and value.lstrip().startswith('{'):
            try:
                plan=json.loads(value)
                if isinstance(plan,dict) and 'events' in plan:
                    key=plan['walker_name']
                    if key in found:assert found[key]==plan,'Conflicting emitted plan in one module'
                    found[key]=plan
            except ValueError:pass
    raw=getattr(gen,'py_bytecode',None)
    if raw:inspect(marshal.loads(raw))
    source=getattr(gen,'py','')
    if source:
        for node in ast.walk(ast.parse(source)):
            if isinstance(node,ast.Constant):inspect(node.value)
    return list(found.values())

def compile_modules(args,out,templates):
    from jaclang.compiler.driver.program import JacProgram
    records=[];all_plans=[]
    assert len(args.module)==1,'One actual module per compiler invocation; preserve module identity'
    for module in args.module:
        module=module.resolve();source=module.read_text();old_cwd=Path.cwd();os.chdir(module.parent)
        try:
            regimes=[(r,p) for p in ((False,True) if templates else (False,)) for r in ('fresh_program','same_program')]
            for base_regime,profiled in regimes:
                regime=base_regime+('_profiled' if profiled else '_unprofiled')
                program=JacProgram()
                if base_regime=='same_program':program.compile(file_path=str(module),use_str=source)
                for repeat in range(args.repeats):
                    if base_regime=='fresh_program':program=JacProgram()
                    if templates:templates.template_metrics(reset=True,enabled=profiled)
                    ir,timing=block(lambda:program.compile(file_path=str(module),use_str=source))
                    assert not program.errors_had,[str(e) for e in program.errors_had]
                    counters=templates.template_metrics(enabled=False) if templates else None
                    artifacts={}
                    for field in ('py','jcir','py_bytecode'):
                        value=getattr(ir.gen,field,None)
                        data=value.encode() if isinstance(value,str) else value
                        if data is not None:
                            artifacts[field]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
                            if repeat==0:
                                path=out/(module.parent.name+'-'+module.stem+'-'+regime+'-'+field+'.artifact')
                                path.write_bytes(data);artifacts[field]['artifact']=ref(path)
                    plans=checkpoint_plans(ir.gen);all_plans.extend(plans)
                    records.append(dict(module=ref(module),regime=regime,profiled=profiled,repeat=repeat,**timing,
                        template_metrics=counters,generated_artifacts=artifacts,checkpoint_plans=len(plans),
                        cache='Fresh/same JacProgram; compiler dependencies/OS caches warmed; source read outside clock; module body not executed'))
        finally:os.chdir(old_cwd)
    unique={p['walker_name']:p for p in all_plans}
    path=out/'emitted-checkpoint-plans.json';path.write_text(json.dumps(dict(module=ref(module),plans=list(unique.values())),indent=2)+'\n')
    return dict(samples=records,emitted_plans=ref(path),
        definition='Actual JacProgram compiler/emitter call; SQL generation counters opt-in; code/J CIR/bytecode bytes measured externally')

def validate_inputs(spec,plan,templates):
    """Outside-clock contract checks: actual emitted sites and exact slot values."""
    bundle=plan['sql_templates'];sites={s['event']:s for s in bundle['sites']}
    rules=spec['dynamic_contract']['rules'];kind=spec['kind']
    assert kind==spec['dynamic_contract']['kind']
    for rule in rules:
        actual=sites[rule['event']]
        assert rule['hops']==actual['hops'] and rule['origin']==actual['origin']
    origins=[UUID(v) for v in spec['dynamic_origins']]
    values=copy.deepcopy(spec['bind_values']);actor=spec.get('actor')
    descriptor=templates.select_template(bundle,kind,bool(actor),spec.get('event',-1))
    assert descriptor is not None
    for name,dtype,nullable in descriptor['slots']:
        assert name in values
        if dtype=='uuid':values[name]=UUID(values[name])
        elif dtype=='uuid[]':values[name]=tuple(UUID(v) for v in values[name])
    assert set(values)=={s[0] for s in descriptor['slots']}
    assert values['row_limit']==spec['max_rows']+1
    if actor:
        assert values['actor_uuid']==UUID(actor) and values['actor_text']==actor
    if kind=='linear':
        assert len(rules)==len(origins)==1 and values['origin']==origins[0]
        for name in ('source_type','source_module'):assert values[name]==spec['dynamic_contract'][name]
        assert values['max_depth']==spec['dynamic_contract']['max_origins']-1
    else:
        active={r['event']:origins[i] for i,r in enumerate(rules)}
        for index,site in enumerate(bundle['sites']):
            assert values['origins_'+str(index)]==((active[site['event']],) if site['event'] in active else ())
    bound=templates.bind_template(descriptor,values)
    assert not getattr(bound,'slots',())
    assert bound.sql==descriptor['sql']
    return values,dict(passed=True,module=spec['module'],walker=spec['walker'],
        active_events=[r['event'] for r in rules],emitted_sites=bundle['sites'],
        slots=descriptor['slots'],bound_parameters=repr(bound.params),
        definition='Same active hop rules, origin UUIDs, actor, scalar limits and types. Inactive emitted batch sites have empty arrays. SQL structure may differ across versions.')

def runtime_blocks(args,out,templates):
    from jaclang.runtime import ttg_fusion_sql as fusion
    emitted=json.loads(args.plans.read_text());plans=emitted['plans'];samples=[];validations=[]
    calls={'runtime_AST_build':0};native=fusion.compile_fused_region
    def counted(*a,**kw):calls['runtime_AST_build']+=1;return native(*a,**kw)
    fusion.compile_fused_region=counted
    try:
        for spec in json.loads(args.spec.read_text())['shapes']:
            assert spec['module']==emitted['module'],'Runtime shape must bind exact compiler module'
            plan=next(p for p in plans if p['walker_name']==spec['walker'])
            kind=spec['kind'];event=spec.get('event',-1);actor=spec.get('actor')
            contract=copy.deepcopy(spec['dynamic_contract']);origins=[UUID(v) for v in spec['dynamic_origins']]
            # Baseline lacks the template module: it still consumes the same
            # exact source-bound shape/spec validated under the next runtime.
            values,validation=validate_inputs(spec,plan,templates) if templates else (None,dict(spec=ref(args.spec),same_spec=True))
            validations.append(dict(shape=spec['name'],**validation))
            def dynamic():return counted(contract,origins,actor,spec['max_rows'])
            methods=('dynamic_AST',) if templates is None else (
                'dynamic_AST','cold_hydrate_only','warm_select_profiled','warm_select_unprofiled',
                'warm_bind_profiled','warm_bind_unprofiled','warm_select_bind_profiled','warm_select_bind_unprofiled')
            raw_bundle=plan.get('sql_templates')
            for method in methods:
                if method=='dynamic_AST':function=dynamic
                elif method=='cold_hydrate_only':
                    cursor=[0];bundles=[]
                    def function():
                        i=cursor[0];cursor[0]+=1
                        return templates.hydrate_templates(bundles[i])
                else:
                    bundle=templates.hydrate_templates(copy.deepcopy(raw_bundle))
                    descriptor=templates.select_template(bundle,kind,bool(actor),event)
                    if method.startswith('warm_select_bind'):
                        def function():return templates.bind_template(templates.select_template(bundle,kind,bool(actor),event),values)
                    elif method.startswith('warm_select'):
                        def function():return templates.select_template(bundle,kind,bool(actor),event)
                    else:
                        def function():return templates.bind_template(descriptor,values)
                if method!='cold_hydrate_only':
                    for _ in range(10):function()
                for repeat in range(args.repeats):
                    if method=='cold_hydrate_only':
                        bundles=[copy.deepcopy(raw_bundle) for _ in range(args.iterations)];cursor[0]=0
                    calls['runtime_AST_build']=0
                    if templates:templates.template_metrics(reset=True,enabled=method.endswith('_profiled'))
                    result,timing=block(function,args.iterations)
                    counters=templates.template_metrics(enabled=False) if templates else None
                    compiled=result if hasattr(result,'sql') else None
                    if compiled:assert not getattr(compiled,'slots',()),'Unbound typed SQL slots remain'
                    samples.append(dict(shape=spec['name'],module=spec['module'],walker=spec['walker'],method=method,repeat=repeat,**timing,
                        runtime_AST_build_calls=calls['runtime_AST_build'],template_metrics=counters,
                        SQL_bytes=len(compiled.sql.encode()) if compiled else None,
                        SQL_sha256=hashlib.sha256(compiled.sql.encode()).hexdigest() if compiled else None,
                        parameter_count=len(compiled.params) if compiled else None,
                        interpretation='Construction-only source-bound inputs. Cold hydration excludes copying/selection/binding; warm methods use one hydrated bundle. Native outputs/state checked separately.'))
    finally:fusion.compile_fused_region=native
    return dict(samples=samples,input_validation=validations,spec=ref(args.spec),compiler_emitted_plans=ref(args.plans),
        definition='No DB. Actual AST/render, cold hydrate and warm select/bind measured separately; profiled/unprofiled controls retained with no subtraction.')

def main(args):
    out=args.output.resolve();assert not out.exists();out.mkdir(parents=True)
    import jaclang
    manifest=json.loads(args.runtime_manifest.read_text());root=Path(manifest['root']).resolve()
    assert Path(jaclang.__file__).resolve().is_relative_to(root),'Selected runtime import mismatch'
    templates=None
    if args.implementation=='next':
        from jaclang.runtime import ttg_templates as templates
    result=dict(passed=False,implementation=args.implementation,runtime_manifest=ref(args.runtime_manifest),
        driver=ref(Path(__file__)),primary_measurement=False,clock_controls=clock_controls(),
        Python=os.sys.version,profiling='Diagnostic only; no ability methods changed')
    try:
        if args.module:result['compiler']=compile_modules(args,out,templates)
        if args.spec:
            assert args.plans,'Emitted plan artifact required for declared runtime shapes'
            result['runtime_construction']=runtime_blocks(args,out,templates)
        result['passed']=True
    except BaseException as error:result['error']=type(error).__name__+': '+str(error);raise
    finally:
        if templates:templates.template_metrics(enabled=False)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--implementation',choices=('baseline850','next'),required=True)
    p.add_argument('--runtime-manifest',type=Path,required=True);p.add_argument('--module',type=Path,nargs='*',default=[])
    p.add_argument('--spec',type=Path);p.add_argument('--plans',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--iterations',type=int,default=100);p.add_argument('--repeats',type=int,default=3)
    a=p.parse_args();assert a.iterations>0 and a.repeats>=3;main(a)

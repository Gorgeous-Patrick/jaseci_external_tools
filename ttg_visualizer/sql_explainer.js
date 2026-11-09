// Read-only explanation of the emitted SQL shapes. All excerpts retain exact
// offsets into the original template. This is logical dataflow, not EXPLAIN.
const cache=new WeakMap();
export function sqlTokens(sql) {
  const re=/\s+|--[^\n]*(?:\n|$)|\/\*[\s\S]*?\*\/|"(?:[^"]|"")*"|'(?:[^']|'')*'|:[A-Za-z_]\w*|[A-Za-z_]\w*|\d+(?:\.\d+)?|->>|->|::|<=|>=|<>|!=|[(),.*=+\-/?<>;\[\]]/gy;
  const tokens=[];let pos=0;
  while(pos<sql.length){re.lastIndex=pos;const m=re.exec(sql);if(!m)throw new Error(`Unsupported SQL token at ${pos}`);
    if(/^--|^\/\*/.test(m[0]))throw new Error('Comment-bearing SQL is outside this generated-SQL adapter');
    if(!/^\s/.test(m[0]))tokens.push({text:m[0],upper:m[0].toUpperCase(),start:pos,end:re.lastIndex});pos=re.lastIndex;}
  const stack=[];for(let i=0;i<tokens.length;i++){
    if(tokens[i].text==='(')stack.push(i);
    if(tokens[i].text===')'){const j=stack.pop();if(j===undefined)throw new Error('Unbalanced SQL');tokens[i].pair=j;tokens[j].pair=i;}
  }if(stack.length)throw new Error('Unbalanced SQL');return tokens;
}
export function splitCTEs(sql) {
  const ts=sqlTokens(sql);let i=0;if(ts[i++]?.upper!=='WITH')throw new Error('Expected WITH');
  const recursive=ts[i]?.upper==='RECURSIVE';if(recursive)i++;
  const ctes=[];
  do{
    const name=ts[i++];if(!name?.text.startsWith('"'))throw new Error('Unsupported CTE name');
    if(ts[i]?.text==='(')i=ts[i].pair+1;
    if(ts[i++]?.upper!=='AS'||ts[i]?.text!=='(')throw new Error('Unsupported CTE definition');
    const open=i,close=ts[open].pair;
    ctes.push({name:name.text.slice(1,-1),start:ts[open].end,end:ts[close].start,sql:sql.slice(ts[open].end,ts[close].start)});
    i=close+1;if(ts[i]?.text!==',')break;i++;
  }while(i<ts.length);
  if(ts[i]?.upper!=='SELECT')throw new Error('Missing outer SELECT');
  return {recursive,ctes,tail:{start:ts[i].start,end:sql.length,sql:sql.slice(ts[i].start)},tokens:ts};
}
const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const valueText=x=>x===null?'NULL':typeof x==='string'?JSON.stringify(x):String(x);
function aliases(sql,params){
  const out=[];
  for(const m of sql.matchAll(/\b(FROM|JOIN)\s+"([^"]+)"\s+AS\s+"([^"]+)"/g)){
    const [,clause,table,alias]=m;if(out.some(x=>x.name===alias))continue;
    const param=field=>{
      const r=new RegExp('"'+esc(alias)+'"\\."'+field+'" = CAST\\(:(\\w+) AS');
      const p=sql.match(r)?.[1];return p?params[p]:undefined;
    };
    const kind=param('kind'),type=param('arch_type');
    let role=table.startsWith('_cte')?'Previously computed CTE result':table==='graph_types'?'Type / subtype lookup':kind==='EdgeAnchor'?'Traversal edge':kind==='NodeAnchor'?(type?`${type} node`:'Node type catalog scan'):'Origin node lookup';
    if(kind==='EdgeAnchor'&&sql.includes(`"${alias}"."src" = CAST(:actor_uuid`))role='ACL group-membership edge';
    out.push({name:alias,table,role,kind:kind??'',type:type===undefined?'':valueText(type),sql:sql.slice(m.index,m.index+m[0].length)});
  }return out;
}
function fragments(sql){
  const ts=sqlTokens(sql),out=[{id:'all',title:'Whole block',sql,start:0,end:sql.length}];
  const add=(id,title,start,end)=>{if(start>=0&&end>start)out.push({id,title,sql:sql.slice(start,end),start,end});};
  const pairs=ts.filter(t=>t.text==='(').map(t=>({start:t.start,end:ts[t.pair].end,sql:sql.slice(t.start,ts[t.pair].end)}));
  const group=(id,title,predicate)=>{const p=pairs.filter(p=>predicate(p.sql)).sort((a,b)=>(a.end-a.start)-(b.end-b.start))[0];if(p)add(id,title,p.start,p.end);};
  const from=ts.findIndex((t,i)=>t.upper==='FROM'&&ts[i+1]?.text==='(');
  if(from>=0){const p=ts[from+1],sub=sql.slice(p.end,ts[p.pair].start);if(/^SELECT (?:CAST\(:origin|DISTINCT COALESCE)/.test(sub))add('input','Origin input',p.end,ts[p.pair].start);}
  const c=ts.findIndex(t=>t.upper==='CASE'),e=ts.findIndex((t,i)=>i>c&&t.upper==='END');
  if(c>=0&&e>c)add('endpoint','Select edge endpoint',ts[c].start,ts[e].end);
  group('direction','Direction / undirected edges',s=>s.includes('."src"')&&s.includes('."undirected"')&&s.includes('."dst"')&&!s.includes('SELECT'));
  group('type','Type / subtype filter',s=>s.includes('"arch_type"')&&s.includes(' IN (SELECT ')&&s.includes('"graph_types"')&&!s.includes(':actor_uuid'));
  group('acl','Node access check',s=>s.includes('"root_id"')&&s.includes(':actor_uuid')&&s.includes(' OR ')&&s.includes('"props"')&&s.includes('EXISTS'));
  group('predicate','Exact type / boolean predicate',s=>s.includes('jsonb_typeof')&&s.includes(':node_module'));
  const window=sql.indexOf('ROW_NUMBER()'),count=sql.indexOf('AS "arity"',window);
  if(window>=0&&count>window)add('order','Path order + cardinality',window,count+10);
  return out;
}
const fragmentNotes={
  all:'Exact block from the selected SQL. Formatting adds whitespace only; aliases and parameter names are unchanged.',
  input:'This derived table supplies origins to the correlated path query. Where present, DISTINCT deduplicates origins for querying; it does not remove native queued visits.',
  endpoint:'For an edge reached from src, return dst; when traversing an undirected edge from dst, return src. This CASE does not define a graph parent.',
  direction:'Accept an edge whose src is the origin, or an undirected edge whose dst is the origin. A directed incoming edge is not accepted.',
  type:'A NULL type parameter means no type restriction. Otherwise accept the exact arch_type or a type listed under that ancestor in graph_types.',
  acl:'A node can pass via ownership, public access, an actor-root grant, or a group grant witnessed by an actor membership edge. This expression is repeated per traversed node.',
  predicate:'The recursive origin set admits only the exact runtime type/module and a JSON boolean trashed value whose text is false. A string "false", missing value, or JSON null does not pass this expression.',
  order:'ROW_NUMBER gives native edge sequence order (with ID tie-breaks); COUNT(*) repeats the total path count for this origin. These are path rows, not a distinct-node count.',
};
function block(id,title,source,start,end,description,why,extra={}){
  const sql=source.slice(start,end);return {id,title,start,end,sql,description,why,fragments:fragments(sql),...extra};
}
export function explainQuery(b,requestId){
  let map=cache.get(b);if(!map){map=new Map();cache.set(b,map);}if(map.has(requestId))return map.get(requestId);
  const request=b.requests.find(r=>r.id===requestId);
  const query=request?.queries.find(q=>q.template_ids.some(t=>/\/regions\/\d+\/templates\/(gated|open)$/.test(t)));
  const template=b.compiler.templates.find(t=>query?.template_ids.includes(t.id)&&/\/regions\/\d+\/templates\//.test(t.id));
  const region=b.compiler.regions.find(r=>r.templates.includes(template?.id));
  if(!template||!region)return {supported:false,reason:'No exact-matched region SQL is available for this request.'};
  try{
    if(template.sql!==query.sql)throw new Error('SQL/template text mismatch');
    const parsed=splitCTEs(template.sql),sql=template.sql,steps=[];let graph=[];
    for(const t of parsed.tokens.filter(t=>t.text.startsWith(':')))if(!Object.hasOwn(template.params,t.text.slice(1))&&!template.slots.some(s=>s[0]===t.text.slice(1)))throw new Error('Unbound parameter');
    const make=(...args)=>block(...args);
    if(region.metadata.kind==='finite_dag'){
      const rules=region.metadata.rules;
      if(b.walker!=='load_feed'||JSON.stringify(rules.map(r=>r.hops))!==JSON.stringify([[[null,'Profile',2]],[['Post','Tweet',2]],[['Follow','Profile',2],['Post','Tweet',2]]])||rules.some((r,i)=>r.slot!==i))throw new Error('This walkthrough covers the recorded LittleX three-visit shape');
      if(parsed.recursive||parsed.ctes.length!==3||rules.length!==3||rules[0].parent!==-1||rules[1].parent!==0||rules[2].parent!==0)throw new Error('Finite DAG shape is not supported');
      for(let i=0;i<3;i++){
        const ct=parsed.ctes[i],rule=rules[i],ev=b.compiler.events.find(e=>e.id===rule.event);
        const parents=[...ct.sql.matchAll(/\bFROM "(_cte\d+)"/g)].map(m=>m[1]);
        if(i>0&&(!parents.includes(parsed.ctes[0].name)||parents.some(x=>x!==parsed.ctes[0].name)))throw new Error('CTE dependency does not match the composed rule');
        const path=rule.hops.map(h=>`${h[0]??'any edge'} → ${h[1]}`).join(' → ');
        steps.push(make('cte'+i,`${ct.name}: ${rule.source_type} → ${rule.hops.at(-1)[1]}`,sql,ct.start,ct.end,
          i===0?'Bind the current Root ID, then resolve its Profile targets.':`Read distinct Profile IDs from ${parsed.ctes[0].name}, then resolve ${path}.`,
          i===0?'LEFT JOIN LATERAL describes a path lookup correlated with each origin. It also retains an origin with no matches as a null target row.':'Both this block and the other collect block depend on the first CTE. They do not consume each other’s Tweet results.',
          {event:rule.event,jac:b.sources[ev.location.file].lines[ev.location.line-1].trim(),location:`${ev.location.file}:${ev.location.line}`,path}));
      }
      // Locate the extra catalog branch using its constant slot = -1, not a
      // hard-coded parameter number or alias.
      const p=Object.entries(template.params).find(([k,v])=>v===-1&&new RegExp(`CAST\\(:${k} AS bigint\\) AS "slot"`).test(parsed.tail.sql));
      if(p){const start=sql.indexOf(`SELECT DISTINCT CAST(:${p[0]} AS bigint) AS "slot"`,parsed.tail.start);
        const op=parsed.tokens.find(t=>t.text==='('&&t.end===start);
        if(start<0||!op)throw new Error('Unknown catalog layout');
        steps.push(make('catalog','Type catalog: slot = −1',sql,start,parsed.tokens[op.pair].start,
          'Return distinct persisted NodeAnchor type/module pairs. The runtime uses these metadata rows for its standard-access contract checks.',
          'These rows are not Tweet results. The path LIMIT is inside the preceding UNION branch, so it does not truncate this catalog.'));
      }
      steps.push(make('output','Tag, combine and order',sql,parsed.tail.start,parsed.tail.end,
        'Tag path records with slots 0, 1 and 2; combine them with UNION ALL, order by slot / origin / ord and apply the path row limit. Add catalog rows separately when present.',
        'UNION ALL preserves path multiplicity. Result rows feed cache validation; feed sorting, search and to_view execute in native Jac.'));
      graph=[{id:'cte0',x:30,y:30,w:300,h:95},{id:'cte1',x:400,y:30,w:300,h:95},{id:'cte2',x:400,y:175,w:300,h:95},...(steps.some(s=>s.id==='catalog')?[{id:'catalog',x:30,y:310,w:300,h:95}]:[]),{id:'output',x:770,y:175,w:300,h:95}];
    }else if(region.metadata.kind==='output_tree'){
      if(b.walker!=='VisibleFolderTree'||JSON.stringify(region.metadata.hops)!==JSON.stringify([['Contains','Folder',2]])||JSON.stringify(region.metadata.predicates)!==JSON.stringify([['trashed','==',false]]))throw new Error('This walkthrough covers the recorded JDrive Folder predicate');
      if(!parsed.recursive||parsed.ctes.length!==1||!parsed.ctes[0].sql.includes(' UNION SELECT '))throw new Error('Recursive shape is not supported');
      const ct=parsed.ctes[0],ts=sqlTokens(ct.sql),union=ts.find(t=>t.upper==='UNION');
      const recStart=ct.start+ts[ts.indexOf(union)+1].start;
      const ev=b.compiler.events.find(e=>e.line===region.metadata.visit_line&&e.ability===region.metadata.ability&&e.kind!=='input');
      steps.push(make('seed','Seed: the known origin',sql,ct.start,ct.start+union.start,
        'Start the recursive origin set with the bound origin UUID. There is one input ID, not a precomputed list of all Folder IDs.',
        'The origin is supplied at runtime. Its concrete Bind value was not retained in this capture.'));
      steps.push(make('recursive','Expand visible Folder origins',sql,ct.start,ct.end,
        'This block includes the seed and recursive terms joined by UNION. For each newly reached origin, find Contains edges, resolve accessible Folder endpoints, then require exact type/module and trashed = false.',
        'UNION (without ALL) deduplicates origin IDs across iterations. Recursion stops when no new IDs are added; the row LIMIT is later and is not a recursion depth cap.',
        {event:ev.id,jac:b.sources[ev.location.file].lines[ev.location.line-1].trim(),location:`${ev.location.file}:${ev.location.line}`}));
      steps.push(make('pairs','Re-enumerate ordered paths',sql,parsed.tail.start,parsed.tail.end,
        'Join each reached origin to its source anchor; a LEFT JOIN LATERAL enumerates accessible Contains → Folder path rows for that origin, with source/target properties.',
        'This is a second pass. Its outer target lookup does not repeat trashed = false: that predicate restricts recursive expansion. Retained properties support native path/predicate checks.'));
      const sort=sql.lastIndexOf('ORDER BY');
      steps.push(make('output','Order and limit returned path rows',sql,sort,sql.length,
        'Order by origin_id and per-origin ord, then limit the returned path rows using :row_limit.',
        'A left-join origin with no targets contributes a null-target row. Total returned rows are neither the number of unique Folders nor the number of native ability calls.'));
      graph=[{id:'seed',x:30,y:65,w:270,h:95},{id:'recursive',x:370,y:65,w:300,h:95},{id:'pairs',x:740,y:65,w:330,h:95},{id:'output',x:740,y:285,w:330,h:95}];
    }else throw new Error('Region kind is not supported');
    const columns=region.metadata.kind==='finite_dag'?[
      ['slot','0 / 1 / 2 identify a visit rule; −1 identifies catalog metadata.'],
      ['origin_id','The origin of this visit slot: Root for slot 0, Profile for slots 1 and 2.'],
      ['target_id','Resolved target identity; NULL in an empty-path or catalog row.'],
      ['edge_id','Terminal edge identity; the last Post edge for a two-hop Follow/Post path.'],
      ['arch_type / arch_module','Target dispatch identity; persisted type metadata in catalog rows.'],
      ['ord','1-based path order for this origin; a two-hop path sorts by both edges’ sequence/ID.'],
      ['arity','Number of returned paths for this origin, repeated per nonempty path row.'],
    ]:[
      ['origin_id','A Folder ID in the recursive reached-origin set.'],['target_id / edge_id','A target Folder and its Contains edge; NULL for an empty path.'],
      ['arch_type / arch_module','Target type and module.'],['ord / arity','Per-origin path order and path count.'],
      ['source_props / target_props','Stored properties retained for validation; not a claim that payload hydration is complete.'],
      ['source_type / source_module','Source identity used by runtime type / effect contracts.'],
    ];
    for(const step of steps){step.aliases=aliases(step.sql,template.params);if(step.id==='recursive')for(const a of step.aliases)if(a.table===parsed.ctes[0].name)a.role='Recursive working-set origins';step.parameters=[...new Set(sqlTokens(step.sql).filter(t=>t.text.startsWith(':')).map(t=>t.text.slice(1)))].map(name=>{
      const slot=template.slots.find(s=>s[0]===name);return {name,type:slot?.[1]??'compiler constant',value:slot?'Runtime Bind not retained':valueText(template.params[name]),dynamic:!!slot};});}
    const links=region.metadata.kind==='finite_dag'?[{path:'M330,78 H398',label:'Profile IDs'},{path:'M330,92 H355 V222 H398',label:''},{path:'M180,125 V290 H750 V245 H768',label:'Profile path rows'},{path:'M700,78 H735 V200 H768',label:''},{path:'M700,222 H768',label:'path rows'},...(steps.some(s=>s.id==='catalog')?[{path:'M330,358 H925 V272',label:'metadata'}]:[])]:[{path:'M300,112 H368',label:'origin'},{path:'M670,112 H738',label:'reached IDs'},{path:'M520,65 V25 H620 V63',label:'until no new IDs'},{path:'M905,160 V283',label:'path rows'}];
    const result={supported:true,template,query,region,steps,columns,graph:graph.map(n=>({...n,title:steps.find(s=>s.id===n.id).path ?? steps.find(s=>s.id===n.id).title})),links,
      finite:region.metadata.kind==='finite_dag',inputSlots:template.slots.map(s=>({name:s[0],type:s[1]})),characters:sql.length,
      payloadQueries:request.queries.filter(q=>q.role==='background_prefetch'&&q.category==='data'),
      constants:Object.keys(template.params).length};map.set(requestId,result);return result;
  }catch(e){return {supported:false,reason:`Exact SQL shape is not covered by this walkthrough: ${e.message}`};}
}
export function walkthroughStep(w,id){return w.supported?(w.steps.find(s=>s.id===id)??w.steps[0]):null;}
export function walkthroughFragment(step,id){const p=step?.fragments.find(f=>f.id===id)??step?.fragments[0];return p?{...p,note:fragmentNotes[p.id]}:null;}
export function highlightedSQL(sql,symbol=''){
  const ts=sqlTokens(sql);let depth=0;
  return ts.map((t,i)=>{
    if(t.text===')')depth=Math.max(0,depth-1);
    const word=t.upper,prev=ts[i-1]?.text;
    const newline=['SELECT','FROM','WHERE','INNER','LEFT','ORDER','UNION','LIMIT','AND','OR'].includes(word);
    const prefix=i===0?'':newline?'\n'+'  '.repeat(Math.min(depth,8)):t.text===','||t.text===')'||t.text==='.'||prev==='.'||prev==='('? '':' ';
    const sym=t.text.startsWith(':')?t.text.slice(1):t.text.startsWith('"')?t.text.slice(1,-1):'';
    if(t.text==='(')depth++;
    return {text:prefix+t.text,symbol:sym,active:!!symbol&&sym===symbol,kind:t.text.startsWith(':')?'param':t.text.startsWith('"')?'identifier':'plain',key:i};
  });
}
export function symbolInfo(step,name){const a=step?.aliases.find(a=>a.name===name);if(a)return `${name} = ${a.table} · ${a.role}${a.type?' · type '+a.type:''}`;const p=step?.parameters.find(p=>p.name===name);return p?`:${name} · ${p.type} · ${p.value}`:'';}

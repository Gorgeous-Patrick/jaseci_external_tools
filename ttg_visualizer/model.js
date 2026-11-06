// Data/layout helpers only. All application rendering and state live in main.jac.
export function validateBundle(b) {
  if (!b || b.schema !== 'jac.ttg.visualization' || b.version !== 1)
    throw new Error('Expected jac.ttg.visualization version 1');
  const arrays = [b.graph?.nodes, b.graph?.edges, b.compiler?.events,
    b.compiler?.edges, b.compiler?.hooks, b.compiler?.regions,
    b.compiler?.templates, b.requests];
  if (arrays.some(x => !Array.isArray(x)) || !b.sources || !b.provenance)
    throw new Error('Incomplete graph/compiler/evidence bundle');
  if (!b.graph.nodes.length || !b.compiler.events.length || !b.compiler.plan?.interability_regions)
    throw new Error('Graph, events and compiler plan must be present');
  for (const s of Object.values(b.sources))
    if (!Array.isArray(s.lines) || typeof s.text !== 'string') throw new Error('Invalid source file');
  const unique = (xs, label) => {
    if (new Set(xs).size !== xs.length) throw new Error(`Duplicate ${label}`);
  };
  unique(b.graph.nodes.map(x => x.id), 'node IDs');
  unique(b.compiler.events.map(x => x.id), 'event IDs');
  unique(b.compiler.templates.map(x => x.id), 'template IDs');
  unique(b.requests.map(x => x.id), 'request IDs');
  const nodes = new Set(b.graph.nodes.map(x => x.id));
  const events = new Set(b.compiler.events.map(x => x.id));
  const templates = new Map(b.compiler.templates.map(x => [x.id, x]));
  for (const e of b.graph.edges)
    if (!nodes.has(e.source) || !nodes.has(e.target)) throw new Error('Dangling graph edge');
  for (const e of b.compiler.edges)
    if (!events.has(e.source) || !events.has(e.target)) throw new Error('Dangling dependency edge');
  for (const h of b.compiler.hooks)
    if (!events.has(h.event)) throw new Error('Hook references missing event');
  for (const r of b.compiler.regions) {
    if (!r.metadata || !Array.isArray(r.templates)) throw new Error('Invalid region metadata');
    if (!events.has(r.entry)) throw new Error('Region references missing entry');
    for (const t of r.templates) if (!templates.has(t)) throw new Error('Missing region template');
  }
  for (const e of b.compiler.events)
    if (!e.location || !b.sources[e.location.file] || !Number.isInteger(e.location.line)
        || e.location.line < 1 || e.location.line > b.sources[e.location.file].lines.length)
      throw new Error('Missing or out-of-range event source location');
  for (const r of b.requests) {
    if (!Array.isArray(r.queries) || !Array.isArray(r.visited)) throw new Error('Invalid request');
    for (const q of r.queries) {
    if (typeof q.sql !== 'string' || !Array.isArray(q.template_ids) || !Number.isFinite(q.duration_ms))
      throw new Error('Invalid SQL record');
    if (!Number.isFinite(q.start_ms) || !Number.isFinite(q.end_ms) || q.end_ms < q.start_ms)
      throw new Error('Invalid SQL interval');
    for (const id of q.template_ids) {
      if (!templates.has(id) || templates.get(id).sql !== q.sql)
        throw new Error('SQL/template link is not exact');
    }
  }
  }
  return b;
}

export async function loadExample(name) {
  if(!['jdrive','littlex'].includes(name)) throw new Error('Unknown example');
  const response = await fetch(`./data/${name}.json`);
  if (!response.ok) throw new Error(`Cannot load bundled capture: HTTP ${response.status}`);
  return validateBundle(await response.json());
}
export async function loadDefault() {
  const name=new URLSearchParams(location.search).get('app') || 'jdrive';
  return loadExample(name);
}
export async function loadFile(event) {
  const f = event.target.files[0];
  if (!f) return null;
  if (f.size > 20 * 1024 * 1024) throw new Error('Use a JSON bundle smaller than 20 MB');
  return validateBundle(JSON.parse(await f.text()));
}
export function firstNode(b) {
  const type = b.compiler.regions[0]?.metadata.source_type ?? b.compiler.regions[0]?.metadata.rules?.[0]?.source_type;
  return b.graph.nodes.find(n => n.type === type)?.id ?? b.graph.nodes[0]?.id ?? '';
}
export function getEvent(b, id) { return b.compiler.events.find(e => e.id === Number(id)) ?? b.compiler.events[0]; }
export function getRequest(b, id) { return b.requests.find(r => r.id === id) ?? b.requests[0] ?? {queries: [], visited: []}; }
export function regionFor(b, node) {
  return b.compiler.regions.find(r => r.metadata.source_type === node.type);
}
export function neighborhood(b, id, page = 0) {
  const focus = b.graph.nodes.find(n => n.id === id) ?? b.graph.nodes[0];
  const children = b.graph.edges.filter(e => e.source === focus.id);
  const chosen = children.slice(page * 2, page * 2 + 2);
  return {focus, children: chosen.map(e => ({...b.graph.nodes.find(n => n.id === e.target), edge: e})),
    count: children.length, pages: Math.max(1, Math.ceil(children.length / 2))};
}
export function cards(b, id, page, requestId, selectedAbility = '') {
  const n = neighborhood(b, id, page);
  const visited = new Set(getRequest(b, requestId).visited);
  return [n.focus, ...n.children].map((node, i) => {
    const handlers = b.compiler.plan.handlers[node.type] ?? [];
    const ability = selectedAbility || regionFor(b, node)?.metadata.ability || handlers[0] || '';
    const r = b.compiler.regions.find(r => r.metadata.source_type === node.type && r.metadata.ability === ability);
    const events = handlers.includes(ability) || r ? b.compiler.events.filter(e => e.ability === ability) : [];
    const height = Math.max(260, events.length * 27 + 177);
    return {...node, x: i * 340 + 20, y: 90, height, regionY: 90 + height - 57, visited: visited.has(node.id),
      region: r?.id ?? '', regionKind: r?.metadata.kind ?? '',
      ability: events.length ? ability : '', events,
      predicate: r?.metadata.predicates?.map(p => p.join(' ')).join(' AND ') ?? '',
      visitLine: r?.metadata.visit_line ?? -1};
  });
}
export function graphHeight(b, id, page, requestId, ability) {
  return Math.max(...cards(b, id, page, requestId, ability).map(c => c.y + c.height)) + 34;
}
export function abilityNames(b) { return Object.keys(b.compiler.plan.entries); }
export function selectedRegion(b, eventId) {
  const e = getEvent(b, eventId);
  return b.compiler.regions.find(r => r.metadata.ability === e.ability) ?? b.compiler.regions.find(r => r.metadata.rules?.some(rule=>rule.ability===e.ability)) ?? null;
}
export function regionExpansion(b, id, page, requestId, ability, levels = 3) {
  const start = b.graph.nodes.find(n => n.id === id) ?? b.graph.nodes[0];
  const region = b.compiler.regions.find(r => r.metadata.source_type === start.type && r.metadata.ability === ability);
  // The first adapter supports homogeneous recursive output-tree certificates.
  // Never portray an arbitrary finite/unsupported certificate as recursion.
  if (!region || region.metadata.kind !== 'output_tree') return {supported:false, nodes:[], links:[], region:null};
  const visit = b.compiler.events.find(e => e.ability === ability && e.line === region.metadata.visit_line && e.kind !== 'input');
  if (!visit) return {supported:false, nodes:[], links:[], region:null};
  const byId = new Map(b.graph.nodes.map(n => [n.id,n]));
  const visited = new Set(getRequest(b,requestId).visited);
  const hop = region.metadata.hops?.[0];
  if (!hop || region.metadata.hops.length !== 1 || hop[2] !== 2)
    return {supported:false, nodes:[], links:[], region:null};
  const predicate = n => (region.metadata.predicates ?? []).every(([field, op, value]) =>
    op === '==' && Object.hasOwn(n.fields ?? {},field) && n.fields[field] === value);
  const nextEdges = n => b.graph.edges.filter(e => e.source === n.id && e.type === hop[0] &&
    byId.get(e.target)?.type === region.metadata.source_type && predicate(byId.get(e.target)));
  const first = nextEdges(start);
  // Prefer nodes present in the selected native report, while retaining the
  // graph's original edge order within each group. This is an illustrative
  // real path, not a reconstruction of individual SQL result membership.
  const ordered = xs => xs.filter(e => visited.has(e.target)).concat(xs.filter(e => !visited.has(e.target)));
  const branchCount = first.length;
  const branch = branchCount ? ((page % branchCount) + branchCount) % branchCount : 0;
  const path = [start], links = [], seen = new Set([start.id]);
  while (path.length < levels) {
    const options = ordered(nextEdges(path.at(-1))).filter(e => !seen.has(e.target));
    const edge = options[path.length === 1 ? branch : 0];
    if (!edge) break;
    links.push(edge);path.push(byId.get(edge.target));seen.add(edge.target);
  }
  const nodes = path.map((n,i) => ({...n, x:20+i*340, level:i,
    event:visit.id, visited:visited.has(n.id), ability,
    key:`${n.id}:${ability}:${visit.id}`}));
  const templates = region.templates.filter(id => id.includes('/templates/'));
  const queries = getRequest(b,requestId).queries.filter(q => q.template_ids.some(t=>templates.includes(t)));
  const nativeEvents = b.compiler.events.filter(e => e.ability===ability && e.id!==visit.id &&
    !['input','phi','join','entry','exit'].includes(e.kind));
  return {supported:true, nodes, links, region, visit, branch, branchCount,
    width:Math.max(320,nodes.length*340-20), queries, templateId:queries[0]?.template_ids.find(t=>templates.includes(t)) ?? templates[0] ?? '',
    accessLabel:`visit ${hop[0]} → ${hop[1]}`,
    predicateLabel:(region.metadata.predicates ?? []).map(p=>p.join(' ')).join(' AND '),
    nativeEvents, entryId:b.compiler.plan.entries[ability],
    nativeLines:nativeEvents.slice(0,4).map(e=>({id:e.id,text:
      b.sources[e.location.file]?.lines[e.location.line-1]?.trim() || e.expression || e.kind}))};
}
// Slide-style nested Jac topology. This is a certificate-derived explanatory
// projection, not a new compiler DAG or a trace of per-node hook firings.
export function nestedRegion(b, id, page, requestId, ability) {
  const base=regionExpansion(b,id,0,requestId,ability);
  if (!base.supported) return base;
  const byId=new Map(b.graph.nodes.map(n=>[n.id,n]));
  const start=byId.get(id) ?? b.graph.nodes[0];
  const meta=base.region.metadata;
  const outgoing=new Map();
  for (const e of b.graph.edges) {
    if (!outgoing.has(e.source)) outgoing.set(e.source,[]);
    outgoing.get(e.source).push(e);
  }
  const valid=n=>n?.type===meta.source_type && (meta.predicates ?? []).every(([f,op,v])=>
    op==='==' && Object.hasOwn(n.fields ?? {},f) && n.fields[f]===v);
  const all=outgoing.get(start.id) ?? [];
  const eligible=all.filter(e=>e.type===meta.hops[0][0] && e.target!==start.id && valid(byId.get(e.target)));
  const pages=Math.max(1,Math.ceil(eligible.length/2));
  const branch=((page%pages)+pages)%pages;
  const shown=eligible.slice(branch*2,branch*2+2);
  const descendants=id=>{
    const seen=new Set([id]), queue=[id];
    for(let i=0;i<queue.length;i++) for(const e of outgoing.get(queue[i])??[])
      if(!seen.has(e.target)){seen.add(e.target);queue.push(e.target);}
    return seen.size-1;
  };
  const visited=new Set(getRequest(b,requestId).visited);
  const nodes=[start,...shown.map(e=>byId.get(e.target))].map((n,i)=>({
    ...n,x:i===0?300:(i-1)*560+20,y:i===0?20:440,
    level:i===0?0:1,event:base.visit.id,ability,visited:visited.has(n.id),
    key:`${n.id}:${ability}:${base.visit.id}`,descendants:descendants(n.id),
    childCount:(outgoing.get(n.id)??[]).length,
  }));
  const links=shown.map((e,i)=>({...e,
    jacPath:`M${i===0?360:740},370 L${i===0?220:880},438`,
    dependencyPath:`M680,242 L550,250 V560 H${nodes[i+1].x+100} V568`,
    labelX:i===0?205:805,
  }));
  // A single polygon joins the parent access slice to every displayed child
  // slice. Output/enqueue boxes stay outside this connected region.
  const right=nodes.length>2?1070:568;
  const regionPath=shown.length
    ? `M310,160 H790 V264 H568 V550 H${right} V652 H30 V550 H532 V264 H310 Z`
    : 'M310,160 H790 V264 H310 Z';
  return {...base,nodes,links,branch,pages,eligibleCount:eligible.length,
    excluded:all.filter(e=>!eligible.includes(e)).map(e=>({id:e.target,type:byId.get(e.target)?.type,
      reason:e.type!==meta.hops[0][0]?'different edge type':byId.get(e.target)?.type!==meta.source_type?'different target type':e.target===start.id?'self edge (not expanded)':'predicate not satisfied'})),
    regionPath,viewHeight:shown.length?830:400,
    folderCount:b.graph.nodes.filter(n=>n.type===meta.source_type).length,
    totalCount:b.graph.nodes.length,
  };
}

// Compact full-snapshot overview: every node occurs exactly once, even for
// disconnected graphs/cycles. Non-tree edges remain in the returned edge list.
export function graphOverview(b, focus, requestId) {
  const outgoing=new Map(), incoming=new Set(), byId=new Map(b.graph.nodes.map(n=>[n.id,n]));
  for(const e of b.graph.edges){
    if(!outgoing.has(e.source))outgoing.set(e.source,[]);
    outgoing.get(e.source).push(e);incoming.add(e.target);
  }
  const seen=new Set(), laid=[], coords=new Map();let leaf=0,maxDepth=0;
  function walk(id,depth){
    if(seen.has(id))return null;
    seen.add(id);maxDepth=Math.max(maxDepth,depth);
    const children=(outgoing.get(id)??[]).map(e=>walk(e.target,depth+1)).filter(x=>x!==null);
    const x=children.length?children.reduce((a,c)=>a+c,0)/children.length:leaf++;
    const n={...byId.get(id),depth,lane:x};laid.push(n);return x;
  }
  for(const n of b.graph.nodes.filter(n=>!incoming.has(n.id)))walk(n.id,0);
  for(const n of b.graph.nodes)if(!seen.has(n.id))walk(n.id,0);
  const visited=new Set(getRequest(b,requestId).visited);
  const nodes=laid.map(n=>{
    const p={...n,x:15+970*n.lane/Math.max(1,leaf-1),y:15+150*n.depth/Math.max(1,maxDepth),
      selected:n.id===focus,visited:visited.has(n.id),
      color:n.id===focus?'#7855ce':visited.has(n.id)?'#137db3':n.fields?.trashed===true?'#bf8c51':'#aab6c4'};
    coords.set(n.id,p);return p;
  });
  return {nodes,links:b.graph.edges.map(e=>({...e,
    path:`M${coords.get(e.source).x},${coords.get(e.source).y} L${coords.get(e.target).x},${coords.get(e.target).y}`}))};
}

export function miniEvents(b, card) {
  // Preserve real event IDs/order. Show all events for the selected ability.
  return card.events.map((e, i) => ({...e, x: card.x + 22, y: 196 + i * 27,
    label: e.line === card.visitLine && e.kind !== 'input' ? `${e.id} · visit · certified access` :
      `${e.id} · ${e.kind}${e.writes ? ' · ' + e.writes : ''}`,
    hook: b.compiler.hooks.some(h => h.event === e.id),
    access: e.line === card.visitLine && e.kind !== 'input'}));
}
export function miniEdges(b, card, kind) {
  const es = miniEvents(b, card), by = new Map(es.map(e => [e.id, e]));
  return b.compiler.edges.filter(e => by.has(e.source) && by.has(e.target) && (kind === 'all' || e.kind === kind))
    .map((e, i) => {
      const s = by.get(e.source), t = by.get(e.target), x = card.x + 304 + (i % 3) * 4;
      return {...e, key: `${card.id}:${i}`, path: `M ${s.x + 270} ${s.y + 9} Q ${x + 20} ${(s.y + t.y) / 2 + 9} ${t.x + 270} ${t.y + 9}`};
    });
}
export function sourceRows(b, eventId, fileChoice) {
  const e = getEvent(b, eventId), name = fileChoice || e?.location.file;
  const source = b.sources[name];
  if (!source) return [];
  const center = e.location.file === name ? e.location.line : 1;
  const lo = Math.max(1, center - 8), hi = Math.min(source.lines.length, center + 20);
  return source.lines.slice(lo - 1, hi).map((text, i) => {
    const line = lo + i;
    const hooks = b.compiler.hooks.filter(h => {
      const event = getEvent(b, h.event);
      return event.location.file === name && event.location.line === line;
    });
    return {line, text, selected: line === center, hooks};
  });
}
export function selectedHooks(b, id) { return b.compiler.hooks.filter(h => h.event === Number(id)); }
export function sqlItems(b, requestId, showControl) {
  return getRequest(b, requestId).queries.filter(q => showControl || q.category !== 'control');
}
export function counts(b, requestId) {
  const qs = getRequest(b, requestId).queries;
  return {data: qs.filter(q => q.category === 'data').length, control: qs.filter(q => q.category === 'control').length,
    background: qs.filter(q => q.role === 'background_prefetch' && q.category === 'data').length,
    ms: qs.reduce((a, q) => a + q.duration_ms, 0).toFixed(3)};
}
export function sqlLabel(q) {
  if (q.template_ids.length) return 'Compiled region';
  if (q.role === 'background_prefetch') return 'Background payload';
  if (q.category === 'control') return 'Transaction / control';
  if (q.sql.includes('identity_users')) return 'Identity lookup';
  return 'Foreground data';
}
export function sqlDetails(b, requestId, queryId, templateId) {
  if (templateId) {
    const t = b.compiler.templates.find(t => t.id === templateId);
    if (t) return {...t, title: 'Compiler SQL template', evidence: {binding: 'Compiler artifact'}, parameters: t.slots};
  }
  const q = getRequest(b, requestId).queries.find(q => q.id === queryId);
  if (q) return {...q, title: sqlLabel(q), parameters: 'Bind values were not retained in this capture.'};
  return null;
}
export function pretty(x) { return JSON.stringify(x, null, 2); }
export function short(x, n = 72) { return String(x ?? '').length > n ? String(x).slice(0, n) + '…' : String(x ?? ''); }
export function timebar(b, requestId, q) {
  const max = Math.max(1, ...getRequest(b, requestId).queries.map(x => x.end_ms));
  return {left: `${100 * q.start_ms / max}%`, width: `${Math.max(.3, 100 * q.duration_ms / max)}%`};
}
// Union boundary of axis-aligned access rectangles and connecting corridors.
// Internal edges cancel, so all slices are drawn as one region, not per-card boxes.
export function regionOutline(rects) {
  const xs=[...new Set(rects.flatMap(r=>[r.x,r.x+r.w]))].sort((a,b)=>a-b);
  const ys=[...new Set(rects.flatMap(r=>[r.y,r.y+r.h]))].sort((a,b)=>a-b);
  const cells=new Set();
  for(let i=0;i<xs.length-1;i++)for(let j=0;j<ys.length-1;j++)
    if(rects.some(r=>(xs[i]+xs[i+1])/2>r.x&&(xs[i]+xs[i+1])/2<r.x+r.w&&(ys[j]+ys[j+1])/2>r.y&&(ys[j]+ys[j+1])/2<r.y+r.h))cells.add(`${i},${j}`);
  const es=[];
  for(let i=0;i<xs.length-1;i++)for(let j=0;j<ys.length-1;j++)if(cells.has(`${i},${j}`)){
    if(!cells.has(`${i},${j-1}`))es.push([[xs[i],ys[j]],[xs[i+1],ys[j]]]);
    if(!cells.has(`${i+1},${j}`))es.push([[xs[i+1],ys[j]],[xs[i+1],ys[j+1]]]);
    if(!cells.has(`${i},${j+1}`))es.push([[xs[i+1],ys[j+1]],[xs[i],ys[j+1]]]);
    if(!cells.has(`${i-1},${j}`))es.push([[xs[i],ys[j+1]],[xs[i],ys[j]]]);
  }
  let d='';const remaining=new Map(es.map(([a,b])=>[a.join(','),b]));
  while(remaining.size){const start=remaining.keys().next().value;let key=start;d+=`M${start}`;
    do{const next=remaining.get(key);if(!next)throw new Error('Invalid region outline');remaining.delete(key);key=next.join(',');d+=` L${key}`;}while(key!==start);d+=' Z';}
  return d;
}
export function finiteDagView(b, id, requestId) {
  const source=b.graph.nodes.find(n=>n.id===id);
  const region=b.compiler.regions.find(r=>r.metadata.kind==='finite_dag'&&r.metadata.rules?.[0]?.source_type===source?.type);
  if(!region)return {supported:false};
  const rules=region.metadata.rules;
  // Initial renderer handles a root visit followed by two composed visit sites.
  // Unsupported shapes remain inspectable in Complete dependencies.
  if(rules.length!==3 || rules[0].parent!==-1 || rules[1].parent!==rules[0].slot || rules[2].parent!==rules[0].slot || rules[0].hops.length!==1 || rules[1].hops.length!==1 || rules[2].hops.length!==2 || rules.some(r=>r.hops.some(h=>h[2]!==2)))return {supported:false};
  const by=new Map(b.graph.nodes.map(n=>[n.id,n]));
  function expand(origins,hops){
    let paths=origins.map(n=>({nodes:[n],edges:[]}));
    for(const [type,target] of hops){
      const next=[];
      for(const p of paths)for(const e of b.graph.edges){
        const from=p.nodes.at(-1).id;
        const tid=e.source===from?e.target:(e.undirected && e.target===from?e.source:null);
        if(tid && (!type || type===e.type) && by.get(tid)?.type===target)next.push({nodes:[...p.nodes,by.get(tid)],edges:[...p.edges,e]});
      }
      if(next.length>5000)return [];
      paths=next;
    }
    return paths;
  }
  const first=expand([source],rules[0].hops);
  const origins=[...new Map(first.map(p=>[p.nodes.at(-1).id,p.nodes.at(-1)])).values()];
  const direct=expand(origins,rules[1].hops), follow=expand(origins,rules[2].hops);
  if(!first.length || !direct.length || !follow.length)return {supported:false};
  // Use representative real paths sharing the same Profile. No invented edges.
  const p=origins.find(n=>direct.some(p=>p.nodes[0].id===n.id)&&follow.some(p=>p.nodes[0].id===n.id));
  if(!p)return {supported:false};
  const d=direct.find(x=>x.nodes[0].id===p.id), f=follow.find(x=>x.nodes[0].id===p.id);
  const cards=[
    {node:source,x:20,y:20,w:420,h:280,ability:rules[0].ability,note:'Known origin + actor / ACL context'},
    {node:p,x:600,y:20,w:520,h:380,ability:rules[1].ability,note:'Two visit sites share the Profile origin'},
    {node:d.nodes[1],x:20,y:600,w:460,h:280,ability:rules[1].target_ability,note:'Representative direct-path target'},
    {node:f.nodes[1],x:650,y:430,w:450,h:190,ability:'Intermediate hop',note:'Follow → Profile → Post; no collect dispatch here'},
    {node:f.nodes[2],x:650,y:770,w:450,h:260,ability:rules[2].target_ability,note:'Representative two-hop target'},
  ].map((c,i)=>({...c,key:`${i}:${c.node.id}`,title:c.node.id,subtitle:c.ability==='Intermediate hop'?c.ability:`${b.walker}.${c.ability}`}));
  const events=new Map(b.compiler.events.map(e=>[e.id,e]));
  const operations=[
    {x:40,y:122,w:380,h:65,event:rules[0].event,title:`visit → ${rules[0].hops[0][1]}`,sub:`event ${rules[0].event} · line ${events.get(rules[0].event).line} · ${first.length} initial path(s)`},
    {x:620,y:122,w:480,h:65,event:rules[1].event,title:rules[1].hops.map(h=>`${h[0]??'*'} → ${h[1]}`).join(' → '),sub:`visit event ${rules[1].event} · line ${events.get(rules[1].event).line} · ${direct.length} initial paths`},
    {x:620,y:232,w:480,h:65,event:rules[2].event,title:rules[2].hops.map(h=>`${h[0]??'*'} → ${h[1]}`).join(' → '),sub:`visit event ${rules[2].event} · line ${events.get(rules[2].event).line} · ${follow.length} initial paths`},
    {x:670,y:510,w:410,h:55,event:rules[2].event,title:'Post → Tweet',sub:'Second hop of the same visit event'},
    {x:40,y:680,w:420,h:65,event:rules[1].event,title:'Resolved target identity',sub:d.nodes[1].id},
    {x:670,y:850,w:410,h:65,event:rules[2].event,title:'Resolved target identity',sub:f.nodes[2].id},
  ];
  const boundaries=cards.filter(c=>c.ability===rules[1].target_ability || c.ability===rules[2].target_ability).map(c=>{
    const event=b.compiler.events.find(e=>e.ability===c.ability&&e.kind==='barrier');
    return {x:c.x+20,y:c.y+160,w:c.w-40,h:72,event:event?.id??region.entry,title:'Native boundary: '+c.ability,
      sub:event?b.sources[event.location.file].lines[event.location.line-1].trim():'Native execution',line:event?.line};
  });
  const rects=operations.map(o=>({x:o.x-10,y:o.y-9,w:o.w+20,h:o.h+18}));
  rects.push({x:420,y:140,w:200,h:40},{x:565,y:145,w:30,h:130},{x:580,y:245,w:40,h:30},{x:970,y:175,w:30,h:346},
    {x:500,y:140,w:35,h:575},{x:450,y:680,w:65,h:35},{x:980,y:555,w:30,h:310});
  const templates=region.templates.filter(t=>t.includes('/templates/'));
  const queries=getRequest(b,requestId).queries.filter(q=>q.template_ids.some(t=>templates.includes(t)));
  const links=[
    {path:'M440,65 H598',label:'Jac edge · '+first.find(x=>x.nodes.at(-1).id===p.id).edges[0].type,x:455,y:52},
    {path:'M600,330 L180,598',label:'Jac edge · '+d.edges[0].type,x:245,y:470},
    {path:'M1110,400 L1080,428',label:'Follow',x:1120,y:424},
    {path:'M1080,620 L1080,768',label:'Post',x:1090,y:710},
  ];
  return {supported:true,region,cards,operations,boundaries,links,regionPath:regionOutline(rects),
    origin:source.id,queries,templateId:queries[0]?.template_ids.find(t=>templates.includes(t))??templates[0]??'',
    bindings:[first,direct,follow].map((paths,i)=>({event:rules[i].event,count:paths.length,paths:paths.map(p=>({nodes:p.nodes.map(n=>n.id),edges:p.edges}))})),
    dependencies:['M420,155 H618','M575,155 V260 H618','M620,170 H518 V700 H458','M985,300 V508','M995,566 V848'],
  };
}

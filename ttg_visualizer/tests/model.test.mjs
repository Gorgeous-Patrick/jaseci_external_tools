import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../model.js', import.meta.url), 'utf8');
const m = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const bundle = JSON.parse(readFileSync(new URL('../public/data/jdrive.json', import.meta.url), 'utf8'));
test('real bundle: exact template match and observed request conservation', () => {
  m.validateBundle(bundle);
  assert.equal(bundle.graph.nodes.length, 486);
  assert.equal(bundle.compiler.hooks.length, 2);
  for (const r of bundle.requests) {
    assert.equal(r.queries.length, 15);
    assert.equal(m.sqlItems(bundle, r.id, false).length, 7);
    const linked = r.queries.filter(q => q.template_ids.length);
    assert.equal(linked.length, 1);
    assert.equal(m.sqlDetails(bundle, r.id, linked[0].id, '').sql, linked[0].sql);
  }
  const rows = m.sqlItems(bundle, '2:6', false);
  assert.equal(rows.at(-1).role, 'background_prefetch');
  assert.equal(rows.at(-1).rows, 115);
});
test('reject invented SQL links, missing graph endpoints, duplicate events and invalid time', () => {
  for (const mutate of [
    b => {b.requests[0].queries[0].template_ids = [b.compiler.templates[0].id];},
    b => {b.graph.edges[0].target = 'does-not-exist';},
    b => {b.compiler.events.push(b.compiler.events[0]);},
    b => {b.requests[0].queries[0].end_ms = -1;},
    b => {b.compiler.hooks[0].event = 99999;},
    b => {b.version = 999;},
  ]) {
    const b = structuredClone(bundle); mutate(b);
    assert.throws(() => m.validateBundle(b));
  }
});
test('source navigation uses declaration for entry, annex for assignment', () => {
  assert.equal(m.getEvent(bundle, 0).location.file, 'server.jac');
  assert.equal(m.getEvent(bundle, 5).location.file, 'server.impl.jac');
  const row = m.sourceRows(bundle, 5, '').find(x => x.selected);
  assert.match(row.text, /self.start_id = cur_id/);
  assert.equal(row.hooks[0].placement, 'after_statement');
  assert.equal(m.getEvent(bundle, 18).location.file, 'server.jac');
  assert.equal(m.sourceRows(bundle,18,'').find(x=>x.selected).line,111);
});
test('graph traversal paginates real edges and preserves event identity', () => {
  const n = m.neighborhood(bundle, m.firstNode(bundle));
  assert.equal(n.focus.type, 'Folder');
  assert.equal(n.children.length, 2);
  for (const c of m.cards(bundle, n.focus.id, 0, '2:6')) {
    for (const e of m.miniEvents(bundle, c)) assert(bundle.compiler.events.some(x => x.id === e.id));
  }
  const p2 = m.neighborhood(bundle, n.focus.id, 1);
  assert.notEqual(p2.children[0].id, n.children[0].id);
});
test('abilities without an accepted region remain visible; layouts fit larger graphs', () => {
  const cs = m.cards(bundle, m.firstNode(bundle), 0, '2:6', 'done');
  assert.equal(cs[0].events.length, 2);
  assert.equal(cs[0].region, '');
  assert.equal(m.selectedRegion(bundle, 17), null);
  const h = m.graphHeight(bundle, m.firstNode(bundle), 0, '2:6', 'walk');
  assert(h > m.miniEvents(bundle, m.cards(bundle,m.firstNode(bundle),0,'2:6')[0]).at(-1).y);
});
test('one recursive region spans a real parent-child-grandchild path', () => {
  const r=m.regionExpansion(bundle,'folder:root',0,'2:6','walk');
  assert.equal(r.supported,true);
  assert.equal(r.nodes.length,3);
  assert.equal(r.links.length,2);
  assert.equal(r.queries.length,1);
  assert.equal(new Set(r.nodes.map(n=>n.event)).size,1);
  assert.equal(new Set(r.nodes.map(n=>n.key)).size,3);
  for(let i=0;i<2;i++) {
    assert.equal(r.links[i].source,r.nodes[i].id);
    assert.equal(r.links[i].target,r.nodes[i+1].id);
    assert(bundle.graph.edges.some(e=>e.source===r.links[i].source && e.target===r.links[i].target));
    assert.equal(r.nodes[i+1].fields.trashed,false);
  }
  assert.equal(m.regionExpansion(bundle,'folder:root',0,'2:6','done').supported,false);
  const other=m.regionExpansion(bundle,'folder:root',1,'2:6','walk');
  assert.notEqual(other.nodes[1].id,r.nodes[1].id);
});
test('expansion stops at leaves and cycles and does not invent recursion for finite certificates', () => {
  const b=structuredClone(bundle);
  const ids=['folder:root','folder:root/0'];
  b.graph.edges=b.graph.edges.filter(e=>e.source===ids[0] && e.target===ids[1]);
  b.graph.edges.push({source:ids[1],target:ids[0],type:'Contains'});
  const r=m.regionExpansion(b,ids[0],0,'2:6','walk');
  assert.equal(r.nodes.length,2);
  b.compiler.regions[0].metadata.kind='finite';
  assert.equal(m.regionExpansion(b,ids[0],0,'2:6','walk').supported,false);
});

test('nested slide layout keeps actual sibling edges and predicate exclusions', () => {
  const r=m.nestedRegion(bundle,'folder:root',0,'2:6','walk');
  assert.deepEqual(r.nodes.map(n=>n.id),['folder:root','folder:root/0','folder:root/1']);
  assert.equal(r.nodes[0].descendants,484);
  assert.equal(r.nodes[1].descendants,160);
  assert.equal(r.nodes[1].y,r.nodes[2].y);
  assert(r.nodes[0].y<r.nodes[1].y);
  assert.equal(r.excluded.find(x=>x.id==='folder:root/2').reason,'predicate not satisfied');
  assert.equal(r.excluded.find(x=>x.id==='folder:root/file').reason,'different target type');
  for(const e of r.links) assert(bundle.graph.edges.some(x=>x.source===e.source && x.target===e.target));
  assert.equal(r.queries.length,1);
});
test('complete overview accounts for every node and edge, including cycles and disconnected nodes', () => {
  for(const b of [bundle,structuredClone(bundle)]) {
    if(b!==bundle)b.graph.edges.push({source:'folder:root/0',target:'folder:root',type:'Contains'});
    const r=m.graphOverview(b,'folder:root','2:6');
    assert.equal(r.nodes.length,486);
    assert.equal(new Set(r.nodes.map(n=>n.id)).size,486);
    assert.equal(r.links.length,b.graph.edges.length);
    assert.equal(r.nodes.filter(n=>n.selected).length,1);
    assert(r.nodes.every(n=>Number.isFinite(n.x)&&Number.isFinite(n.y)));
  }
});
const littlex=JSON.parse(readFileSync(new URL('../public/data/littlex.json',import.meta.url),'utf8'));
test('LittleX sealed capture joins finite DAG template across all four feed requests',()=>{
  m.validateBundle(littlex);
  assert.equal(m.firstNode(littlex),'root:user:0');
  assert.equal(littlex.graph.nodes.length,1100);
  assert.equal(littlex.requests.length,4);
  for(const r of littlex.requests){
    assert.equal(r.queries.length,14);
    assert.equal(r.visited.length,0); // Feed output is not a complete visit trace.
    const view=m.finiteDagView(littlex,m.firstNode(littlex),r.id);
    assert(view.supported);
    assert.equal(view.queries.length,1);
    assert.equal(view.queries[0].sql,littlex.compiler.templates.find(t=>t.id===view.templateId).sql);
    assert.deepEqual(view.bindings.map(x=>[x.event,x.count]),[[1,1],[4,20],[5,40]]);
    assert.equal(view.regionPath.split(' Z').length-1,1);
    for(const binding of view.bindings)for(const p of binding.paths){
      assert.equal(p.edges.length,p.nodes.length-1);
      for(let i=0;i<p.edges.length;i++){
        assert.equal(p.edges[i].source,p.nodes[i]);assert.equal(p.edges[i].target,p.nodes[i+1]);
        assert(littlex.graph.edges.includes(p.edges[i]));
      }
    }
    assert.equal(view.boundaries.length,2);
    assert(view.boundaries.every(x=>x.event===8&&x.sub.includes('here.to_view()')));
  }
});
test('LittleX finite projection fails closed for unsupported direction, missing graph path and unknown origin',()=>{
  assert.equal(m.finiteDagView(littlex,'missing','2:152').supported,false);
  const b=structuredClone(littlex);b.compiler.regions[0].metadata.rules[0].hops[0][2]=0;
  assert.equal(m.finiteDagView(b,'root:user:0','2:152').supported,false);
  const c=structuredClone(littlex);c.graph.edges=c.graph.edges.filter(e=>e.type!=='Follow');
  assert.equal(m.finiteDagView(c,'root:user:0','2:152').supported,false);
});

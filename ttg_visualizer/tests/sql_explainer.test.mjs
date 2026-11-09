import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const m=await import('data:text/javascript;base64,'+Buffer.from(readFileSync(new URL('../sql_explainer.js',import.meta.url),'utf8')).toString('base64'));
const bundles=['littlex','jdrive'].map(n=>JSON.parse(readFileSync(new URL(`../public/data/${n}.json`,import.meta.url),'utf8')));
test('every block and fragment is an exact original SQL slice; formatted tokens are unchanged',()=>{
  for(const b of bundles)for(const r of b.requests){
    const w=m.explainQuery(b,r.id);assert.equal(w.supported,true,w.reason);
    assert.equal(w.template.sql,w.query.sql);
    for(const step of w.steps){
      assert.equal(step.sql,w.query.sql.slice(step.start,step.end));
      for(const f of step.fragments){
        assert.equal(f.sql,step.sql.slice(f.start,f.end));
        const formatted=m.highlightedSQL(f.sql).map(t=>t.text).join('');
        assert.deepEqual(m.sqlTokens(formatted).map(t=>t.text),m.sqlTokens(f.sql).map(t=>t.text));
      }
      for(const p of step.parameters)assert(!p.value.includes('undefined'));
    }
  }
});
test('LittleX dependencies, aliases, ACL fragments and catalog slot are source bound',()=>{
  const w=m.explainQuery(bundles[0],bundles[0].requests[0].id);
  assert.deepEqual(w.steps.map(s=>s.id),['cte0','cte1','cte2','catalog','output']);
  const post=w.steps[1];
  assert.match(post.sql,/FROM "_cte0"/);assert(!post.sql.includes('FROM "_cte2"'));
  assert(post.aliases.some(a=>a.name==='_t15'&&a.role==='Traversal edge'&&a.type==='"Post"'));
  assert(post.aliases.some(a=>a.name==='_t16'&&a.role==='Tweet node'));
  assert(post.aliases.some(a=>a.name==='_t18'&&a.role==='ACL group-membership edge'));
  const acl=post.fragments.find(f=>f.id==='acl');assert(acl.sql.includes('root_id'));assert(acl.sql.includes('EXISTS'));
  const catalog=w.steps.find(s=>s.id==='catalog');
  assert(catalog.parameters.some(p=>p.value==='-1'&&!p.dynamic));
  assert(!catalog.sql.includes('LIMIT'));
  assert.match(w.steps.at(-1).sql,/UNION ALL/);
  assert.equal(w.query.rows,64);
});
test('JDrive UNION origin set is separate from outer path filtering/order/LIMIT',()=>{
  const w=m.explainQuery(bundles[1],bundles[1].requests[0].id);
  assert.deepEqual(w.steps.map(s=>s.id),['seed','recursive','pairs','output']);
  const parsed=m.splitCTEs(w.template.sql);
  assert(parsed.recursive);assert.equal(parsed.ctes.length,1);
  assert(parsed.ctes[0].sql.includes(' UNION SELECT '));assert(!parsed.ctes[0].sql.includes('UNION ALL'));
  assert(!parsed.ctes[0].sql.includes('LIMIT'));
  assert(w.steps[1].fragments.some(f=>f.id==='predicate'&&f.sql.includes('jsonb_typeof')));
  assert(!w.steps[2].fragments.some(f=>f.id==='predicate'));
  assert(w.steps[2].sql.includes('LEFT JOIN LATERAL'));
  assert(w.steps.at(-1).sql.includes('LIMIT CAST(:row_limit'));
  assert(w.columns.some(c=>c[0].includes('source_props')));
});
test('lexer respects quoted parentheses / commas and rejects malformed delimiters',()=>{
  const x=`WITH "a" ("x") AS (SELECT '(not a CTE), it''s text' AS "x") SELECT * FROM "a"`;
  const parsed=m.splitCTEs(x);assert.equal(parsed.ctes.length,1);assert(parsed.ctes[0].sql.includes("it''s"));
  assert.throws(()=>m.splitCTEs('WITH "x" AS (SELECT 1'));assert.throws(()=>m.splitCTEs('SELECT 1'));
});
test('unsupported SQL and unlinked queries do not get an invented walkthrough',()=>{
  const b=structuredClone(bundles[0]);b.requests[0].queries.forEach(q=>q.template_ids=[]);
  assert.equal(m.explainQuery(b,b.requests[0].id).supported,false);
  const c=structuredClone(bundles[0]);const q=c.requests[0].queries.find(q=>q.template_ids.length);
  q.sql=q.sql.replaceAll('FROM "_cte0" AS "_t0" WHERE','FROM "_cte1" AS "_t0" WHERE');
  c.compiler.templates.find(t=>q.template_ids.includes(t.id)).sql=q.sql;
  assert.equal(m.explainQuery(c,c.requests[0].id).supported,false);
});
test('symbol selection uses exact tokens, not overlapping alias prefixes',()=>{
  const tokens=m.highlightedSQL('SELECT "_t1"."id", "_t10"."id", :p1, :p10','_t1');
  assert.equal(tokens.filter(t=>t.active).length,1);
  const w=m.explainQuery(bundles[0],bundles[0].requests[0].id);
  assert.match(m.symbolInfo(w.steps[1],'_t16'),/Tweet node/);
  assert.match(m.symbolInfo(w.steps[1],'actor_uuid'),/Runtime Bind not retained/);
});

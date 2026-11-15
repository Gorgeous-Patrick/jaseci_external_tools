"""Uniform excluded admin ANALYZE boundary; no instrumentation/runtime mutation."""
import json,time
from pathlib import Path
from ia_interop import require,reference

def normalize(pg,directory,database,requests):
 directory=Path(directory);path=directory/'planner-statistics-before-workflow.json'
 require(not path.exists(),'Statistics normalization repeated inside workflow')
 require(not any(r['phase']=='workflow' for r in requests),'Primary already started')
 require(database in pg.databases,'Unowned statistics target')
 started=time.perf_counter_ns();commands=['ANALYZE anchors','ANALYZE graph_types']
 results=[pg.sql(command,database) for command in commands]
 query="SELECT json_build_object('relations',(SELECT json_agg(row_to_json(x)) FROM (SELECT c.relname,c.reltuples,c.relpages,s.last_analyze FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace LEFT JOIN pg_stat_all_tables s ON s.relid=c.oid WHERE n.nspname='public' AND c.relname IN ('anchors','graph_types') ORDER BY c.relname) x),'statistics_rows',(SELECT count(*) FROM pg_stats WHERE schemaname='public' AND tablename IN ('anchors','graph_types')))"
 proof=json.loads(pg.sql(query,database));ended=time.perf_counter_ns()
 require({r['relname'] for r in proof['relations']}=={'anchors','graph_types'},'Statistics census missing target table')
 require(all(r['reltuples']>=0 for r in proof['relations']),'ANALYZE relation statistics absent')
 path.write_text(json.dumps(dict(passed=True,database=database,cluster_owner=pg.owner,commands=commands,
   results=results,proof_SQL=query,observed=proof,admin_start_ns=started,admin_end_ns=ended,
   placement='After import/setup/restart verification; before first workflow post constructs profile-reset header and HTTP clocks.',
   primary_excluded=True,source=reference(Path(__file__))),indent=2)+'\n')
 return reference(path)

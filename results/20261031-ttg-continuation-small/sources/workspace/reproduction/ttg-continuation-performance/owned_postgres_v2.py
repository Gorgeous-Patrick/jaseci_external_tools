"""NEW cleanup-only subclass; original owned_postgres.py stays unchanged."""
from pathlib import Path
import re
import json
from evidence import sha256,read_json
from owned_postgres import OwnedPostgres as OriginalOwnedPostgres
from cleanup_guard_v2 import require,validate_acceptance,verify_source_context,validate_raw_case
from semantic_cleanup_v2 import create_acceptance


class OwnedPostgres(OriginalOwnedPostgres):
    def __init__(self,*args,cleanup_context=None,**kwargs):
        super().__init__(*args,**kwargs);self.cleanup_context=cleanup_context

    def create_database(self):
        require(isinstance(self.cleanup_context,dict),'Cleanup context required before DB creation')
        name=super().create_database()
        context=self.cleanup_context
        context.update(database=name,cluster_owner=self.owner)
        path=Path(context['case_directory'])/'cleanup-target.json'
        require(not path.exists(),'Owned DB target binding already exists')
        target=dict(kind='owned_cleanup_target',**{key:context[key] for key in
            ('database','cluster_owner','run_directory','case_directory','app','config_id','seed')})
        target['cleanup_review']=context['cleanup_review']
        path.write_text(json.dumps(target,indent=2)+'\n')
        context['target_binding']=dict(path=str(path),sha256=sha256(path))
        return name

    def drop_completed_database(self,name,artifacts_manifest):
        self.verify_owner()
        require(name in self.databases and re.fullmatch(r'continuation_[0-9a-f]{32}',name),'Unowned database')
        require(not any(service.poll() is None for service in self.services),'Workload service still active')
        require(isinstance(self.cleanup_context,dict),'Reviewed cleanup source/semantic context missing')
        require(self.cleanup_context.get('mode')=='live_cleanup','Historical/offline proof cannot authorize DROP')
        require(self.cleanup_context.get('database')==name and self.cleanup_context.get('cluster_owner')==self.owner,
            'Cleanup context is not this owned cluster/database')
        directory=Path(artifacts_manifest).resolve().parent
        acceptance=Path(self.cleanup_context['acceptance_directory'])/(directory.name+'.json')
        acceptance.parent.mkdir(parents=True,exist_ok=True)
        verify_source_context(self.cleanup_context)
        validate_raw_case(directory,self.cleanup_context)
        names=self.cleanup_context['domain_types']
        require(names and all(re.fullmatch(r'\w+',x) for x in names),'Invalid/missing domain type census')
        values=','.join("'"+x+"'" for x in names)
        sql=("WITH domain AS (SELECT id FROM anchors WHERE arch_type IN ("+values+")) "
            "SELECT coalesce(json_agg(row_to_json(q)), '[]'::json) FROM ("
            "SELECT id,kind,arch_type,root_id,src,dst,undirected,props FROM anchors WHERE id IN (SELECT id FROM domain) "
            "OR (kind='EdgeAnchor' AND (src IN (SELECT id FROM domain) OR dst IN (SELECT id FROM domain))) ORDER BY seq) q")
        actual=json.loads(self.sql(sql,name));sealed=read_json(directory/'final-graph-raw.json')
        require(actual==sealed,'Independent physical DB census differs from sealed final state')
        self.cleanup_context['database_state']=dict(matches_sealed_final_graph=True,
            final_graph_sha256=sha256(directory/'final-graph-raw.json'),actual_row_count=len(actual),
            database=name,cluster_owner=self.owner,SQL=sql,
            scope='Independent post-service clean-driver census; excluded from application workload')
        create_acceptance(directory,acceptance,self.cleanup_context)
        first=validate_acceptance(directory,acceptance,self.cleanup_context)
        active=self.sql(f"SELECT count(*) FROM pg_stat_activity WHERE datname='{name}'")
        require(active=='0','Owned database still has active sessions')
        # Source, CAS and semantic proof are validated again AFTER session check,
        # immediately before actual SQL deletion; no wrapper-only approval.
        final=validate_acceptance(directory,acceptance,self.cleanup_context)
        require(first==final,'Cleanup acceptance changed before DROP')
        self.sql('DROP DATABASE '+name);self.databases.remove(name)
        self.record('successful_database_dropped',database=name,validated_acceptance=final,active_sessions=0)

"""Relational oracle for the pinned BenchBase Wikipedia variant, no native DB."""
import argparse
import sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from state_keys import wiki_key, edge_sort, root_edge
import hashlib
import json
from pathlib import Path
import random
import sqlite3

TABLES={
'WikiUser':('useracct','user_id INTEGER PRIMARY KEY,user_name TEXT,user_touched TEXT,user_editcount INTEGER'),
'UserGroup':('user_groups','user_id INTEGER,group_name TEXT'),
'Page':('page','page_id INTEGER PRIMARY KEY,page_namespace INTEGER,page_title TEXT,page_latest INTEGER,page_touched TEXT,page_is_new INTEGER,page_is_redirect INTEGER,page_len INTEGER'),
'PageRestriction':('page_restrictions','pr_page INTEGER,pr_type TEXT'),
'IPBlock':('ipblocks','ipb_user INTEGER,ipb_address TEXT,ipb_expiry TEXT'),
'Text':('text','old_id INTEGER PRIMARY KEY AUTOINCREMENT,old_page INTEGER,old_text TEXT,old_flags TEXT'),
'Revision':('revision','rev_id INTEGER PRIMARY KEY AUTOINCREMENT,rev_page INTEGER,rev_text_id INTEGER,rev_comment TEXT,rev_minor_edit INTEGER,rev_user INTEGER,rev_user_text TEXT,rev_timestamp TEXT,rev_deleted INTEGER,rev_len INTEGER,rev_parent_id INTEGER'),
'Watch':('watchlist','wl_user INTEGER,wl_namespace INTEGER,wl_title TEXT,wl_notificationtimestamp TEXT,PRIMARY KEY(wl_user,wl_namespace,wl_title)'),
'RecentChange':('recentchanges','rc_timestamp TEXT,rc_cur_time TEXT,rc_namespace INTEGER,rc_title TEXT,rc_type INTEGER,rc_minor INTEGER,rc_cur_id INTEGER,rc_user INTEGER,rc_user_text TEXT,rc_comment TEXT,rc_this_oldid INTEGER,rc_last_oldid INTEGER,rc_bot INTEGER,rc_moved_to_ns INTEGER,rc_moved_to_title TEXT,rc_ip TEXT,rc_old_len INTEGER,rc_new_len INTEGER'),
'Log':('logging','log_type TEXT,log_action TEXT,log_timestamp TEXT,log_user INTEGER,log_user_text TEXT,log_namespace INTEGER,log_title TEXT,log_page INTEGER,log_comment TEXT,log_params TEXT')}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def fixture(seed=42):
    nodes=[];edges=[]
    def add(key,kind,**fields):nodes.append(dict(id=key,type=kind,fields=fields))
    for i,name in [(1,'Avery'),(2,'Blair'),(3,'Casey')]:add(f'user:{i}','WikiUser',user_id=i,user_name=name,user_touched='20260101000000',user_editcount=0)
    add('group:1','UserGroup',user_id=1,group_name='editor')
    for i,title in [(1,'Graph Systems'),(2,'Quiet Page')]:
        text='Article '+str(i)+' about graph systems.'
        add(f'page:{i}','Page',page_id=i,page_namespace=0,page_title=title,page_latest=i,page_touched='20260101000000',page_is_new=1,page_is_redirect=0,page_len=len(text))
        add(f'text:{i}','Text',old_id=i,old_page=i,old_text=text,old_flags='utf-8')
        add(f'revision:{i}','Revision',rev_id=i,rev_page=i,rev_text_id=i,rev_comment='Initial revision',rev_minor_edit=0,rev_user=1,rev_user_text='Avery',rev_timestamp='20260101000000',rev_deleted=0,rev_len=len(text),rev_parent_id=0)
        edges.extend([dict(source=f'page:{i}',target=f'revision:{i}',type='HasRevision'),dict(source=f'revision:{i}',target=f'text:{i}',type='HasText')])
    add('restriction:1','PageRestriction',pr_page=1,pr_type='edit')
    add('block:1','IPBlock',ipb_user=2,ipb_address='192.0.2.2',ipb_expiry='infinity')
    add('watch:2:0','Watch',wl_user=2,wl_namespace=0,wl_title='Graph Systems',wl_notificationtimestamp=None)
    add('watch:1:talk','Watch',wl_user=1,wl_namespace=1,wl_title='Quiet Page',wl_notificationtimestamp=None)
    add('watch:3:0','Watch',wl_user=3,wl_namespace=0,wl_title='Graph Systems',wl_notificationtimestamp='20260101000100')
    random.Random(seed).shuffle(nodes)
    return {'nodes':nodes,'edges':edges}


def database(graph):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    for table,columns in TABLES.values():db.execute('CREATE TABLE '+table+'('+columns+')')
    for row in graph['nodes']:
        table,_=TABLES[row['type']];fields=row['fields'];names=list(fields)
        db.execute('INSERT INTO '+table+'('+','.join(names)+') VALUES ('+','.join('?' for _ in names)+')',list(fields.values()))
    db.commit();return db


def snapshot(db):
    tables={kind:sorted([dict(row) for row in db.execute('SELECT * FROM '+table)],key=lambda row:json.dumps(row,sort_keys=True)) for kind,(table,_) in TABLES.items()}
    # Infer expected links from independent relational foreign keys, never from
    # the native graph or the native inspection result.
    edges=[]
    for row in tables['Revision']:
        edges.append(dict(source=wiki_key('Page',dict(page_id=row['rev_page'])),target=wiki_key('Revision',row),type='HasRevision',undirected=False))
        edges.append(dict(source=wiki_key('Revision',row),target=wiki_key('Text',dict(old_id=row['rev_text_id'])),type='HasText',undirected=False))
    roots=[root_edge('primary',wiki_key(kind,row)) for kind,rows in tables.items() for row in rows]
    return dict(tables=tables,edges=sorted(edges,key=edge_sort),root_edges=sorted(roots,key=edge_sort))


class OracleAbort(Exception):pass


def execute(db,case,body,timestamp='<mutation-time>'):
    if case in ['GetPageAnonymous','GetPageAuthenticated']:
        user_text=body['user_ip']
        if case=='GetPageAuthenticated' and body['user_id']>0:
            user=db.execute('SELECT * FROM useracct WHERE user_id=?',(body['user_id'],)).fetchone()
            if user is None:raise OracleAbort('invalid_user')
            user_text=user['user_name'];db.execute('SELECT group_name FROM user_groups WHERE user_id=?',(body['user_id'],)).fetchall()
        page=db.execute('SELECT * FROM page WHERE page_namespace=? AND page_title=? LIMIT 1',(body['namespace'],body['title'])).fetchone()
        if page is None:raise OracleAbort('invalid_page')
        db.execute('SELECT * FROM page_restrictions WHERE pr_page=?',(page['page_id'],)).fetchall()
        if case=='GetPageAuthenticated':db.execute('SELECT * FROM ipblocks WHERE ipb_user=?',(body['user_id'],)).fetchall()
        else:db.execute('SELECT * FROM ipblocks WHERE ipb_address=?',(body['user_ip'],)).fetchall()
        revision=db.execute('SELECT r.* FROM page p,revision r WHERE p.page_id=r.rev_page AND r.rev_page=? AND p.page_id=? AND r.rev_id=p.page_latest LIMIT 1',(page['page_id'],page['page_id'])).fetchone()
        if revision is None:raise OracleAbort('invalid_revision')
        text=db.execute('SELECT old_text,old_flags FROM text WHERE old_id=? LIMIT 1',(revision['rev_text_id'],)).fetchone()
        if text is None:raise OracleAbort('missing_text')
        return None if body['for_select'] else {'userText':user_text,'pageId':page['page_id'],'oldText':text['old_text'],'textId':revision['rev_text_id'],'revisionId':revision['rev_id']}
    if case in ['AddWatchList','RemoveWatchList']:
        if body['user_id']<=0:return None
        for namespace in [body['namespace']]+([1] if body['namespace']==0 else []):
            params=(body['user_id'],namespace,body['title'])
            if case=='AddWatchList':db.execute('INSERT INTO watchlist VALUES (?,?,?,NULL)',params)
            else:db.execute('DELETE FROM watchlist WHERE wl_user=? AND wl_namespace=? AND wl_title=?',params)
        db.execute('UPDATE useracct SET user_touched=? WHERE user_id=?',(timestamp,body['user_id']));return None
    if case!='UpdatePage':raise ValueError('Unsupported Wikipedia procedure '+case)
    b=body;length=len(b['page_text'])
    text_id=db.execute('INSERT INTO text(old_page,old_text,old_flags) VALUES (?,?,?)',(b['page_id'],b['page_text'],'utf-8')).lastrowid
    rev_id=db.execute('INSERT INTO revision(rev_page,rev_text_id,rev_comment,rev_minor_edit,rev_user,rev_user_text,rev_timestamp,rev_deleted,rev_len,rev_parent_id) VALUES (?,?,?,?,?,?,?,?,?,?)',(b['page_id'],text_id,b['revision_comment'][:254],b['minor_edit'],b['user_id'],b['user_text'],timestamp,0,length,b['revision_id'])).lastrowid
    db.execute('UPDATE page SET page_latest=?,page_touched=?,page_is_new=0,page_is_redirect=0,page_len=? WHERE page_id=?',(rev_id,timestamp,length,b['page_id']))
    db.execute('INSERT INTO recentchanges VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(timestamp,timestamp,b['namespace'],b['page_title'],0,0,b['page_id'],b['user_id'],b['user_text'],b['revision_comment'],text_id,b['text_id'],0,0,'',b['user_ip'],length,length))
    watchers=db.execute('SELECT wl_user FROM watchlist WHERE wl_title=? AND wl_namespace=? AND wl_user!=? AND wl_notificationtimestamp IS NULL',(b['page_title'],b['namespace'],b['user_id'])).fetchall()
    for watcher in watchers:db.execute('UPDATE watchlist SET wl_notificationtimestamp=? WHERE wl_title=? AND wl_namespace=? AND wl_user=?',(timestamp,b['page_title'],b['namespace'],watcher['wl_user']))
    for watcher in watchers:db.execute('SELECT * FROM useracct WHERE user_id=?',(watcher['wl_user'],)).fetchall()
    db.execute("INSERT INTO logging VALUES ('patrol','patrol',?,?,?,?,?,?,'',?)",(timestamp,b['user_id'],b['page_title'],b['namespace'],b['user_text'],b['page_id'],f"{rev_id}\n{b['revision_id']}\n1"))
    db.execute('UPDATE useracct SET user_editcount=user_editcount+1 WHERE user_id=?',(b['user_id'],))
    db.execute('UPDATE useracct SET user_touched=? WHERE user_id=?',(timestamp,b['user_id']));return None


def actions():
    read=dict(user_id=1,user_ip='192.0.2.1',namespace=0,title='Graph Systems',for_select=False)
    update=dict(text_id=1,page_id=1,page_title='Graph Systems',page_text='Revised graph systems article.',namespace=0,user_id=1,user_ip='192.0.2.1',user_text='Avery',revision_id=1,revision_comment='Improve the introduction',minor_edit=1)
    return [('GetPageAnonymous',read),('GetPageAuthenticated',read),('GetPageAuthenticated',{**read,'user_id':999}),('GetPageAnonymous',{**read,'for_select':True}),('AddWatchList',dict(user_id=1,namespace=0,title='Graph Systems')),('AddWatchList',dict(user_id=1,namespace=0,title='Graph Systems')),('AddWatchList',dict(user_id=1,namespace=0,title='Quiet Page')),('UpdatePage',update),('GetPageAuthenticated',read),('RemoveWatchList',dict(user_id=1,namespace=0,title='Graph Systems')),('RemoveWatchList',dict(user_id=0,namespace=0,title='Graph Systems')),('UpdatePage',{**update,'text_id':2,'page_id':2,'page_title':'Quiet Page','revision_id':2})]


def prepare(output,seed=42):
    output.mkdir(parents=True,exist_ok=False);graph=fixture(seed);write(output/'graph.json',graph);db=database(graph);rows=[]
    try:
        for index,(case,body) in enumerate(actions()):
            before=snapshot(db);db.execute('BEGIN');error=None
            try:result=execute(db,case,body,timestamp=f'<mutation-time:{index}>');db.commit()
            except (OracleAbort,sqlite3.IntegrityError) as exception:
                db.rollback();result=None;error=str(exception) if isinstance(exception,OracleAbort) else 'duplicate_watch'
            after=snapshot(db)
            if error and before!=after:raise AssertionError('Oracle transaction did not roll back')
            rows.append(dict(request_id=index,case_id='wikipedia/'+case,walker=case,body=body,expected=result,expected_error=error,pre_state_sha256=digest(before),post_state_sha256=digest(after),post_state=after,fresh_session=True))
        with (output/'requests.jsonl').open('w') as file:
            for row in rows:file.write(json.dumps(row,sort_keys=True)+'\n')
        write(output/'manifest.json',dict(seed=seed,request_seed=4242,operations=5,requests=len(rows),oracle_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),fixture_sha256=digest(graph),native='pending',restart='pending',rollback='native_pending',scope='Sequential small correctness fixture; not full synthetic BenchBase population or Wikipedia deployment',deviations=['Generated integer IDs use max+1 in single-worker Jac adapter; relational oracle uses auto-increment','Mutation time is symbolic only in offline oracle; native validation must prove narrow fields are in actual request windows','Pinned recentchanges old_len/new_len and logging user-text/title binding intentionally preserved','GetPageAuthenticated repairs pinned Java group-block statement reuse: execute selectGroup rather than re-executing outer selectUser; query trace intentionally differs']))
        print(json.dumps({'operations':5,'requests':len(rows),'oracle_errors':[r['expected_error'] for r in rows if r['expected_error']]}))
    finally:db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=42);a=p.parse_args();prepare(a.output,a.seed)

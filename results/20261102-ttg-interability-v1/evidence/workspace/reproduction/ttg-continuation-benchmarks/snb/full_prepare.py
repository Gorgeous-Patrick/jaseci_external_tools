"""Full SNB v1 correctness fixture and relational SQL oracles, never app timing."""
import argparse
import sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from state_keys import wiki_key, edge_sort, root_edge
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sqlite3

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('short_read_oracles',HERE/'prepare.py');short=importlib.util.module_from_spec(spec);spec.loader.exec_module(short)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def fixture(seed=42):
    graph=short.fixture(seed);nodes={r['id']:r for r in graph['nodes']};edges=graph['edges']
    def node(key,archetype,**fields):nodes[key]=dict(id=key,type=archetype,fields=fields)
    def edge(source,target,kind,**fields):edges.append(dict(source=source,target=target,type=kind,fields=fields))
    for row in nodes.values():
        fields=row['fields']
        if row['type']=='Person':fields.update(emails=[fields['first_name'].lower()+str(fields['person_id'])+'@example.test'],languages=['English'])
        elif row['type']=='Place':fields['kind']='City'
        elif row['type']=='Forum':fields['creation_date']=10
        elif row['type']=='Message':fields.update(length=len(fields['content']),language='English' if not fields['is_comment'] else '',location_ip='192.0.2.10',browser='Firefox')
    for i,name in [(10,'United States'),(11,'United Kingdom'),(12,'France')]:node(f'place:{i}','Place',place_id=i,name=name,kind='Country')
    for city,country in [(1,10),(2,11),(3,12)]:edge(f'place:{city}',f'place:{country}','PartOf')
    node('forum:20','Forum',forum_id=20,title='Empty Forum',creation_date=20);edge('forum:20','person:2','HasModerator')
    for person,forum,date in [(1,10,100),(2,10,500),(3,10,600),(4,10,700),(5,20,800)]:edge(f'forum:{forum}',f'person:{person}','HasMember',join_date=date)
    for i,name,kind,place in [(10,'Graph Labs','Company',11),(20,'Query Works','Company',11),(30,'Harbor University','University',1)]:
        node(f'organization:{i}','Organization',organization_id=i,name=name,kind=kind);edge(f'organization:{i}',f'place:{place}','LocatedIn')
    for person,org,year,kind in [(2,10,1999,'WorkAt'),(3,10,2000,'WorkAt'),(5,20,2001,'WorkAt'),(4,10,2002,'WorkAt'),(4,30,1998,'StudyAt')]:edge(f'person:{person}',f'organization:{org}',kind,year=year)
    for i,name in [(1,'Technology'),(2,'Systems'),(3,'Data'),(4,'Other')]:node(f'class:{i}','TagClass',class_id=i,name=name)
    edge('class:2','class:1','SubClassOf');edge('class:3','class:1','SubClassOf')
    for i,name,category in [(1,'Graph',2),(2,'Synchronization',2),(3,'Databases',3),(4,'NovelTopic',4)]:
        node(f'tag:{i}','Tag',tag_id=i,name=name);edge(f'tag:{i}',f'class:{category}','HasType')
    edge('person:1','tag:1','Interest');edge('person:1','tag:2','Interest')
    def message(i,author,date,content,location,parent=None,forum=10,image=''):
        node(f'message:{i}','Message',message_id=i,content=content,image_file=image,creation_date=date,is_comment=parent is not None,length=len(content),language='English' if parent is None else '',location_ip='192.0.2.10',browser='Firefox')
        edge(f'message:{i}',f'person:{author}','HasCreator');edge(f'message:{i}',f'place:{location}','LocatedIn')
        if parent is None:edge(f'forum:{forum}',f'message:{i}','ContainerOf')
        else:edge(f'message:{i}',f'message:{parent}','ReplyOf')
    for i,author,date,content,location,parent in [(130,4,350,'New topics',10,None),(140,5,650,'Shared interests',11,None),(150,3,10000,'Visit one',10,None),(160,3,11000,'Visit two',11,None),(170,2,700,'A new topic',10,None),(230,1,550,'Reply to a friend',10,100),(250,4,600,'A photo reply',10,110),(260,2,900,'Reply to the start person',11,120),(270,4,910,'Reply to a nested comment',10,210)]:message(i,author,date,content,location,parent)
    # Add location to each base message. A Comment can be posted while visiting.
    for i,country in [(100,10),(110,12),(120,10),(200,10),(210,10),(220,10)]:edge(f'message:{i}',f'place:{country}','LocatedIn')
    for message_id,tags in [(100,[1,2]),(110,[3]),(120,[1]),(130,[3,4]),(140,[1,2]),(150,[3]),(160,[3]),(170,[1,4])]:
        for tag in tags:edge(f'message:{message_id}',f'tag:{tag}','HasTag')
    for person,message_id,date in [(2,120,1000),(2,210,100000),(3,210,120000),(4,120,180000)]:edge(f'person:{person}',f'message:{message_id}','Likes',creation_date=date)
    graph['nodes']=list(nodes.values());rng=random.Random(seed);rng.shuffle(graph['nodes']);rng.shuffle(edges)
    return graph


def database(graph):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.executescript('''CREATE TABLE nodes(key TEXT PRIMARY KEY,type TEXT,props TEXT NOT NULL);
CREATE TABLE edges(source TEXT,target TEXT,type TEXT,props TEXT NOT NULL,UNIQUE(source,target,type));''')
    for r in graph['nodes']:db.execute('INSERT INTO nodes VALUES (?,?,?)',(r['id'],r['type'],json.dumps(r['fields'],sort_keys=True)))
    for r in graph['edges']:db.execute('INSERT INTO edges VALUES (?,?,?,?)',(r['source'],r['target'],r['type'],json.dumps(r.get('fields',{}),sort_keys=True)))
    # Each entity/association has an explicit relational view. SQL evaluation
    # shares fixture data but no native traversal/result-building implementation.
    db.executescript('''
CREATE VIEW person AS SELECT key,json_extract(props,'$.person_id') id,json_extract(props,'$.first_name') first,json_extract(props,'$.last_name') last,json_extract(props,'$.birthday') birthday,json_extract(props,'$.location_ip') ip,json_extract(props,'$.browser') browser,json_extract(props,'$.gender') gender,json_extract(props,'$.creation_date') created,json_extract(props,'$.emails') emails,json_extract(props,'$.languages') languages,(SELECT json_extract(p.props,'$.place_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='LocatedIn') city FROM nodes n WHERE type='Person';
CREATE VIEW place AS SELECT key,json_extract(props,'$.place_id') id,json_extract(props,'$.name') name,json_extract(props,'$.kind') kind,(SELECT json_extract(p.props,'$.place_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='PartOf') parent FROM nodes n WHERE type='Place';
CREATE VIEW message AS SELECT key,json_extract(props,'$.message_id') id,json_extract(props,'$.content') content,json_extract(props,'$.image_file') image,json_extract(props,'$.creation_date') created,json_extract(props,'$.is_comment') is_comment,(SELECT json_extract(p.props,'$.person_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='HasCreator') author,(SELECT json_extract(p.props,'$.message_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='ReplyOf') parent,(SELECT json_extract(p.props,'$.forum_id') FROM edges e JOIN nodes p ON p.key=e.source WHERE e.target=n.key AND e.type='ContainerOf') forum,(SELECT json_extract(p.props,'$.place_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='LocatedIn') location FROM nodes n WHERE type='Message';
CREATE VIEW forum AS SELECT key,json_extract(props,'$.forum_id') id,json_extract(props,'$.title') title,(SELECT json_extract(p.props,'$.person_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='HasModerator') moderator FROM nodes n WHERE type='Forum';
CREATE VIEW knows AS SELECT a.id a,b.id b,json_extract(e.props,'$.creation_date') created FROM edges e JOIN person a ON a.key=e.source JOIN person b ON b.key=e.target WHERE e.type='Knows' UNION ALL SELECT b.id,a.id,json_extract(e.props,'$.creation_date') FROM edges e JOIN person a ON a.key=e.source JOIN person b ON b.key=e.target WHERE e.type='Knows';
CREATE VIEW organization AS SELECT key,json_extract(props,'$.organization_id') id,json_extract(props,'$.name') name,json_extract(props,'$.kind') kind,(SELECT json_extract(p.props,'$.place_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='LocatedIn') location FROM nodes n WHERE type='Organization';
CREATE VIEW tagclass AS SELECT key,json_extract(props,'$.class_id') id,json_extract(props,'$.name') name,(SELECT json_extract(p.props,'$.class_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='SubClassOf') parent FROM nodes n WHERE type='TagClass';
CREATE VIEW tag AS SELECT key,json_extract(props,'$.tag_id') id,json_extract(props,'$.name') name,(SELECT json_extract(p.props,'$.class_id') FROM edges e JOIN nodes p ON p.key=e.target WHERE e.source=n.key AND e.type='HasType') class FROM nodes n WHERE type='Tag';
CREATE VIEW message_tag AS SELECT m.id message,t.id tag FROM edges e JOIN message m ON m.key=e.source JOIN tag t ON t.key=e.target WHERE e.type='HasTag';
CREATE VIEW interest AS SELECT p.id person,t.id tag FROM edges e JOIN person p ON p.key=e.source JOIN tag t ON t.key=e.target WHERE e.type='Interest';
CREATE VIEW membership AS SELECT f.id forum,p.id person,json_extract(e.props,'$.join_date') joined FROM edges e JOIN forum f ON f.key=e.source JOIN person p ON p.key=e.target WHERE e.type='HasMember';
CREATE VIEW work AS SELECT p.id person,o.id organization,json_extract(e.props,'$.year') year FROM edges e JOIN person p ON p.key=e.source JOIN organization o ON o.key=e.target WHERE e.type='WorkAt';
CREATE VIEW study AS SELECT p.id person,o.id organization,json_extract(e.props,'$.year') year FROM edges e JOIN person p ON p.key=e.source JOIN organization o ON o.key=e.target WHERE e.type='StudyAt';
CREATE VIEW likes AS SELECT p.id person,m.id message,json_extract(e.props,'$.creation_date') created FROM edges e JOIN person p ON p.key=e.source JOIN message m ON m.key=e.target WHERE e.type='Likes';
''');db.commit();return db


NEAR='near(id) AS (SELECT b FROM knows WHERE a=:person UNION SELECT k2.b FROM knows k1 JOIN knows k2 ON k2.a=k1.b WHERE k1.a=:person AND k2.b!=:person)'
SQL=dict(short.SQL)
SQL.update({
'IC1':'''WITH RECURSIVE path(id,distance,seen) AS (SELECT :person,0,','||:person||',' UNION ALL SELECT k.b,p.distance+1,p.seen||k.b||',' FROM path p JOIN knows k ON k.a=p.id WHERE p.distance<3 AND instr(p.seen,','||k.b||',')=0), closest AS (SELECT id,min(distance) distance FROM path WHERE id!=:person GROUP BY id) SELECT p.id friendId,p.last friendLastName,c.distance distanceFromPerson,p.birthday friendBirthday,p.created friendCreationDate,p.gender friendGender,p.browser friendBrowserUsed,p.ip friendLocationIp,p.emails friendEmails,p.languages friendLanguages,city.name friendCityName,(SELECT json_group_array(json_array(name,year,location_name)) FROM (SELECT o.name,s.year,l.name location_name FROM study s JOIN organization o ON o.id=s.organization JOIN place l ON l.id=o.location WHERE s.person=p.id ORDER BY o.name,s.year,l.name)) friendUniversities,(SELECT json_group_array(json_array(name,year,location_name)) FROM (SELECT o.name,w.year,l.name location_name FROM work w JOIN organization o ON o.id=w.organization JOIN place l ON l.id=o.location WHERE w.person=p.id ORDER BY o.name,w.year,l.name)) friendCompanies FROM closest c JOIN person p ON p.id=c.id JOIN place city ON city.id=p.city WHERE p.first=:first_name ORDER BY c.distance,p.last,p.id LIMIT 20''',
'IC2':'''SELECT p.id personId,p.first personFirstName,p.last personLastName,m.id messageId,CASE WHEN m.image!='' THEN m.image ELSE m.content END messageContent,m.created messageCreationDate FROM person p JOIN message m ON m.author=p.id JOIN knows k ON k.b=p.id WHERE k.a=:person AND m.created<:max_date ORDER BY m.created DESC,m.id ASC LIMIT 20''',
'IC3':'''WITH '''+NEAR+''' SELECT p.id personId,p.first personFirstName,p.last personLastName,sum(m.location=x.id) xCount,sum(m.location=y.id) yCount,count(*) count FROM near n JOIN person p ON p.id=n.id JOIN place city ON city.id=p.city JOIN place country ON country.id=city.parent JOIN message m ON m.author=p.id JOIN place x ON x.name=:country_x JOIN place y ON y.name=:country_y WHERE country.name NOT IN (:country_x,:country_y) AND m.created>=:start_date AND m.created<:start_date+:duration_days*86400000 AND m.location IN (x.id,y.id) GROUP BY p.id HAVING xCount>0 AND yCount>0 ORDER BY count DESC,p.id ASC LIMIT 20''',
'IC4':'''SELECT t.name tagName,count(*) postCount FROM knows k JOIN message m ON m.author=k.b JOIN message_tag mt ON mt.message=m.id JOIN tag t ON t.id=mt.tag WHERE k.a=:person AND m.parent IS NULL AND m.created>=:start_date AND m.created<:start_date+:duration_days*86400000 AND NOT EXISTS(SELECT 1 FROM knows oldk JOIN message oldm ON oldm.author=oldk.b JOIN message_tag oldt ON oldt.message=oldm.id WHERE oldk.a=:person AND oldm.parent IS NULL AND oldm.created<:start_date AND oldt.tag=t.id) GROUP BY t.id ORDER BY postCount DESC,t.name ASC LIMIT 10''',
'IC5':'''WITH '''+NEAR+''' SELECT f.title forumTitle,count(m.id) postCount FROM near n JOIN membership fp ON fp.person=n.id JOIN forum f ON f.id=fp.forum LEFT JOIN message m ON m.forum=f.id AND m.author=n.id WHERE fp.joined>:min_date GROUP BY f.id ORDER BY postCount DESC,f.id ASC LIMIT 20''',
'IC6':'''WITH '''+NEAR+''' SELECT t.name tagName,count(*) postCount FROM near n JOIN message m ON m.author=n.id JOIN message_tag mt ON mt.message=m.id JOIN tag t ON t.id=mt.tag WHERE m.parent IS NULL AND t.name!=:tag_name AND EXISTS(SELECT 1 FROM message_tag other JOIN tag wanted ON wanted.id=other.tag WHERE other.message=m.id AND wanted.name=:tag_name) GROUP BY t.id ORDER BY postCount DESC,t.name ASC LIMIT 10''',
'IC7':'''WITH ranked AS (SELECT l.person,l.message,l.created,row_number() OVER(PARTITION BY l.person ORDER BY l.created DESC,m.id ASC) rank FROM likes l JOIN message m ON m.id=l.message WHERE m.author=:person) SELECT p.id personId,p.first personFirstName,p.last personLastName,r.created likeCreationDate,m.id commentOrPostId,CASE WHEN m.image!='' THEN m.image ELSE m.content END commentOrPostContent,(r.created-m.created)/60000 minutesLatency,NOT EXISTS(SELECT 1 FROM knows k WHERE k.a=:person AND k.b=p.id) isNew FROM ranked r JOIN person p ON p.id=r.person JOIN message m ON m.id=r.message WHERE r.rank=1 ORDER BY r.created DESC,p.id ASC LIMIT 20''',
'IC8':'''SELECT p.id personId,p.first personFirstName,p.last personLastName,r.created commentCreationDate,r.id commentId,r.content commentContent FROM message parent JOIN message r ON r.parent=parent.id JOIN person p ON p.id=r.author WHERE parent.author=:person ORDER BY r.created DESC,r.id ASC LIMIT 20''',
'IC9':'''WITH '''+NEAR+''' SELECT p.id personId,p.first personFirstName,p.last personLastName,m.id messageId,CASE WHEN m.image!='' THEN m.image ELSE m.content END messageContent,m.created messageCreationDate FROM near n JOIN person p ON p.id=n.id JOIN message m ON m.author=p.id WHERE m.created<:max_date ORDER BY m.created DESC,m.id ASC LIMIT 20''',
'IC10':'''WITH candidates AS (SELECT DISTINCT k2.b id FROM knows k1 JOIN knows k2 ON k2.a=k1.b WHERE k1.a=:person AND k2.b!=:person AND NOT EXISTS(SELECT 1 FROM knows direct WHERE direct.a=:person AND direct.b=k2.b)) SELECT p.id personId,p.first personFirstName,p.last personLastName,(SELECT coalesce(sum(CASE WHEN EXISTS(SELECT 1 FROM message_tag mt JOIN interest i ON i.tag=mt.tag WHERE mt.message=m.id AND i.person=:person) THEN 1 ELSE -1 END),0) FROM message m WHERE m.author=p.id AND m.parent IS NULL) commonInterestScore,p.gender personGender,city.name personCityName FROM candidates c JOIN person p ON p.id=c.id JOIN place city ON city.id=p.city WHERE (cast(substr(p.birthday,6,2) AS INTEGER)=:month AND cast(substr(p.birthday,9,2) AS INTEGER)>=21) OR (cast(substr(p.birthday,6,2) AS INTEGER)=:month%12+1 AND cast(substr(p.birthday,9,2) AS INTEGER)<22) ORDER BY commonInterestScore DESC,p.id ASC LIMIT 10''',
'IC11':'''WITH '''+NEAR+''' SELECT p.id personId,p.first personFirstName,p.last personLastName,o.name organizationName,w.year organizationWorkFromYear FROM near n JOIN person p ON p.id=n.id JOIN work w ON w.person=p.id JOIN organization o ON o.id=w.organization JOIN place country ON country.id=o.location WHERE country.name=:country_name AND w.year<:work_from_year ORDER BY w.year ASC,p.id ASC,o.name DESC LIMIT 10''',
'IC12':'''WITH RECURSIVE classes(id) AS (SELECT id FROM tagclass WHERE name=:tag_class_name UNION SELECT c.id FROM tagclass c JOIN classes parent ON c.parent=parent.id), matches AS (SELECT DISTINCT p.id person,p.first,p.last,comment.id comment,t.name tag FROM knows k JOIN person p ON p.id=k.b JOIN message comment ON comment.author=p.id JOIN message post ON post.id=comment.parent JOIN message_tag mt ON mt.message=post.id JOIN tag t ON t.id=mt.tag JOIN classes c ON c.id=t.class WHERE k.a=:person AND post.parent IS NULL) SELECT person personId,first personFirstName,last personLastName,(SELECT json_group_array(tag) FROM (SELECT DISTINCT m2.tag FROM matches m2 WHERE m2.person=m.person ORDER BY m2.tag)) tagNames,count(DISTINCT comment) replyCount FROM matches m GROUP BY person ORDER BY replyCount DESC,person ASC LIMIT 20''',
'IC14':'''WITH RECURSIVE paths(id,distance,path,seen) AS (SELECT :person,0,json_array(:person),','||:person||',' UNION ALL SELECT k.b,p.distance+1,json_insert(p.path,'$[#]',k.b),p.seen||k.b||',' FROM paths p JOIN knows k ON k.a=p.id WHERE instr(p.seen,','||k.b||',')=0), targets AS (SELECT * FROM paths WHERE id=:target), shortest AS (SELECT * FROM targets WHERE distance=(SELECT min(distance) FROM targets)), interactions AS (SELECT a.author a,b.author b,CASE WHEN b.parent IS NULL THEN 1.0 ELSE 0.5 END weight FROM message a JOIN message b ON b.id=a.parent), steps AS (SELECT s.path,s.distance,cast(j.value AS INTEGER) a,cast(json_extract(s.path,'$['||(cast(j.key AS INTEGER)+1)||']') AS INTEGER) b FROM shortest s,json_each(s.path) j WHERE j.key<s.distance) SELECT s.path personIdsInPath,coalesce((SELECT sum(i.weight) FROM steps e JOIN interactions i ON (i.a=e.a AND i.b=e.b) OR (i.a=e.b AND i.b=e.a) WHERE e.path=s.path),0.0) pathWeight FROM shortest s ORDER BY pathWeight DESC'''
})


def answer(db,case,parameters):
    rows=[dict(row) for row in db.execute(SQL[case],parameters)]
    json_fields={'IC1':['friendEmails','friendLanguages','friendUniversities','friendCompanies'],'IC12':['tagNames'],'IC14':['personIdsInPath']}.get(case,[])
    for row in rows:
        for field in json_fields:row[field]=json.loads(row[field])
        if case=='IS7':row['replyAuthorKnowsOriginalMessageAuthor']=bool(row['replyAuthorKnowsOriginalMessageAuthor'])
        if case=='IC7':row['isNew']=bool(row['isNew'])
    return rows[0] if case=='IC13' else rows


def snapshot(db):
    nodes=[dict(id=r['key'],type=r['type'],fields=json.loads(r['props'])) for r in db.execute('SELECT * FROM nodes ORDER BY key')]
    edges=[dict(source=r['source'],target=r['target'],type=r['type'],fields=json.loads(r['props']),undirected=False) for r in db.execute('SELECT * FROM edges')]
    return dict(nodes=nodes,edges=sorted(edges,key=edge_sort),root_edges=sorted([root_edge('primary',n['id']) for n in nodes],key=edge_sort))


def parameters():
    return [('IC1',dict(person=1,first_name='Avery')),('IC2',dict(person=1,max_date=500)),('IC3',dict(person=1,country_x='United States',country_y='United Kingdom',start_date=0,duration_days=1)),('IC4',dict(person=1,start_date=250,duration_days=1)),('IC5',dict(person=1,min_date=400)),('IC6',dict(person=1,tag_name='Graph')),('IC7',dict(person=1)),('IC8',dict(person=1)),('IC9',dict(person=1,max_date=200000)),('IC10',dict(person=1,month=12)),('IC11',dict(person=1,country_name='United Kingdom',work_from_year=2010)),('IC12',dict(person=1,tag_class_name='Technology')),('IC13',dict(person=1,target=3)),('IC14',dict(person=1,target=3)),('IS1',dict(person=1)),('IS2',dict(person=1)),('IS3',dict(person=1)),('IS4',dict(message=110)),('IS5',dict(message=210)),('IS6',dict(message=210)),('IS7',dict(message=100))]


def body_for(case,params):
    result={}
    for name,value in params.items():
        if name in ['person','target','message']:
            field='person1_jid' if case in ['IC13','IC14'] and name=='person' else 'person2_jid' if name=='target' else 'person_jid' if name=='person' else 'message_jid'
            result[field]={'$node':('message:' if name=='message' else 'person:')+str(value)}
        else:result[name]=value
    return result



class OracleAbort(Exception):pass


def node_record(db,key,kind):
    row=db.execute('SELECT * FROM nodes WHERE key=? AND type=?',(key,kind)).fetchone()
    if row is None:raise OracleAbort('missing_'+kind.lower())
    return json.loads(row['props'])


def insert_node(db,key,kind,props):db.execute('INSERT INTO nodes VALUES (?,?,?)',(key,kind,json.dumps(props,sort_keys=True)))
def insert_edge(db,source,target,kind,**props):
    if db.execute('SELECT count(*) FROM nodes WHERE key IN (?,?)',(source,target)).fetchone()[0]!=(1 if source==target else 2):raise OracleAbort('missing_endpoint')
    db.execute('INSERT INTO edges VALUES (?,?,?,?)',(source,target,kind,json.dumps(props,sort_keys=True)))
def bound(value):return value['$node'] if isinstance(value,dict) else value


def update(db,case,body):
    b=body
    if case=='U1':
        key=f"person:{b['person_id']}"
        props={k:v for k,v in b.items() if k not in ['city_jid','tag_jids','study_at','work_at']}
        insert_node(db,key,'Person',props);insert_edge(db,key,bound(b['city_jid']),'LocatedIn')
        # SQL uniqueness constraints on component rows independently enforce
        # duplicate list entries after the Person has already been inserted.
        db.execute('CREATE TABLE IF NOT EXISTS components(person TEXT,kind TEXT,value TEXT,PRIMARY KEY(person,kind,value))')
        for kind in ['emails','languages']:
            for value in b[kind]:db.execute('INSERT INTO components VALUES (?,?,?)',(key,kind,value))
        for tag in b['tag_jids']:insert_edge(db,key,bound(tag),'Interest')
        for field,kind in [('study_at','StudyAt'),('work_at','WorkAt')]:
            for row in b[field]:insert_edge(db,key,bound(row['organization_jid']),kind,year=row['year'])
    elif case in ['U2','U3']:
        person=bound(b['person_jid']);message=bound(b['message_jid']);m=node_record(db,message,'Message');node_record(db,person,'Person')
        if m['is_comment']!=(case=='U3'):raise OracleAbort('post_required' if case=='U2' else 'comment_required')
        insert_edge(db,person,message,'Likes',creation_date=b['creation_date'])
    elif case=='U4':
        key=f"forum:{b['forum_id']}";insert_node(db,key,'Forum',{k:b[k] for k in ['forum_id','title','creation_date']})
        insert_edge(db,key,bound(b['moderator_jid']),'HasModerator')
        for tag in b['tag_jids']:insert_edge(db,key,bound(tag),'HasTag')
    elif case=='U5':insert_edge(db,bound(b['forum_jid']),bound(b['person_jid']),'HasMember',join_date=b['join_date'])
    elif case in ['U6','U7']:
        key=f"message:{b['message_id']}";fields={name:b[name] for name in ['message_id','content','creation_date','location_ip','browser','length']}
        fields.update(is_comment=case=='U7',image_file='' if case=='U7' else b['image_file'],language='' if case=='U7' else b['language'])
        insert_node(db,key,'Message',fields);insert_edge(db,key,bound(b['author_jid']),'HasCreator');insert_edge(db,key,bound(b['country_jid']),'LocatedIn')
        if case=='U7':insert_edge(db,key,bound(b['parent_jid']),'ReplyOf')
        else:insert_edge(db,bound(b['forum_jid']),key,'ContainerOf')
        for tag in b['tag_jids']:insert_edge(db,key,bound(tag),'HasTag')
    elif case=='U8':
        a,bkey=bound(b['person1_jid']),bound(b['person2_jid']);node_record(db,a,'Person');node_record(db,bkey,'Person')
        if a==bkey:raise OracleAbort('duplicate_or_self_friendship')
        if db.execute("SELECT count(*) FROM edges WHERE type='Knows' AND ((source=? AND target=?) OR (source=? AND target=?))",(a,bkey,bkey,a)).fetchone()[0]:raise OracleAbort('duplicate_or_self_friendship')
        insert_edge(db,a,bkey,'Knows',creation_date=b['creation_date'])
    else:raise ValueError('Unknown update operation '+case)
    return None


def update_actions():
    ref=lambda value:{'$node':value}
    person=dict(person_id=8,first_name='Harper',last_name='North',birthday='1980-01-15',location_ip='192.0.2.8',browser='Firefox',gender='female',creation_date=200000,city_jid=ref('place:3'),emails=['harper@example.test'],languages=['English'],tag_jids=[ref('tag:1')],study_at=[dict(organization_jid=ref('organization:30'),year=2010)],work_at=[dict(organization_jid=ref('organization:10'),year=2011)])
    invalid=copy.deepcopy(person);invalid.update(person_id=9,emails=['duplicate@example.test']*2)
    membership=dict(forum_jid=ref('forum:20'),person_jid=ref('person:1'),join_date=200000)
    friendship=dict(person1_jid=ref('person:1'),person2_jid=ref('person:7'),creation_date=1003000)
    return [('U1',person),('U1',invalid),('U2',dict(person_jid=ref('person:5'),message_jid=ref('message:120'),creation_date=200000)),('U3',dict(person_jid=ref('person:5'),message_jid=ref('message:210'),creation_date=210000)),('U4',dict(forum_id=30,title='Continuation Forum',creation_date=220000,moderator_jid=ref('person:2'),tag_jids=[ref('tag:1')])),('U5',membership),('U5',membership),('U6',dict(message_id=300,content='A continuation benchmark post',image_file='',creation_date=1000000,location_ip='192.0.2.1',browser='Firefox',language='English',length=len('A continuation benchmark post'),author_jid=ref('person:1'),forum_jid=ref('forum:10'),country_jid=ref('place:10'),tag_jids=[ref('tag:1')])),('U7',dict(message_id=400,content='A new direct reply',creation_date=1001000,location_ip='192.0.2.2',browser='Firefox',length=len('A new direct reply'),author_jid=ref('person:2'),parent_jid=ref('message:100'),country_jid=ref('place:11'),tag_jids=[ref('tag:2')])),('U7',dict(message_id=410,content='A reply to a comment',creation_date=1002000,location_ip='192.0.2.4',browser='Firefox',length=len('A reply to a comment'),author_jid=ref('person:4'),parent_jid=ref('message:210'),country_jid=ref('place:10'),tag_jids=[])),('U8',friendship),('U8',friendship)]


def prepare(output,seed=42):
    output.mkdir(parents=True,exist_ok=False);graph=fixture(seed);write(output/'graph.json',graph);db=database(graph);rows=[]
    try:
        for case,params in parameters():
            before=snapshot(db);result=answer(db,case,params)
            if not result:raise AssertionError('Empty-only positive case '+case)
            rows.append(dict(request_id=len(rows),case_id='snb/'+case,walker=case,body=body_for(case,params),oracle_parameters=params,expected=result,expected_error=None,pre_state_sha256=digest(before),post_state_sha256=digest(snapshot(db)),post_state=snapshot(db),fresh_session=True,variant='positive'))
            (output/(case+'.reference.sql')).write_text(SQL[case]+'\n')
        params=dict(person=1,max_date=450);state=snapshot(db)
        rows.append(dict(request_id=len(rows),case_id='snb/IC2',walker='IC2',body=body_for('IC2',params),oracle_parameters=params,expected=answer(db,'IC2',params),expected_error=None,pre_state_sha256=digest(state),post_state_sha256=digest(state),post_state=state,fresh_session=True,variant='exclusive_max_date_boundary'))
        for boundary in [500,800]:
            case='IC5';params=dict(person=1,min_date=boundary);state=snapshot(db)
            rows.append(dict(request_id=len(rows),case_id='snb/IC5',walker=case,body=body_for(case,params),oracle_parameters=params,expected=answer(db,case,params),expected_error=None,pre_state_sha256=digest(state),post_state_sha256=digest(state),post_state=state,fresh_session=True,variant='exclusive_date_boundary'))
        negative=[('IC1',dict(person=1,first_name='NoSuchName')),('IC2',dict(person=1,max_date=-1)),('IC3',dict(person=1,country_x='France',country_y='France',start_date=90000000,duration_days=1)),('IC4',dict(person=1,start_date=90000000,duration_days=1)),('IC5',dict(person=1,min_date=90000000)),('IC6',dict(person=1,tag_name='NoSuchTag')),('IC7',dict(person=7)),('IC8',dict(person=7)),('IC9',dict(person=1,max_date=-1)),('IC10',dict(person=1,month=6)),('IC11',dict(person=1,country_name='NoSuchCountry',work_from_year=2010)),('IC12',dict(person=1,tag_class_name='NoSuchClass')),('IC13',dict(person=1,target=7)),('IC14',dict(person=1,target=7)),('IS2',dict(person=7)),('IS3',dict(person=7)),('IS7',dict(message=140))]
        for case,params in negative:
            before=snapshot(db);result=answer(db,case,params)
            rows.append(dict(request_id=len(rows),case_id='snb/'+case,walker=case,body=body_for(case,params),oracle_parameters=params,expected=result,expected_error=None,pre_state_sha256=digest(before),post_state_sha256=digest(snapshot(db)),post_state=snapshot(db),fresh_session=True,variant='negative_no_match'))
        for case,body in update_actions():
            before=snapshot(db);db.execute('BEGIN');error=None
            try:result=update(db,case,body);db.commit()
            except (OracleAbort,sqlite3.IntegrityError) as exception:
                db.rollback();result=None
                error=str(exception) if isinstance(exception,OracleAbort) else {'U1':'duplicate_person_component','U2':'duplicate_like','U3':'duplicate_like','U4':'duplicate_forum','U5':'duplicate_membership','U6':'duplicate_message','U7':'duplicate_message','U8':'duplicate_or_self_friendship'}[case]
            after=snapshot(db)
            if error and after!=before:raise AssertionError('SNB update rollback failed')
            rows.append(dict(request_id=len(rows),case_id='snb/'+case,walker=case,body=body,expected=result,expected_error=error,pre_state_sha256=digest(before),post_state_sha256=digest(after),post_state=after,fresh_session=True,variant='error_rollback' if error else 'positive_update'))
        for case,params in [('IS2',dict(person=1)),('IC12',dict(person=1,tag_class_name='Technology')),('IC13',dict(person=1,target=7))]:
            before=snapshot(db);rows.append(dict(request_id=len(rows),case_id='snb/'+case,walker=case,body=body_for(case,params),oracle_parameters=params,expected=answer(db,case,params),expected_error=None,pre_state_sha256=digest(before),post_state_sha256=digest(before),post_state=before,fresh_session=True,variant='after_updates'))
        with (output/'requests.jsonl').open('w') as file:
            for row in rows:file.write(json.dumps(row,sort_keys=True)+'\n')
        cases=sorted({r['case_id'] for r in rows})
        manifest=dict(seed=seed,request_seed=4242,read_operations=21,update_operations=8,requests=len(rows),cases=cases,native='pending',fresh_session='pending',restart='pending',rollback='native_pending',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),fixture_sha256=digest(graph),actions_sha256=hashlib.sha256((output/'requests.jsonl').read_bytes()).hexdigest(),scope='All29 v1 operations; positive reads, no-match branches, update state and partial-write rollback; not official SF/data-mix qualification',semantic_audit='SEMANTICS.md; IC12 counts distinct comments despite multi-tag parent; IS2 uses specified message-ID tie key; IC14=v1')
        write(output/'manifest.json',manifest);print(json.dumps({k:manifest[k] for k in ['read_operations','update_operations','requests','native']}))
    finally:db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seed',type=int,default=42);args=parser.parse_args();prepare(args.output,args.seed)

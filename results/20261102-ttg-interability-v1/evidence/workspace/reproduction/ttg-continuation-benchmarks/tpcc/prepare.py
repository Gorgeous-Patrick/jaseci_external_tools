"""Independent relational post-state/rollback oracle for five procedural ports.

The inherited Payment's upper-middle selection and abbreviated BC prefix are
retained as named legacy-subset behavior, not full TPC-C conformance.
"""
import argparse
import sys
sys.path.insert(0,str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from state_keys import wiki_key, edge_sort, root_edge
import ast
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3

HERE=Path(__file__).resolve().parent


def defaults():
    text=(HERE.parent/'vendor/local/tpcc/app.jac').read_text();result={}
    for name,body in re.findall(r'node (\w+) \{(.*?)\n\}',text,re.S):
        fields={}
        for field,value in re.findall(r'(\w+):\s*[^=\n]+\s*=\s*([^,;\n]+)',body):fields[field]=ast.literal_eval(value.strip())
        result[name]=fields
    return result


DEFAULTS=defaults()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def fixture(seed=42):
    nodes=[];edges=[]
    def node(key,kind,**data):nodes.append(dict(id=key,type=kind,fields={**copy.deepcopy(DEFAULTS[kind]),**data}))
    def edge(source,target,kind=None):edges.append(dict(source=source,target=target,type=kind))
    node('warehouse:1','Warehouse',w_id=1,w_name='Warehouse One',w_tax=.05,w_ytd=300000.)
    for district in range(1,11):
        dk=f'district:{district}';node(dk,'District',d_id=district,d_name=f'District {district}',d_tax=.02,d_ytd=30000.,d_next_o_id=3 if district<=2 else 1);edge('warehouse:1',dk)
        for customer in range(1,7):
            ck=f'customer:{district}:{customer}'
            node(ck,'Customer',c_id=customer,c_first=['Alex','Blair','Casey','Devon','Emery','Frankie'][customer-1],c_middle='OE',c_last='Brown' if customer<=4 else 'Green',c_since='2026-01-01T00:00:00Z',c_credit='BC' if customer==3 else 'GC',c_credit_lim=50000.,c_discount=.1,c_balance=-10.,c_ytd_payment=10.,c_payment_cnt=1,c_data='Existing customer data')
            edge(dk,ck)
            if district<=2 and customer<=2:
                ok=f'order:{district}:{customer}';node(ok,'Order',o_id=customer,o_c_id=customer,o_d_id=district,o_entry_d='2026-01-01T00:00:00Z',o_ol_cnt=2,new_order=True);edge(ck,ok,'Placed')
                for number,item in enumerate([1,6],1):
                    lk=f'line:{district}:{customer}:{number}';node(lk,'OrderLine',ol_number=number,ol_i_id=item,ol_supply_w_id=1,ol_quantity=2,ol_amount=float(2*item),ol_dist_info=f'District {district}');edge(ok,lk)
    for item in range(1,7):
        ik=f'item:{item}';sk=f'stock:{item}'
        node(ik,'Item',i_id=item,i_im_id=item,i_name=f'Item {item}',i_price=10.+item,i_data='ORIGINAL item data' if item%2 else 'Generic item data')
        node(sk,'Stock',s_i_id=item,s_quantity=15 if item<=5 else 8,s_dist=[f'District {i}' for i in range(1,11)],s_data='Stock data')
        edge('warehouse:1',sk);edge(sk,ik,'Of')
    rng=random.Random(seed);rng.shuffle(nodes);rng.shuffle(edges)
    return dict(nodes=nodes,edges=edges,root_attachment={'warehouse':['warehouse:1'],'catalog':[f'item:{i}' for i in range(1,7)]})


def database(graph):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    for kind,fields in DEFAULTS.items():
        columns=[]
        for name,value in fields.items():columns.append(name+' '+('INTEGER' if type(value) in [int,bool] else 'REAL' if type(value) is float else 'TEXT'))
        db.execute('CREATE TABLE "'+kind+'"'+'(_key TEXT PRIMARY KEY,_parent TEXT,'+','.join(columns)+')')
    db.execute('CREATE TABLE edges(src TEXT,dst TEXT,kind TEXT)')
    parents={e['target']:e['source'] for e in graph['edges'] if e['type']!='Of'}
    for row in graph['nodes']:insert(db,row['type'],row['id'],parents.get(row['id'],''),row['fields'])
    for edge in graph['edges']:db.execute('INSERT INTO edges VALUES (?,?,?)',(edge['source'],edge['target'],edge['type']))
    db.commit();return db


def insert(db,kind,key,parent,fields):
    names=['_key','_parent',*fields];values=[key,parent,*[json.dumps(v) if type(v) is list else v for v in fields.values()]]
    db.execute('INSERT INTO "'+kind+'"'+'('+','.join(names)+') VALUES ('+','.join('?' for _ in names)+')',values)


def one(db,kind,key):return db.execute('SELECT * FROM "'+kind+'"'+' WHERE _key=?',(key,)).fetchone()
def linked(db,kind,parent):return db.execute('SELECT * FROM "'+kind+'"'+' WHERE _parent=?',(parent,)).fetchall()
def logical(value):return value['$node'] if isinstance(value,dict) else value


def snapshot(db):
    nodes=[]
    for kind,fields in DEFAULTS.items():
        for row in db.execute('SELECT * FROM "'+kind+'"'+' ORDER BY _key'):
            data={name:json.loads(row[name]) if type(default) is list else bool(row[name]) if type(default) is bool else row[name] for name,default in fields.items()}
            nodes.append(dict(id=row['_key'],type=kind,fields=data))
    edges=[dict(source=r['src'],target=r['dst'],type=r['kind'],undirected=False) for r in db.execute('SELECT * FROM edges')]
    roots=[root_edge('catalog' if n['type']=='Item' else 'primary',n['id']) for n in nodes if n['type'] in ['Item','Warehouse']]
    return dict(nodes=sorted(nodes,key=lambda r:r['id']),edges=sorted(edges,key=edge_sort),root_edges=sorted(roots,key=edge_sort))



class OracleAbort(Exception):pass


def execute(db,case,body,timestamp):
    district=logical(body.get('district_id',''))
    if case=='NewOrder':
        d=one(db,'District',district);c=one(db,'Customer',logical(body['customer_id']));w=one(db,'Warehouse','warehouse:1');number=d['d_next_o_id']
        db.execute('UPDATE District SET d_next_o_id=d_next_o_id+1 WHERE _key=?',(district,))
        order=f"order:{d['d_id']}:{number}"
        values={**DEFAULTS['Order'],'o_id':number,'o_c_id':c['c_id'],'o_d_id':d['d_id'],'o_entry_d':timestamp,'o_ol_cnt':len(body['lines']),'o_all_local':int(all(x['supply_w_id']==1 for x in body['lines'])),'new_order':True}
        insert(db,'Order',order,c['_key'],values);db.execute("INSERT INTO edges VALUES (?,?,'Placed')",(c['_key'],order));total=0.
        for index,line in enumerate(body['lines'],1):
            item=one(db,'Item',logical(line['item_id']));stock=one(db,'Stock',logical(line['stock_id']))
            if item is None or stock is None:raise OracleAbort('item_not_found')
            quantity=line['quantity'];new=stock['s_quantity']-quantity;amount=round(quantity*item['i_price'],2);total+=amount
            db.execute('UPDATE Stock SET s_quantity=?,s_ytd=s_ytd+?,s_order_cnt=s_order_cnt+1,s_remote_cnt=s_remote_cnt+? WHERE _key=?',(new+91 if new<10 else new,quantity,int(line['supply_w_id']!=1),stock['_key']))
            key=f"line:{d['d_id']}:{number}:{index}";fields={**DEFAULTS['OrderLine'],'ol_number':index,'ol_i_id':item['i_id'],'ol_supply_w_id':line['supply_w_id'],'ol_quantity':quantity,'ol_amount':amount,'ol_dist_info':json.loads(stock['s_dist'])[d['d_id']-1]}
            insert(db,'OrderLine',key,order,fields);db.execute('INSERT INTO edges VALUES (?,?,NULL)',(order,key))
        # Relational expression independent of the native report construction.
        amount=db.execute('SELECT round(?*(1-c_discount)*(1+?+?),2) FROM Customer WHERE _key=?',(total,w['w_tax'],d['d_tax'],c['_key'])).fetchone()[0]
        return dict(success=True,o_id=number,total=amount,ol_cnt=len(body['lines']))
    if case in ['Payment','OrderStatus']:
        customer_key=logical(body.get('customer_id',''))
        if customer_key:c=one(db,'Customer',customer_key)
        else:
            parent=logical(body.get('c_district_id',district));matches=db.execute('SELECT * FROM Customer WHERE _parent=? AND c_last=? ORDER BY c_first',(parent,body['c_last'])).fetchall()
            if not matches:raise OracleAbort('customer_not_found')
            c=matches[len(matches)//2 if case=='Payment' else (len(matches)-1)//2]
        if case=='Payment':
            amount=body['amount'];d=one(db,'District',district);w=one(db,'Warehouse','warehouse:1')
            db.execute('UPDATE Warehouse SET w_ytd=w_ytd+?',(amount,));db.execute('UPDATE District SET d_ytd=d_ytd+? WHERE _key=?',(amount,district))
            data=(f"{c['c_id']},{d['d_id']},{w['w_id']},{str(round(amount,2))}|"+c['c_data'])[:500] if c['c_credit']=='BC' else c['c_data']
            db.execute('UPDATE Customer SET c_balance=c_balance-?,c_ytd_payment=c_ytd_payment+?,c_payment_cnt=c_payment_cnt+1,c_data=? WHERE _key=?',(amount,amount,data,c['_key']))
            count=db.execute('SELECT count(*) FROM History').fetchone()[0]+1;key=f'history:{count}'
            insert(db,'History',key,c['_key'],{**DEFAULTS['History'],'h_d_id':d['d_id'],'h_w_id':w['w_id'],'h_date':timestamp,'h_amount':amount,'h_data':w['w_name']+'    '+d['d_name']})
            db.execute('INSERT INTO edges VALUES (?,?,NULL)',(c['_key'],key));return dict(success=True,c_id=c['c_id'],amount=amount)
        order=db.execute('SELECT * FROM "Order" WHERE _parent=? ORDER BY o_id DESC LIMIT 1',(c['_key'],)).fetchone()
        if order is None:raise OracleAbort('order_not_found')
        lines=db.execute('SELECT ol_i_id AS item_id,ol_supply_w_id AS supply_warehouse_id,ol_quantity AS quantity,ol_amount AS amount,ol_delivery_d AS delivery_date FROM OrderLine WHERE _parent=? ORDER BY ol_number',(order['_key'],)).fetchall()
        return dict(customer=dict(id=c['c_id'],first=c['c_first'],middle=c['c_middle'],last=c['c_last'],balance=c['c_balance']),order=dict(id=order['o_id'],entry_date=order['o_entry_d'],carrier_id=order['o_carrier_id']),lines=[dict(row) for row in lines])
    if case=='Delivery':
        completed=[]
        for d in db.execute('SELECT * FROM District ORDER BY d_id').fetchall():
            order=db.execute('SELECT o.* FROM "Order" o JOIN Customer c ON c._key=o._parent WHERE c._parent=? AND o.new_order=1 ORDER BY o.o_id LIMIT 1',(d['_key'],)).fetchone()
            if order is None:continue
            db.execute('UPDATE "Order" SET new_order=0,o_carrier_id=? WHERE _key=?',(body['carrier_id'],order['_key']))
            db.execute('UPDATE OrderLine SET ol_delivery_d=? WHERE _parent=?',(timestamp,order['_key']))
            total=db.execute('SELECT sum(ol_amount) FROM OrderLine WHERE _parent=?',(order['_key'],)).fetchone()[0]
            db.execute('UPDATE Customer SET c_balance=c_balance+?,c_delivery_cnt=c_delivery_cnt+1 WHERE _key=?',(total,order['_parent']));completed.append(dict(district_id=d['d_id'],order_id=order['o_id']))
        return dict(delivered=completed)
    if case=='StockLevel':
        next_id=one(db,'District',district)['d_next_o_id']
        value=db.execute('SELECT count(DISTINCT s.s_i_id) FROM Stock s JOIN OrderLine l ON l.ol_i_id=s.s_i_id JOIN "Order" o ON o._key=l._parent JOIN Customer c ON c._key=o._parent WHERE c._parent=? AND o.o_id>=? AND o.o_id<? AND s.s_quantity<?',(district,next_id-20,next_id,body['threshold'])).fetchone()[0]
        return dict(low_stock_count=value)
    raise ValueError('Unsupported transaction '+case)


def actions():
    lines=[dict(item_id={'$node':f'item:{i}'},stock_id={'$node':f'stock:{i}'},supply_w_id=1,quantity=2) for i in range(1,6)]
    new=dict(district_id={'$node':'district:1'},customer_id={'$node':'customer:1:1'},lines=lines)
    invalid=copy.deepcopy(new);invalid['lines'][-1]['item_id']={'$node':'item:missing'}
    return [('NewOrder',new),('NewOrder',invalid),('Payment',dict(district_id={'$node':'district:1'},c_district_id={'$node':'district:1'},customer_id={'$node':'customer:1:1'},c_last='',amount=20.)),('Payment',dict(district_id={'$node':'district:1'},c_district_id={'$node':'district:1'},customer_id='',c_last='Brown',amount=25.)),('OrderStatus',dict(district_id={'$node':'district:1'},customer_id={'$node':'customer:1:1'},c_last='')),('OrderStatus',dict(district_id={'$node':'district:1'},customer_id='',c_last='Brown')),('Delivery',dict(carrier_id=3)),('StockLevel',dict(district_id={'$node':'district:1'},threshold=15)),('NewOrder',{**new,'lines':[dict(item_id={'$node':f'item:{i}'},stock_id={'$node':f'stock:{i}'},supply_w_id=1,quantity=2) for i in [1,2,3,4,6]]})]


def prepare(output,seed=42):
    output.mkdir(parents=True,exist_ok=False);graph=fixture(seed);write(output/'graph.json',graph);db=database(graph);rows=[]
    try:
        for index,(case,body) in enumerate(actions()):
            before=snapshot(db);db.execute('BEGIN');error=None
            try:result=execute(db,case,body,f'<mutation-time:{index}>');db.commit()
            except OracleAbort as exception:db.rollback();result=None;error=str(exception)
            after=snapshot(db)
            if error and before!=after:raise AssertionError('Partial NewOrder changes escaped rollback')
            rows.append(dict(request_id=index,case_id='tpcc/'+case,walker={'NewOrder':'new_order','Payment':'payment','OrderStatus':'order_status','Delivery':'delivery','StockLevel':'stock_level'}[case],body=body,expected=result,expected_error=error,pre_state_sha256=digest(before),post_state_sha256=digest(after),post_state=after,fresh_session=True))
        with (output/'requests.jsonl').open('w') as file:
            for row in rows:file.write(json.dumps(row,sort_keys=True)+'\n')
        write(output/'manifest.json',dict(seed=seed,request_seed=4242,transactions=5,requests=len(rows),native='pending',restart='pending',rollback='native_pending',oracle_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),legacy_subset=['NewOrder','Payment'],new_ports=['OrderStatus','Delivery','StockLevel'],scope='W1 small sequential procedural research fixture; not TPC-C qualification',exclusions=['W>1 remote suppliers','TPC-C concurrency/throughput/think-time rules','Full-scale 3000-customer/100000-item population'],legacy_deviations=['Payment upper-middle customer for even last-name matches retained from existing source','Payment BC prefix is abbreviated in inherited variant; OrderStatus new port uses specification lower-middle','Native unused t0 diagnostic fields require monotonic request-window validation, never used as DB timing']))
        print(json.dumps({'transactions':5,'requests':len(rows),'oracle_errors':[r['expected_error'] for r in rows if r['expected_error']]}))
    finally:db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=42);a=p.parse_args();prepare(a.output,a.seed)

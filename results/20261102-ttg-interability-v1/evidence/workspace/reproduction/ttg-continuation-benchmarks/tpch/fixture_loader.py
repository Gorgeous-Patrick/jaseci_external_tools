"""Native graph provisioning only; independent relational query oracle is separate."""
from dataclasses import fields
from pathlib import Path
from jaclang import JacRuntimeInterface as Jac

COLUMNS={
 'region':'r_regionkey r_name r_comment',
 'nation':'n_nationkey n_name n_regionkey n_comment',
 'supplier':'s_suppkey s_name s_address s_nationkey s_phone s_acctbal s_comment',
 'customer':'c_custkey c_name c_address c_nationkey c_phone c_acctbal c_mktsegment c_comment',
 'part':'p_partkey p_name p_mfgr p_brand p_type p_size p_container p_retailprice p_comment',
 'partsupp':'ps_partkey ps_suppkey ps_availqty ps_supplycost ps_comment',
 'orders':'o_orderkey o_custkey o_orderstatus o_totalprice o_orderdate o_orderpriority o_clerk o_shippriority o_comment',
 'lineitem':'l_orderkey l_partkey l_suppkey l_linenumber l_quantity l_extendedprice l_discount l_tax l_returnflag l_linestatus l_shipdate l_commitdate l_receiptdate l_shipinstruct l_shipmode l_comment'}
INTS=set('r_regionkey n_nationkey n_regionkey s_suppkey s_nationkey c_custkey c_nationkey p_partkey p_size ps_partkey ps_suppkey ps_availqty o_orderkey o_custkey o_shippriority l_orderkey l_partkey l_suppkey l_linenumber'.split())
FLOATS=set('s_acctbal c_acctbal p_retailprice ps_supplycost o_totalprice l_quantity l_extendedprice l_discount l_tax'.split())
KEYS={'region':['r_regionkey'],'nation':['n_nationkey'],'supplier':['s_suppkey'],'customer':['c_custkey'],'part':['p_partkey'],'partsupp':['ps_partkey','ps_suppkey'],'orders':['o_orderkey'],'lineitem':['l_orderkey','l_linenumber']}


def load_tables(directory: str,node_types: dict,edge_types: dict) -> dict:
    objects={};rows_by_table={};mapping={}
    for table,columns in COLUMNS.items():
        objects[table]={};rows_by_table[table]=[]
        names=columns.split(); native_fields={f.name for f in fields(node_types[table])}
        for line in (Path(directory)/(table+'.tbl')).read_text().splitlines():
            values=line.rstrip('|').split('|')
            if len(values)!=len(names):raise ValueError('Malformed '+table+' fixture row')
            row={name:(int(value) if name in INTS else float(value) if name in FLOATS else value.strip()) for name,value in zip(names,values)}
            key=':'.join(str(row[name]) for name in KEYS[table])
            if key in objects[table]:raise ValueError('Duplicate '+table+' key '+key)
            node=node_types[table](**{k:v for k,v in row.items() if k in native_fields})
            Jac.save(node);objects[table][key]=node;rows_by_table[table].append((key,row))
            mapping[table+':'+key]=Jac.object_ref(node)
    def link(source,target,kind):Jac.connect(source,target,edge_types[kind])
    for table in ['region','part']:
        for node in objects[table].values():Jac.connect(Jac.root(),node)
    for key,row in rows_by_table['nation']:link(objects['region'][str(row['n_regionkey'])],objects['nation'][key],'nation')
    for table,prefix in [('supplier','s'),('customer','c')]:
        for key,row in rows_by_table[table]:link(objects['nation'][str(row[prefix+'_nationkey'])],objects[table][key],table)
    for key,row in rows_by_table['partsupp']:
        link(objects['part'][str(row['ps_partkey'])],objects['partsupp'][key],'part_ps')
        link(objects['supplier'][str(row['ps_suppkey'])],objects['partsupp'][key],'supplier_ps')
    for key,row in rows_by_table['orders']:link(objects['customer'][str(row['o_custkey'])],objects['orders'][key],'orders')
    for key,row in rows_by_table['lineitem']:
        link(objects['orders'][str(row['l_orderkey'])],objects['lineitem'][key],'lineitem')
        link(objects['lineitem'][key],objects['partsupp'][str(row['l_partkey'])+':'+str(row['l_suppkey'])],'line_ps')
    if Jac.get_context().diagnostics:raise AssertionError('Native import permission diagnostics')
    return {'mapping':mapping,'counts':{table:len(values) for table,values in objects.items()}}

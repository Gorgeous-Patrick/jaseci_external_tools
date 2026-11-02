"""Ordered TPC-H comparison: only explicit equal ORDER-BY-key groups may permute."""
from decimal import Decimal, InvalidOperation
from itertools import groupby
import math

# Field and direction are the pinned query ORDER BY clauses. Financial ORDER BY
# keys have exact base-table DECIMAL scales, not an approximate global sort.
ORDER={
 1:[('l_returnflag',1,None),('l_linestatus',1,None)],
 2:[('s_acctbal',-1,2),('n_name',1,None),('s_name',1,None),('p_partkey',1,0)],
 3:[('revenue',-1,4),('o_orderdate',1,None)],4:[('o_orderpriority',1,None)],
 5:[('revenue',-1,4)],6:[],7:[('supp_nation',1,None),('cust_nation',1,None),('l_year',1,0)],
 8:[('o_year',1,0)],9:[('nation',1,None),('o_year',-1,0)],10:[('revenue',-1,4)],
 11:[('value',-1,2)],12:[('l_shipmode',1,None)],13:[('custdist',-1,0),('c_count',-1,0)],
 14:[],15:[('s_suppkey',1,0)],16:[('supplier_cnt',-1,0),('p_brand',1,None),('p_type',1,None),('p_size',1,0)],
 17:[],18:[('o_totalprice',-1,2),('o_orderdate',1,None)],19:[],20:[('s_name',1,None)],
 21:[('numwait',-1,0),('s_name',1,None)],22:[('cntrycode',1,None)]}
ABSOLUTE=Decimal('0.000001')
RELATIVE=Decimal('0.000000001')


def finite_number(value):
    if isinstance(value,bool) or not isinstance(value,(int,float,Decimal)):raise ValueError('Expected a numeric value, not a coercible string or bool')
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Non-finite number')
    return result


def scalar_equal(actual,expected):
    if expected is None:return actual is None
    if type(expected) is bool:return type(actual) is bool and actual is expected
    if isinstance(expected,(int,float,Decimal)):
        try:a,e=finite_number(actual),finite_number(expected)
        except (ValueError,InvalidOperation):return False
        # Integer reference outputs (identifiers/counts) are exact.
        if type(expected) is int:return a==e and a==a.to_integral_value()
        return abs(a-e)<=ABSOLUTE or abs(a-e)<=RELATIVE*max(abs(a),abs(e))
    return type(actual) is type(expected) and actual==expected


def order_key(number,row):
    result=[]
    for field,direction,scale in ORDER[number]:
        value=row[field]
        if scale is not None:
            value=finite_number(value).quantize(Decimal(1).scaleb(-scale))
            if direction<0:value=-value
        elif direction<0:raise ValueError('Descending textual key must have an explicit comparator')
        result.append(value)
    return tuple(result)


def rows_equal(actual,expected,columns):
    return set(actual)==set(columns) and all(scalar_equal(actual[name],expected[name]) for name in columns)


def injective_match(actual,candidates,columns):
    """Bipartite matching preserves duplicate cardinality within one legal tie."""
    assigned={}
    def place(index,seen):
        for candidate,row in enumerate(candidates):
            if candidate in seen or not rows_equal(actual[index],row,columns):continue
            seen.add(candidate)
            if candidate not in assigned or place(assigned[candidate],seen):
                assigned[candidate]=index;return True
        return False
    return all(place(index,set()) for index in range(len(actual)))


def compare(number,actual,reference):
    columns=reference['columns']
    expected=[dict(zip(columns,row)) for row in reference['rows']]
    if isinstance(actual,dict):actual=[actual]
    if not isinstance(actual,list) or not all(isinstance(row,dict) for row in actual):raise AssertionError('Query report must be rows or the declared scalar-row dict')
    if len(actual)!=len(expected):raise AssertionError('Row count mismatch')
    for row in actual:
        if set(row)!=set(columns):raise AssertionError('Result columns differ')
    actual_keys=[order_key(number,row) for row in actual]
    expected_keys=[order_key(number,row) for row in expected]
    if actual_keys!=sorted(actual_keys):raise AssertionError('ORDER BY violated')
    if actual_keys!=expected_keys:raise AssertionError('Ordered key/multiplicity mismatch')
    start=0
    for key,group in groupby(expected_keys):
        count=len(list(group));candidates=expected[start:start+count]
        boundary=reference.get('boundary_ties')
        if boundary and start+count==len(expected):
            candidates=[dict(zip(columns,row)) for row in boundary['eligible_rows']]
            if any(order_key(number,row)!=key for row in candidates):raise AssertionError('Untrusted boundary tie oracle')
        if not injective_match(actual[start:start+count],candidates,columns):raise AssertionError('Semantic values/duplicates differ within ordered tie group')
        start+=count
    return {'passed':True,'rows':len(actual),'ordering':'Explicit ORDER BY sequence; permutations only within equal declared keys','absolute_tolerance':str(ABSOLUTE),'relative_tolerance':str(RELATIVE),'null_equals_zero':False}

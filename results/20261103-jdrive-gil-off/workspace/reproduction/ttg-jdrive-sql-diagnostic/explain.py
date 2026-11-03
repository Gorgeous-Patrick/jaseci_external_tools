"""Inline diagnostic EXPLAIN in the actual recapture connection/transaction."""
import base64
import json
import math
from capture import require


def number(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'Missing/invalid server-reported plan time')
    return value


def plan_nodes(plan, path='Plan'):
    result = [dict(path=path, node_type=plan['Node Type'],
                   estimated_rows=plan.get('Plan Rows'), actual_rows_per_loop=plan.get('Actual Rows'),
                   actual_loops=plan.get('Actual Loops'),
                   buffers={key: value for key, value in plan.items() if key.endswith(' Blocks')})]
    for index, child in enumerate(plan.get('Plans', [])):
        result.extend(plan_nodes(child, path + '/Plans/' + str(index)))
    return result


def inline(connection, original_sql, params, wire, state, timeout_ms=30000):
    """ACTIVE caller guard excludes recursion; preserve actual transaction/state."""
    from jaclang.data.pgwire import _named_to_positional, _encode_param
    sql, args = _named_to_positional(original_sql, params)
    require(sql == wire['positional_sql'], 'Inline selected SQL changed')
    actual = [None if value is None else base64.b64encode(_encode_param(value)).decode('ascii')
              for value in args]
    require(actual == wire['parameters_base64'], 'Original parameters differ from actual Bind packet')
    require(type(timeout_ms) is int and 1 <= timeout_ms <= 60000, 'Bounded timeout required')
    original_timeout = dict(state['settings'])['statement_timeout']
    results = []
    connection.run('SET LOCAL statement_timeout = ' + str(timeout_ms))
    try:
        for repetition in (0, 1):
            rows = connection.run('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + original_sql, **params)
            require(len(rows) == 1 and len(rows[0]) == 1, 'Unexpected EXPLAIN result shape')
            plan = json.loads(rows[0][0]) if isinstance(rows[0][0], str) else rows[0][0]
            require(isinstance(plan, list) and len(plan) == 1 and 'Plan' in plan[0], 'Missing actual plan')
            value = plan[0]
            results.append(dict(repetition=repetition,
                cache_regime='First after census' if repetition == 0 else 'Immediate repeated EXPLAIN',
                planning_ms=number(value['Planning Time']), execution_ms=number(value['Execution Time']),
                nodes=plan_nodes(value['Plan']), full_plan=plan))
    finally:
        connection.run("SELECT set_config('statement_timeout', :value, true)", value=original_timeout)
    return dict(kind='same_connection_pre_statement_explain', provisional=True,
                transaction='Same connection/transaction; isolation captured; controlled unchanged graph',
                actual_parameters_verified=True, repetitions=results, primary_measurement=False,
                definition='Server EXPLAIN times; separate from primary client protocol wall',
                buffers='Per-node counters are inclusive; never sum parent and child counters')

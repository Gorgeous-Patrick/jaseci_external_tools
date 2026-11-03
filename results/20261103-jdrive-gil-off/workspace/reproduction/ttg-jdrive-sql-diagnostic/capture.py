"""Diagnostic-only selected pre-send SQL/Bind capture; install after release."""
import base64
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import struct
import threading
import uuid

ACTIVE = ContextVar('ttg_diagnostic_capture', default=False)
LOCK = threading.Lock()
COUNTS = {}
ANCHORS = ('SELECT id,seq,kind,arch_type,arch_module,root_id,src,dst,undirected,props '
           'FROM anchors ORDER BY seq,id')
INDEXES = ("SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes "
           "WHERE schemaname='public' ORDER BY tablename,indexname")
STATISTICS = ("SELECT schemaname,tablename,attname,null_frac,avg_width,n_distinct,correlation,"
              "most_common_vals::text,most_common_freqs::text,histogram_bounds::text "
              "FROM pg_stats WHERE schemaname='public' AND tablename IN ('anchors','graph_types') "
              "ORDER BY tablename,attname")
RELATIONS = ("SELECT c.relname,c.reltuples,c.relpages,s.n_live_tup,s.n_dead_tup,"
             "s.last_analyze::text,s.last_autoanalyze::text,s.n_mod_since_analyze,s.analyze_count,s.autoanalyze_count "
             "FROM pg_class c JOIN pg_stat_all_tables s ON s.relid=c.oid "
             "WHERE s.schemaname='public' AND c.relname IN ('anchors','graph_types') ORDER BY c.relname")
GRAPH_TYPES = 'SELECT type_name,ancestor FROM graph_types ORDER BY type_name,ancestor'
CONSTRAINTS = ("SELECT c.relname,k.conname,k.contype,pg_get_constraintdef(k.oid) FROM pg_constraint k "
               "JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
               "WHERE n.nspname='public' AND c.relname IN ('anchors','graph_types') ORDER BY c.relname,k.conname")
CONTEXT = ("SELECT current_database(),current_user,pg_backend_pid(),"
           "current_setting('transaction_isolation'),current_setting('transaction_read_only'),"
           "txid_current_snapshot()::text")
SETTINGS = ("SELECT name,setting FROM pg_settings WHERE name IN "
            "('server_version_num','search_path','row_security','enable_seqscan',"
            "'enable_indexscan','enable_bitmapscan','enable_hashjoin','enable_mergejoin',"
            "'enable_nestloop','jit','jit_above_cost','jit_inline_above_cost','jit_optimize_above_cost','work_mem','random_page_cost','effective_cache_size',"
            "'default_statistics_target','plan_cache_mode','standard_conforming_strings',"
            "'client_encoding','statement_timeout') ORDER BY name")


def require(value, message):
    if not value:
        raise ValueError(message)


def default(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    raise TypeError('Unsupported diagnostic state value: ' + type(value).__name__)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Reader:
    def __init__(self, data):
        self.data = data
        self.position = 0

    def take(self, size):
        require(size >= 0 and self.position + size <= len(self.data), 'Truncated protocol field')
        result = self.data[self.position:self.position + size]
        self.position += size
        return result

    def integer(self, size):
        return int.from_bytes(self.take(size), 'big', signed=True)

    def string(self):
        end = self.data.find(b'\0', self.position)
        require(end >= self.position, 'Unterminated protocol string')
        result = self.take(end - self.position)
        self.take(1)
        return result.decode('utf-8', errors='strict')

    def finish(self):
        require(self.position == len(self.data), 'Unexpected trailing protocol fields')


def decode_packet(packet):
    """Accept only the pinned native unnamed, text-format P/B/D/E/S protocol."""
    reader = Reader(packet)
    frames = []
    while reader.position < len(packet):
        kind = reader.take(1).decode('ascii')
        size = reader.integer(4)
        require(size >= 4, 'Invalid frame length')
        frames.append((kind, reader.take(size - 4)))
    require([kind for kind, _ in frames] == list('PBDES'), 'Unexpected native statement framing')
    parse = Reader(frames[0][1])
    require(parse.string() == '', 'Named statement is outside this diagnostic contract')
    sql = parse.string()
    require(parse.integer(2) == 0, 'Explicit parameter OIDs require a reviewed extension')
    parse.finish()
    bind = Reader(frames[1][1])
    require(bind.string() == bind.string() == '', 'Named portal/statement is unsupported')
    require(bind.integer(2) == 0, 'Binary/mixed parameter formats are unsupported')
    count = bind.integer(2)
    require(count >= 0, 'Invalid Bind parameter count')
    values = []
    for _ in range(count):
        size = bind.integer(4)
        require(size >= -1, 'Invalid parameter length')
        values.append(None if size == -1 else base64.b64encode(bind.take(size)).decode('ascii'))
    require(bind.integer(2) == 0, 'Nondefault result formats are unsupported')
    bind.finish()
    require(frames[2][1] == b'P\0' and frames[3][1] == b'\0' + struct.pack('!i', 0)
            and frames[4][1] == b'', 'Unexpected describe/execute/sync payload')
    return dict(positional_sql=sql, parameter_format='text', parameters_base64=values,
                packet_sha256=digest(packet), packet_base64=base64.b64encode(packet).decode('ascii'))


def before_send(connection, original_sql, positional_sql, params, packet):
    """Called by a disclosed copied-driver overlay immediately before send."""
    if ACTIVE.get() or not os.environ.get('TTG_DIAG_SELECTION'):
        return
    import continuation_probe as probe
    from sql_reconciliation import fingerprint
    from jaclang.data.pgwire import _named_to_positional
    request, role, executor = probe.binding()
    selection_path = Path(os.environ['TTG_DIAG_SELECTION'])
    selection_bytes = selection_path.read_bytes()
    selection = json.loads(selection_bytes)
    require(selection.get('purpose') == 'matched_jdrive_read_only_diagnostic', 'Wrong selection purpose')
    targets = selection['targets']
    require(1 <= len(targets) <= 8, 'Selection must remain bounded')
    matched = [target for target in targets if target['config_id'] == os.environ['TTG_DIAG_CONFIG_ID']
               and target['request'] == request and str(target['generation']) ==
               str(probe.BASE['TTG_PERF_SERVER_GENERATION']) and target['role'] == role
               and target['fingerprint'] == fingerprint(positional_sql)]
    if not matched:
        return
    require(len(matched) == 1, 'Ambiguous selected query')
    target = matched[0]
    require(positional_sql == target['sql'], 'Selected SQL differs from audited primary target')
    require(target['read_only_source_reviewed'] is True, 'Read-only source proof required')
    require(positional_sql.lstrip().upper().startswith(('SELECT ', 'WITH ')), 'Data SELECT required')
    key = (str(selection_path), target['target_id'], os.getpid())
    with LOCK:
        COUNTS[key] = COUNTS.get(key, 0) + 1
        occurrence = COUNTS[key]
    if occurrence != target['occurrence']:
        return
    token = ACTIVE.set(True)
    try:
        parsed = decode_packet(packet)
        require(parsed['positional_sql'] == positional_sql, 'Parse SQL differs from selected driver SQL')
        rewritten, names = _named_to_positional(original_sql, {name: name for name in params})
        require(rewritten == positional_sql and len(names) == len(parsed['parameters_base64']),
                'Named-to-wire parameter lineage differs')
        # These are disclosed diagnostic setup SELECTs in this same connection
        # and transaction. They may warm buffers; no cold-cache claim is made.
        state = dict(context=connection.run(CONTEXT), settings=connection.run(SETTINGS),
                     indexes=connection.run(INDEXES), constraints=connection.run(CONSTRAINTS), anchors=connection.run(ANCHORS),
                     graph_types=connection.run(GRAPH_TYPES), statistics=connection.run(STATISTICS), relations=connection.run(RELATIONS))
        from explain import inline
        plans = inline(connection, original_sql, params, parsed, state)
        state['statistics_after_explain'] = connection.run(STATISTICS)
        state['relations_after_explain'] = connection.run(RELATIONS)
        output = Path(os.environ['TTG_DIAG_OUTPUT'])
        output.mkdir(parents=True, exist_ok=True)
        capture = dict(statistics_freshness='pg_stats/planner estimates and cumulative pg_stat_all_tables observed before selected send; counters may lag and may be cached within transaction, not synchronous modification counts', kind='exact_matched_recapture', target=target, request=request,
                       role=role, executor=executor, pid=os.getpid(),
                       generation=probe.BASE['TTG_PERF_SERVER_GENERATION'],
                       database=connection.database, original_sql=original_sql,
                       original_sql_sha256=digest(original_sql.encode()),
                       parameter_names=names, wire=parsed, state=state,
                       explain=plans, acceptance='provisional_until_full_native_oracles',
                       selection=dict(path=str(selection_path), sha256=digest(selection_bytes)),
                       context_refs=selection['context_refs'],
                       capture_position='Before actual selected send; same-connection census',
                       cache_regime='After diagnostic census; not a cold-cache observation',
                       primary_instance_parameters=False)
        name = f"{target['target_id']}-pid{os.getpid()}.json"
        with (output / name).open('x') as stream:
            json.dump(capture, stream, default=default, indent=2)
            stream.write('\n')
    finally:
        ACTIVE.reset(token)

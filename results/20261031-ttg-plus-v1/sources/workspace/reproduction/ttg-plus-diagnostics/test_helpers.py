"""Pure packet/overlay checks; run only after the independent audit quiet signal."""
import base64
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from capture import decode_packet
from explain import inline, number
from overlay import transform


def frame(kind, value):
    return kind.encode() + struct.pack('!i', len(value) + 4) + value


def packet(values=(b'abc', None, b''), formats=0):
    bind = b'\0\0' + struct.pack('!hh', formats, len(values))
    for value in values:
        bind += struct.pack('!i', -1 if value is None else len(value))
        if value is not None:
            bind += value
    bind += b'\0\0'
    return (frame('P', b'\0SELECT $1,$2,$3\0\0\0') + frame('B', bind) +
            frame('D', b'P\0') + frame('E', b'\0\0\0\0\0') + frame('S', b''))


class PacketTests(unittest.TestCase):
    def test_exact_values_null_and_empty(self):
        value = decode_packet(packet())
        self.assertEqual(value['parameters_base64'], [base64.b64encode(b'abc').decode(), None, ''])
        self.assertEqual(base64.b64decode(value['packet_base64']), packet())

    def test_repeated_values_and_order(self):
        value = decode_packet(packet((b'2', b'2', b'1')))
        self.assertEqual([base64.b64decode(x) for x in value['parameters_base64']], [b'2', b'2', b'1'])

    def test_binary_format_rejected(self):
        with self.assertRaises(ValueError):
            decode_packet(packet(formats=1))

    def test_every_truncated_prefix_rejected(self):
        raw = packet()
        for end in range(len(raw)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                decode_packet(raw[:end])

    def test_extra_frame_rejected(self):
        with self.assertRaises(ValueError):
            decode_packet(packet() + frame('S', b''))

    def test_unexpected_execute_limit_rejected(self):
        raw = packet().replace(frame('E', b'\0\0\0\0\0'), frame('E', b'\0\0\0\0\1'))
        with self.assertRaises(ValueError):
            decode_packet(raw)


class OverlayTests(unittest.TestCase):
    def test_only_declared_insertions(self):
        source = ('import continuation_probe as _perf_sink;\n'
                  '        _perf_send_ns = _perf_clock.perf_counter_ns();\n')
        result = transform(source)
        self.assertIn('before_send(self, sql, pos_sql, params, _perf_frame)', result)
        self.assertEqual(result.replace('import capture as _ttg_diagnostic;\n', '').replace(
            '        _ttg_diagnostic.before_send(self, sql, pos_sql, params, _perf_frame);\n', ''), source)

    def test_wrong_or_duplicate_boundary_rejected(self):
        for source in ('', '        _perf_send_ns = _perf_clock.perf_counter_ns();\n' * 2):
            with self.assertRaises(ValueError):
                transform(source)


class InlineTests(unittest.TestCase):
    def fake_module(self):
        return SimpleNamespace(_named_to_positional=lambda sql, params: ('SELECT $1', [params['x']]),
                               _encode_param=lambda value: value.encode())

    def test_same_connection_two_plans_timeout_restored_no_transaction_replacement(self):
        calls = []
        class Connection:
            def run(self, sql, **params):
                calls.append((sql, params))
                if sql.startswith('EXPLAIN '):
                    return [([{'Planning Time':.1,'Execution Time':.2,
                        'Plan':{'Node Type':'Result','Actual Rows':1,'Actual Loops':1,'Shared Hit Blocks':2}}],)]
                return []
        with patch.dict(sys.modules, {'jaclang.data.pgwire':self.fake_module()}):
            result = inline(Connection(), 'SELECT :x', {'x':'abc'},
                {'positional_sql':'SELECT $1','parameters_base64':['YWJj']}, {'settings':[['statement_timeout','0']]})
        self.assertEqual(len(result['repetitions']), 2)
        self.assertTrue(result['provisional'])
        self.assertEqual(sum(sql.startswith('EXPLAIN ') for sql,_ in calls), 2)
        self.assertFalse(any(sql.startswith(('BEGIN','COMMIT','ROLLBACK')) for sql,_ in calls))
        self.assertEqual(calls[-1][1], {'value':'0'})

    def test_wrong_bind_rejected_before_any_query(self):
        class Connection:
            def run(self, *args, **kwargs):
                raise AssertionError('No SQL should run for mismatched Bind')
        with patch.dict(sys.modules, {'jaclang.data.pgwire':self.fake_module()}), self.assertRaises(ValueError):
            inline(Connection(), 'SELECT :x', {'x':'wrong'},
                {'positional_sql':'SELECT $1','parameters_base64':['YWJj']}, {'settings':[['statement_timeout','0']]})

    def test_invalid_server_times_rejected(self):
        for value in (True, None, -1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                number(value)


if __name__ == '__main__':
    unittest.main()

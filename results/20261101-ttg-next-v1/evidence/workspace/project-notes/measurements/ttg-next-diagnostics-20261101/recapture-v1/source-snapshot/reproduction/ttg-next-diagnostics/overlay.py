"""Pure targeted transform for a NEW copied DIRECT driver, never primary source."""


def transform(source):
    from capture import require
    marker = '        _perf_send_ns = _perf_clock.perf_counter_ns();\n'
    require(source.count(marker) == 1, 'Pinned DIRECT pre-send position changed')
    import_marker = 'import continuation_probe as _perf_sink;\n'
    require(source.count(import_marker) == 1, 'Pinned DIRECT sink import changed')
    source = source.replace(import_marker, import_marker + 'import capture as _ttg_diagnostic;\n', 1)
    return source.replace(marker,
        '        _ttg_diagnostic.before_send(self, sql, pos_sql, params, _perf_frame);\n' + marker, 1)

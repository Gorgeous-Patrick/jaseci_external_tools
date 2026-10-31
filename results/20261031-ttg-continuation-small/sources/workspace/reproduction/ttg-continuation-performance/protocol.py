"""Protocol diagnostics for the NEW experiment; no sockets or runtime imports.

The final immutable runtime needs its own disclosed direct-boundary overlay.
This module validates packets/counters offline, outside measured app intervals.
"""
import struct


def backend_pid(payload: bytes) -> int:
    """Read BackendKeyData's process ID; never retain its cancellation secret."""
    if len(payload) != 8:
        raise ValueError('BackendKeyData must contain exactly eight bytes')
    pid = struct.unpack('!I', payload[:4])[0]
    if pid <= 0:
        raise ValueError('Invalid PostgreSQL backend PID')
    return pid


def frames(packet: bytes):
    """Parse an already-built frontend packet BEFORE starting a send clock."""
    offset = 0
    result = []
    while offset < len(packet):
        if len(packet) - offset < 5:
            raise ValueError('Truncated frontend frame header')
        size = struct.unpack('!I', packet[offset + 1:offset + 5])[0]
        if size < 4 or offset + 1 + size > len(packet):
            raise ValueError('Invalid frontend frame size')
        result.append((chr(packet[offset]), packet[offset + 5:offset + 1 + size]))
        offset += 1 + size
    return result


def packet_diagnostics(packet: bytes):
    parsed = frames(packet)
    return dict(frontend_types=[kind for kind, _ in parsed],
                sync_messages=sum(kind == 'S' for kind, _ in parsed),
                query_messages=sum(kind == 'Q' for kind, _ in parsed),
                execute_messages=sum(kind == 'E' for kind, _ in parsed),
                sent_bytes=len(packet))


def response_diagnostics(messages):
    """Separate diagnostic mode only; primary counters belong in C/D/Z branches."""
    result = dict(command_complete=0, data_rows=0, data_row_payload_bytes=0,
                  ready_messages=0, error_messages=0, received_frame_bytes=0)
    for kind, payload in messages:
        result['received_frame_bytes'] += 5 + len(payload)
        if kind == 'C':
            result['command_complete'] += 1
        elif kind == 'D':
            result['data_rows'] += 1
            result['data_row_payload_bytes'] += len(payload)
        elif kind == 'Z':
            result['ready_messages'] += 1
        elif kind == 'E':
            result['error_messages'] += 1
    return result

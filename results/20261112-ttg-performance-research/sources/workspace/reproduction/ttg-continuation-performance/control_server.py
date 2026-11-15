"""Loopback-only explicit post-response drain; instantiated by the harness."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import continuation_probe as probe


def start(port):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                if self.path!='/drain': raise ValueError('Unknown control endpoint')
                origin=self.headers.get('X-TTG-Perf-Drain-Request')
                if not origin: raise ValueError('Missing drain request identity')
                result=probe.drain_after_response(origin)
                status=200
            except Exception as error:
                result=dict(passed=False,error=f'{type(error).__name__}: {error}')
                status=500
            raw=json.dumps(result).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True,name='perf-control').start()
    return server

"""Independent post-response drain channel; never runs inside app dispatch."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import driver_probe

def start(port, observed=True):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            rid = self.headers.get('X-TTG-Perf-Drain-Request')
            if observed:
                result = driver_probe.drain_request(rid)
            else:
                # Fully uninstrumented application path. This isolated process
                # serves one sequential workload; join only known runtime worker
                # names, after its HTTP response has been read by the client.
                threads = [t for t in threading.enumerate() if
                    '_prefetch_worker' in t.name or '_signal_done_after_all' in t.name]
                deadline = time.monotonic() + 30
                for thread in threads:
                    thread.join(max(0, deadline - time.monotonic()))
                result = {'request': rid, 'pending': sum(t.is_alive() for t in threads),
                          'observed_threads': len(threads), 'uninstrumented': True}
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, name='TTGPerfControl', daemon=True).start()
    return server

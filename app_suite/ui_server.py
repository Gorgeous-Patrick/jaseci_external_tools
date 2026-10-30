#!/usr/bin/env python3
"""Serve suite frontends and proxy native Jac APIs on isolated loopback ports."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import urllib.error
import urllib.request

WEB = Path(__file__).resolve().parent / 'web'


def make_handler(app, backend, config):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/config.json':
                self.respond(200, 'application/json', json.dumps({'app': app, **config}).encode())
                return
            paths = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                     '/domains.js': ('domains.js', 'text/javascript'),
                     '/style.css': ('style.css', 'text/css')}
            entry = paths.get(self.path)
            if entry is None:
                self.respond(404, 'text/plain', b'Page not found')
                return
            self.respond(200, entry[1], (WEB / entry[0]).read_bytes())

        def do_POST(self):
            if not self.path.startswith('/api/'):
                self.respond(404, 'application/json', b'{"error":"Endpoint not found"}')
                return
            data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            headers = {'Content-Type': self.headers.get('Content-Type', 'application/json')}
            if self.headers.get('Authorization'):
                headers['Authorization'] = self.headers['Authorization']
            request = urllib.request.Request(backend + self.path[4:], data=data, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=180) as result:
                    self.respond(result.status, result.headers.get('Content-Type', 'application/json'), result.read())
            except urllib.error.HTTPError as error:
                self.respond(error.code, 'application/json', error.read())

        def respond(self, code, content_type, body):
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True)
    parser.add_argument('--backend', required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    handler = make_handler(args.app, args.backend, json.loads(args.config.read_text()))
    print(f'{args.app} frontend: http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler).serve_forever()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Tiny renamer-control webhook on the VPS (Tailscale only).

Endpoints
---------
    GET  /ping                  -> "ok"
    POST /restart-renamer       -> systemctl restart sooka-renamer.service
                                   (requires X-Renamer-Key matching the
                                    shared secret in ~/.hermes/.env
                                    RENAMER_WEBHOOK_SECRET)

Bind is 100.87.218.6:8060 (Tailscale IP) — unreachable from the public
internet, which keeps this safe without TLS on the wire.
"""
import json
import os
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET_FILE = '/home/ubuntu/.hermes/renamer_webhook_secret'
PORT = 8060


def _load_secret():
    if os.path.exists(SECRET_FILE):
        return open(SECRET_FILE).read().strip()
    # generate once and store
    s = os.urandom(24).hex()
    open(SECRET_FILE, 'w', encoding='utf-8').write(s)
    os.chmod(SECRET_FILE, 0o600)
    return s


SECRET = _load_secret()


class Handler(BaseHTTPRequestHandler):
    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_GET(self):
        if self.path == '/health':
            self._json({'ok': True})
            return
        self.send_error(404)

    def do_POST(self):
        auth = self.headers.get('X-Renamer-Secret', '')
        if auth != SECRET:
            self._json({'ok': False, 'error': 'unauthorized'}, status=401)
            return
        if self.path == '/restart-renamer':
            self._json(_restart_renamer())
            return
        self.send_error(404)


def _restart_renamer():
    subprocess.run(['systemctl', 'restart', 'sooka-renamer.service'],
                   timeout=30, capture_output=True)
    return {'ok': True, 'action': 'restarted sooka-renamer'}


if __name__ == '__main__':
    SERVER_IP = '100.87.218.6'   # VPS Tailscale IP
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.close()
    from http.server import HTTPServer
    httpd = HTTPServer(('100.87.218.6', PORT), Handler)   # tailscale only
    print('renamer webhook listening on http://%s:%d (tailscale-only)' % (SERVER_IP, PORT))
    httpd.serve_forever()

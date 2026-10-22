"""Минимальный HTTPS-приёмник для тестов отправителя (stdlib)."""
from __future__ import annotations

import json
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TLS = Path(__file__).parent / 'fixtures' / 'tls'


def cert_pem(name: str = 'server') -> str:
    return (TLS / f'{name}-cert.pem').read_text()


class FakeReceiver:
    """Принимает POST /v1/events; ``status`` — что отвечать (200, 401, 429…)."""

    def __init__(self, name: str = 'server', key: str = 'k1', port: int = 0):
        self.events: list[dict] = []
        self.auth: list[str] = []
        self.status = 200
        self.key = key
        owner = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
                owner.auth.append(self.headers.get('Authorization', ''))
                if self.headers.get('Authorization') != f'Bearer {owner.key}':
                    code = 401
                else:
                    code = owner.status
                if code == 200:
                    batch = json.loads(body)['events']
                    seen = {e['id'] for e in owner.events}
                    new = [e for e in batch if e['id'] not in seen]
                    owner.events += new
                    out = {'accepted': len(new), 'duplicates': len(batch) - len(new)}
                else:
                    out = {}
                data = json.dumps(out).encode()
                self.send_response(code)
                if code == 429:
                    self.send_header('Retry-After', '1')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer(('127.0.0.1', port), H)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(TLS / f'{name}-cert.pem', TLS / f'{name}-key.pem')
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.port = self.httpd.server_address[1]
        self.url = f'https://127.0.0.1:{self.port}'
        self._t = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._t.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class HungServer:
    """Принимает соединение и молчит."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(50)
        self.port = self.sock.getsockname()[1]
        self.url = f'https://127.0.0.1:{self.port}'
        self.conns = []
        self._t = threading.Thread(target=self._accept, daemon=True)
        self._t.start()

    def _accept(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.conns.append(c)

    def stop(self):
        self.sock.close()
        for c in self.conns:
            c.close()


def free_port() -> int:
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p

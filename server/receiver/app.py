"""Приёмник телеметрии Orthofill.

Ключ установки даёт только запись (POST /v1/events); ответ — только счётчики.
Чтение (страница, сводки, сырые события) — по паролю администратора.
Перед записью в базу — вырезание ФИО (вторая линия после программы)."""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hmac
import json
import ssl
from dataclasses import dataclass, field
from pathlib import Path

from aiohttp import web

from .limits import FailGuard, RateLimiter
from .scrub import scrub_event
from .store import Store

MAX_BODY = 1024 * 1024
MAX_EVENTS = 500
PAGE = Path(__file__).with_name('page.html')

STORE = web.AppKey('store', Store)
CFG = web.AppKey('cfg', object)
RATE = web.AppKey('rate', RateLimiter)
GUARD = web.AppKey('guard', FailGuard)


@dataclass
class ServerConfig:
    db: Path
    keys: set[str]
    admin_password: str
    retention_days: int = 180
    rate_per_min: int = 600
    fail_max: int = 10
    fail_window: float = 600.0
    block_seconds: float = 3600.0
    host: str = '0.0.0.0'
    port: int = 8443
    cert: Path | None = None
    key: Path | None = None
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: Path) -> 'ServerConfig':
        d = json.loads(Path(path).read_text(encoding='utf-8'))
        return cls(db=Path(d['db']), keys=set(d['keys']), admin_password=d['admin_password'],
                   retention_days=int(d.get('retention_days', 180)),
                   rate_per_min=int(d.get('rate_per_min', 600)),
                   host=d.get('host', '0.0.0.0'), port=int(d.get('port', 8443)),
                   cert=Path(d['cert']) if d.get('cert') else None,
                   key=Path(d['key']) if d.get('key') else None)


def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode('utf-8'), b.encode('utf-8'))


def _ip(request: web.Request) -> str:
    return request.remote or '?'


@web.middleware
async def guard_mw(request: web.Request, handler):
    ip = _ip(request)
    if request.app[GUARD].blocked(ip):
        return web.json_response({'error': 'blocked'}, status=403)
    wait = request.app[RATE].check(ip)
    if wait:
        return web.json_response({'error': 'rate'}, status=429,
                                 headers={'Retry-After': str(int(wait) + 1)})
    resp = await handler(request)
    resp.headers.setdefault('Cache-Control', 'no-store')
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    return resp


def _admin(request: web.Request) -> bool:
    auth = request.headers.get('Authorization', '')
    ok = False
    if auth.startswith('Basic '):
        try:
            _, _, pwd = base64.b64decode(auth[6:]).decode('utf-8').partition(':')
            ok = _eq(pwd, request.app[CFG].admin_password)
        except (binascii.Error, UnicodeDecodeError):
            ok = False
    if not ok:
        request.app[GUARD].fail(_ip(request))
    return ok


def _need_admin(request: web.Request):
    if not _admin(request):
        raise web.HTTPUnauthorized(headers={'WWW-Authenticate': 'Basic realm="orthofill"'})


async def post_events(request: web.Request) -> web.Response:
    auth = request.headers.get('Authorization', '')
    key = auth[7:] if auth.startswith('Bearer ') else ''
    if not key or not any(_eq(key, k) for k in request.app[CFG].keys):
        request.app[GUARD].fail(_ip(request))
        return web.json_response({'error': 'key'}, status=401)
    try:
        body = await request.read()
    except web.HTTPRequestEntityTooLarge:
        return web.json_response({'error': 'too large'}, status=413)
    try:
        events = json.loads(body)['events']
    except (ValueError, KeyError, TypeError):
        return web.json_response({'error': 'bad json'}, status=400)
    if not isinstance(events, list):
        return web.json_response({'error': 'bad json'}, status=400)
    if len(events) > MAX_EVENTS:
        return web.json_response({'error': 'too many'}, status=413)
    if not all(isinstance(e, dict) and isinstance(e.get('id'), str) and 0 < len(e['id']) <= 64
               for e in events):
        return web.json_response({'error': 'bad event'}, status=400)
    clean = [scrub_event(e) for e in events]
    accepted, dup = request.app[STORE].add('', clean)
    return web.json_response({'accepted': accepted, 'duplicates': dup})


def _int(request: web.Request, name: str, default: int) -> int:
    try:
        return int(request.query.get(name, default))
    except ValueError:
        return default


async def page(request: web.Request) -> web.Response:
    _need_admin(request)
    try:
        html = PAGE.read_text(encoding='utf-8')
    except OSError:
        html = '<!doctype html><meta charset="utf-8"><p>Страница не установлена.'
    return web.Response(text=html, content_type='text/html', headers={
        'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; "
                                   "style-src 'unsafe-inline'; connect-src 'self'; img-src data:"})


async def feed(request: web.Request) -> web.Response:
    _need_admin(request)
    st = request.app[STORE]
    return web.json_response({'events': st.feed(_int(request, 'since', 0)),
                              'last': st.last_rowid(), 'online': st.online()})


async def usage(request: web.Request) -> web.Response:
    _need_admin(request)
    return web.json_response({'days': request.app[STORE].usage(_int(request, 'days', 30))})


async def speed(request: web.Request) -> web.Response:
    _need_admin(request)
    return web.json_response({'rows': request.app[STORE].speed(_int(request, 'days', 30))})


async def raw_events(request: web.Request) -> web.StreamResponse:
    _need_admin(request)
    resp = web.StreamResponse(headers={'Content-Type': 'application/x-ndjson; charset=utf-8'})
    await resp.prepare(request)
    for e in request.app[STORE].events(request.query.get('type', ''), _int(request, 'since', 0)):
        await resp.write((json.dumps(e, ensure_ascii=False) + '\n').encode('utf-8'))
    await resp.write_eof()
    return resp


def make_app(cfg: ServerConfig) -> web.Application:
    app = web.Application(client_max_size=MAX_BODY, middlewares=[guard_mw])
    app[CFG] = cfg
    app[STORE] = Store(cfg.db)
    app[RATE] = RateLimiter(cfg.rate_per_min)
    app[GUARD] = FailGuard(cfg.fail_max, cfg.fail_window, cfg.block_seconds)
    app.router.add_post('/v1/events', post_events)
    app.router.add_get('/', page)
    app.router.add_get('/v1/feed', feed)
    app.router.add_get('/v1/usage', usage)
    app.router.add_get('/v1/speed', speed)
    app.router.add_get('/v1/events', raw_events)

    async def purge_daily(app):
        async def loop():
            while True:
                app[STORE].purge(cfg.retention_days)
                await asyncio.sleep(24 * 3600)
        task = asyncio.create_task(loop())
        yield
        task.cancel()
    app.cleanup_ctx.append(purge_daily)
    return app


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description='Приёмник телеметрии Orthofill')
    ap.add_argument('--config', default='/etc/orthofill-receiver/config.json')
    args = ap.parse_args(argv)
    cfg = ServerConfig.from_file(Path(args.config))
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cfg.cert, cfg.key)
    web.run_app(make_app(cfg), host=cfg.host, port=cfg.port, ssl_context=ctx,
                access_log=None)


if __name__ == '__main__':
    main()

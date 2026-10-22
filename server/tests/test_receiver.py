import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from receiver.app import ServerConfig, make_app
from receiver.store import Store

ROOT = Path(__file__).resolve().parents[2]
KEY = 'k-test-1'
PWD = 'admin-pass'


def _cfg(tmp_path, **kw):
    return ServerConfig(db=tmp_path / 'rx.db', keys={KEY}, admin_password=PWD, **kw)


def _run(cfg, fn):
    async def main():
        async with TestClient(TestServer(make_app(cfg))) as c:
            return await fn(c)
    return asyncio.run(main())


def _bearer(key=KEY):
    return {'Authorization': f'Bearer {key}'}


def _basic(pwd=PWD):
    return {'Authorization': 'Basic ' + base64.b64encode(f'admin:{pwd}'.encode()).decode()}


def _ev(i, event='ui', **kw):
    return {'id': f'id{i}', 'ts': datetime.now().isoformat(timespec='seconds'),
            'event': event, 'install': 'inst1', 'version': '0.4.0b1', **kw}


def test_accepts_batch(tmp_path):
    async def go(c):
        r = await c.post('/v1/events', json={'events': [_ev(1), _ev(2)]}, headers=_bearer())
        assert r.status == 200
        assert await r.json() == {'accepted': 2, 'duplicates': 0}
    _run(_cfg(tmp_path), go)


def test_duplicate_ids_ignored(tmp_path):
    async def go(c):
        await c.post('/v1/events', json={'events': [_ev(1), _ev(2)]}, headers=_bearer())
        r = await c.post('/v1/events', json={'events': [_ev(2), _ev(3)]}, headers=_bearer())
        assert await r.json() == {'accepted': 1, 'duplicates': 1}
    _run(_cfg(tmp_path), go)
    assert Store(tmp_path / 'rx.db').count() == 3


def test_wrong_key_401(tmp_path):
    async def go(c):
        r = await c.post('/v1/events', json={'events': [_ev(1)]}, headers=_bearer('чужой'.encode().hex()))
        assert r.status == 401
        r = await c.post('/v1/events', json={'events': [_ev(1)]})
        assert r.status == 401
    _run(_cfg(tmp_path), go)


def test_key_cannot_read(tmp_path):
    async def go(c):
        for path in ('/', '/v1/feed', '/v1/usage', '/v1/speed', '/v1/events'):
            r = await c.get(path, headers=_bearer())
            assert r.status == 401, path
    _run(_cfg(tmp_path), go)


def test_password_reads(tmp_path):
    async def go(c):
        await c.post('/v1/events', json={'events': [_ev(1)]}, headers=_bearer())
        r = await c.get('/v1/feed?since=0', headers=_basic())
        assert r.status == 200
        body = await r.json()
        assert body['events'][0]['id'] == 'id1' and body['last'] >= 1
        r = await c.get('/v1/events?type=ui', headers=_basic())
        lines = (await r.text()).splitlines()
        assert json.loads(lines[0])['event'] == 'ui'
    _run(_cfg(tmp_path), go)


def test_body_too_large_413(tmp_path):
    async def go(c):
        big = {'events': [_ev(1, pad='я' * 700_000)]}
        r = await c.post('/v1/events', json=big, headers=_bearer())
        assert r.status == 413
    _run(_cfg(tmp_path), go)


def test_too_many_events_413(tmp_path):
    async def go(c):
        r = await c.post('/v1/events', json={'events': [_ev(i) for i in range(501)]},
                         headers=_bearer())
        assert r.status == 413
    _run(_cfg(tmp_path), go)


def test_bad_json_400(tmp_path):
    async def go(c):
        r = await c.post('/v1/events', data=b'{not json', headers=_bearer())
        assert r.status == 400
        r = await c.post('/v1/events', json={'events': [{'no_id': 1}]}, headers=_bearer())
        assert r.status == 400
    _run(_cfg(tmp_path), go)


def test_rate_limit_429(tmp_path):
    async def go(c):
        codes = []
        for i in range(5):
            r = await c.post('/v1/events', json={'events': [_ev(i)]}, headers=_bearer())
            codes.append(r.status)
        assert codes[:3] == [200, 200, 200] and codes[3] == 429
        assert int(r.headers['Retry-After']) >= 1
    _run(_cfg(tmp_path, rate_per_min=3), go)


def test_bruteforce_blocks_ip(tmp_path):
    async def go(c):
        for _ in range(3):
            assert (await c.get('/v1/feed', headers=_basic('nope'))).status == 401
        r = await c.get('/v1/feed', headers=_basic())     # верный пароль, но IP уже в блоке
        assert r.status == 403
    _run(_cfg(tmp_path, fail_max=3), go)


def test_server_scrubs_again(tmp_path):
    async def go(c):
        await c.post('/v1/events', json={'events': [_ev(1, 'generate', raw='Иванова Мария Петровна, брекеты')]},
                     headers=_bearer())
    _run(_cfg(tmp_path), go)
    stored = json.dumps(Store(tmp_path / 'rx.db').feed(0), ensure_ascii=False)
    assert 'Иванова' not in stored and '‹ФИО›, брекеты' in stored


def _day(n):
    return (datetime.now() - timedelta(days=n)).isoformat(timespec='seconds')


def test_usage_by_day(tmp_path):
    s = Store(tmp_path / 'rx.db')
    s.add('i', [
        {'id': 'a', 'ts': _day(1), 'event': 'note_confirm', 'edited_lines': 0},
        {'id': 'b', 'ts': _day(1), 'event': 'note_confirm', 'edited_lines': 2},
        {'id': 'c', 'ts': _day(1), 'event': 'hint', 'action': 'accepted'},
        {'id': 'd', 'ts': _day(1), 'event': 'hint', 'action': 'shown'},
        {'id': 'e', 'ts': _day(0), 'event': 'note_confirm', 'edited_lines': 0},
        {'id': 'f', 'ts': _day(0), 'event': 'smartphrase', 'action': 'expanded'},
        {'id': 'g', 'ts': _day(0), 'event': 'habit', 'action': 'word'},
        {'id': 'h', 'ts': _day(0), 'event': 'add_search', 'chosen': True},
    ])
    u = {r['day']: r for r in s.usage(7)}
    d1, d0 = _day(1)[:10], _day(0)[:10]
    assert u[d1]['notes'] == 2 and u[d1]['hints'] == 1 and u[d1]['hints_shown'] == 1
    assert u[d1]['edited'] == 1
    assert u[d0]['phrases'] == 1 and u[d0]['habits'] == 1 and u[d0]['adds'] == 1


def test_speed_median_p95(tmp_path):
    s = Store(tmp_path / 'rx.db')
    evs = [{'id': f's{i}', 'ts': _day(0), 'event': 'session_start', 'version': '0.4.0b1',
            'install': 'i', 'startup_ms': ms} for i, ms in enumerate(range(100, 2100, 100))]
    evs += [{'id': f'p{i}', 'ts': _day(0), 'event': 'perf', 'version': '0.4.0b1', 'install': 'i',
             'preview_ms_med': 10.0 + i, 'preview_n': 3} for i in range(5)]
    s.add('i', evs)
    rows = {(r['metric']): r for r in s.speed(7)}
    st = rows['startup_ms']
    assert st['n'] == 20 and st['med'] == 1100 and st['p95'] == 2000 and st['version'] == '0.4.0b1'
    assert rows['preview_ms']['med'] == 12.0


def test_purge_old(tmp_path):
    s = Store(tmp_path / 'rx.db')
    s.add('i', [{'id': 'old', 'ts': _day(200), 'event': 'ui'}, {'id': 'new', 'ts': _day(1), 'event': 'ui'}])
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(timespec='seconds')
    s._db.execute("UPDATE events SET received = ? WHERE id = 'old'", (old,))
    s._db.commit()
    assert s.purge(180) == 1 and s.count() == 1


def test_scrub_copy_identical():
    for name in ('scrub.py', 'names_ru.txt'):
        assert (ROOT / 'orthofill' / name).read_bytes() == (ROOT / 'server' / 'receiver' / name).read_bytes(), name


def test_post_response_has_only_counts(tmp_path):
    async def go(c):
        r = await c.post('/v1/events', json={'events': [_ev(1)]}, headers=_bearer())
        assert set((await r.json()).keys()) == {'accepted', 'duplicates'}
    _run(_cfg(tmp_path), go)

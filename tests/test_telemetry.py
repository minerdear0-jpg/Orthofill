import json
import time

import pytest

from orthofill.telemetry import Telemetry, TelemetryConfig, load_config
from telemetry_server import FakeReceiver, HungServer, cert_pem, free_port


def _cfg(url, key='k1', cert=None):
    return TelemetryConfig(url=url, key=key, cert=cert or cert_pem())


def _fast(t: Telemetry) -> Telemetry:
    t.flush_every = 0.05
    t.backoff_min = 0.05
    t.backoff_max = 0.2
    t.timeout = 2.0
    return t


def _wait(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def rx():
    r = FakeReceiver()
    yield r
    r.stop()


def test_sends_batch(rx, tmp_path):
    t = _fast(Telemetry(_cfg(rx.url), tmp_path))
    t.start()
    for i in range(3):
        t.put({'event': 'x', 'n': i})
    assert _wait(lambda: len(rx.events) == 3)
    assert all(e['id'] for e in rx.events) and rx.auth[0] == 'Bearer k1'
    assert _wait(lambda: t.status().sent == 3 and t.status().queued == 0)
    assert t.status().error == '' and t.status().last_ok
    t.close()


def test_spool_survives_restart(rx, tmp_path):
    dead = f'https://127.0.0.1:{free_port()}'
    t = _fast(Telemetry(_cfg(dead), tmp_path))
    t.start()
    for i in range(5):
        t.put({'event': 'x', 'n': i})
    t.close()
    assert not rx.events
    t2 = _fast(Telemetry(_cfg(rx.url), tmp_path))
    assert t2.status().queued == 5
    t2.start()
    assert _wait(lambda: len(rx.events) == 5)
    assert sorted(e['n'] for e in rx.events) == [0, 1, 2, 3, 4]
    t2.close()


def test_hung_server_does_not_block(tmp_path):
    hs = HungServer()
    t = _fast(Telemetry(_cfg(hs.url), tmp_path))
    t.timeout = 10.0
    t.start()
    time.sleep(0.2)                     # отправка уже висит
    start = time.perf_counter()
    for i in range(1000):
        t.put({'event': 'x', 'n': i})
    assert time.perf_counter() - start < 0.05
    start = time.perf_counter()
    t.close()
    assert time.perf_counter() - start < 0.6
    hs.stop()
    t2 = Telemetry(_cfg(hs.url), tmp_path)
    assert t2.status().queued == 1000   # ничего не потеряно


def test_close_does_not_wait(tmp_path):
    hs = HungServer()
    t = _fast(Telemetry(_cfg(hs.url), tmp_path))
    t.timeout = 10.0
    t.start()
    t.put({'event': 'x'})
    time.sleep(0.3)
    start = time.perf_counter()
    t.close()
    assert time.perf_counter() - start < 0.6
    hs.stop()


def test_foreign_cert_refused(tmp_path):
    bad = FakeReceiver(name='foreign')
    try:
        t = _fast(Telemetry(_cfg(bad.url), tmp_path))
        t.start()
        t.put({'event': 'x'})
        assert _wait(lambda: t.status().error == 'сертификат не совпадает')
        assert not bad.events and t.status().queued == 1
        t.close()
    finally:
        bad.stop()


def test_wrong_key_reported(rx, tmp_path):
    t = _fast(Telemetry(_cfg(rx.url, key='wrong-key'), tmp_path))
    t.start()
    t.put({'event': 'x'})
    assert _wait(lambda: t.status().error == 'ключ не принят')
    assert not rx.events and t.status().queued == 1
    t.close()


def test_spool_overflow_moves_not_deletes(tmp_path):
    dead = f'https://127.0.0.1:{free_port()}'
    t = _fast(Telemetry(_cfg(dead), tmp_path))
    t.max_bytes = 2000
    t.batch = 5
    for i in range(60):
        t.put({'event': 'x', 'pad': 'я' * 40, 'n': i})
    t.close()
    over = list((tmp_path / 'overflow').glob('*.jsonl'))
    assert over
    kept = sum(len(p.read_text(encoding='utf-8').splitlines()) for p in over)
    left = Telemetry(_cfg(dead), tmp_path).status()
    assert kept + left.queued == 60 and left.overflowed == kept


def test_scrubbed_before_spool(tmp_path):
    dead = f'https://127.0.0.1:{free_port()}'
    t = Telemetry(_cfg(dead), tmp_path)
    t.put({'event': 'generate', 'raw': 'Петров И.И., лигатурная'})
    t.close()
    text = ''.join(p.read_text(encoding='utf-8') for p in tmp_path.rglob('*.jsonl*'))
    assert 'Петров' not in text and '‹ФИО›' in text and 'лигатурная' in text


def test_keep_words_respected(tmp_path):
    dead = f'https://127.0.0.1:{free_port()}'
    t = Telemetry(_cfg(dead), tmp_path, keep=lambda: frozenset({'мария'}))
    t.put({'event': 'x', 'raw': 'Мария'})
    t.close()
    text = ''.join(p.read_text(encoding='utf-8') for p in tmp_path.rglob('*.jsonl*'))
    assert 'Мария' in text


def _write_cfg(folder, url):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'telemetry.json').write_text(json.dumps(
        {'url': url, 'key': 'k', 'cert': cert_pem(), 'doctor': 'д1'}), encoding='utf-8')


def test_load_config_order(tmp_path):
    app, data, bundle = tmp_path / 'app', tmp_path / 'data', tmp_path / 'bundle'
    assert load_config(app, data, bundle) is None and load_config.error == ''
    _write_cfg(bundle, 'https://10.0.0.3:8443')
    assert load_config(app, data, bundle).url == 'https://10.0.0.3:8443'
    _write_cfg(data, 'https://10.0.0.2:8443')
    assert load_config(app, data, bundle).url == 'https://10.0.0.2:8443'
    _write_cfg(app, 'https://10.0.0.1:8443')
    c = load_config(app, data, bundle)
    assert c.url == 'https://10.0.0.1:8443' and c.doctor == 'д1'


def test_bad_config_reported(tmp_path):
    (tmp_path / 'telemetry.json').write_text('{"url": "http://1.2.3.4"}', encoding='utf-8')
    assert load_config(tmp_path, tmp_path / 'x', None) is None
    assert 'telemetry.json' in load_config.error
    _write_cfg(tmp_path, 'https://1.2.3.4')
    c = json.loads((tmp_path / 'telemetry.json').read_text(encoding='utf-8'))
    c['key'] = 'ключ'
    (tmp_path / 'telemetry.json').write_text(json.dumps(c), encoding='utf-8')
    assert load_config(tmp_path, tmp_path / 'x', None) is None and 'латиницей' in load_config.error


def test_segment_capped_by_bytes(tmp_path):
    dead = f'https://127.0.0.1:{free_port()}'
    t = Telemetry(_cfg(dead), tmp_path)
    t.max_segment_bytes = 1000
    for i in range(20):
        t.put({'event': 'error', 'traceback': 'x' * 200, 'n': i})
    t.close()
    segs = list(tmp_path.glob('seg-*.jsonl'))
    assert len(segs) >= 4 and all(p.stat().st_size <= 1000 + 400 for p in segs)


def test_rejected_segment_does_not_block(rx, tmp_path):
    rx.status = 413
    t = _fast(Telemetry(_cfg(rx.url), tmp_path))
    t.start()
    t.put({'event': 'huge'})
    assert _wait(lambda: list((tmp_path / 'overflow').glob('*.jsonl')))
    assert 'не принята' in t.status().error
    rx.status = 200
    t.put({'event': 'next'})
    assert _wait(lambda: any(e['event'] == 'next' for e in rx.events))
    assert t.status().overflowed == 1
    t.close()


def test_segment_names_unique_same_tick(tmp_path, monkeypatch):
    """Сборка на Windows: часы идут шагами ~15 мс — два сегмента в один шаг
    получали одно имя (на Linux второй переименованием затирал бы первый)."""
    import orthofill.telemetry as tm
    monkeypatch.setattr(tm.time, 'time_ns', lambda: 1_700_000_000_000_000_000)
    dead = f'https://127.0.0.1:{free_port()}'
    t = Telemetry(_cfg(dead), tmp_path)
    t.batch = 5
    for i in range(23):
        t.put({'event': 'x', 'n': i})
    t.close()
    segs = sorted(tmp_path.glob('seg-*.jsonl'))
    lines = [json.loads(s) for p in segs for s in p.read_text(encoding='utf-8').splitlines()]
    assert len(segs) == 5 and sorted(e['n'] for e in lines) == list(range(23))
    assert [e['n'] for e in lines] == list(range(23))      # порядок сегментов — порядок событий

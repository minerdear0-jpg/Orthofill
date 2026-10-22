import json
import socket
import time

import pytest

import orthofill.controller as controller_mod
from orthofill.controller import Controller
from orthofill.journal import Journal
from orthofill.telemetry import TelemetryConfig
from telemetry_server import FakeReceiver, cert_pem


def _events(ctl):
    out = []
    for p in sorted(ctl.diag_dir.glob('*.jsonl')):
        out += [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
    return out


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


@pytest.fixture
def with_cfg(monkeypatch, rx):
    cfg = TelemetryConfig(url=rx.url, key='k1', cert=cert_pem(), doctor='д1')
    monkeypatch.setattr(controller_mod, 'find_telemetry_config', lambda: cfg)
    return cfg


def _fast(ctl):
    t = ctl.telemetry
    t.flush_every = 0.05
    t._wake.set()


def test_off_means_no_network(ctl, order_xlsx, with_cfg, monkeypatch):
    calls = []
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: calls.append(a))
    ctl.import_xlsx(order_xlsx)
    ctl.startup()
    ctl.generate('лигатурная')
    ctl.track('ui', name='x')
    assert ctl.telemetry is None and not calls
    assert not (ctl.journal.db_path.parent / 'telemetry').exists()


def test_on_sends_generate(ctl, order_xlsx, with_cfg, rx):
    ctl.import_xlsx(order_xlsx)
    ctl.set_diagnostics(True)
    assert ctl.telemetry is not None
    _fast(ctl)
    ctl.generate('лигатурная, Петров И.И.')
    assert _wait(lambda: any(e['event'] == 'generate' for e in rx.events))
    ev = next(e for e in rx.events if e['event'] == 'generate')
    assert ev['install'] == ctl.install_id() and ev['doctor'] == 'д1'
    assert 'Петров' not in json.dumps(ev, ensure_ascii=False)
    assert any(e['event'] == 'diagnostics_on' for e in rx.events)
    ctl.set_diagnostics(False)
    assert ctl.telemetry is None


def test_track_goes_to_diag_and_server(ctl, with_cfg, rx):
    ctl.set_diagnostics(True)
    _fast(ctl)
    ctl.track('ui', name='copy')
    assert _wait(lambda: any(e['event'] == 'ui' for e in rx.events))
    assert any(e['event'] == 'ui' and e['name'] == 'copy' for e in _events(ctl))


def test_install_id_stable(ctl, tmp_path):
    a = ctl.install_id()
    assert a == ctl.install_id() and len(a) >= 16
    ctl.journal._db.commit()
    assert Controller(Journal(ctl.journal.db_path), lambda t: None).install_id() == a


def test_about_line_states(ctl, with_cfg, rx, monkeypatch):
    assert ctl.telemetry_line() == 'Телеметрия: выключена (нужна «Диагностика»)'
    ctl.set_diagnostics(True)
    _fast(ctl)
    ctl.track('ui', name='x')
    assert _wait(lambda: 'сервер доступен' in ctl.telemetry_line())
    assert 'отправлено' in ctl.telemetry_line()
    ctl.set_diagnostics(False)
    monkeypatch.setattr(controller_mod, 'find_telemetry_config', lambda: None)
    ctl.set_diagnostics(True)
    assert ctl.telemetry_line() == 'Телеметрия: не настроена (нет telemetry.json)'


def test_perf_is_aggregated(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.set_diagnostics(True)
    for _ in range(50):
        ctl.preview('лигатурная, перепел')
    assert sum(e['event'] == 'perf' for e in _events(ctl)) <= 1
    ctl.perf_window = 0
    ctl.preview('лигатурная')
    perf = [e for e in _events(ctl) if e['event'] == 'perf']
    assert perf and perf[-1]['preview_n'] >= 1 and 'preview_ms_med' in perf[-1]


def test_perf_not_collected_when_off(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.perf_window = 0
    ctl.preview('лигатурная')
    assert not ctl.diag_dir.exists() or not _events(ctl)


def test_proposal_events(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.set_diagnostics(True)
    ctl.decline_proposal(('замена', 'замена дуги {верх|низ}', 5))
    assert any(e['event'] == 'proposal' and e['action'] == 'no' for e in _events(ctl))


def test_note_confirm_via(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.set_diagnostics(True)
    p = ctl.preview('лигатурная').text
    ctl.generate('лигатурная', via='ctrl_enter', text=p + '\nмоя строка', stats={'keys': 12})
    ev = [e for e in _events(ctl) if e['event'] == 'note_confirm'][-1]
    assert ev['via'] == 'ctrl_enter' and ev['edited_lines'] == 1 and ev['keys'] == 12


def test_session_start_and_close(app, monkeypatch):
    seen = []
    monkeypatch.setattr(app.ctl, 'track', lambda ev, **d: seen.append((ev, d)))
    app._session_start()
    ev, d = seen[-1]
    assert ev == 'session_start' and d['startup_ms'] > 0 and 'os' in d and 'scale' in d
    closed = []
    monkeypatch.setattr(app.ctl, 'shutdown', lambda: closed.append(1))
    app.root.destroy = lambda: None
    app.close()
    del app.root.destroy
    assert closed


def test_about_shows_telemetry_line(app):
    from orthofill.ui import AboutDialog
    d = AboutDialog(app)
    assert 'Телеметрия:' in d.info_text
    d.top.destroy()


def test_perf_hints_and_unknown(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.set_diagnostics(True)
    ctl.perf_window = 0
    ctl.hints('лиг')
    ctl.find_unknown('лигатурная, квакозябра')
    keys = set().union(*(e.keys() for e in _events(ctl) if e['event'] == 'perf'))
    assert 'hints_ms_med' in keys and 'unknown_ms_med' in keys

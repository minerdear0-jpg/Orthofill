import asyncio
import json
import os
import socket
import ssl
import stat
import sys
import threading
import time
from pathlib import Path

import pytest
from aiohttp import web

import mkconfig
from receiver.app import ServerConfig, make_app

ROOT = Path(__file__).resolve().parents[2]


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture
def made(tmp_path):
    port = _free_port()
    mkconfig.main(['--ip', '127.0.0.1', '--port', str(port), '--out', str(tmp_path)])
    return tmp_path, port


def test_files_written(made):
    out, port = made
    cfg = json.loads((out / 'config.json').read_text())
    tel = json.loads((out / 'telemetry.json').read_text())
    assert tel['url'] == f'https://127.0.0.1:{port}' and tel['key'] in cfg['keys']
    assert 'BEGIN CERTIFICATE' in tel['cert'] and len(cfg['admin_password']) >= 24
    assert tel['cert'] == (out / 'cert.pem').read_text()


def test_mkconfig_files_private(made):
    out, _ = made
    for name in ('key.pem', 'config.json'):
        assert stat.S_IMODE((out / name).stat().st_mode) == 0o600, name


def test_refuses_to_overwrite(made):
    out, port = made
    with pytest.raises(SystemExit):
        mkconfig.main(['--ip', '127.0.0.1', '--port', str(port), '--out', str(out)])


def test_mkconfig_cert_has_ip_san(made):
    """Программа (orthofill.telemetry) с выданным telemetry.json доверяет серверу."""
    out, port = made
    sys.path.insert(0, str(ROOT))
    from orthofill.telemetry import Telemetry, load_config
    cfg = ServerConfig.from_file(out / 'config.json')
    cfg.host, cfg.port = '127.0.0.1', port
    app = make_app(cfg)
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def serve():
        asyncio.set_event_loop(loop)
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(cfg.cert, cfg.key)
        loop.run_until_complete(web.TCPSite(runner, '127.0.0.1', port, ssl_context=ctx).start())
        ready.set()
        loop.run_forever()
        loop.run_until_complete(runner.cleanup())
    th = threading.Thread(target=serve, daemon=True)
    th.start()
    assert ready.wait(5)
    try:
        tcfg = load_config(out, out / 'none', None)
        t = Telemetry(tcfg, out / 'spool')
        t.flush_every = 0.05
        t.start()
        t.put({'event': 'ui', 'name': 'x'})
        end = time.monotonic() + 5
        from receiver.store import Store
        while time.monotonic() < end and Store(cfg.db).count() == 0:
            time.sleep(0.05)
        assert Store(cfg.db).count() == 1 and t.status().error == ''
        t.close()
    finally:
        loop.call_soon_threadsafe(loop.stop)
        th.join(5)


def test_existing_port_and_ip_check(made, capsys):
    """Повторный install.sh: порт — из прежних настроек; другой IP или порт — отказ."""
    out, port = made
    capsys.readouterr()
    assert mkconfig.main(['--out', str(out), '--existing', '--ip', '127.0.0.1']) == 0
    assert capsys.readouterr().out.strip() == str(port)
    assert mkconfig.main(['--out', str(out), '--existing', '--ip', '10.0.0.9']) == 1
    assert mkconfig.main(['--out', str(out), '--existing', '--ip', '127.0.0.1',
                          '--port', str(port + 1)]) == 1

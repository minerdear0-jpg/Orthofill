"""0.3 beta 1: живой протокол и токены — на настоящем Tk (нужен дисплей)."""
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


@pytest.fixture
def live(app):
    app.live_delay, app.unknown_delay = 20, 40
    app.copied = []
    app.ctl.clipboard = app.copied.append
    return app


def _type(app, text):
    app.raw_txt.focus_force()
    app.raw_txt.insert('insert', text)
    app.root.update()


def _wait(app, ms=120):
    app.root.after(ms)
    app.root.update()
    app.root.after(10)
    app.root.update()


def _out(app):
    return app.out_txt.get('1.0', 'end-1c')


def test_live_rebuild_after_pause(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    assert 'Перепел' in _out(live) and not live.copied
    assert 'Ctrl+Enter' in live.status_lbl['text']


def test_debounce_one_rebuild(live, monkeypatch):
    calls = []
    orig = live.ctl.preview
    monkeypatch.setattr(live.ctl, 'preview', lambda *a, **k: calls.append(1) or orig(*a, **k))
    live.live_delay = 300                       # как у врача: пауза в наборе
    for ch in 'лигатурная, перепел, явка 6 недель, гигиена неуд':
        live.raw_txt.insert('end', ch)
        live.root.update()
    _wait(live, 450)
    assert len(calls) == 1


def test_hand_edit_freezes_live(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    _type(live, ', лиса')
    _wait(live)
    assert 'моя правка' in _out(live) and live.live_frozen and live.live_bar.winfo_manager()


def test_update_button_unfreezes(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    _type(live, ', юстировка изгиб первого')
    _wait(live)
    live._live_update_now()
    assert 'моя правка' not in _out(live) and 'первого порядка' in _out(live)
    assert not live.live_frozen and not live.live_bar.winfo_manager()


def test_keep_button_does_not_nag(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    _type(live, ', перепел')
    _wait(live)
    live._live_keep()
    assert not live.live_bar.winfo_manager()
    _type(live, ', лиса')
    _wait(live)
    assert not live.live_bar.winfo_manager() and 'моя правка' in _out(live)


def test_confirm_copies_edited(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    live.generate()
    assert live.copied and live.copied[-1].endswith('моя правка')


def test_confirm_copies_live(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    n = live.ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
    live.generate()
    assert live.copied[-1] == _out(live) and 'Перепел' in live.copied[-1]
    assert live.ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0] == n + 1
    assert not live.live_frozen


def test_empty_note_clears_protocol(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.raw_txt.delete('1.0', 'end')
    live.root.update()
    _wait(live)
    assert _out(live) == ''


def test_live_unknown_underline(live):
    _type(live, 'лигатурная, квакозябра')
    _wait(live, 200)
    assert live.raw_txt.tag_ranges('unknown')

"""0.4 beta 1: события поведения врача в окне — на настоящем Tk (нужен дисплей)."""
import json
import os
import sys

import pytest

from orthofill.workbook import Phrase

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


@pytest.fixture
def ev(app, monkeypatch):
    seen = []
    monkeypatch.setattr(app.ctl, 'track', lambda e, **d: seen.append((e, d)))
    return seen


def _type(app, text):
    app.raw_txt.focus_force()
    app.raw_txt.insert('insert', text)
    app.root.update()
    app.hint_box.update()
    app.root.update()


def _key(app, key, w=None):
    w = w or app.raw_txt
    w.focus_force()
    app.root.update()
    w.event_generate(f'<{key}>', when='now')
    app.root.update()


def _of(ev, name):
    return [d for e, d in ev if e == name]


def test_hint_accepted_tab(app, ev):
    app.ctl.learn('торк', '4g3')
    _type(app, 'лигатурная, тор')
    _key(app, 'Tab')
    h = _of(ev, 'hint')
    assert h[0] == {'action': 'shown', 'kind': 'doctor', 'count': 1, 'prefix_len': 3}
    assert h[-1]['action'] == 'accepted' and h[-1]['via'] == 'tab' and h[-1]['pos'] == 0
    assert sum(d['action'] == 'shown' for d in h) == 1


def test_hint_right_arrow(app, ev):
    app.ctl.learn('торк', '4g3')
    _type(app, 'тор')
    _key(app, 'Right')
    assert _of(ev, 'hint')[-1]['via'] == 'right'


def test_hint_ignored(app, ev):
    app.ctl.learn('торк', '4g3')
    _type(app, 'тор')
    _type(app, 'т ')
    h = _of(ev, 'hint')
    assert [d['action'] for d in h] == ['shown', 'ignored']


def test_hint_erased_after_accept(app, ev):
    app.ctl.learn('торк', '4g3')
    _type(app, 'тор')
    _key(app, 'Tab')
    app.raw_txt.delete('insert -2c', 'insert')
    _key(app, 'KeyRelease-BackSpace')
    assert _of(ev, 'hint')[-1]['action'] == 'erased'


def test_phrase_expand_events(app, ev):
    app.ctl.presets.add_phrase(app.ctl.preset_id,
                               Phrase('замена', 'замена дуги {верх|низ|обе} {18х25|16х25} тма'))
    app.ctl._reload()
    _type(app, '.зам')
    _key(app, 'Tab')                 # раскрыть
    _key(app, 'Down')
    _key(app, 'Return')              # поле 1 — из списка
    _key(app, 'Escape')              # выйти
    acts = [d['action'] for d in _of(ev, 'smartphrase')]
    assert acts[:2] == ['shown', 'expanded']
    assert 'field_list' in acts and 'field_left' in acts
    assert _of(ev, 'smartphrase')[-1] == {'action': 'exit', 'exit': 'esc', 'fields': 2}


def _history(app):
    for raw in ('активация, лигатурная, замена дуги верх 18х25 тма, явка 6 нед',
                'активация, лигатурная, замена дуги верх 18х25 тма, перепел'):
        app.ctl.generate(raw)


def test_habit_accepted(app, ev):
    _history(app)
    _type(app, 'замена ду')
    _key(app, 'Tab')
    assert [d['action'] for d in _of(ev, 'habit')] == ['shown', 'accepted']


def test_habit_ignored(app, ev):
    _history(app)
    _type(app, 'замена ду')
    _type(app, 'х')
    assert [d['action'] for d in _of(ev, 'habit')] == ['shown', 'ignored']


def test_ui_button_named(app, ev):
    btn = next(w for w in _walk(app.root) if _text(w) == 'Отметить ошибку')
    btn.invoke()
    app.root.update()
    assert ('ui', {'name': 'Отметить ошибку'}) in ev
    for w in app.root.winfo_children():
        if w.winfo_class() == 'Toplevel':
            w.destroy()


def test_ui_menu_named(app, ev):
    m = app._text_menu(app.raw_txt)
    i = next(k for k in range(m.index('end') + 1)
             if m.type(k) == 'command' and m.entrycget(k, 'label') == 'Выделить всё')
    m.invoke(i)
    assert ('ui', {'name': 'Выделить всё'}) in ev


def test_key_noop_on_empty_clipboard_paste(app, ev):
    app.root.clipboard_clear()
    _type(app, 'лигатурная')
    _key(app, 'KeyPress-Control_L')
    _key(app, 'Control-v')
    app.root.update()
    k = _of(ev, 'key_noop')
    assert k and k[-1]['key'] == 'ctrl+v' and k[-1]['field'] == 'raw'


def test_paste_that_works_is_not_noop(app, ev):
    app.root.clipboard_clear()
    app.root.clipboard_append('перепел')
    _key(app, 'KeyPress-Control_L')
    _key(app, 'Control-v')
    app.root.update()
    assert not _of(ev, 'key_noop')


def test_live_bar_events(app, ev):
    app._live_keep()
    app._live_update_now()
    assert [d['live_bar'] for d in _of(ev, 'protocol_edit')] == ['keep', 'update']


def test_add_search_events(app, ev):
    app.add_entry.insert(0, 'изгиб')
    app._on_add_query()
    app._add_selected(0)
    a = _of(ev, 'add_search')[-1]
    assert a['chosen'] and a['qlen'] == 5 and a['found'] >= 1 and a['pos'] == 0
    app.add_entry.insert(0, 'квакозябра')
    app._on_add_query()
    app._close_add()
    a = _of(ev, 'add_search')[-1]
    assert not a['chosen'] and a['found'] == 0


def test_note_stats_in_confirm(app, monkeypatch):
    got = {}
    real = app.ctl.generate

    def spy(*a, **k):
        got.update(k)
        return real(*a, **k)
    monkeypatch.setattr(app.ctl, 'generate', spy)
    app.raw_txt.focus_force()
    for ch in 'abc':
        _key(app, f'KeyPress-{ch}')
    app.raw_txt.insert('end', 'атурная')
    _key(app, 'BackSpace')
    app.generate('ctrl_enter')
    assert got['via'] == 'ctrl_enter'
    assert got['stats']['backspaces'] == 1 and got['stats']['keys'] >= 1


def test_no_typed_text_in_behavior(app, ev):
    app.ctl.learn('торк', '4g3')
    _type(app, 'лигатурная, тор')
    _key(app, 'Tab')
    _type(app, ', квакозябра')
    app.add_entry.insert(0, 'перепел')
    app._on_add_query()
    app._close_add()
    app._live_keep()
    blob = json.dumps(ev, ensure_ascii=False)
    for word in ('торк', 'лигатурн', 'квакозябр', 'перепел'):
        assert word not in blob


def _walk(w):
    yield w
    for c in w.winfo_children():
        yield from _walk(c)


def _text(w):
    try:
        return w.cget('text')
    except Exception:
        return None


def test_protocol_menu_counted_once(app, ev):
    app.ctl.generate('лигатурная')
    m = app._protocol_menu('1.0')
    i = next(k for k in range(m.index('end') + 1)
             if m.type(k) == 'command' and m.entrycget(k, 'label') == 'Выделить всё')
    m.invoke(i)
    assert ev.count(('ui', {'name': 'Выделить всё'})) == 1

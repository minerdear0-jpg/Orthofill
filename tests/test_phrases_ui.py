"""0.3 beta 3: SmartPhrase в поле записи — на настоящем Tk (нужен дисплей)."""
import os
import sys

import pytest

from orthofill.workbook import Phrase

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")

TPL = 'замена дуги {верх|низ|обе} {18х25|16х25} тма'


@pytest.fixture
def ph(app):
    app.ctl.presets.add_phrase(app.ctl.preset_id, Phrase('замена', TPL))
    app.ctl._reload()
    return app


def _type(app, text):
    app.raw_txt.focus_force()
    app.raw_txt.insert('insert', text)
    app.root.update()
    app.hint_box.update()
    app.root.update()


def _key(app, key, **kw):
    app.raw_txt.focus_force()
    app.root.update()
    app.raw_txt.event_generate(f'<{key}>', when='now', **kw)
    app.root.update()


def _raw(app):
    return app.raw_txt.get('1.0', 'end-1c')


def _expand(app, text='.зам'):
    _type(app, text)
    _key(app, 'Tab')


def test_command_shows_phrase(ph):
    _type(ph, 'активация, .зам')
    hb = ph.hint_box
    assert hb.items[0].word == '.замена' and hb.items[0].becomes == 'замена дуги верх 18х25 тма'
    assert hb.list_shown


def test_tab_expands_with_fields(ph):
    _expand(ph, 'активация, .зам')
    assert _raw(ph) == 'активация, замена дуги верх 18х25 тма'
    assert ph.hint_box.field_i == 0 and len(ph.hint_box.fields) == 2
    assert len(ph.raw_txt.tag_ranges('field')) == 4
    assert [h.word for h in ph.hint_box.items] == ['верх', 'низ', 'обе']


def test_tab_moves_to_next_field_then_exits(ph):
    _expand(ph)
    _key(ph, 'Tab')
    assert ph.hint_box.field_i == 1 and [h.word for h in ph.hint_box.items] == ['18х25', '16х25']
    _key(ph, 'Tab')
    assert not ph.hint_box.fields and not ph.raw_txt.tag_ranges('field')


def test_choose_value_with_arrow(ph):
    _expand(ph)
    _key(ph, 'Down')
    _key(ph, 'Down')
    _key(ph, 'Return')
    assert _raw(ph) == 'замена дуги низ 18х25 тма' and ph.hint_box.field_i == 1


def test_typing_replaces_field(ph):
    _expand(ph)
    _key(ph, 'KeyPress', keysym='x')
    assert _raw(ph) == 'замена дуги x 18х25 тма'
    _key(ph, 'Tab')
    _key(ph, 'KeyPress', keysym='y')
    assert _raw(ph) == 'замена дуги x y тма'


def test_escape_exits(ph):
    _expand(ph)
    _key(ph, 'Escape')
    assert not ph.hint_box.fields and not ph.raw_txt.tag_ranges('field')
    assert _raw(ph) == 'замена дуги верх 18х25 тма'


@pytest.mark.parametrize('text', ['явка 6 нед.', 'дуга 0.016', 'т.к. '])
def test_dot_inside_word_is_not_command(ph, text):
    _type(ph, text)
    assert not any(h.word.startswith('.') for h in ph.hint_box.items)


def test_confirm_inside_phrase(ph):
    copied = []
    ph.ctl.clipboard = copied.append
    _expand(ph, 'лигатурная, .зам')
    ph.generate()
    assert copied and 'TMA' in copied[-1]
    assert not ph.hint_box.fields and not ph.raw_txt.tag_ranges('field')


def test_one_undo_restores_command(ph):
    _type(ph, 'а, ')
    ph.raw_txt.edit_separator()
    _expand(ph, '.зам')
    _key(ph, 'Escape')
    ph.raw_txt.edit_undo()
    assert _raw(ph) == 'а, .зам'


def test_use_counted(ph):
    _expand(ph)
    assert ph.ctl.presets.load(ph.ctl.preset_id).phrases[0].uses == 1

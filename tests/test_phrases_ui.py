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


# ---------- Task 4 ----------
NOTES = ['активация, замена дуги верх 18х25 тма, перепел', 'активация, замена дуги верх 18х25 тма',
         'лигатурная, замена дуги низ 16х25 тма', 'активация, замена дуги верх 16х25 тма',
         'рабочий, замена дуги верх 18х25 тма']


def test_proposal_bar_after_confirm(app):
    for raw in NOTES:
        app.ctl.generate(raw)
    app.raw_txt.insert('1.0', 'активация, замена дуги низ 18х25 тма')
    app.generate()
    app.root.update()
    assert app.phrase_bar.winfo_manager() and '.замена' in app.phrase_lbl['text']
    app._phrase_yes()
    assert not app.phrase_bar.winfo_manager()
    assert [p.name for p in app.ctl.workbook.phrases] == ['замена']
    app.raw_txt.delete('1.0', 'end')
    _expand(app)
    assert _raw(app) == 'замена дуги верх 18х25 тма'


def test_proposal_declined_not_again(app):
    for raw in NOTES:
        app.ctl.generate(raw)
    app.raw_txt.insert('1.0', 'активация, замена дуги низ 18х25 тма')
    app.generate()
    app.root.update()
    app._phrase_no()
    assert not app.phrase_bar.winfo_manager()
    app.generate()
    app.root.update()
    assert not app.phrase_bar.winfo_manager()


def test_editor_phrases_tab(app):
    ed = app.open_editor('4a')
    assert ed.notebook.tab(ed.phrases_page, 'text') == 'Фразы (0)'
    assert ed.add_phrase('акт', 'активация, {лигатурная|самолиг}') is None
    assert [p.name for p in ed.draft.wb.phrases] == ['акт']
    assert 'не закрыта' in ed.add_phrase('плохо', 'замена {верх')
    ed.undo()
    assert ed.draft.wb.phrases == []
    ed.add_phrase('акт', 'активация, {лигатурная|самолиг}')
    ed.delete_phrase('акт')
    assert ed.draft.wb.phrases == []


def test_save_draft_keeps_phrase_added_meanwhile(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    d = ctl.open_draft()
    ctl.presets.add_phrase(ctl.preset_id, Phrase('замена', TPL))      # «Да» в главном окне
    d.set_text('4a', 'Осмотр.')
    ctl.save_draft()
    assert [p.name for p in ctl.workbook.phrases] == ['замена']


# ---------- итоговая проверка ----------
@pytest.mark.parametrize('exit_key', ['Escape', 'Tab2'])
def test_exit_puts_cursor_after_phrase(ph, exit_key):
    _expand(ph)
    if exit_key == 'Tab2':
        _key(ph, 'Tab')
        _key(ph, 'Tab')
    else:
        _key(ph, 'Escape')
    ph.raw_txt.insert('insert', ', перепел')
    assert _raw(ph) == 'замена дуги верх 18х25 тма, перепел'


def test_enter_in_fields_newline_after_phrase(ph):
    _expand(ph)
    _key(ph, 'Return')
    assert _raw(ph) == 'замена дуги верх 18х25 тма\n'


def test_select_all_retype_leaves_field_mode(ph):
    _expand(ph)
    ph.raw_txt.delete('1.0', 'end')
    _type(ph, 'ab')
    assert not ph.hint_box.fields
    _key(ph, 'Tab')
    assert _raw(ph).startswith('ab')


def test_undo_leaves_field_mode(ph):
    _expand(ph, '.зам')
    ph.raw_txt.event_generate('<<Undo>>')
    ph.root.update()
    ph.hint_box.update()
    assert not ph.hint_box.fields and not ph.raw_txt.tag_ranges('field')


def test_resize_in_fields_no_false_tail(ph):
    _expand(ph)
    _key(ph, 'KeyPress', keysym='x')
    ph.root.geometry(f'{ph.root.winfo_width() + 30}x{ph.root.winfo_height()}')
    ph.root.update()
    ph.root.update()
    assert ph.hint_box.tail['text'] == ''
    _key(ph, 'Right')
    assert 'замена дуги x 18х25' in _raw(ph)


def test_choose_is_one_undo(ph):
    _expand(ph)
    _key(ph, 'Down')
    _key(ph, 'Down')
    _key(ph, 'Return')
    ph.raw_txt.edit_undo()
    assert _raw(ph) == 'замена дуги верх 18х25 тма'


def test_proposal_bar_hidden_on_preset_switch(app):
    for raw in NOTES:
        app.ctl.generate(raw)
    app.raw_txt.insert('1.0', 'активация, замена дуги низ 18х25 тма')
    app.generate()
    app.root.update()
    other = next(p.id for p in app.ctl.presets.list() if p.id != app.ctl.preset_id)
    app.switch_to(other)
    assert not app.phrase_bar.winfo_manager() and app._phrase_prop is None

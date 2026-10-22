"""Подсказки в поле записи — на настоящем Tk (нужен дисплей)."""
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


def _type(app, text):
    app.raw_txt.focus_force()
    app.raw_txt.insert('insert', text)
    app.root.update()
    app.hint_box.update()
    app.root.update()


def _key(app, key, ctrl=False):
    app.raw_txt.focus_force()
    app.root.update()
    app.raw_txt.event_generate(f'<Control-{key}>' if ctrl else f'<{key}>', when='now')
    app.root.update()


def _raw(app):
    return app.raw_txt.get('1.0', 'end-1c')


def test_popup_and_tab_accepts(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'лигатурная, тор')
    hb = app.hint_box
    assert hb.visible and hb.items[0].word == 'торк' and hb.tail['text'] == 'к'
    _key(app, 'Tab')
    assert _raw(app) == 'лигатурная, торк' and not hb.visible and hb.tail['text'] == ''


def test_single_candidate_only_tail(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'тор')
    assert app.hint_box.items == app.hint_box.items[:1] and not app.hint_box.list_shown


def test_list_for_several(app):
    app.ctl.learn('торк', '4g3')
    app.ctl.generate('лигатурная, торцевание')
    _type(app, 'тор')
    assert app.hint_box.list_shown and len(app.hint_box.items) >= 2


def test_enter_without_arrow_is_newline(app):
    _type(app, 'перепел, яв')
    _type(app, 'к')                                   # «явк» — подсказка «явка»
    assert app.hint_box.visible
    _key(app, 'Return')
    assert _raw(app).endswith('явк\n') and not app.hint_box.visible


def test_arrow_then_enter_accepts_second(app):
    app.ctl.learn('торк', '4g3')
    app.ctl.generate('лигатурная, торцевание')
    app.raw_txt.delete('1.0', 'end')
    _type(app, 'тор')
    _key(app, 'Down')
    _key(app, 'Down')
    _key(app, 'Return')
    assert _raw(app) == 'торцевание'


def test_ctrl_enter_not_intercepted(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'лигатурная, тор')
    _key(app, 'Return', ctrl=True)
    assert app.out_txt.get('1.0', 'end-1c') and not app.hint_box.visible
    assert _raw(app) == 'лигатурная, тор'


def test_escape_space_comma_close(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'тор')
    _key(app, 'Escape')
    assert not app.hint_box.visible and _raw(app) == 'тор'
    for sep in (' ', ','):
        app.raw_txt.delete('1.0', 'end')
        _type(app, 'тор')
        assert app.hint_box.visible
        _type(app, sep)
        assert not app.hint_box.visible


def test_ctrl_space_opens_with_short_prefix(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'то')
    assert not app.hint_box.visible
    _key(app, 'space', ctrl=True)
    assert app.hint_box.visible and app.hint_box.items[0].word == 'торк'


def test_closes_on_scroll_and_resize(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'строка\n' * 30 + 'тор')
    assert app.hint_box.visible
    app.raw_txt.yview_moveto(0)
    app.root.update()
    assert not app.hint_box.visible
    app.raw_txt.see('end')
    app.root.update()
    app.hint_box.update()
    assert app.hint_box.visible
    app.root.geometry('500x700')
    app.root.update()
    assert not app.hint_box.visible


def test_toggle_off(app):
    app.ctl.learn('торк', '4g3')
    app.hints_on.set(False)
    app._toggle_hints()
    _type(app, 'тор')
    assert not app.hint_box.visible and app.hint_box.tail['text'] == ''
    assert app.ctl.journal.get_setting('hints') == '0'
    _key(app, 'Tab')
    assert _raw(app) == 'тор\t'                       # Tab — как без подсказок


# ---------- итоговая проверка: подсказка не должна устаревать ----------
def test_tab_after_undo_does_not_corrupt(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'лигатурная ')
    app.raw_txt.edit_separator()
    _type(app, 'тор')
    app.raw_txt.edit_undo()                            # Ctrl+Z убрал «тор», хвост ещё виден
    app.raw_txt.event_generate('<KeyRelease>', keysym='z', state=0x4, when='now')
    _key(app, 'Tab')
    assert not _raw(app).startswith('лигатурн') or 'торк' not in _raw(app)
    assert 'лигатурнторк' not in _raw(app)


def test_tab_after_cursor_moved_does_nothing(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'абв\nгде тор')
    _key(app, 'Up')                                    # только хвост: ↑ двигает курсор
    _key(app, 'Tab')
    assert _raw(app).startswith('абв') and 'торк' not in _raw(app)


def test_accept_rechecks_prefix(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'лигатурная тор')
    app.raw_txt.mark_set('insert', '1.3')              # курсор ушёл без событий
    _key(app, 'Tab')
    assert _raw(app).startswith('лиг') and 'торк' not in _raw(app)


def test_width_only_resize_closes(app):
    app.ctl.learn('торк', '4g3')
    app.ctl.generate('лигатурная, торцевание')
    _type(app, 'тор')
    assert app.hint_box.list_shown
    app.root.geometry(f'{app.root.winfo_width() + 40}x{app.root.winfo_height()}')
    app.root.update()
    assert not app.hint_box.visible


def test_invisible_hint_is_shown_as_list(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'njh')                                  # английская раскладка: хвоста нет
    assert app.hint_box.list_shown


def test_one_undo_restores_prefix(app):
    app.ctl.learn('торк', '4g3')
    _type(app, 'лигатурная, ')
    app.raw_txt.edit_separator()
    _type(app, 'тор')
    _key(app, 'Tab')
    app.raw_txt.edit_undo()
    assert _raw(app) == 'лигатурная, тор'


def test_shift_arrows_and_ctrl_tab_pass_through(app):
    app.ctl.learn('торк', '4g3')
    app.ctl.generate('лигатурная, торцевание')
    _type(app, 'абв\nтор')
    assert app.hint_box.list_shown
    app.raw_txt.focus_force()
    app.root.update()
    app.raw_txt.event_generate('<Shift-Up>', when='now')
    app.root.update()
    assert app.hint_box.selected == -1


def test_ctrl_space_off_passes_through(app):
    app.hints_on.set(False)
    app._toggle_hints()
    assert app.hint_box._manual(None) is None

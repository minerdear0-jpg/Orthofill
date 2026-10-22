"""0.5 beta 1: оболочка в поле записи — на настоящем Tk (нужен дисплей)."""
import os
import sys

import pytest

from orthofill.shell import format_path

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


@pytest.fixture
def sh(app):
    app.ctl.set_shell_mode(True)
    app._apply_shell_mode()
    return app


def _type(app, text):
    app.raw_txt.focus_force()
    app.raw_txt.insert('insert', text)
    app.root.update()
    app.shell_box.update()
    app.root.update()


def _key(app, key, **kw):
    app.raw_txt.focus_force()
    app.root.update()
    app.raw_txt.event_generate(f'<{key}>', when='now', **kw)
    app.root.update()


def _raw(app):
    return app.raw_txt.get('1.0', 'end-1c')


def _wb(app):
    return app.ctl.workbook


def test_tab_expands_unique(sh):
    _type(sh, 'лигатурная')
    assert sh.shell_box.ghost
    _key(sh, 'Tab')
    assert _raw(sh) == format_path(_wb(sh), ('2', '2b', '2b2'))


def test_ambiguous_list(sh):
    _type(sh, 'лиг')
    sb = sh.shell_box
    assert sb.list_shown and {c[-1] for c in sb.choices} == {'2b2', '4d', '4e', '4h1'}
    _key(sh, 'Tab')
    assert _raw(sh) == 'лиг'


def test_second_word_then_tab(sh):
    _type(sh, 'ду вер')
    _key(sh, 'Tab')
    assert _raw(sh) == format_path(_wb(sh), ('4', '4b')) + ' › '


def test_question_lists_branches(sh):
    _type(sh, format_path(_wb(sh), ('4', '4f')) + ' › ')
    _key(sh, 'KeyPress', keysym='question')
    sb = sh.shell_box
    assert sb.list_shown and [c[-1] for c in sb.choices][:2] == ['4f1', '4f2']
    assert '?' not in _raw(sh)


def test_question_not_inserted(sh):
    _type(sh, 'лиг')
    _key(sh, 'KeyPress', keysym='question')
    assert _raw(sh) == 'лиг'


def test_list_arrow_and_enter(sh):
    _type(sh, format_path(_wb(sh), ('4', '4f')) + ' › ')
    _key(sh, 'KeyPress', keysym='question')
    assert sh.shell_box.selected == 0       # первый вариант уже выбран — Enter его возьмёт
    _key(sh, 'Down')
    _key(sh, 'Return')                      # выбран 4f2 «Лиса» — лист: строка готова
    first = _raw(sh).split('\n')[0]
    assert first == format_path(_wb(sh), ('4', '4f', '4f2'))


def test_enter_on_leaf_finishes(sh):
    _type(sh, format_path(_wb(sh), ('4', '4b', '4b5')))
    _key(sh, 'Return')
    t = sh.raw_txt
    assert _raw(sh).endswith('\n') and t.tag_ranges('shell_ok')
    assert t.index('insert') == '2.0'
    assert '4b5' in [c for r in sh.ctl.preview(_raw(sh)).rows for c in r.codes]


def test_enter_on_group_lists(sh):
    _type(sh, format_path(_wb(sh), ('4', '4b')) + ' › ')
    _key(sh, 'Return')
    assert sh.shell_box.list_shown and '\n' not in _raw(sh)


def test_bad_word_marked(sh):
    _type(sh, 'эластики кв')
    r = sh.raw_txt.tag_ranges('shell_bad')
    assert r and sh.raw_txt.get(r[0], r[1]) == 'кв'


def test_backspace_undoes_expand(sh):
    _type(sh, 'лигатурная')
    _key(sh, 'Tab')
    _key(sh, 'BackSpace')
    assert _raw(sh) == 'лигатурная'


def test_tab_on_empty_line(sh):
    _key(sh, 'Tab')
    assert _raw(sh) == ''


def test_hints_off_in_shell(sh):
    sh.ctl.learn('торк', '4g3')
    sh.raw_txt.insert('insert', 'тор')
    sh.root.update()
    sh.hint_box.update()
    assert not sh.hint_box.visible


def test_synonym_word(sh):
    sh.ctl.learn('торк', '4g3')
    _type(sh, 'торк')
    _key(sh, 'Tab')
    assert _raw(sh) == format_path(_wb(sh), ('4', '4g', '4g3'))


def test_typing_line_not_underlined(sh):
    """Строку, которую ещё набирают, «непонятой» не подчёркивать."""
    _type(sh, format_path(_wb(sh), ('4', '4f', '4f1')) + '\nду в')
    sh._show_unknown(sh.ctl.find_unknown(_raw(sh)))
    assert not sh.raw_txt.tag_ranges('unknown')
    sh.raw_txt.mark_set('insert', '1.0')
    sh._show_unknown(sh.ctl.find_unknown(_raw(sh)))
    assert sh.raw_txt.tag_ranges('unknown')          # курсор ушёл — строка 2 непонята

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


# ---------- Task 5: стрелки по уровням ----------
def _line_at(sh, path):
    _type(sh, format_path(_wb(sh), path))
    sh.raw_txt.mark_set('insert', '1.end')


def _col(sh):
    return int(sh.raw_txt.index('insert').split('.')[1])


def _dwell(sh):
    sh.root.after(sh.shell_box.dwell_ms + 80)
    sh.root.update()


def test_arrows_move_by_level(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    line = _raw(sh)
    starts = [0, line.index(' › Смена') + 3, line.rindex(' › ') + 3]
    _key(sh, 'Left')
    assert _col(sh) == starts[2]
    _key(sh, 'Left')
    assert _col(sh) == starts[1]
    _key(sh, 'Left')
    assert _col(sh) == starts[0]
    _key(sh, 'Right')
    assert _col(sh) == starts[1]


def test_dwell_opens_siblings(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _dwell(sh)
    sb = sh.shell_box
    assert sb.list_shown and len(sb.choices) == 21 and sb.choices[sb.selected][-1] == '4b5'


def test_typing_does_not_open_siblings(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _key(sh, 'KeyPress', keysym='a')         # набор отменяет «намеренную остановку»
    _dwell(sh)
    assert not sh.shell_box.list_shown


def test_replace_level_keeps_tail(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _key(sh, 'Left')                          # на «Смена дуги на верхней челюсти»
    _dwell(sh)
    sb = sh.shell_box
    sb.selected = [c[-1] for c in sb.choices].index('4c')
    _key(sh, 'Return')
    assert _raw(sh) == format_path(_wb(sh), ('4', '4c')) + ' › '


def test_replace_leaf(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _dwell(sh)
    sb = sh.shell_box
    sb.selected = [c[-1] for c in sb.choices].index('4b18')
    _key(sh, 'Return')
    from orthofill.shell import parse_line
    assert parse_line(_wb(sh), _raw(sh).split('\n')[0]) == ('4', '4b', '4b18')
    assert '4b18' in [c for r in sh.ctl.preview(_raw(sh)).rows for c in r.codes]


def test_complete_line_no_ghost(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    sh.shell_box.update()
    assert not sh.shell_box.ghost and not sh.shell_box.list_shown


# ---------- Task 6: переключатель и телеметрия ----------
def test_switch_per_preset(app):
    b = app.ctl.preset_id                       # «консультация» — текущий
    a = next(p.id for p in app.ctl.presets.list() if p.id != b)
    app.shell_var.set(True)
    app._toggle_shell()
    assert app.ctl.shell_mode
    app.switch_to(a)
    assert not app.shell_var.get() and not app.ctl.shell_mode
    app.switch_to(b)
    assert app.shell_var.get() and app.ctl.shell_mode


def test_switch_back_restores_hints(app):
    app.shell_var.set(True)
    app._toggle_shell()
    app.shell_var.set(False)
    app._toggle_shell()
    app.ctl.learn('торк', '4g3')
    _type(app, 'тор')
    app.hint_box.update()
    assert app.hint_box.visible


def test_line_done_event_no_text(sh, monkeypatch):
    seen = []
    monkeypatch.setattr(sh.ctl, 'track', lambda e, **d: seen.append((e, d)))
    _type(sh, 'лигатурная')
    _key(sh, 'Tab')
    _key(sh, 'Return')
    done = [d for e, d in seen if e == 'shell' and d.get('action') == 'line_done']
    assert done and done[-1]['depth'] == 3 and done[-1]['tabs'] == 1
    assert done[-1]['typed_chars'] == len('лигатурная')
    assert 'лигатур' not in repr(seen)


def test_bad_word_event_once(sh, monkeypatch):
    seen = []
    monkeypatch.setattr(sh.ctl, 'track', lambda e, **d: seen.append((e, d)))
    _type(sh, 'эластики кв')
    _type(sh, 'а')
    assert sum(1 for e, d in seen if e == 'shell' and d.get('action') == 'bad_word') == 1

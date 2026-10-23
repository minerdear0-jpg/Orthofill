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
    assert sb.list_shown and {c[-1] for c in sb.choices} == {'2b2', '4'}    # 0.5 b8: развилка
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
    """0.5 b3: Tab на пустой строке — карусель кандидатов (первый — предсказание), текст не меняется."""
    sh.shell_box.update()
    _key(sh, 'Tab')
    sb = sh.shell_box
    assert _raw(sh) == '' and sb.list_shown and sb.choices[sb.selected] == ('1', '1a')


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


def _dwell(sh, expect: bool = True):
    """Подождать «намеренную остановку»: под нагрузкой (полный прогон) таймер
    срабатывает позже — ждём список до 2 с (или ровно паузу, если он не ожидается)."""
    import time
    end = time.monotonic() + (2.0 if expect else (sh.shell_box.dwell_ms + 150) / 1000)
    while time.monotonic() < end:
        sh.root.update()
        if expect and sh.shell_box.list_shown:
            return
        time.sleep(0.02)


def _siblings(sh):
    """Соседи уровня без ожидания таймера (его проверяет test_dwell_opens_siblings):
    на общем экране окно теста может потерять фокус, и список закроется."""
    sh.shell_box._open_siblings()
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
    _dwell(sh, expect=False)
    assert not sh.shell_box.list_shown


def test_replace_level_keeps_tail(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _key(sh, 'Left')                          # на «Смена дуги на верхней челюсти»
    _siblings(sh)
    sb = sh.shell_box
    sb.selected = [c[-1] for c in sb.choices].index('4c')
    _key(sh, 'Return')
    assert _raw(sh) == format_path(_wb(sh), ('4', '4c')) + ' › '


def test_replace_leaf(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _siblings(sh)
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


# ---------- итоговая проверка 0.5b1 ----------
def test_tab_keeps_unused_words(sh):
    _type(sh, 'верх 16')
    _key(sh, 'Tab')
    assert _raw(sh) == format_path(_wb(sh), ('4', '4b')) + ' › 16'
    assert sh.shell_box.list_shown and len(sh.shell_box.choices) == 5


def test_question_list_survives_key_release(sh):
    _type(sh, format_path(_wb(sh), ('4', '4f')) + ' › ')
    _key(sh, 'KeyPress', keysym='question')
    _key(sh, 'KeyRelease', keysym='7')          # Shift отпущен раньше «7»
    assert sh.shell_box.list_shown


def test_enter_on_not_understood_line_breaks(sh):
    _type(sh, 'квакозябра')
    _key(sh, 'Return')
    assert _raw(sh) == 'квакозябра\n'


def test_click_in_siblings_keeps_tail(sh):
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _key(sh, 'Left')
    _siblings(sh)
    sb = sh.shell_box
    k = [c[-1] for c in sb.choices].index('4c')
    sb._click(k)
    assert _raw(sh) == format_path(_wb(sh), ('4', '4c')) + ' › '
    sb_line = _raw(sh)
    _line2 = sb_line
    assert _line2.endswith(' › ')
    # тот же уровень на листе: щелчок по 4b18 — путь целиком, не обрезан
    sh.raw_txt.delete('1.0', 'end')
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _siblings(sh)
    sb._click([c[-1] for c in sb.choices].index('4b18'))
    assert _raw(sh) == format_path(_wb(sh), ('4', '4b', '4b18'))


def test_no_phrase_offer_and_no_learning_in_shell(sh, monkeypatch):
    offered = []
    monkeypatch.setattr(sh, 'phrase_bar', type('B', (), {'pack': lambda *a, **k: offered.append(1),
                                                         'pack_forget': lambda *a, **k: None})())
    sh._offer_phrase(format_path(_wb(sh), ('4', '4f', '4f1')))
    assert not offered
    asked = []
    monkeypatch.setattr(sh, '_ask_learning', lambda *a: asked.append(a))
    _type(sh, 'квакозябра')
    sh.add_entry.insert(0, 'изгиб')
    sh._on_add_query()
    sh._add_selected(0)
    assert not asked


# ---------- 0.5 b2: предсказание ----------
def _history(sh, *notes):
    for paths in notes:
        sh.ctl.generate('\n'.join(format_path(_wb(sh), p) for p in paths))
    sh.raw_txt.delete('1.0', 'end')


def _finish_line(sh, path):
    _type(sh, format_path(_wb(sh), path))
    _key(sh, 'Return')


def test_prediction_ghost_on_empty_line(sh):
    _finish_line(sh, ('2', '2b', '2b2'))
    sb = sh.shell_box
    assert sb.prediction is not None and sb.prediction.path == ('2', '2c')
    assert 'Этап' in sb.ghost and _raw(sh).endswith('\n')


def test_tab_accepts_prediction_group(sh):
    _history(sh, [('2', '2b', '2b2'), ('2', '2c', '2c3')],
             [('2', '2b', '2b2'), ('2', '2c', '2c3'), ('4', '4f', '4f1')])   # разные записи
    _finish_line(sh, ('2', '2b', '2b2'))
    _key(sh, 'Return')                                   # 0.5 b3: Enter — принять предсказание
    assert _raw(sh).split('\n')[1] == format_path(_wb(sh), ('2', '2c')) + ' › '
    sb = sh.shell_box
    assert sb.list_shown and sb.choices[sb.selected][-1] == '2c3'


def test_ctrl_right_one_level(sh):
    _finish_line(sh, ('2', '2b', '2b2'))
    _key(sh, 'Control-Right')
    assert _raw(sh).split('\n')[1] == format_path(_wb(sh), ('2',)) + ' › '
    _key(sh, 'Control-Right')
    assert _raw(sh).split('\n')[1] == format_path(_wb(sh), ('2', '2c')) + ' › '


def test_question_lists_predictions(sh):
    _finish_line(sh, ('2', '2b', '2b2'))
    _key(sh, 'KeyPress', keysym='question')
    sb = sh.shell_box
    assert sb.list_shown and sb.choices[0] == ('2', '2c') and len(sb.choices) <= 12


def test_predict_middle_line(sh):
    wb = _wb(sh)
    sh.raw_txt.insert('1.0', format_path(wb, ('2', '2b', '2b2')) + '\n\n' + format_path(wb, ('2', '2c', '2c2')))
    sh.raw_txt.mark_set('insert', '2.0')
    sh.shell_box.update()
    assert sh.shell_box.prediction.path == ('2', '2d')        # 2c уже есть ниже


def test_typing_dismisses_prediction(sh):
    _finish_line(sh, ('2', '2b', '2b2'))
    _type(sh, 'д')
    assert sh.shell_box.prediction is None and not sh.shell_box.ghost.startswith('Анамнез')
    assert _raw(sh).split('\n')[1] == 'д'


def test_enter_without_prediction_is_newline(sh, monkeypatch):
    """0.5 b3: Enter на пустой строке принимает предсказание; нет его — обычный перенос."""
    import orthofill.shellbox as sbm
    monkeypatch.setattr(sbm, 'predict', lambda *a, **k: [])
    _finish_line(sh, ('2', '2b', '2b2'))
    _key(sh, 'Return')
    assert _raw(sh).split('\n')[1:] == ['', '']


def test_lists_ranked(sh):
    _history(sh, [('4', '4b', '4b18')], [('4', '4b', '4b18'), ('4', '4f', '4f1')],
             [('4', '4b', '4b18'), ('4', '4f', '4f2')])                       # разные записи
    _type(sh, format_path(_wb(sh), ('4', '4b')) + ' › ')
    _key(sh, 'KeyPress', keysym='question')
    assert sh.shell_box.choices[0][-1] == '4b18'


def test_predict_events(sh, monkeypatch):
    seen = []
    monkeypatch.setattr(sh.ctl, 'track', lambda e, **d: seen.append((e, d)))
    _finish_line(sh, ('2', '2b', '2b2'))       # первую строку врач набрал сам — «ignored»
    seen.clear()
    _key(sh, 'Return')
    outcomes = [d['outcome'] for e, d in seen if e == 'shell' and d.get('action') == 'predict']
    assert outcomes == ['accepted']
    sh.raw_txt.delete('1.0', 'end')
    _finish_line(sh, ('2', '2b', '2b2'))
    seen.clear()
    _type(sh, 'д')
    assert [d['outcome'] for e, d in seen if e == 'shell' and d.get('action') == 'predict'] == ['ignored']


def test_modifier_release_keeps_dwell(sh):
    """Отпустили Alt/Shift/переключили раскладку после ← — остановка на уровне не сбивается."""
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    import tkinter as tk
    for ks in ('Alt_L', 'Shift_L', 'Caps_Lock', 'ISO_Next_Group', 'a'):
        try:                # ISO_Next_Group (смена раскладки) есть только в X11
            sh.raw_txt.event_generate('<KeyRelease>', keysym=ks, when='now')
        except tk.TclError:
            pass
    assert sh.shell_box._dwell_job is not None


# ---------- итоговая проверка 0.5b2 ----------
def test_arrow_up_refreshes_prediction(sh):
    wb = _wb(sh)
    sh.raw_txt.insert('1.0', format_path(wb, ('2', '2b', '2b2')) + '\n\n'
                      + format_path(wb, ('4', '4b', '4b5')) + '\n')
    sh.raw_txt.mark_set('insert', '4.0')
    sh.shell_box.update()
    assert sh.shell_box.prediction.path[1] != '2c'
    sh.raw_txt.mark_set('insert', '2.0')                 # стрелкой вверх
    _key(sh, 'KeyRelease', keysym='Up')
    assert sh.shell_box.prediction.path == ('2', '2c')
    sh.raw_txt.mark_set('insert', '4.0')
    _key(sh, 'Tab')                                      # Tab сам сверяет строку
    assert sh.raw_txt.get('4.0', '4.end') != format_path(wb, ('2', '2c')) + ' › '


def test_enter_moves_ghost(sh):
    _finish_line(sh, ('2', '2b', '2b2'))
    sh.root.update()
    sb = sh.shell_box
    assert sb._pred_line == 2 and sb.prediction is not None      # подсказка — на новой строке


def test_question_pick_prediction_logged_accepted(sh, monkeypatch):
    seen = []
    _finish_line(sh, ('2', '2b', '2b2'))
    monkeypatch.setattr(sh.ctl, 'track', lambda e, **d: seen.append((e, d)))
    _key(sh, 'KeyPress', keysym='question')
    _key(sh, 'Return')
    out = [d['outcome'] for e, d in seen if e == 'shell' and d.get('action') == 'predict']
    assert out == ['accepted']


def test_ignored_logged_once(sh, monkeypatch):
    seen = []
    _finish_line(sh, ('2', '2b', '2b2'))
    monkeypatch.setattr(sh.ctl, 'track', lambda e, **d: seen.append((e, d)))
    _type(sh, 'д')
    sh.raw_txt.delete('insert -1c', 'insert')
    sh.shell_box.update()
    _type(sh, 'д')
    out = [d['outcome'] for e, d in seen if e == 'shell' and d.get('action') == 'predict']
    assert out == ['ignored']


def test_group_from_question_list_opens_branches(sh):
    _finish_line(sh, ('2', '2b', '2b2'))
    _key(sh, 'KeyPress', keysym='question')
    _key(sh, 'Return')                                  # первый — группа «Этап»
    sb = sh.shell_box
    assert sb.list_shown and sb.choices[0][:2] == ('2', '2c')


def test_siblings_ranked(sh):
    _history(sh, [('4', '4b', '4b18')], [('4', '4b', '4b18'), ('4', '4f', '4f1')],
             [('4', '4b', '4b18'), ('4', '4f', '4f2')])
    _line_at(sh, ('4', '4b', '4b5'))
    _key(sh, 'Left')
    _siblings(sh)
    sb = sh.shell_box
    assert sb.choices[0][-1] == '4b18' and sb.choices[sb.selected][-1] == '4b5'


# ---------- 0.5 b3: Tab — карусель, Enter — подтверждение ----------
def _at_group(sh, path):
    _type(sh, format_path(_wb(sh), path) + ' › ')


def test_tab_cycles_carousel(sh):
    _at_group(sh, ('4', '4f'))
    _key(sh, 'Tab')
    sb = sh.shell_box
    assert sb.list_shown and sb.choices[sb.selected][-1] == '4f1'
    before = _raw(sh)
    _key(sh, 'Tab')
    _key(sh, 'Tab')
    assert sb.choices[sb.selected][-1] == '4f3' and _raw(sh) == before
    for _ in range(len(sb.choices) - 2):
        _key(sh, 'Tab')
    assert sb.choices[sb.selected][-1] == '4f1'                # по кругу


def test_shift_tab_back(sh):
    _at_group(sh, ('4', '4f'))
    _key(sh, 'Tab')
    sh.raw_txt.event_generate('<Shift-Tab>', when='now')
    sh.root.update()
    sb = sh.shell_box
    assert sb.selected == len(sb.choices) - 1


def test_enter_confirms_leaf(sh):
    _at_group(sh, ('4', '4f'))
    _key(sh, 'Tab')
    _key(sh, 'Tab')
    _key(sh, 'Return')
    assert _raw(sh).split('\n')[0] == format_path(_wb(sh), ('4', '4f', '4f2'))
    assert sh.raw_txt.index('insert') == '2.0'


def test_enter_on_group_opens_branches_carousel(sh):
    _finish_line(sh, ('2', '2b', '2b2'))
    _key(sh, 'Return')
    sb = sh.shell_box
    assert sb.list_shown and sb.selected == 0 and sb.choices[0][:2] == ('2', '2c')


def test_one_key_fill(sh):
    """Без истории: Enter, Enter — строка по предсказанию готова (только Enter)."""
    sh.shell_box.update()
    _key(sh, 'Return')                 # пустая строка → путь до предсказанного
    _key(sh, 'Return')                 # выбранный вариант → строка готова
    from orthofill.shell import parse_line, is_leaf
    first = _raw(sh).split('\n')[0]
    path = parse_line(_wb(sh), first)
    assert path and is_leaf(_wb(sh), path) and _raw(sh).endswith('\n')


def test_typing_narrows_carousel(sh):
    _at_group(sh, ('4', '4b'))
    _type(sh, '16')
    sb = sh.shell_box
    assert sb.list_shown and sb.selected == 0
    _key(sh, 'Tab')
    assert sb.selected == 1


def test_tab_unique_expands(sh):
    _type(sh, 'лигатурная')
    _key(sh, 'Tab')
    assert _raw(sh) == format_path(_wb(sh), ('2', '2b', '2b2'))


def test_held_tab_fast(sh, monkeypatch):
    import time
    import orthofill.shellbox as sbm
    _at_group(sh, ('4', '4b'))
    _key(sh, 'Tab')
    calls = []
    real = sbm.resolve
    monkeypatch.setattr(sbm, 'resolve', lambda *a, **k: calls.append(1) or real(*a, **k))
    t0 = time.perf_counter()
    for _ in range(60):
        sh.shell_box._tab(None)
    sh.root.update()
    assert time.perf_counter() - t0 < 1.0 and not calls


def test_siblings_carousel(sh):
    _line_at(sh, ('4', '4f', '4f1'))
    _key(sh, 'Left')
    _siblings(sh)
    _key(sh, 'Tab')
    _key(sh, 'Return')
    from orthofill.shell import parse_line
    assert parse_line(_wb(sh), _raw(sh).split('\n')[0]) == ('4', '4f', '4f2')


# ---------- → дописывает серую подсказку (как в fish) ----------
def test_right_accepts_prediction(sh):
    _finish_line(sh, ('2', '2b', '2b2'))
    _key(sh, 'Right')
    assert _raw(sh).split('\n')[1] == format_path(_wb(sh), ('2', '2c')) + ' › '
    assert not sh.shell_box.list_shown                     # только текст, без списка


def test_right_accepts_unique_completion(sh):
    _type(sh, 'лигатурная')
    _key(sh, 'Right')
    assert _raw(sh) == format_path(_wb(sh), ('2', '2b', '2b2'))


def test_right_completes_common_prefix(sh):
    _type(sh, 'ду вер')
    _key(sh, 'Right')
    assert _raw(sh) == format_path(_wb(sh), ('4', '4b')) + ' › '
    assert not sh.shell_box.list_shown


def test_right_without_ghost_moves_cursor(sh):
    _type(sh, 'квакозябра')
    sh.raw_txt.mark_set('insert', '1.2')
    _key(sh, 'Right')
    assert sh.raw_txt.index('insert') == '1.3' and _raw(sh) == 'квакозябра'


# ---------- 0.5 b7: просмотр вариантов ----------
@pytest.fixture
def shw(sh):
    sh.root.geometry('1200x700')
    sh.root.update()
    assert sh.mode == 'wide'
    return sh


def _preview_text(sb):
    return sb.preview_txt.get('1.0', 'end-1c')


def test_carousel_label_distinct(sh):
    _at_group(sh, ('3', '3e'))
    _key(sh, 'Tab')
    sb = sh.shell_box
    first = sb._rows[0].winfo_children()[0].cget('text')
    assert first.startswith('…без видимых патологических изменений')


def test_preview_shows_with_carousel(shw):
    sh = shw
    _at_group(sh, ('3', '3e'))
    _key(sh, 'Tab')
    sb = sh.shell_box
    assert sb.preview_shown and sb.preview.winfo_ismapped()
    assert _wb(sh).by_id['3e1'].text.strip() in _preview_text(sb)
    ranges = sb.preview_txt.tag_ranges('diff')
    assert ranges and sb.preview_txt.get(ranges[0], ranges[1]).startswith('без видимых')


def test_preview_follows_selection(shw):
    sh = shw
    _at_group(sh, ('3', '3e'))
    _key(sh, 'Tab')
    _key(sh, 'Tab')
    sb = sh.shell_box
    assert sb.choices[sb.selected][-1] == '3e2'
    assert _wb(sh).by_id['3e2'].text.strip() in _preview_text(sb)
    assert '3e1' in sb.preview_sib.cget('text')


def test_preview_hidden_after_close(shw):
    sh = shw
    _at_group(sh, ('3', '3e'))
    _key(sh, 'Tab')
    _key(sh, 'Escape')
    sb = sh.shell_box
    assert not sb.preview_shown and not sb.preview.winfo_ismapped()


def test_preview_over_drawer(shw):
    sh = shw
    sh.set_shell_view('drawer')
    sh.root.update()
    _at_group(sh, ('3', '3e'))
    _key(sh, 'Tab')
    sb = sh.shell_box
    assert sb.preview.winfo_ismapped() and sh.out_panel.winfo_ismapped()
    _key(sh, 'Escape')
    assert not sb.preview.winfo_ismapped() and sh.out_panel.winfo_ismapped()


def test_carousel_left_of_preview(shw):
    sh = shw
    _at_group(sh, ('3', '3e'))
    _key(sh, 'Tab')
    sb = sh.shell_box
    sh.root.update()
    assert sb.frame.winfo_rootx() + sb.frame.winfo_width() <= sb.preview.winfo_rootx() + 1


def test_no_preview_when_narrow(sh):
    _at_group(sh, ('3', '3e'))
    _key(sh, 'Tab')
    sb = sh.shell_box
    assert sh.mode == 'narrow' and sb.list_shown and not sb.preview_shown


# ---------- 0.5 b7: раскраска записи ----------
def _tagged(sh, tag):
    r = sh.raw_txt.tag_ranges(tag)
    return [sh.raw_txt.get(r[i], r[i + 1]) for i in range(0, len(r), 2)]


def test_tags_applied(sh):
    _type(sh, format_path(_wb(sh), ('2', '2b', '2b2')) + '\n' + format_path(_wb(sh), ('4', '4f')) + ' › пер')
    assert _tagged(sh, 'sh_sec2') == ['Анамнез: активация']
    assert _tagged(sh, 'sh_sec4') == ['Лечение:']
    assert 'Тип системы' in _tagged(sh, 'sh_grp')
    assert _tagged(sh, 'sh_leaf') == ['вестибулярная лигатурная.']
    assert len(_tagged(sh, 'sh_sep')) == 4
    assert _tagged(sh, 'sh_typed') == ['пер']
    from orthofill.colorize import section_color
    assert sh.raw_txt.tag_cget('sh_sec2', 'foreground') == section_color(2)


def test_current_level_highlight(sh):
    _at_group(sh, ('3', '3e'))
    _key(sh, 'Tab')
    assert sh.shell_box.list_shown
    assert _tagged(sh, 'sh_cur') == ['Слизистая:']
    _key(sh, 'Escape')
    assert _tagged(sh, 'sh_cur') == []


def test_comma_mode_no_colors(sh):
    _type(sh, format_path(_wb(sh), ('2', '2b', '2b2')))
    assert _tagged(sh, 'sh_leaf')
    sh.ctl.set_shell_mode(False)
    sh._apply_shell_mode()
    sh.root.update()
    tags = {t for t in sh.raw_txt.tag_names() if t.startswith('sh_') and sh.raw_txt.tag_ranges(t)}
    assert tags == set()

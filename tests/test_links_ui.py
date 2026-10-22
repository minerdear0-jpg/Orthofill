"""0.5 beta 7: номера строк записи и «откуда» у строк протокола (на настоящем Tk)."""
import os
import sys

import pytest

from orthofill.links import chip_color
from orthofill.shell import format_path

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


@pytest.fixture
def sh(app):
    app.ctl.set_shell_mode(True)
    app._apply_shell_mode()
    app.root.geometry('1200x700')
    app.root.update()
    return app


def _note(app, *paths):
    t = app.raw_txt
    t.delete('1.0', 'end')
    t.insert('1.0', '\n'.join(format_path(app.ctl.workbook, p) for p in paths))
    app._live_show()
    app.root.update()                   # «запись изменилась» → снова ввод
    app.set_shell_view('review')        # набор возвращает во ввод — проверка снова
    app.root.update()
    app.gutters.refresh()
    app.root.update()


def _line_of(app, needle):
    idx = app.out_txt.search(needle, '1.0', 'end')
    assert idx, needle
    return int(idx.split('.')[0])


def _chips(canvas):
    """{номер: (y центра, цвет)} кружков на колонке."""
    out = {}
    for item in canvas.find_withtag('chip'):
        n = int(canvas.gettags(item)[1][1:])
        x0, y0, x1, y1 = canvas.coords(item)
        out.setdefault(n, []).append(((y0 + y1) / 2, canvas.itemcget(item, 'fill')))
    return out


def _labels(canvas):
    return {canvas.itemcget(i, 'text') for i in canvas.find_withtag('src')}


def _y_of(text, line):
    x, y, w, h, base = text.dlineinfo(f'{line}.0')
    return y + h / 2


def test_gutters_drawn(sh):
    _note(sh, ('2', '2b', '2b2'), ('4', '4b', '4b5'))
    g = sh.gutters
    assert g.in_gutter.winfo_ismapped() and g.out_gutter.winfo_ismapped()
    left = _chips(g.in_gutter)
    assert set(left) == {1, 2} and left[2][0][1] == chip_color(2)
    assert abs(left[2][0][0] - _y_of(sh.raw_txt, 2)) <= 2
    assert {'всегда', 'по умолч.'} <= _labels(g.out_gutter)
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.see(f'{n}.0')
    sh.root.update()
    right = _chips(g.out_gutter)
    assert abs(right[2][0][0] - _y_of(sh.out_txt, n)) <= 2


def test_click_row_moves_cursor(sh):
    _note(sh, ('2', '2b', '2b2'), ('4', '4b', '4b5'), ('4', '4f', '4f1'))
    sh.raw_txt.mark_set('insert', '3.0')
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.see(f'{n}.0')
    sh.root.update()
    y = int(_y_of(sh.out_txt, n))
    sh.gutters.out_gutter.event_generate('<Button-1>', x=10, y=y, when='now')
    sh.root.update()
    assert sh.raw_txt.index('insert').split('.')[0] == '2'
    assert sh.out_txt.tag_ranges('hl')


def test_gutter_follows_scroll(sh):
    _note(sh, ('2', '2b', '2b2'), ('4', '4f', '4f3'))
    g, t = sh.gutters, sh.out_txt
    n = _line_of(sh, 'Медведь')
    t.yview_moveto(0)
    sh.root.update()
    top = _chips(g.out_gutter).get(1)
    t.see(f'{n}.0')
    sh.root.update()
    right = _chips(g.out_gutter)
    assert abs(right[2][0][0] - _y_of(t, n)) <= 2
    if top and t.dlineinfo(f'{_line_of(sh, "Тип системы")}.0'):
        assert right[1][0][0] != top[0][0]          # сдвинулся вместе с текстом


def test_comma_mode_no_gutters(app):
    app.ctl.set_shell_mode(False)
    app._apply_shell_mode()
    app.root.update()
    g = app.gutters
    assert not g.in_gutter.winfo_ismapped() and not g.out_gutter.winfo_ismapped()


def test_gutter_not_misaligned_after_protocol_edit(sh):
    _note(sh, ('2', '2b', '2b2'), ('4', '4b', '4b5'))
    t = sh.out_txt
    n = _line_of(sh, 'Тип системы')
    t.focus_force()                                  # врач пишет в протоколе
    sh.root.update()
    t.insert(f'{n}.0', 'Своя строка\n')
    t.event_generate('<KeyRelease>', keysym='Return', when='now')
    sh.root.update()
    g = sh.gutters
    right = _chips(g.out_gutter)
    for num, marks in right.items():                 # кружок — только у своей строки
        line = 'Тип системы' if num == 1 else 'Смена дуги'
        k = _line_of(sh, line)
        if t.dlineinfo(f'{k}.0'):
            assert all(abs(y - _y_of(t, k)) <= 2 for y, _ in marks)
    y = int(_y_of(t, _line_of(sh, 'Тип системы')))
    sh.raw_txt.mark_set('insert', '2.0')
    g.out_gutter.event_generate('<Button-1>', x=10, y=y, when='now')
    sh.root.update()
    assert sh.raw_txt.index('insert').split('.')[0] == '1'

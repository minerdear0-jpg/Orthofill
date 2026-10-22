"""0.5 beta 5: оболочка на всю ширину, протокол — по F2 и на финале."""
import os
import sys

import pytest

from orthofill.shell import format_path

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


@pytest.fixture
def sh(app):
    app.root.geometry('1200x700')
    app.root.update()
    app.ctl.set_shell_mode(True)
    app.shell_var.set(True)
    app._apply_shell_mode()
    app.root.update()
    return app


def _w(widget):
    widget.update_idletasks()
    return widget.winfo_width()


def _key(app, key, w=None, **kw):
    w = w or app.raw_txt
    w.focus_force()
    app.root.update()
    w.event_generate(f'<{key}>', when='now', **kw)
    app.root.update()


def test_input_full_width(sh):
    assert sh.shell_view == 'input' and not sh.out_panel.winfo_manager()
    assert _w(sh.in_panel) > 0.9 * _w(sh.body)


def test_f2_opens_drawer(sh):
    _key(sh, 'F2')
    assert sh.shell_view == 'drawer' and sh.out_panel.winfo_manager() == 'place'
    assert abs(_w(sh.out_panel) / _w(sh.body) - 0.46) < 0.05
    assert _w(sh.in_panel) > 0.9 * _w(sh.body)


def test_f2_again_closes(sh):
    _key(sh, 'F2')
    _key(sh, 'F2')
    assert sh.shell_view == 'input' and not sh.out_panel.winfo_manager()


def test_tab_button_toggles(sh):
    sh.drawer_btn.invoke()
    sh.root.update()
    assert sh.shell_view == 'drawer'


def test_drawer_keeps_focus(sh):
    _key(sh, 'F2')
    assert sh.root.focus_get() is sh.raw_txt
    _key(sh, 'KeyPress', keysym='a')
    assert sh.raw_txt.get('1.0', 'end-1c') == 'a'


def test_escape_order(sh):
    _key(sh, 'F2')
    sh.raw_txt.insert('1.0', format_path(sh.ctl.workbook, ('4', '4f')) + ' › ')
    sh.root.update()
    _key(sh, 'Tab')                              # открыть карусель
    assert sh.shell_box.list_shown
    _key(sh, 'Escape')
    assert not sh.shell_box.list_shown and sh.shell_view == 'drawer'
    _key(sh, 'Escape')
    assert sh.shell_view == 'input'


def test_comma_layout_restored(sh):
    _key(sh, 'F2')
    sh.ctl.set_shell_mode(False)
    sh.shell_var.set(False)
    sh._apply_shell_mode()
    sh.root.update()
    assert sh.out_panel.winfo_manager() == 'grid' and sh.in_panel.winfo_manager() == 'grid'
    assert _w(sh.out_panel) > 0.4 * _w(sh.body)


def test_narrow_window(sh):
    sh.root.geometry('760x700')
    sh.root.update()
    sh._on_resize(type('E', (), {'widget': sh.root, 'width': 760, 'height': 700})())
    sh.root.update()
    _key(sh, 'F2')
    assert _w(sh.out_panel) <= _w(sh.body) and _w(sh.out_panel) > 0.9 * _w(sh.body)


def test_drawer_shows_live_protocol(sh):
    sh.live_delay = 20
    sh.raw_txt.insert('1.0', format_path(sh.ctl.workbook, ('4', '4f', '4f1')))
    sh._live_show()
    _key(sh, 'F2')
    assert 'Перепел' in sh.out_txt.get('1.0', 'end-1c')


# ---------- Task 2: Ctrl+Enter — проверка в две колонки ----------
def _note(sh, *paths):
    sh.raw_txt.delete('1.0', 'end')
    sh.raw_txt.insert('1.0', '\n'.join(format_path(sh.ctl.workbook, p) for p in paths))
    sh._live_show()
    sh.root.update()


def test_confirm_opens_review(sh):
    clip = []
    sh.ctl.clipboard = clip.append
    _note(sh, ('4', '4f', '4f1'))
    sh.generate('ctrl_enter')
    sh.root.update()
    assert clip and 'Перепел' in clip[-1]
    assert sh.shell_view == 'review' and sh.out_panel.winfo_manager() == 'grid'
    assert abs(_w(sh.in_panel) / _w(sh.body) - 0.55) < 0.07


def test_typing_closes_review(sh):
    _note(sh, ('4', '4f', '4f1'))
    sh.generate('ctrl_enter')
    sh.raw_txt.insert('end', '\nл')
    sh.root.update()
    assert sh.shell_view == 'input'


def test_escape_closes_review(sh):
    _note(sh, ('4', '4f', '4f1'))
    sh.generate('ctrl_enter')
    _key(sh, 'Escape')
    assert sh.shell_view == 'input'


def test_review_recopy_edit(sh):
    clip = []
    sh.ctl.clipboard = clip.append
    _note(sh, ('4', '4f', '4f1'))
    sh.generate('ctrl_enter')
    sh.out_txt.insert('end', '\nСвоё после проверки')
    sh.generate('ctrl_enter')
    assert 'Своё после проверки' in clip[-1] and sh.shell_view == 'review'


def test_review_from_drawer(sh):
    _note(sh, ('4', '4f', '4f1'))
    _key(sh, 'F2')
    sh.generate('ctrl_enter')
    assert sh.shell_view == 'review' and sh.out_panel.winfo_manager() == 'grid'


def test_layout_events(sh, monkeypatch):
    seen = []
    monkeypatch.setattr(sh.ctl, 'track', lambda e, **d: seen.append((e, d)))
    _key(sh, 'F2')
    _key(sh, 'F2')
    _note(sh, ('4', '4f', '4f1'))
    sh.generate('ctrl_enter')
    names = [d.get('name') for e, d in seen if e == 'ui']
    assert names[:2] == ['drawer_open', 'drawer_close'] and 'review_open' in names


# ---------- итоговая проверка 0.5b5: одно окно, несколько переходов ----------
def test_full_width_after_review_and_escape(sh):
    _note(sh, ('4', '4f', '4f1'))
    sh.generate('ctrl_enter')
    _key(sh, 'Escape')
    assert sh.shell_view == 'input' and _w(sh.in_panel) > 0.9 * _w(sh.body)
    _key(sh, 'F2')
    assert _w(sh.in_panel) > 0.9 * _w(sh.body)


def test_comma_after_review_like_fresh(sh, app):
    _note(sh, ('4', '4f', '4f1'))
    sh.generate('ctrl_enter')
    sh.ctl.set_shell_mode(False)
    sh.shell_var.set(False)
    sh._apply_shell_mode()
    sh.root.update()
    body = _w(sh.body)
    assert 0.42 < _w(sh.in_panel) / body < 0.52          # как в новом окне (568/1200), не 2:3 строго
    assert str(sh.out_panel.cget('relief')) in ('flat', '') and str(sh.out_panel.cget('borderwidth')) in ('0', '')


def test_drawer_border_cleared_in_comma(sh):
    _key(sh, 'F2')
    sh.ctl.set_shell_mode(False)
    sh.shell_var.set(False)
    sh._apply_shell_mode()
    sh.root.update()
    assert str(sh.out_panel.cget('relief')) == 'flat' and str(sh.out_panel.cget('padding')) in ('0', '', '0 0 0 0', '(0,)')


def test_narrow_review_after_wide(sh):
    _note(sh, ('4', '4f', '4f1'))
    sh.generate('ctrl_enter')
    _key(sh, 'Escape')
    sh.root.geometry('760x700')
    sh.root.update()
    sh._on_resize(type('E', (), {'widget': sh.root, 'width': 760, 'height': 700})())
    sh.generate('ctrl_enter')
    sh.root.update()
    assert _w(sh.in_panel) > 0.9 * _w(sh.body) and _w(sh.out_panel) > 0.9 * _w(sh.body)


def test_f2_ignored_in_other_windows(sh):
    import tkinter as tk
    top = tk.Toplevel(sh.root)
    t = tk.Text(top)
    t.pack()
    sh.root.update()
    t.focus_force()
    sh.root.update()
    t.event_generate('<F2>', when='now')
    sh.root.update()
    assert sh.shell_view == 'input'
    top.destroy()


def test_close_event_when_shell_off(sh, monkeypatch):
    seen = []
    _key(sh, 'F2')
    monkeypatch.setattr(sh.ctl, 'track', lambda e, **d: seen.append((e, d)))
    sh.ctl.set_shell_mode(False)
    sh.shell_var.set(False)
    sh._apply_shell_mode()
    assert ('ui', {'name': 'drawer_close'}) in seen

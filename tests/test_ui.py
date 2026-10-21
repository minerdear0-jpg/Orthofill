"""Окно — на настоящем Tk (нужен дисплей)."""
import os
import shutil
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


@pytest.fixture
def app(tmp_path, order_xlsx):
    import tkinter as tk
    from orthofill.controller import Controller
    from orthofill.journal import Journal
    from orthofill.ui import App
    root = tk.Tk()
    ctl = Controller(Journal(tmp_path / "j.db"), clipboard=lambda t: None)
    a = App(root, ctl)
    ctl.clipboard = a._clipboard
    other = tmp_path / "консультация.xlsx"
    shutil.copy(order_xlsx, other)
    ctl.import_xlsx(order_xlsx)
    ctl.import_xlsx(other)
    a._show_file_status()
    yield a
    root.destroy()


def test_switch_says_clipboard_is_old(app):
    """Ревью 0.2b1: после смены пресета в окне новый протокол, а в буфере — прежний."""
    app.raw_txt.insert("1.0", "лигатурная, перепел")
    app.generate()
    first = next(p.id for p in app.ctl.presets.list() if p.name == "order")
    app.switch_to(first)
    status = app.status_lbl["text"]
    assert "в буфере прежний" in status and "Копировать" in status


# ---------- 0.2 beta 2: вид протокола ----------
def _gen(app, raw):
    app.raw_txt.delete("1.0", "end")
    app.raw_txt.insert("1.0", raw)
    app.out_txt.delete("1.0", "end")
    app.generate()


def _marked(t):
    r = t.tag_ranges("check")
    return [t.get(r[i], r[i + 1]) for i in range(0, len(r), 2)]


def test_sections_bold_and_marks(app):
    _gen(app, "лигатурная, по молярам 1, явка 5 нед")
    t = app.out_txt
    assert "section" in t.tag_names("1.0")
    assert any("Соотношение моляров" in m for m in _marked(t))
    assert "!" in app.warn_lbl["text"]


def test_edit_removes_mark(app):
    _gen(app, "лигатурная, по молярам 1")
    t = app.out_txt
    first = t.index(t.tag_ranges("check")[0])
    t.mark_set("insert", f"{first} lineend")
    t.insert("insert", " (проверено)")
    app.root.update()
    t.focus_force()
    t.event_generate("<KeyRelease>", keysym="space", when="now")
    assert "check" not in t.tag_names(f"{first} linestart")


def test_copy_has_no_marks(app):
    _gen(app, "лигатурная, по молярам 1")
    clip = app.root.clipboard_get()
    assert clip == app.ctl.last_protocol.text and "!" not in clip


def test_regenerate_resets_tags(app):
    _gen(app, "лигатурная, по молярам 1")
    _gen(app, "лигатурная, явка 6 нед")
    assert not app.out_txt.tag_ranges("check")
    assert len(app.out_txt.tag_ranges("section")) == 2 * 5


def test_narrow_marks_list_is_capped(app):
    """Смоук 0.2b2: в узком окне 6 причин съедали всю высоту — поле протокола исчезало."""
    app._relayout("narrow")
    _gen(app, "активация, самолигируемая, класс 1 по молярам, цепочка на верхней, "
              "замена дуги 18х25 тма, перепел, явка 5 нед")
    lines = app.warn_lbl["text"].splitlines()
    assert len(lines) <= 4 and "ещё" in lines[-1]


def test_marks_list_recapped_on_resize(app):
    app._relayout("wide")
    _gen(app, "активация, самолигируемая, класс 1 по молярам, цепочка на верхней, "
              "замена дуги 18х25 тма, перепел, явка 5 нед")
    assert len(app.warn_lbl["text"].splitlines()) > 4
    app._relayout("narrow")
    assert len(app.warn_lbl["text"].splitlines()) <= 4


def test_narrow_keeps_warnings_without_row(app):
    """Ревью 0.2b2: «класс не указан» (строки нет) не должно прятаться за «… и ещё»."""
    app._relayout("narrow")
    _gen(app, "активация, лигатурная, класс 1, замена дуги 18х25 тма, явка 3 нед")
    text = app.warn_lbl["text"]
    assert "⚠" in text and text.splitlines()[0].startswith("⚠")

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


# ---------- 0.2 beta 3: «Добавить пункт», словарь, непонятые слова ----------
def test_add_item_flow(app):
    copied = []
    app.ctl.clipboard = copied.append      # буфер X11 в тестах портит длинный UTF-8 на границе порций
    _gen(app, "лигатурная, изгиб 12 зуб квакозябра")
    app.add_entry.insert(0, "третьего")
    app._on_add_query()
    assert app.add_list.get(0).startswith("Изгиб третьего порядка")
    app._add_selected(0)
    assert "Юстировка дуги: Изгиб третьего порядка." in app.out_txt.get("1.0", "end")
    assert copied[-1] == app.out_txt.get("1.0", "end-1c")
    assert "section" in app.out_txt.tag_names("1.0")                 # вид протокола не потерян
    assert "квакозябра" in app.learn_text()                            # вопрос с кандидатом
    app._learn_yes()
    assert app.ctl.workbook.dictionary[0].word == "квакозябра"
    assert app.raw_txt.tag_ranges("learned") and not app.learn_text()


def test_unknown_underlined_and_cleared_per_word(app):
    _gen(app, "лигатурная, квакозябра, бармаглот")
    assert len(app.raw_txt.tag_ranges("unknown")) == 4
    s = app.raw_txt.search("квакозябра", "1.0")
    app.raw_txt.mark_set("insert", f"{s}+3c")
    app.raw_txt.insert("insert", "х")
    app.root.update()
    app.raw_txt.focus_force()
    app.raw_txt.event_generate("<KeyRelease>", keysym="x", when="now")
    assert len(app.raw_txt.tag_ranges("unknown")) == 2


def test_click_unknown_word_adds_and_learns(app):
    _gen(app, "лигатурная, изгиб 12 зуб квакозябра")
    app._open_add_for_word("квакозябра")
    app.add_entry.insert(0, "третьего")
    app._on_add_query()
    app._add_selected(0)
    assert "Юстировка дуги: Изгиб третьего порядка." in app.out_txt.get("1.0", "end")
    assert app.ctl.workbook.dictionary[0].word == "квакозябра" and not app.learn_text()


def test_learn_bar_cleared_on_generate(app):
    _gen(app, "лигатурная, изгиб 12 зуб квакозябра")
    app.add_entry.insert(0, "третьего")
    app._on_add_query()
    app._add_selected(0)
    assert app.learn_text()
    _gen(app, "лигатурная")
    assert not app.learn_text()


def test_ctrl_enter_not_eaten_by_add_entry(app):
    app.raw_txt.insert("1.0", "лигатурная")
    app.root.update()
    app.add_entry.focus_force()
    app.add_entry.event_generate("<Control-Return>", when="now")
    assert app.out_txt.get("1.0", "end-1c").startswith("Жалобы")

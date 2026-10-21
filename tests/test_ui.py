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

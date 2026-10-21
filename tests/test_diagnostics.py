"""Диагностика: при включённой галочке каждое действие пишется в JSONL."""
import json

import pytest

from orthofill.controller import Controller
from orthofill.journal import Journal


@pytest.fixture
def make_ctl(tmp_path):
    def make():
        return Controller(Journal(tmp_path / "j.db"), clipboard=lambda t: None)
    return make


def events(ctl):
    files = sorted(ctl.diag_dir.glob("diag-*.jsonl"))
    return [json.loads(line) for f in files for line in f.read_text(encoding="utf-8").splitlines()]


def test_off_by_default(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.open_file(order_xlsx)
    ctl.generate("лигатурная")
    assert not ctl.diagnostics and not ctl.diag_dir.exists()


def test_diag_dir_next_to_db(make_ctl, tmp_path):
    assert make_ctl().diag_dir == tmp_path / "diagnostics"


def test_generate_event(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.open_file(order_xlsx)
    ctl.generate("лигатурная, замена дуги верх 14x25 ss")
    ev = [e for e in events(ctl) if e["event"] == "generate"][-1]
    assert ev["raw"] == "лигатурная, замена дуги верх 14x25 ss"
    assert ev["facts"]["system_type"] == "ligature"
    assert ev["facts"]["wires"]["upper"] == [["14", "25"], "SS"]
    assert ["1", "Жалобы: активация"] in ev["lines"]
    assert any("нет в классификаторе" in w for w in ev["warnings"])
    assert ev["file"] == "order.xlsx" and len(ev["sha256"]) == 64
    assert ev["version"] == "0.1.0b1" and ev["ts"] and ev["entry_id"]


def test_copy_event_has_diff(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.open_file(order_xlsx)
    text = ctl.generate("лигатурная").text
    edited = text.replace("4 недели.", "6 недель.")
    ctl.copy(edited)
    ev = [e for e in events(ctl) if e["event"] == "copy"][-1]
    assert ev["edited"] is True and ev["raw"] == "лигатурная"
    assert "-4 недели." in ev["diff"] and "+6 недель." in ev["diff"]
    assert ev["copied"] == edited


def test_copy_unchanged_is_not_edited(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.open_file(order_xlsx)
    ctl.copy(ctl.generate("лигатурная").text)
    ev = [e for e in events(ctl) if e["event"] == "copy"][-1]
    assert ev["edited"] is False and ev["diff"] == ""


def test_save_reference_event(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.open_file(order_xlsx)
    text = ctl.generate("лигатурная, перепел").text
    ctl.save_reference("лигатурная, перепел", text)
    ev = [e for e in events(ctl) if e["event"] == "save_reference"][-1]
    assert ev["case_id"] == "2" and ev["raw"] == "лигатурная, перепел"


def test_open_file_event(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.open_file(order_xlsx)
    ev = [e for e in events(ctl) if e["event"] == "open_file"][-1]
    assert ev["file"] == "order.xlsx" and ev["status"].startswith("✓")


def test_error_event(make_ctl, order_xlsx, monkeypatch):
    import orthofill.controller as cmod
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.open_file(order_xlsx)

    def boom(*a, **k):
        raise RuntimeError("сбой")
    monkeypatch.setattr(cmod, "build_protocol", boom)
    ctl.generate("лигатурная")
    ev = [e for e in events(ctl) if e["event"] == "error"][-1]
    assert ev["where"] == "generate" and "сбой" in ev["error"] and "Traceback" in ev["traceback"]


def test_setting_persists(make_ctl):
    make_ctl().set_diagnostics(True)
    ctl = make_ctl()
    ctl.startup()
    assert ctl.diagnostics
    ctl.set_diagnostics(False)
    ctl2 = make_ctl()
    ctl2.startup()
    assert not ctl2.diagnostics


def test_toggle_is_logged(make_ctl):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.set_diagnostics(False)
    assert [e["event"] for e in events(ctl)] == ["diagnostics_on", "diagnostics_off"]

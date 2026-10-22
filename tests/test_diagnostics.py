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
    ctl.import_xlsx(order_xlsx)
    ctl.generate("лигатурная")
    assert not ctl.diagnostics and not ctl.diag_dir.exists()


def test_diag_dir_next_to_db(make_ctl, tmp_path):
    assert make_ctl().diag_dir == tmp_path / "diagnostics"


def test_generate_event(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    ctl.generate("лигатурная, замена дуги верх 14x25 ss")
    ev = [e for e in events(ctl) if e["event"] == "generate"][-1]
    assert ev["raw"] == "лигатурная, замена дуги верх 14x25 ss"
    assert ev["facts"]["system_type"] == "ligature"
    assert ev["facts"]["wires"]["upper"] == [["14", "25"], "SS"]
    assert ["1", "Жалобы: активация"] in ev["lines"]
    assert any("нет в классификаторе" in w for w in ev["warnings"])
    assert ev["preset"]["name"] == "order" and len(ev["sha256"]) == 64
    import orthofill
    assert ev["version"] == orthofill.__version__ and ev["ts"] and ev["entry_id"]


def test_copy_event_has_diff(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    text = ctl.generate("лигатурная").text
    edited = text.replace("4 недели.", "6 недель.")
    ctl.copy(edited)
    ev = [e for e in events(ctl) if e["event"] == "copy"][-1]
    assert ev["edited"] is True and ev["raw"] == "лигатурная"
    assert "-Явка на следующую активацию через 4 недели." in ev["diff"] and "+Явка на следующую активацию через 6 недель." in ev["diff"]
    assert ev["copied"] == edited


def test_copy_unchanged_is_not_edited(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    ctl.copy(ctl.generate("лигатурная").text)
    ev = [e for e in events(ctl) if e["event"] == "copy"][-1]
    assert ev["edited"] is False and ev["diff"] == ""


def test_save_reference_event(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    text = ctl.generate("лигатурная, перепел").text
    ctl.save_reference("лигатурная, перепел", text)
    ev = [e for e in events(ctl) if e["event"] == "save_reference"][-1]
    assert ev["case_id"] == "2" and ev["raw"] == "лигатурная, перепел"


def test_import_event(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    ev = [e for e in events(ctl) if e["event"] == "import"][-1]
    assert ev["file"] == "order.xlsx" and ev["status"].startswith("✓")
    assert ev["preset"]["name"] == "order" and ev["items"] == 124 and ev["references"] == 1


def test_export_and_switch_events(make_ctl, order_xlsx, tmp_path):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    first = ctl.preset_id
    ctl.export_xlsx(tmp_path / "out.xlsx")
    ctl.import_xlsx(tmp_path / "out.xlsx")
    ctl.switch_preset(first)
    names = [e["event"] for e in events(ctl)]
    assert "export" in names
    ev = [e for e in events(ctl) if e["event"] == "preset_switch"][-1]
    assert ev["to"]["name"] == "order" and ev["from"]["name"] == "out"


def test_error_event(make_ctl, order_xlsx, monkeypatch):
    import orthofill.controller as cmod
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)

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


# ---------- «Отметить ошибку» ----------
def test_mark_case_saved_even_if_diagnostics_off(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.import_xlsx(order_xlsx)
    gen = ctl.generate("лигатурная, явка 6 нед").text
    fixed = gen.replace("6 недель.", "8 недель.")
    status = ctl.mark_case("program", fixed, comment="писал 6, а надо 8")
    assert status == "Спасибо, случай сохранён"
    ev = [e for e in events(ctl) if e["event"] == "case"][-1]
    assert ev["kind"] == "program" and ev["kind_label"] == "Программа"
    assert ev["raw"] == "лигатурная, явка 6 нед" and ev["generated"] == gen
    assert ev["corrected"] == fixed and "+Явка на следующую активацию через 8 недель." in ev["diff"]
    assert ev["comment"] == "писал 6, а надо 8" and ev["corrected_raw"] is None
    assert ev["facts"]["weeks"] == 6 and ev["preset"]["name"] == "order"
    assert not ctl.diagnostics          # галочку не включили


def test_mark_case_me_keeps_corrected_raw(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.import_xlsx(order_xlsx)
    gen = ctl.generate("лигатурная, явка 6 нед").text
    ctl.mark_case("me", gen, corrected_raw="лигатурная, явка 8 нед")
    ev = [e for e in events(ctl) if e["event"] == "case"][-1]
    assert ev["kind_label"] == "Я" and ev["corrected_raw"] == "лигатурная, явка 8 нед"


def test_mark_case_unknown_default_and_no_protocol(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.import_xlsx(order_xlsx)
    assert ctl.mark_case("unknown", "x") == "Сначала сформируйте протокол"
    ctl.generate("лигатурная")
    assert ctl.mark_case("unknown", "x") == "Спасибо, случай сохранён"
    assert [e for e in events(ctl) if e["event"] == "case"][-1]["kind_label"] == "Не знаю"


def test_copy_edited_flag(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.import_xlsx(order_xlsx)
    text = ctl.generate("лигатурная").text
    ctl.copy(text)
    assert ctl.last_copy_edited is False
    ctl.copy(text + "\nправка")
    assert ctl.last_copy_edited is True
    ctl.generate("лигатурная, перепел")
    assert ctl.last_copy_edited is False


def test_note_changed_logged(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    ctl.generate("лигатурная, рабочий, перепел, явка 6 нед")
    ctl.generate("лигатурная, рабочий, перепел, явка 8 нед")
    ev = [e for e in events(ctl) if e["event"] == "note_changed"][-1]
    assert ev["before"].endswith("6 нед") and ev["after"].endswith("8 нед")


def test_note_changed_not_logged_for_next_patient(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    ctl.generate("лигатурная, рабочий, перепел, явка 6 нед")
    ctl.generate("самолигирующая, детализация, замена дуги низ 19x25 ss")
    assert not [e for e in events(ctl) if e["event"] == "note_changed"]


# ---------- 0.2 beta 3 ----------
def test_learning_events(make_ctl, order_xlsx):
    ctl = make_ctl()
    ctl.set_diagnostics(True)
    ctl.import_xlsx(order_xlsx)
    r = ctl.generate("лигатурная, квакозябра")
    ctl.find_unknown()
    ctl.add_item(r.text, "4g3")
    ctl.skip_learning("4g3")
    ctl.learn("квакозябра", "4g3")
    ctl.unlearn("квакозябра")
    names = [e["event"] for e in events(ctl)]
    assert {"add_item", "learn_skip", "learn", "learn_undo"} <= set(names)
    gen = [e for e in events(ctl) if e["event"] == "generate"][0]
    assert gen["dictionary_hits"] == []
    assert [e for e in events(ctl) if e["event"] == "unknown"][0]["words"] == ["квакозябра"]

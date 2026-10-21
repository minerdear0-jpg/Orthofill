"""Экспорт пресета в xlsx и обратное чтение: A–F, «Настройки», «Словарь»."""
import openpyxl
import pytest

from orthofill.engine import guess_settings
from orthofill.workbook import DictEntry, WorkbookError, load_workbook_file
from orthofill.xlsx_export import export_workbook


def props(wb):
    return [(i.id, i.text, i.method, i.when, i.default, i.words) for i in wb.items]


def refs(wb):
    return [(r.case_id, r.raw, r.lines) for r in wb.references]


def test_roundtrip(order_xlsx_with, tmp_path):
    wb = order_xlsx_with(("4o", "Подвязывание зуба короткой металлической лигатурой."))
    guess_settings(wb)
    wb.by_id["5d"].default = "5d3"
    wb.by_id["4b"].words = ["дуг", "проволок"]
    wb.dictionary = [DictEntry("торк", "Изгиб третьего порядка", "4g3", "2026-10-21", 2)]
    out = tmp_path / "out.xlsx"
    export_workbook(wb, out)
    wb2 = load_workbook_file(out)
    assert not wb2.problems
    assert props(wb2) == props(wb)
    assert refs(wb2) == refs(wb)
    assert wb2.dictionary == wb.dictionary


def test_file_01_has_empty_settings(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    assert wb.by_id["3f"].method is None and wb.dictionary == []


def test_unknown_method_label_is_problem(order_xlsx, tmp_path):
    wb = load_workbook_file(order_xlsx)
    out = tmp_path / "out.xlsx"
    export_workbook(wb, out)
    xl = openpyxl.load_workbook(out)
    ws = xl["Настройки"]
    ws.append(["3f", "по звёздам", None, None, None])
    xl.save(out)
    assert any("по звёздам" in p for p in load_workbook_file(out).problems)


def _sheet(tmp_path, rows):
    p = tmp_path / "x.xlsx"
    xl = openpyxl.Workbook()
    for r in rows:
        xl.active.append(r)
    xl.save(p)
    return p


def test_header_in_wrong_column(tmp_path):
    p = _sheet(tmp_path, [(None, None, "ID_CLASS", "CLASS_LIST"), (None, None, "1", "Жалобы")])
    with pytest.raises(WorkbookError, match="колонке C, а должна быть в A"):
        load_workbook_file(p)


def test_header_missing_message(tmp_path):
    p = _sheet(tmp_path, [(None, "Calibri"), ("1", "Жалобы")])
    with pytest.raises(WorkbookError, match="в колонке A должно стоять ID_CLASS"):
        load_workbook_file(p)

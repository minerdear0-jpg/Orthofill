"""Ошибки, найденные по диагностике врача (21.10.2026, сборка e7a33ad).

Записи — дословно из diag-2026-10-21.jsonl. Пункты 4o/4p/4l врач добавил
в свой классификатор (order-new.xlsx) — здесь добавляем их так же."""
import pytest

from orthofill.engine import build_protocol
from orthofill.parse import extract_facts

DOCTOR_ROWS = [
    ("4o", "Подвязывание зуба короткой металлической лигатурой."),
    ("4p", "Эластическая цепочка без шага"),
    ("4p1", " на нижней челюсти."),
    ("4p2", "на верхней челюсти."),
    ("4l", "Активация тяги"),
    ("4l1", "к минивинту в 1 сегменте."),
    ("4l2", "к минивинту в 2 сегменте."),
    ("4l3", "к минивинту в 3 сегменте."),
    ("4l4", "к минивинту в 4 сегменте."),
]


@pytest.fixture
def wb(order_xlsx_with):
    return order_xlsx_with(*DOCTOR_ROWS)


def ids(p):
    return [c for c, _ in p.lines]


# ---------- пункт без вариантов, которого нет в эталонах, — только по записи ----------
def test_new_single_item_not_always_added(wb):
    p = build_protocol(wb, "активация, система лигатурная, гигиена неудовлетворительная, "
                           "класс 1, замена лигатур на верхней, цепочка на нижней. эластики лиса.")
    assert "4o" not in ids(p)


def test_new_single_item_added_when_written(wb):
    p = build_protocol(wb, "лигатурная, подвязывание 13 зуба короткой лигатурой")
    assert "4o" in ids(p)


def test_items_from_references_still_always(wb):
    p = build_protocol(wb, "лигатурная")
    assert {"4a", "4j"} <= set(ids(p))       # осмотр, фотопротокол


# ---------- новая группа: только если о ней написано, вариант — из её фразы ----------
def test_chain_not_added_without_mention(wb):
    p = build_protocol(wb, "лигатурная, замена лигатур на верхней")
    assert "4p" not in ids(p)


def test_chain_arch_from_its_own_phrase(wb):
    p = build_protocol(wb, "лигатурная, замена лигатур на нижней, цепочка на верхней")
    assert ("4p2", "на верхней челюсти.") in p.lines
    assert "4p1" not in ids(p)


def test_chain_both_arches(wb):
    p = build_protocol(wb, "самолигируемая, цепочка на обеих челюстях")
    assert {"4p", "4p1", "4p2"} <= set(ids(p))


def test_chain_without_arch_warns(wb):
    p = build_protocol(wb, "самолигируемая, цепочка")
    assert "4p" in ids(p) and "4p1" not in ids(p) and "4p2" not in ids(p)
    assert any("цепочка" in w.lower() for w in p.warnings)


def test_minivint_segment(wb):
    p = build_protocol(wb, "лигатурная, активация тяги к минивинту во 2 сегменте")
    assert ("4l2", "к минивинту в 2 сегменте.") in p.lines
    assert not any("эластики" in w for w in p.warnings)


def test_minivint_without_segment_warns(wb):
    p = build_protocol(wb, "активация, система лигатур этап нивелирование гигиена "
                           "удовлетворительная, , замена лигатур, активация тяги к минивинту ")
    assert "4l" in ids(p) and not {"4l1", "4l2", "4l3", "4l4"} & set(ids(p))
    assert any("тяги" in w.lower() for w in p.warnings)
    assert not any("эластики" in w for w in p.warnings)


# ---------- челюсть цепочки/лигатур не переходит на дугу ----------
@pytest.mark.parametrize("raw, expected", [
    ("активация, система самолигируемая, гигиена удовлетворительная, класс 1 по молярам, "
     "цепочка на обеих челюстях, замена дуги 18 * 25 TMA  на верхней",
     {"upper": (("18", "25"), "TMA")}),
    ("эластическая цепочка на верхней, лигатуры на нижней,  замена дуги на верху 18 25 нити. "
     "ношение эластиков перепел",
     {"upper": (("18", "25"), "NiTi")}),
    # прежнее поведение: челюсть для дуги по-прежнему понимается
    ("лигатуры на нижней, верх 16х25 нити", {"upper": (("16", "25"), "NiTi")}),
    ("лигатурная дуга верх 16х25 нити явка 4 нед", {"upper": (("16", "25"), "NiTi")}),
])
def test_other_items_arch_not_used_for_wire(raw, expected):
    assert extract_facts(raw)["wires"] == expected


# ---------- лигатуры на самолигирующей системе ----------
def test_ligatures_on_self_ligating(wb):
    p = build_protocol(wb, "активация, самолигируемая, лигатуры на нижней")
    assert {"4d", "4d2"} <= set(ids(p))


def test_ligature_system_word_is_not_ligature_change():
    assert extract_facts("самолигируемая, система лигатур")["ligature_change"] is False or \
        extract_facts("самолигируемая, система лигатур")["system_type"] == "self_ligating"


# ---------- опечатки в типе системы ----------
@pytest.mark.parametrize("raw", ["система самолинируемая", "система самолиuируемая",
                                 "самолиг", "самолигирующая"])
def test_self_ligating_typos(raw):
    assert extract_facts(raw)["system_type"] == "self_ligating"


# ---------- «класс 1» без моляров/клыков ----------
def test_class_without_teeth_warns(wb):
    p = build_protocol(wb, "лигатурная, класс 1")
    assert any("класс" in w for w in p.warnings)


# ---------- юстировка ----------
def test_adjust_unrecognized_warns(wb):
    p = build_protocol(wb, "самолигируемая, юстировка изгиб 12 зуб")
    assert any("юстировка" in w for w in p.warnings)


def test_torque_is_third_order(wb):
    p = build_protocol(wb, "самолигируемая, изгиб 12 зуб - торк")
    assert "4g3" in ids(p)


# ---------- врач переименовал группу «Смена дуги на верхней челюсти» → «Смена дуги» ----------
def test_wire_group_arch_from_variants(order_xlsx):
    import openpyxl
    from orthofill.workbook import load_workbook_file
    from orthofill.engine import rule_warnings
    xl = openpyxl.load_workbook(order_xlsx)
    ws = xl.worksheets[0]
    for row in ws.iter_rows(min_col=1, max_col=2):
        if row[0].value == "4b":
            row[1].value = "Смена дуги"
    xl.save(order_xlsx)
    wb = load_workbook_file(order_xlsx)
    assert not any("дуга на верхней" in w for w in rule_warnings(wb))
    p = build_protocol(wb, "лигатурная, замена дуги верх 18х25 нити")
    assert "4b7" in ids(p) and "4c7" not in ids(p)


def test_wire_without_arch_is_reported(wb):
    p = build_protocol(wb, "самолигируемая, замена дуги 18 * 25 TMA")
    assert {"4b16", "4c16"} <= set(ids(p))
    assert any("обеих" in d for d in p.defaults)
    p = build_protocol(wb, "самолигируемая, замена дуги верх 18 * 25 TMA")
    assert not any("обеих" in d for d in p.defaults)

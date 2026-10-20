"""Регрессии из финального ревью: протокол не должен быть молча неверным."""
import pytest

from orthofill.engine import build_protocol
from orthofill.parse import extract_facts
from orthofill.workbook import load_workbook_file


@pytest.fixture
def wb(order_xlsx):
    return load_workbook_file(order_xlsx)


def ids(p):
    return [i for i, _ in p.lines]


# C1 — жалобы не выдумываются из других пунктов
@pytest.mark.parametrize("raw", [
    "лигатурная, рабочий, брекет-система удовлетворительная, явка 4 нед",
    "лигатурная, состояние брекетов норм",
    "лигатурная, гигиена хорошая, перелома нет",
])
def test_c1_no_invented_complaint(wb, raw):
    assert build_protocol(wb, raw).lines[1][0] == "1a"


def test_c1_unknown_complaint_warns(wb):
    p = build_protocol(wb, "лигатурная, жалобы на боль")
    assert any(w.startswith("жалоба не распознана") for w in p.warnings)


# C2 — срок явки из фразы про явку
def test_c2_weeks_from_visit_clause():
    assert extract_facts("лигатурная, перепел на 2 недели, явка через 4 недели")["weeks"] == 4
    assert extract_facts("2 недели назад отклеился брекет, явка 4 нед")["weeks"] == 4
    assert extract_facts("явка через 2 месяца")["weeks"] == 8


def test_c2_visit_unparsed_warns(wb):
    p = build_protocol(wb, "лигатурная, явка через пару недель")
    assert any(w.startswith("явка: срок не распознан") for w in p.warnings)


# C3 — дуги без запятых и без слова «дуга»
@pytest.mark.parametrize("raw, expected", [
    ("лигатурная рабочий дуга верх 16х25 нити низ 14 нити перепел явка 4 нед", {"4b5", "4c1"}),
    ("лигатурная, замена верх 16х25 нити", {"4b5"}),
    ("лигатурная, верх 0.019x0.025 SS", {"4b21"}),
    ("лигатурная, в/ч 19/25 сталь, н/ч 16x25 cuniti", {"4b21", "4c10"}),
    ("лигатурная, обе 17*25 тма", {"4b15", "4c15"}),
    ("лигатурная, низ 0.014 NiTi", {"4c1"}),
])
def test_c3_wires_found(wb, raw, expected):
    assert expected <= set(ids(build_protocol(wb, raw)))


def test_c3_tooth_number_is_not_wire(wb):
    assert not {"4b", "4c"} & set(ids(build_protocol(wb, "лигатурная, отклеился брекет на верх 16")))


def test_c3_unrecognised_wire_warns(wb):
    p = build_protocol(wb, "лигатурная, поставили niti")
    assert any(w.startswith("дуга: упоминание не распознано") for w in p.warnings)


# I1 — упомянуто, но не распознано: не подставлять противоположное
@pytest.mark.parametrize("raw, code", [
    ("лигатурная, гигиена неуд", "3f2"),
    ("лигатурная, гигиена не удовл", "3f2"),
    ("лигатурная, брекет-система не удовлетворительно", "3k2"),
    ("лигатурная, эрозии нет", "3e1"),
])
def test_i1_values(wb, raw, code):
    assert code in ids(build_protocol(wb, raw))


def test_i1_unknown_value_warns(wb):
    p = build_protocol(wb, "лигатурная, гигиена так себе")
    assert "гигиена: значение не распознано — выберите вручную" in p.warnings
    assert not {"3f1", "3f2"} & set(ids(p))


# I2 — отрицания
def test_i2_elastics_cancelled(wb):
    assert "4f1" not in ids(build_protocol(wb, "лигатурная, перепел отменен"))


def test_i2_wire_kept(wb):
    p = build_protocol(wb, "лигатурная, замена дуги верх 16 нити, на нижней оставили 14 нити")
    assert "4b2" in ids(p) and "4c" not in ids(p)


def test_i2_binding_without_jaw_warns(wb):
    p = build_protocol(wb, "лигатурная, подвязал 13 лигатурой")
    assert "подвязывание: челюсть не распознана — выберите вручную" in p.warnings


# I3 — несколько эластиков
def test_i3_several_elastics_warn(wb):
    p = build_protocol(wb, "лигатурная, лиса справа, кролик слева")
    assert any(w.startswith("эластики: несколько вариантов") for w in p.warnings)


# I4 — классы по сторонам
def test_i4_sided_classes_warn(wb):
    p = build_protocol(wb, "лигатурная, класс по молярам 2 справа 1 слева")
    assert any(w.startswith("класс по сторонам") for w in p.warnings)


# I5 — неизвестный тип системы
def test_i5_unknown_system(wb):
    p = build_protocol(wb, "самолиг, рабочий")
    assert "тип системы не распознан (лигатурная / самолигирующая)" in p.warnings
    assert not {"4h1", "4h2"} & set(ids(p))


# I6 — материал по умолчанию виден
def test_i6_default_material(wb):
    p = build_protocol(wb, "лигатурная, дуга верх 16х25")
    assert "материал дуги NiTi" in p.defaults


def test_kept_wire_is_not_unrecognised(wb):
    p = build_protocol(wb, "лигатурная, на нижней оставили 14 нити")
    assert not any(w.startswith("дуга: упоминание") for w in p.warnings)

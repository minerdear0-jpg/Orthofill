"""Диагностика врача 22.10.2026 (сборка 9891440): записи и найденные ошибки."""
import pytest
from conftest import ORDER

from orthofill.engine import build_protocol
from orthofill.workbook import DictEntry, load_workbook_file


@pytest.fixture
def wb():
    return load_workbook_file(ORDER)


def codes(p):
    return [c for c, _ in p.lines]


def test_metal_ligature_is_binding(wb):
    p = build_protocol(wb, 'лигатурная, нивелирование, замена дуги на верхней 016, эластические '
                           'лигатуры на верхней, металлическая лигатура на нижней.')
    assert '4e2' in codes(p) and '4d1' in codes(p) and '4d2' not in codes(p)


def test_short_metal_ligature_is_not_long_binding(order_xlsx_with):
    wb = order_xlsx_with(('4o', 'Подвязывание зуба короткой металлической лигатурой.'))
    p = build_protocol(wb, 'лигатурная, короткая металлическая лигатура 12 зуб')
    assert not {'4e1', '4e2'} & set(codes(p))


def test_named_elastic_beats_learned_word(wb):
    wb.dictionary.append(DictEntry('тяги', 'Лиса', '4f2'))
    p = build_protocol(wb, 'самолигируемая, тяги перепел')
    assert '4f1' in codes(p) and '4f2' not in codes(p)
    assert '4f2' in codes(build_protocol(wb, 'самолигируемая, тяги лиса'))
    assert '4f2' in codes(build_protocol(wb, 'самолигируемая, тяги'))


def test_adjust_detail_carried(wb):
    p = build_protocol(wb, 'самолигируемая, изгиб первого 22 брекет, гигиена неудовлетворительная')
    assert 'Юстировка дуги: Изгиб первого порядка 22 брекет.' in [r.text for r in p.rows]


def test_adjust_without_detail(wb):
    p = build_protocol(wb, 'самолигируемая, юстировка дуги изгиб первого порядка')
    assert 'Юстировка дуги: Изгиб первого порядка.' in [r.text for r in p.rows]


def test_metal_ligature_alone_is_not_elastic_ligature(wb):
    p = build_protocol(wb, 'лигатурная, металлическая лигатура на нижней')
    assert '4e2' in codes(p) and '4d2' not in codes(p)


# ---------- итоговая проверка: уточнение — только то, что сказано ----------
def _adjust_row(wb, raw):
    return next(r for r in build_protocol(wb, raw).rows if r.codes[0] == '4g')


@pytest.mark.parametrize('raw, text', [
    ('самолигируемая, изгиб первого 22 брекет и замена лигатур', 'Юстировка дуги: Изгиб первого порядка 22 брекет.'),
    ('самолигируемая, изгиб первого порядка с 13 по 23', 'Юстировка дуги: Изгиб первого порядка с 13 по 23.'),
    ('самолигируемая, изгиб второго порядка на 13 зубе', 'Юстировка дуги: Изгиб второго порядка на 13 зубе.'),
    ('самолигируемая, изгиб первого 22 брекет замена дуги 014 на нижней', 'Юстировка дуги: Изгиб первого порядка 22 брекет.'),
    ('самолигируемая, изгиб первого 22 брекет перепел', 'Юстировка дуги: Изгиб первого порядка 22 брекет.'),
    ('самолигируемая, изгиб первого порядка на верхней дуге', 'Юстировка дуги: Изгиб первого порядка.'),
    ('самолигируемая, юстировка: изгиб первого порядка 22', 'Юстировка дуги: Изгиб первого порядка 22.'),
    ('самолигируемая, изгиб первого 22 Брекет', 'Юстировка дуги: Изгиб первого порядка 22 Брекет.'),
    ('самолигируемая, юстировка торк 12', 'Юстировка дуги: Изгиб третьего порядка.'),
])
def test_adjust_detail_only_teeth(wb, raw, text):
    assert _adjust_row(wb, raw).text == text


def test_adjust_detail_is_checked(wb):
    assert _adjust_row(wb, 'самолигируемая, изгиб первого 22 брекет').check
    assert not _adjust_row(wb, 'самолигируемая, изгиб первого порядка').check


@pytest.mark.parametrize('raw', ['лигатурная, лигатура металлическая на нижней',
                                 'лигатурная, мет. лигатура на нижней',
                                 'лигатурная, металл. лигатура на нижней'])
def test_metal_ligature_word_orders(wb, raw):
    p = build_protocol(wb, raw)
    assert '4e2' in codes(p) and '4d2' not in codes(p)


def test_without_metal_ligature_is_not_binding(wb):
    p = build_protocol(wb, 'лигатурная, без металлической лигатуры')
    assert not {'4e1', '4e2'} & set(codes(p))
    assert not any('подвязывание' in w for w in p.warnings)


def test_same_word_twice_keeps_remap(wb):
    wb.dictionary.append(DictEntry('лиса', 'Медведь', '4f3'))
    p = build_protocol(wb, 'лигатурная, лиса, лиса')
    assert '4f3' in codes(p) and '4f2' not in codes(p)

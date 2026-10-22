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

"""Коды ID_CLASS: свободный код, проверка, перенос, обмен, перенумерация, каскад."""
import pytest
from conftest import ORDER

from orthofill.codes import apply_map, code_error, next_code, rename_map, renumber_map, swap_map
from orthofill.workbook import DictEntry, load_workbook_file


@pytest.fixture
def wb():
    return load_workbook_file(ORDER)


def test_next_code(wb):
    assert next_code(wb, '4d', 3) == '4d4'
    assert next_code(wb, '4', 2) == '4i'      # буква h занята сиротами 4h1/4h2
    assert next_code(wb, None, 1) == str(max(int(s.id) for s in wb.sections) + 1)


def test_code_error(wb):
    assert code_error(wb, '4d1', '4d4') is None
    assert 'уже занят' in code_error(wb, '4d1', '4d2')
    assert 'уровень' in code_error(wb, '4d1', '4x')
    assert 'нет группы' in code_error(wb, '4d1', '4x1')
    assert 'формат' in code_error(wb, '4d1', 'd41')
    assert code_error(wb, '4d1', '4d1') is None


def test_rename_group_renames_children(wb):
    assert rename_map(wb, '4d', '4i') == {'4d': '4i', '4d1': '4i1', '4d2': '4i2', '4d3': '4i3'}


def test_swap_and_cascade(wb):
    wb.references[0].lines.append(('4d1', 'на верхней челюсти.'))
    wb.dictionary.append(DictEntry('верх лиг', 'на верхней челюсти.', '4d1'))
    apply_map(wb, swap_map('4d1', '4d2', wb))
    assert wb.by_id['4d2'].text == 'на верхней челюсти.'
    assert wb.by_id['4d1'].text == 'на нижней челюсти.'
    assert ('4d2', 'на верхней челюсти.') in wb.references[0].lines
    assert wb.dictionary[-1].code == '4d2'
    assert [c.id for c in wb.by_id['4d'].children] == ['4d2', '4d1', '4d3']   # порядок вывода прежний


def test_move_variant_to_other_group(wb):
    apply_map(wb, rename_map(wb, '4e2', '4d4'))
    assert wb.by_id['4d4'].parent == '4d' and wb.by_id['4d4'] in wb.by_id['4d'].children
    assert '4e2' not in wb.by_id
    assert all(c.id != '4e2' for c in wb.by_id['4e'].children)
    items = [it.id for it in wb.items]
    assert items.index('4d4') == items.index('4d3') + 1


def test_rename_group_cascades_to_items_list(wb):
    apply_map(wb, rename_map(wb, '4d', '4i'))
    assert '4i1' in wb.by_id and wb.by_id['4i1'].parent == '4i'
    assert wb.by_id['4i'] in wb.by_id['4'].children


def test_default_follows_code(wb):
    wb.by_id['4k'].default = '4k1'
    apply_map(wb, swap_map('4k1', '4k2', wb))
    assert wb.by_id['4k'].default == '4k2'


def test_renumber_closes_gaps(wb):
    apply_map(wb, rename_map(wb, '4d3', '4d7'))
    assert renumber_map(wb, '4d') == {'4d7': '4d3'}


def test_renumber_follows_output_order(wb):
    apply_map(wb, swap_map('4d1', '4d2', wb))     # 4d2 «верхней» стоит первым
    assert renumber_map(wb, '4d') == {'4d2': '4d1', '4d1': '4d2'}


def test_variant_1_is_not_parent_of_10_to_19(wb):
    assert '4b19' in wb.by_id                     # в order.xlsx у дуг ≥10 вариантов
    assert rename_map(wb, '4b1', '4b30') == {'4b1': '4b30'}
    assert swap_map('4b1', '4b2', wb) == {'4b1': '4b2', '4b2': '4b1'}
    apply_map(wb, swap_map('4b1', '4b2', wb))
    assert wb.by_id['4b10'].parent == '4b' and '4b10' in [c.id for c in wb.by_id['4b'].children]
    assert [c.id for c in wb.by_id['4b'].children][:3] == ['4b2', '4b1', '4b3']


def test_section_descendants(wb):
    m = rename_map(wb, '4', '7')
    assert m['4b12'] == '7b12' and '3a' not in m

"""0.5 beta 1: оболочка — сопоставление строки с деревом пресета."""
import pytest

from orthofill.shell import children_of, format_path, is_leaf, parse_line, resolve
from orthofill.workbook import load_workbook_file


@pytest.fixture
def wb(order_xlsx):
    return load_workbook_file(order_xlsx)


def test_unique_word_anywhere(wb):        # «лигатурная» → один лист 2b2, путь вверх достроен
    r = resolve(wb, (), 'лигатурная', {})
    assert r.leaves == [('2', '2b', '2b2')] and r.common == ('2', '2b', '2b2')

def test_short_prefix_is_ambiguous(wb):    # «лиг»: лигатурная / лигатур / лигатурой — не угадывать
    r = resolve(wb, (), 'лиг', {})
    assert {p[-1] for p in r.choices} == {'2b2', '4d', '4e', '4h1'} and len(r.leaves) > 1

def test_ambiguous_shows_matched_nodes(wb):   # «ду» — узлы, где совпало слово, с путём
    r = resolve(wb, (), 'ду', {})
    assert {p[-1] for p in r.choices} == {'1c', '1d', '3e2', '4b', '4c', '4g', '4h1', '4h2', '5c'}
    assert r.common == ()

def test_second_word_narrows(wb):         # «ду вер» → группа 4b (21 вариант)
    assert resolve(wb, (), 'ду вер', {}).common == ('4', '4b')

def test_numbers(wb):                      # внутри 4b: «16х» → 4 материала; «16х25 ni» → 4b5
    assert [p[-1] for p in resolve(wb, ('4', '4b'), '16х', {}).leaves] == ['4b5', '4b10', '4b14', '4b18']
    assert resolve(wb, ('4', '4b'), '16х25 ni', {}).common[-1] == '4b5'
    assert resolve(wb, ('4', '4b'), '16x25 ni', {}).common[-1] == '4b5'
    assert '4b2' in [p[-1] for p in resolve(wb, ('4', '4b'), '16', {}).leaves]

def test_inflection(wb):                   # «дуга» подходит к «дуги»
    assert resolve(wb, (), 'дуга верх', {}).common == ('4', '4b')

def test_bad_word(wb):                     # «эластики кв» → bad_word == 1, leaves == []
    r = resolve(wb, (), 'эластики кв', {})
    assert r.bad_word == 1 and r.leaves == []

def test_synonym(wb):                      # словарь «торк» → 4g3
    assert resolve(wb, (), 'торк', {'торк': '4g3'}).common == ('4', '4g', '4g3')

def test_no_meaning_guess(wb):             # «хор» не находит «удовлетворительная»
    assert resolve(wb, (), 'гигиена хор', {}).leaves == []

def test_parse_and_format_roundtrip(wb):
    line = format_path(wb, ('4', '4b', '4b5'))
    assert line == 'Лечение: › Смена дуги на верхней челюсти › на верхней челюсти 0.016×0.025" NiTi'
    assert parse_line(wb, line) == ('4', '4b', '4b5')
    assert parse_line(wb, 'лигатурная, перепел') is None


def test_children_and_leaf(wb):
    assert [c.id for c in children_of(wb, None)] == ['1', '2', '3', '4', '5']
    assert [c.id for c in children_of(wb, '4f')][:2] == ['4f1', '4f2']
    assert is_leaf(wb, ('4', '4b', '4b5')) and not is_leaf(wb, ('4', '4b'))
    assert is_leaf(wb, ('4', '4j'))          # пункт без вариантов


def test_cancel_branch_in_tree(order_xlsx_with):
    wb = order_xlsx_with(('4j1', 'нет'))
    assert [c.id for c in children_of(wb, '4j')] == ['4j1']
    assert is_leaf(wb, ('4', '4j')) and is_leaf(wb, ('4', '4j', '4j1'))   # и пункт, и «нет» — конечны
    assert resolve(wb, ('4', '4j'), 'нет', {}).common == ('4', '4j', '4j1')


def test_done_path_restricts(wb):
    r = resolve(wb, ('4', '4f'), 'пер', {})
    assert r.leaves == [('4', '4f', '4f1')]


def test_empty_typed_lists_children(wb):
    r = resolve(wb, ('4', '4f'), '', {})
    assert [p[-1] for p in r.choices][:3] == ['4f1', '4f2', '4f3'] and r.bad_word is None

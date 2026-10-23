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
    r = resolve(wb, (), 'лиг', {})           # 0.5 b8: развилка — 2b2 (одно) и «Лечение ›»
    assert {p[-1] for p in r.choices} == {'2b2', '4'} and len(r.leaves) > 1
    assert {p[-1] for p in resolve(wb, ('4',), 'лиг', {}).choices} >= {'4d', '4e', '4h1'}

def test_ambiguous_shows_matched_nodes(wb):   # «ду» — узлы, где совпало слово, с путём
    r = resolve(wb, (), 'ду', {})
    assert {p[-1] for p in r.choices} == {'1', '3e2', '4', '5c'}     # 0.5 b8: развилка по разделам
    assert {p[-1] for p in resolve(wb, ('4',), 'ду', {}).choices} == {'4b', '4c', '4g', '4h1', '4h2'}
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


# ---------- 0.5 b4: ввод как угодно ----------
CUNITI = {'4b9', '4b10', '4b11', '4b12', '4b13'}


@pytest.mark.parametrize('typed', ['кунити', 'CuNiTi', 'cuniti', 'cu ni ti', 'cu niti', 'ку нити'])
def test_cuniti_all_spellings(wb, typed):
    assert {p[-1] for p in resolve(wb, ('4', '4b'), typed, {}).leaves} == CUNITI


def test_size_and_material(wb):
    assert [p[-1] for p in resolve(wb, ('4', '4b'), '16х25 кунити', {}).leaves] == ['4b10']
    assert [p[-1] for p in resolve(wb, ('4', '4b'), '.016*.025 тма', {}).leaves] == ['4b14']
    assert [p[-1] for p in resolve(wb, ('4', '4b'), '16х25 сс', {}).leaves] == ['4b18']


def test_niti_not_cuniti(wb):
    assert {p[-1] for p in resolve(wb, ('4', '4b'), '16х25 нити', {}).leaves} == {'4b5'}
    assert {p[-1] for p in resolve(wb, ('4', '4b'), 'ni-ti 16х25', {}).leaves} == {'4b5'}


def test_glued_and_split(wb):
    assert resolve(wb, (), 'фото протокол', {}).common[-1] == '4j'
    assert resolve(wb, (), 'само лиг', {}).common[-1] == '2b1'      # склейка начала слова


def test_layout_swap_fallback(wb):
    assert resolve(wb, (), 'kbufnehyfz', {}).common[-1] == '2b2'


def test_layout_only_when_no_match(wb):
    """«tma» совпадает как набрано — другая раскладка («ещф») не подмешивается."""
    r = resolve(wb, ('4', '4b'), 'tma', {})
    assert {p[-1] for p in r.leaves} == {'4b14', '4b15', '4b16', '4b17'}


def test_numbers_not_glued(wb):
    a = {p[-1] for p in resolve(wb, ('4', '4b'), '16х25', {}).leaves}
    assert a == {'4b5', '4b10', '4b14', '4b18'}
    assert {p[-1] for p in resolve(wb, ('4', '4b'), '16 25', {}).leaves} >= a


def test_comma_mode_untouched(wb):
    from orthofill.engine import build_protocol
    assert [c for c, _ in build_protocol(wb, 'т.к. боль, лигатурная, перепел').lines]


def test_synonym_any_spelling(wb):
    assert resolve(wb, (), 'TORK', {'торк': '4g3'}).common[-1] == '4g3'


def test_resolve_fast_with_canon(wb):
    import time
    t0 = time.perf_counter()
    for _ in range(200):
        resolve(wb, (), 'ду вер 16х25 кунити', {})
    assert time.perf_counter() - t0 < 1.0


# ---------- итоговая проверка 0.5b4 ----------
@pytest.mark.parametrize('done, typed', [
    (('4',), 'ск'), ((), 'с зу'), ((), 'ц эр'), (('4', '4c'), 'ё'), (('4', '4b'), 'эл'),
    (('4', '4b'), 'м'),
])
def test_layout_never_guesses_cyrillic_typos(wb, done, typed):
    """Кириллическая опечатка не превращается в пункт через другую раскладку."""
    r = resolve(wb, done, typed, {})
    assert r.leaves == [] and r.bad_word is not None


def test_latin_prefix_not_russian_word_start(wb):
    assert [p[-1] for p in resolve(wb, ('4', '4c'), '16х25 ni', {}).leaves] == ['4c5']


@pytest.mark.parametrize('typed, code', [('ключично', '3b'), ('крыловидных', '3b'),
                                         ('розовая', '3e1'), ('систем', '5a')])
def test_hyphen_parts_found(wb, typed, code):
    assert code in [p[-1] for p in resolve(wb, (), typed, {}).leaves] + \
        [p[1] for p in resolve(wb, (), typed, {}).leaves if len(p) > 1]


def test_glued_pair_needs_both_words(wb):
    assert not any(p[-1] in ('3a', '3d') for p in resolve(wb, (), 'под', {}).leaves)
    assert not any(p[-1] == '3b' for p in resolve(wb, (), 'состо', {}).leaves)


def test_cyrillic_word_with_stray_latin(order_xlsx_with):
    wb = order_xlsx_with(('4f7', 'Проволокa'))            # «a» латинская
    assert [p[-1] for p in resolve(wb, ('4', '4f'), 'проволок', {}).leaves] == ['4f7']


def test_spaced_size(wb):
    a = {p[-1] for p in resolve(wb, ('4', '4b'), '16х25', {}).leaves}
    assert {p[-1] for p in resolve(wb, ('4', '4b'), '16 х 25', {}).leaves} == a
    assert [p[-1] for p in resolve(wb, ('4', '4b'), '16 x 25 ni', {}).leaves] == ['4b5']


def test_bad_word_index_is_raw(wb):
    r = resolve(wb, ('4', '4b'), 'нити - кун', {})
    assert r.leaves == [] and r.bad_word == 2


def test_numeric_synonym(wb):
    assert resolve(wb, ('4', '4b'), '1625', {'1625': '4b5'}).common[-1] == '4b5'


def test_comma_mode_codes_unchanged(wb):
    from orthofill.engine import build_protocol
    codes = [c for c, _ in build_protocol(wb, 'лигатурная, перепел').lines]
    assert '2b2' in codes and '4f1' in codes


def test_roman_numerals_are_numbers(wb):
    """«по I классу»: I — число 1, а не буква «и» (союз «и» не находит классы)."""
    assert not any(p[-1].startswith(('3g', '3h', '3y', '3j')) for p in resolve(wb, (), 'и', {}).leaves)
    assert '3g1' in [p[-1] for p in resolve(wb, ('3', '3g'), '1', {}).leaves]
    assert [p[-1] for p in resolve(wb, ('3', '3g'), '2', {}).leaves] == ['3g2']


def test_single_letters_not_glued(wb):
    assert len(resolve(wb, (), 'ду г', {}).leaves) <= 2
    assert len(resolve(wb, (), 'с м', {}).leaves) <= 17


def test_typed_roman_and_single_latin(wb):
    assert '3g2' in [p[-1] for p in resolve(wb, ('3', '3g'), 'ii', {}).leaves]
    assert resolve(wb, ('3', '3g'), 'iii', {}).common[-1] == '3g3'
    assert resolve(wb, (), 'аппарат s', {}).leaves == []          # «s» ≠ предлог «с»


# ---------- 0.5 b8: точное имя родителя ----------
def test_exact_parent_name_narrows(wb):
    r = resolve(wb, (), 'лечение', {})
    assert r.common == ('4',) and all(p[0] == '4' for p in r.leaves)


def test_exact_parent_other_layout(wb):
    assert resolve(wb, (), 'ktxtybt', {}).common == ('4',)


def test_not_exact_keeps_all(wb):
    r = resolve(wb, (), 'лечен', {})
    assert {p[0] for p in r.leaves} >= {'2', '4'}


def test_same_name_twice_keeps_both(wb):
    r = resolve(wb, ('4',), 'на верхней челюсти', {})
    assert {p[1] for p in r.leaves} >= {'4d', '4e'}


# ---------- 0.5 b8: развилка и «начинается с» ----------
def test_fork_branches(wb):
    r = resolve(wb, (), '014', {})
    assert r.common == ('4',)
    assert r.choices == [('4', '4b'), ('4', '4c')]
    assert r.counts[('4', '4b')] == 3 and r.counts[('4', '4c')] == 3


def test_fork_inside_branch_gives_values(wb):
    r = resolve(wb, ('4', '4b'), '014', {})
    assert len(r.choices) == 3 and all(len(p) == 3 for p in r.choices)


def test_single_value_branch_collapses(wb):
    r = resolve(wb, (), 'осмо', {})
    assert ('4', '4a') in r.choices and ('3',) in r.choices
    assert r.counts[('3',)] == 3
    assert ('4', '4a') in r.starts and not any(p[0] == '1' for p in r.starts)


def test_unique_unchanged(wb):
    r = resolve(wb, (), 'перепел', {})
    assert r.leaves == [('4', '4f', '4f1')]

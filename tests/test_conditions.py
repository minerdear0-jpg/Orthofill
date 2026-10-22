"""Логика полей в движке: условия по фактам записи, пары «не вместе», И/ИЛИ."""
import pytest
from conftest import ORDER

from orthofill.engine import build_protocol, guess_condition
from orthofill.workbook import DictEntry, load_workbook_file


@pytest.fixture
def wb():
    return load_workbook_file(ORDER)


def codes(p):
    return [c for c, _ in p.lines]


def checked(p, code):
    return any(code in r.codes and r.check for r in p.rows)


def test_guessed_condition_keeps_old_behaviour(wb):
    assert guess_condition(wb.by_id['4h1'], wb) == {'all': [{'field': '2b', 'is': '2b2'}]}
    assert guess_condition(wb.by_id['4h2'], wb) == {'all': [{'field': '2b', 'is': '2b1'}]}
    assert guess_condition(wb.by_id['4a'], wb) is None
    assert '4h1' in codes(build_protocol(wb, 'лигатурная, осмотр'))
    assert '4h1' not in codes(build_protocol(wb, 'самолигирующая, осмотр'))
    assert '4h2' in codes(build_protocol(wb, 'самолигирующая, осмотр'))
    assert not {'4h1', '4h2'} & set(codes(build_protocol(wb, 'осмотр')))   # тип не назван


def test_not_on_unknown_field_prints_nothing(wb):
    wb.by_id['4a'].when = 'condition'
    wb.by_id['4a'].condition = {'all': [{'field': '2b', 'is': '2b1', 'not': True}]}
    assert '4a' not in codes(build_protocol(wb, 'перепел'))
    assert '4a' in codes(build_protocol(wb, 'лигатурная'))
    assert '4a' not in codes(build_protocol(wb, 'самолигирующая'))


def test_default_is_not_a_fact(wb):
    wb.by_id['4a'].when = 'condition'
    wb.by_id['4a'].condition = {'all': [{'field': '2c', 'is': '2c2'}]}
    assert '2c2' in codes(build_protocol(wb, 'лигатурная'))          # этап подставлен
    assert '4a' not in codes(build_protocol(wb, 'лигатурная'))
    assert '4a' in codes(build_protocol(wb, 'лигатурная, этап рабочий'))


def test_preset_default_is_not_a_fact(wb):
    wb.by_id['4k'].default = '4k1'
    wb.by_id['4a'].when = 'condition'
    wb.by_id['4a'].condition = {'all': [{'field': '4k', 'is': '4k1'}]}
    assert '4a' not in codes(build_protocol(wb, 'лигатурная'))


def test_narrowing_condition_on_always(wb):
    wb.by_id['4a'].condition = {'all': [{'field': '2b', 'is': '2b2'}]}      # 4a — «всегда»
    assert '4a' in codes(build_protocol(wb, 'лигатурная'))
    assert '4a' not in codes(build_protocol(wb, 'самолигирующая'))


def test_condition_on_mentioned_item(wb):
    wb.by_id['4a'].when = 'condition'
    wb.by_id['4a'].condition = {'all': [{'field': '4j', 'mentioned': True}]}
    assert '4a' not in codes(build_protocol(wb, 'лигатурная'))
    assert '4a' in codes(build_protocol(wb, 'лигатурная, фотопротокол'))


def test_doctor_word_prints_with_check(wb):
    wb.dictionary.append(DictEntry('клипсы', wb.by_id['4h2'].text, '4h2'))
    p = build_protocol(wb, 'лигатурная, клипсы')
    assert '4h2' in codes(p) and checked(p, '4h2') and not checked(p, '4h1')


def test_pair_flags_both(wb):
    wb.not_together = [('4h1', '4h2')]
    wb.dictionary.append(DictEntry('клипсы', wb.by_id['4h2'].text, '4h2'))
    p = build_protocol(wb, 'лигатурная, клипсы')
    assert {'4h1', '4h2'} <= set(codes(p)) and checked(p, '4h1')
    assert any('не бывают вместе' in w for w in p.warnings)
    assert not any('не бывают' in w for w in build_protocol(wb, 'лигатурная').warnings)


def test_elastics_or_two_mentioned_both_checked(wb):
    p = build_protocol(wb, 'лигатурная, эластики перепел и лиса')
    assert {'4f1', '4f2'} <= set(codes(p)) and checked(p, '4f1')
    assert any('несколько вариантов' in w and 'проверьте' in w for w in p.warnings)


def test_elastics_and(wb):
    wb.by_id['4f'].combine = 'and'
    p = build_protocol(wb, 'лигатурная, эластики перепел и лиса')
    assert {'4f1', '4f2'} <= set(codes(p)) and not checked(p, '4f1')
    assert not any('эластики' in w for w in p.warnings)


def test_adjust_two_orders(wb):
    p = build_protocol(wb, 'лигатурная, юстировка изгиб первого и второго порядка')
    assert {'4g1', '4g2'} <= set(codes(p)) and checked(p, '4g1')
    wb.by_id['4g'].combine = 'and'
    p = build_protocol(wb, 'лигатурная, юстировка изгиб первого и второго порядка')
    assert {'4g1', '4g2'} <= set(codes(p)) and not checked(p, '4g1')


def test_words_group_and(order_xlsx_with):
    wb = order_xlsx_with(('4q', 'Рекомендовано'), ('4q1', 'ирригатор.'), ('4q2', 'ершик.'))
    assert '4q' not in codes(build_protocol(wb, 'лигатурная'))
    p = build_protocol(wb, 'лигатурная, рекомендовано ирригатор и ершик')
    assert {'4q1', '4q2'} <= set(codes(p)) and checked(p, '4q1')       # ИЛИ: оба, проверьте
    assert any('несколько вариантов' in w for w in p.warnings)
    wb.by_id['4q'].combine = 'and'          # «по словам» и так с «проверьте», но без спора
    p = build_protocol(wb, 'лигатурная, рекомендовано ирригатор и ершик')
    assert {'4q1', '4q2'} <= set(codes(p))
    assert not any('несколько вариантов' in w for w in p.warnings)


def test_references_unchanged(wb):
    """Эталоны order.xlsx совпадают и после логики полей (файлы врача — в журнале выпуска)."""
    from orthofill.engine import check_references
    assert all(r.ok for r in check_references(wb))


# ---------- итоговая проверка: факты только из записи ----------
def _cond(wb, code, node, when='always'):
    wb.by_id[code].when, wb.by_id[code].condition = when, node


@pytest.mark.parametrize('raw, node', [
    ('система лигатурная, смена дуги на верхней 014', {'all': [{'field': '4b', 'mentioned': True, 'not': True}]}),
    ('система лигатурная, смена дуги на верхней', {'all': [{'field': '4b', 'mentioned': True, 'not': True}]}),
    ('система лигатурная, эластики назначены', {'all': [{'field': '4f', 'mentioned': True, 'not': True}]}),
    ('система лигатурная, замена лигатур', {'all': [{'field': '4d', 'mentioned': True, 'not': True}]}),
    ('система лигатурная, явка', {'all': [{'field': '5d', 'is': '5d2'}]}),
    ('система лигатурная, явка через 5 недель', {'all': [{'field': '5d', 'is': '5d2'}]}),
    ('система лигатурная, смена дуги 014', {'all': [{'field': '4c', 'is': '4c1'}]}),
    ('система лигатурная', {'all': [{'field': '4p', 'mentioned': True, 'not': True}]}),   # 4p нет
])
def test_guess_is_not_a_fact(wb, raw, node):
    _cond(wb, '4j', node)
    assert '4j' not in codes(build_protocol(wb, raw))


def test_real_mention_still_works(wb):
    _cond(wb, '4j', {'all': [{'field': '4b', 'mentioned': True}]})
    assert '4j' in codes(build_protocol(wb, 'система лигатурная, смена дуги на верхней 014 нити'))
    _cond(wb, '4j', {'all': [{'field': '4f', 'mentioned': True, 'not': True}]})
    assert '4j' in codes(build_protocol(wb, 'система лигатурная'))     # эластики не названы — да
    _cond(wb, '4j', {'all': [{'field': '5d', 'is': '5d2'}]})
    assert '4j' in codes(build_protocol(wb, 'система лигатурная, явка через 4 недели'))

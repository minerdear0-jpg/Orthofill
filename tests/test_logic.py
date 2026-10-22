"""Язык условий: разбор и запись текста xlsx, трёхзначное вычисление."""
import pytest

from orthofill.logic import Facts, evaluate, format, has_positive, is_simple, parse, refs, remap

F = Facts(known={'2b': {'2b1'}}, mentioned={'2b', '4p'})
CODES = {'2b', '2b1', '2b2', '4p', '4d'}


def test_eval_three_valued():
    assert evaluate({'field': '2b', 'is': '2b1'}, F) is True
    assert evaluate({'field': '2b', 'is': '2b2'}, F) is False
    assert evaluate({'field': '2c', 'is': '2c1'}, F) is None


def test_not_unknown_stays_unknown():
    assert evaluate({'field': '2c', 'is': '2c1', 'not': True}, F) is None
    assert evaluate({'field': '2b', 'is': '2b2', 'not': True}, F) is True


def test_all_any():
    t, n, f = {'field': '2b', 'is': '2b1'}, {'field': '2c', 'is': '2c1'}, {'field': '2b', 'is': '2b2'}
    assert evaluate({'all': [t, n]}, F) is None and evaluate({'all': [f, n]}, F) is False
    assert evaluate({'all': [t, t]}, F) is True
    assert evaluate({'any': [t, n]}, F) is True and evaluate({'any': [f, n]}, F) is None
    assert evaluate({'any': [f, f]}, F) is False
    assert evaluate({'all': [t], 'not': True}, F) is False


def test_mentioned_two_valued():
    assert evaluate({'field': '4p', 'mentioned': True}, F) is True
    assert evaluate({'field': '4d', 'mentioned': True, 'not': True}, F) is True
    assert evaluate(None, F) is True                       # нет условия — не мешает


def test_parse_format_roundtrip():
    t = parse('2b = 2b2 и не 4p', CODES)
    assert t == {'all': [{'field': '2b', 'is': '2b2'}, {'field': '4p', 'mentioned': True, 'not': True}]}
    assert format(t) == '2b = 2b2 И НЕ 4p'
    assert parse('4p упомянут', CODES) == {'all': [{'field': '4p', 'mentioned': True}]}
    assert parse('2b=2b1 ИЛИ 2b = 2b2', CODES)['any'][1] == {'field': '2b', 'is': '2b2'}
    hard = '(2b = 2b1 ИЛИ 2b = 2b2) И 4d'
    assert format(parse(hard, CODES)) == hard
    assert not is_simple(parse(hard, CODES)) and is_simple(t)
    assert parse('  ', CODES) is None and format(None) == ''


def test_parse_errors():
    with pytest.raises(ValueError, match='не знаю код 4x'):
        parse('4x = 4x1', {'4p'})
    with pytest.raises(ValueError, match='после «2b»'):
        parse('2b 2b1', CODES)
    with pytest.raises(ValueError, match='скобк'):
        parse('(2b = 2b1', CODES)


def test_refs_remap_positive():
    t = {'all': [{'field': '2b', 'is': '2b2'}, {'field': '4p', 'mentioned': True, 'not': True}]}
    assert refs(t) == {'2b', '2b2', '4p'}
    r = remap(t, {'4p': '4q', '2b2': '2b1'})
    assert r['all'][1]['field'] == '4q' and r['all'][0]['is'] == '2b1' and t['all'][1]['field'] == '4p'
    assert has_positive(t)
    assert not has_positive({'all': [{'field': '4p', 'mentioned': True, 'not': True}]})
    assert not has_positive({'any': [t, {'field': '4d', 'mentioned': True, 'not': True}]})

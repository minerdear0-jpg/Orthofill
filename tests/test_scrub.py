import pytest

from orthofill.scrub import scrub_event, scrub_text


@pytest.mark.parametrize('raw, out', [
    ('Иванова Мария Петровна, брекеты', '‹ФИО›, брекеты'),
    ('пац. Петров И.И. замена дуги', 'пац. ‹ФИО› замена дуги'),
    ('И. И. Петров жалоб нет', '‹ФИО› жалоб нет'),
    ('лигатурная, петров и.и.', 'лигатурная, ‹ФИО›'),
    ('отклеился один т.е. нижний', 'отклеился один т.е. нижний'),
    ('иван иванович, активация', '‹ФИО›, активация'),
    ('Маша жалуется на боль', '‹ФИО› жалуется на боль'),
    ('у Ольги Сергеевны отклеился', 'у ‹ФИО› отклеился'),
    ('класс по Энглу, 18х25 тма', 'класс по Энглу, 18х25 тма'),
    ('Лигатурная, перепел', 'Лигатурная, перепел'),
    ('сверху слева, левой стороны', 'сверху слева, левой стороны'),
    ('дуга симметрична, ровна', 'дуга симметрична, ровна'),
    ('Т.к. боль, нед. 0.016 нити', 'Т.к. боль, нед. 0.016 нити'),
])
def test_scrub_text(raw, out):
    assert scrub_text(raw)[0] == out


def test_count():
    assert scrub_text('Иванова Мария Петровна и Петров И.И.')[1] == 2
    assert scrub_text('лигатурная')[1] == 0


def test_short_keep_words_do_not_protect_initials():
    assert scrub_text('Петров И.И.', keep=frozenset({'и'}))[0] == '‹ФИО›'


def test_keep_words_untouched():
    assert scrub_text('Мария', keep=frozenset({'мария'}))[0] == 'Мария'


def test_scrub_event_nested():
    ev = {'event': 'generate', 'raw': 'Петров И.И.', 'lines': [['4g3', 'Иван Иванович']], 'n': 3}
    out = scrub_event(ev)
    assert out['raw'] == '‹ФИО›' and out['lines'][0][1] == '‹ФИО›'
    assert out['scrubbed'] == 2 and out['n'] == 3 and out['lines'][0][0] == '4g3'
    assert ev['raw'] == 'Петров И.И.'      # исходный не изменён


def test_clean_event_has_no_counter():
    assert 'scrubbed' not in scrub_event({'raw': 'лигатурная'})

"""0.3 beta 2: привычки ввода — хвост фразы и следующая фраза."""
from orthofill.habits import Habits, continuation, phrases_of

NOTES = ['активация, лигатурная, замена дуги верх 18х25 тма, явка 6 нед',
         'активация, лигатурная, замена дуги верх 18х25 тма, перепел',
         'активация, самолиг, замена лигатур']


def test_phrases_of():
    assert phrases_of('активация,  лигатурная;\nзамена дуги ,') == ['активация', 'лигатурная', 'замена дуги']


def test_tail_of_habitual_phrase():
    h = Habits(NOTES)
    assert h.tail('замена дуги') == ' верх 18х25 тма'
    assert h.tail('ЗАМЕНА д') == 'уги верх 18х25 тма'


def test_needs_two_uses():
    assert Habits(NOTES).tail('замена лиг') == ''


def test_whole_phrase_typed_has_no_tail():
    assert Habits(NOTES).tail('замена дуги верх 18х25 тма') == ''


def test_next_phrase():
    h = Habits(NOTES)
    assert h.next_phrase('активация') == 'лигатурная'
    assert h.next_phrase('Лигатурная') == 'замена дуги верх 18х25 тма'
    assert h.next_phrase('замена лигатур') == ''


def test_fresher_wins_on_tie():
    h = Habits(['а, замена дуги низ', 'а, замена дуги низ', 'а, замена дуги верх', 'а, замена дуги верх'])
    assert h.tail('замена ду') == 'ги низ'                # новые первыми: «низ» свежее


def test_continuation():
    h = Habits(NOTES)
    assert continuation('активация, лигатурная, ', h) == 'замена дуги верх 18х25 тма'
    assert continuation('активация,', h) == ' лигатурная'
    assert continuation('активация, замена ду', h) == 'ги верх 18х25 тма'
    assert continuation('активация, за', h) == ''            # < 3 символов
    assert continuation('', h) == ''


def test_controller_continuation(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    for raw in NOTES[:2]:
        ctl.generate(raw)
    assert ctl.continuation('замена ду') == 'ги верх 18х25 тма'
    assert ctl.continuation('активация, ') == 'лигатурная'

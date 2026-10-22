"""0.5 beta 4: приведение слов — регистр, алфавиты, звучание, знаки."""
import pytest

from orthofill.canon import canon, layout_swap, spellings


@pytest.mark.parametrize('a, b', [
    ('кунити', 'CuNiTi'), ('cuniti', 'СuNiTi'), ('ni-ti', 'нити'), ('tma', 'ТМА'),
    ('ss', 'сс'), ('Перепёл', 'перепел'), ('NiTi', 'нити'), ('Ni.Ti', 'niti'),
])
def test_same_canon(a, b):
    assert canon(a) == canon(b)


def test_different_stay_different():
    assert canon('niti') != canon('cuniti') and canon('tma') != canon('ss')


def test_layout_swap():
    assert layout_swap('kbufnehyfz') == 'лигатурная'
    assert layout_swap('лшт') == 'kin'


def test_spellings():
    assert spellings('kbufnehyfz') == [canon('kbufnehyfz'), canon('лигатурная')]

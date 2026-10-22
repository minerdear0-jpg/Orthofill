"""Приведение слов (0.5 b4): врач пишет как удобно — программа сравнивает
звуковой вид. Регистр, «ё», знаки внутри слова, смесь алфавитов («СuNiTi» с
кириллической «С»), латиница ↔ кириллица по звучанию. Однозначные правила,
без «похоже»: разные слова остаются разными («нити» ≠ «кунити»)."""
from __future__ import annotations

import re

from .addition import _EN, _RU

_PUNCT = re.compile(r'''[-.'"/_’`]''')
_LAT = re.compile(r'[a-z]')
# кириллица, похожая на латиницу, — в словах со смесью алфавитов
_LOOKALIKE = str.maketrans('авекмнорстух', 'abekmhopctyx')
_LOOKALIKE_BACK = str.maketrans('abekmhopctyx', 'авекмнорстух')
_CYR = re.compile(r'[а-я]')
_PAIRS = [('sch', 'щ'), ('sh', 'ш'), ('ch', 'ч'), ('zh', 'ж'), ('ts', 'ц'), ('ya', 'я'),
          ('yu', 'ю'), ('yo', 'е'), ('kh', 'х'), ('ph', 'ф')]
_ONE = dict(zip('abcdefghijklmnopqrstuvwxyz',
                ['а', 'б', 'к', 'д', 'е', 'ф', 'г', 'х', 'и', 'й', 'к', 'л', 'м', 'н', 'о',
                 'п', 'к', 'р', 'с', 'т', 'у', 'в', 'в', 'кс', 'ы', 'з']))
_SWAP = str.maketrans(_EN + _RU, _RU + _EN)


def is_latin(word: str) -> bool:
    """Слово набрано (записано) латиницей: латинских букв больше, чем кириллических."""
    w = word.lower()
    lat = len(_LAT.findall(w))
    return lat > 0 and lat >= len(_CYR.findall(w.replace("ё", "е")))   # ничья — латиница


def canon(word: str) -> str:
    w = _PUNCT.sub('', word.lower().replace('ё', 'е'))
    if _LAT.search(w) and _CYR.search(w) and not is_latin(w):
        return w.translate(_LOOKALIKE_BACK)      # «проволокa» с латинской «a» — русское слово
    if _LAT.search(w):
        w = w.translate(_LOOKALIKE)
        for a, b in _PAIRS:
            w = w.replace(a, b)
        w = ''.join(_ONE.get(ch, ch) for ch in w)
    return w


def layout_swap(word: str) -> str:
    """Набрано не в той раскладке: ЙЦУКЕН ↔ QWERTY."""
    return word.lower().translate(_SWAP)


def spellings(word: str) -> list[str]:
    """Как набрано и (запасной вариант) в другой раскладке."""
    return [canon(word), canon(layout_swap(word))]

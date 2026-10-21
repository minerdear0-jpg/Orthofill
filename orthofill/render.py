"""Вывод протокола: группа и вариант — одной строкой, без повторов.
Модель протокола — пункты (коды); здесь только то, как они читаются глазами."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .text import norm

_EDGE = re.compile(r'^[^\w]+|[^\w]+$')


@dataclass
class Row:
    text: str
    codes: tuple[str, ...]
    section: bool = False
    check: list[str] = field(default_factory=list)   # причины «проверьте»


def _ws(text: str) -> str:
    return ' '.join(text.split())


def _key(word: str) -> str:
    return _EDGE.sub('', norm(word))


def join_group(group_text: str, variant_text: str) -> str:
    """«Смена дуги на верхней челюсти» + «на верхней челюсти 0.018"…» →
    «Смена дуги на верхней челюсти 0.018"….»; вариант, уже начинающийся с
    текста группы («Тип системы: …»), — как есть."""
    group, variant = _ws(group_text), _ws(variant_text)
    g = group.rstrip(':').split()
    v = variant.split()
    gk, vk = [_key(w) for w in g], [_key(w) for w in v]
    if not v:
        return group
    if vk[:len(gk)] == gk:                       # вариант начинается со всей группы
        return variant
    overlap = next((k for k in range(min(len(gk), len(vk)), 0, -1) if gk[-k:] == vk[:k]), 0)
    if overlap:
        out = ' '.join(g + v[overlap:])
    elif variant[0].isupper():
        out = f'{" ".join(g)}: {variant}'
    else:
        out = f'{" ".join(g)} {variant}'
    return out if out[-1] in '.:!?' else out + '.'

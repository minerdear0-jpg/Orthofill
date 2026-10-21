"""Непонятые слова записи — самопроверкой (разбор ТРИЗ, 22.10): слово «понято»,
если без него протокол меняется, если оно есть в текстах пунктов пресета или в
словаре врача. Ручного списка «понятных» слов нет: проверка сама верна для
любых правил и пресетов."""
from __future__ import annotations

import re

from .engine import build_protocol
from .text import norm, word_stem
from .workbook import Workbook

SERVICE = frozenset('на и по с со в во к ко о об от до за из у а не ни да при для или но же '
                    'то это'.split())
_TOKEN = re.compile(r'[^\s,;:.()«»"!?]+')


def _signature(wb: Workbook, raw: str):
    p = build_protocol(wb, raw)
    return [c for c, _ in p.lines], p.warnings, p.defaults


def _known_stems(wb: Workbook) -> set[str]:
    words = set()
    for it in wb.items:
        words.update(w for w in re.findall(r'[а-яa-z]+', norm(it.text)) if len(w) >= 3)
    for e in wb.dictionary:
        words.update(w for w in norm(e.word).split() if len(w) >= 3)
    return {word_stem(w) for w in words}


def unknown_words(wb: Workbook, raw: str) -> list[tuple[int, int, str]]:
    """[(начало, конец, слово)] в исходной записи — слова, которые программа не поняла."""
    known = _known_stems(wb)
    groups: dict[str, list[tuple[int, int, str]]] = {}
    for m in _TOKEN.finditer(raw):
        tok = m.group().strip('-/')
        n = norm(tok)
        if not n or re.search(r'\d', n) or n in SERVICE or len(n) < 2:
            continue
        if any(n.startswith(st) for st in known):
            continue
        groups.setdefault(word_stem(n), []).append((m.start(), m.end(), m.group()))
    if not groups:
        return []
    base = _signature(wb, raw)
    out = []
    for spans in groups.values():
        chars = list(raw)
        for s, e, _ in spans:
            chars[s:e] = ' ' * (e - s)
        if _signature(wb, ''.join(chars)) == base:
            out += spans
    return sorted(out)

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
# Слова-связки записи: правило их не требует (смысл несут соседние слова), но и
# «непонятыми» они не являются — без них протокол не меняется, поэтому
# самопроверка подчеркнула бы их зря
FILLER = frozenset('замена заменили заменена заменён заменен смена сменили поменяли '
                   'установлена установлен установили поставили зуб зуба зубов зубу '
                   'челюсть челюсти'.split())
_TOKEN = re.compile(r'[^\s,;:.()«»"!?]+')


def signature(p) -> tuple:
    """Что считается «протокол изменился»: пункты, предупреждения, строки по умолчанию."""
    return [c for c, _ in p.lines], p.warnings, p.defaults


def _known(wb: Workbook) -> tuple[set[str], set[str]]:
    """Слова пресета и словаря: целиком — любые; по основе — только основы от 4 букв
    (иначе «при», «сле», «тре» прячут «приклеен», «слетела», «треснул»)."""
    words = set()
    for it in wb.items:
        words.update(re.findall(r'[а-яa-z]+', norm(it.text)))
    for e in wb.dictionary:
        words.update(norm(e.word).split())
    long_stems = {word_stem(w) for w in words if len(word_stem(w)) >= 4}
    all_stems = {word_stem(w) for w in words}
    return words | all_stems, long_stems


def unknown_words(wb: Workbook, raw: str, base: tuple | None = None) -> list[tuple[int, int, str]]:
    """[(начало, конец, слово)] в исходной записи — слова, которые программа не поняла.
    base — signature() уже построенного протокола (чтобы не строить его заново)."""
    words, stems = _known(wb)
    groups: dict[str, list[tuple[int, int, str]]] = {}
    for m in _TOKEN.finditer(raw):
        tok = m.group().strip('-/')
        n = norm(tok)
        if not n or re.search(r'\d', n) or n in SERVICE or len(n) < 2:
            continue
        if n in FILLER or n in words or word_stem(n) in words \
                or any(n.startswith(st) for st in stems):
            continue
        groups.setdefault(word_stem(n), []).append((m.start(), m.end(), m.group()))
    if not groups:
        return []
    if base is None:
        base = signature(build_protocol(wb, raw))
    out = []
    for spans in groups.values():
        chars = list(raw)
        for s, e, _ in spans:
            chars[s:e] = ' ' * (e - s)
        if signature(build_protocol(wb, ''.join(chars))) == base:
            out += spans
    return sorted(out)

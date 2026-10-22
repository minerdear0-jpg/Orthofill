"""Подсказки при наборе записи (как IntelliSense): слова по началу.

Источники по порядку: словарь врача (что программа точно поймёт), прошлые
записи врача из журнала (его язык, по частоте), слова пунктов пресета.
«Во что превратится» пишется, только когда это известно наверняка: слово
словаря или слово, которое есть ровно в одном пункте."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .addition import _EN_RU, _choices, row_text
from .vocab import FILLER, SERVICE
from .workbook import Workbook

MIN_PREFIX = 3
_WORD = re.compile(r'[а-яёa-z]+')


@dataclass
class Hint:
    word: str
    becomes: str        # во что превратится; '' — неизвестно
    kind: str           # 'doctor' — ваше слово · 'history' — из ваших записей · 'item' — пункт


def _key(word: str) -> str:
    return word.lower().replace('ё', 'е')


def words_of(text: str) -> list[str]:
    """Слова записи для истории: ≥3 букв, без служебных и чисел."""
    return [w for w in _WORD.findall(text.lower())
            if len(w) >= MIN_PREFIX and w not in SERVICE]


class HintIndex:
    def __init__(self, entries: list[Hint]):
        self.entries = entries          # уже по порядку: словарь → история → пункты

    def suggest(self, prefix: str, limit: int = 7) -> list[Hint]:
        p = _key(prefix.strip())
        if len(p) < MIN_PREFIX or not _WORD.fullmatch(p):
            return []
        out = self._find(p, limit)
        if not out and re.search(r'[a-z]', p):          # набрано в английской раскладке
            out = self._find(p.translate(_EN_RU), limit)
        return out

    def _find(self, p: str, limit: int) -> list[Hint]:
        return [h for h in self.entries
                if _key(h.word).startswith(p) and _key(h.word) != p][:limit]


def build_index(wb: Workbook, history: dict[str, int]) -> HintIndex:
    entries: list[Hint] = []
    seen: set[str] = set()

    def add(word: str, becomes: str, kind: str):
        k = _key(word)
        if k not in seen:
            seen.add(k)
            entries.append(Hint(word, becomes, kind))

    rows = {it.id: row_text(it, g) for it, g in _choices(wb)}
    for e in sorted(wb.dictionary, key=lambda e: -e.hits):
        if ' ' not in e.word.strip():
            add(e.word, rows.get(e.code, e.item_text), 'doctor')

    owners: dict[str, set[str]] = {}            # слово пункта → в каких пунктах
    for it, g in _choices(wb):
        for w in words_of(it.text) + [w.lower() for w in it.words if ' ' not in w]:
            if len(w) >= 4 and w not in FILLER:
                owners.setdefault(w, set()).add(it.id)

    def becomes_of(word: str) -> str:
        own = owners.get(word, set())
        return rows[next(iter(own))] if len(own) == 1 else ''

    for w, _ in sorted(history.items(), key=lambda kv: (-kv[1], kv[0])):
        add(w, becomes_of(w), 'history')
    for w in sorted(owners):
        add(w, becomes_of(w), 'item')
    return HintIndex(entries)

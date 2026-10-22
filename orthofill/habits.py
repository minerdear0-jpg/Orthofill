"""Привычки ввода врача (как подсказки в fish shell): серым — остаток привычной
фразы и следующая привычная фраза. Источник — только записи этого пресета из
журнала. Фраза — кусок записи между запятыми (точками с запятой, переводами
строк). Предлагается только то, что врач писал не меньше двух раз."""
from __future__ import annotations

import re
from collections import Counter

MIN_USES = 2
MIN_PREFIX = 3


def _ws(text: str) -> str:
    return re.sub(r'\s+', ' ', text)


def _key(text: str) -> str:
    return _ws(text).strip().lower().replace('ё', 'е')


def phrases_of(raw: str) -> list[str]:
    """Фразы записи — по запятым, точкам с запятой и переводам строк."""
    return [p for p in (_ws(x).strip() for x in re.split(r'[,;\n]', raw or '')) if p]


class Habits:
    def __init__(self, notes: list[str]):
        """notes — записи, новые первыми."""
        self._count: Counter = Counter()
        self._fresh: dict[str, int] = {}           # фраза → номер самой свежей записи с ней
        self._forms: dict[str, Counter] = {}       # фраза → как её писали
        self._pairs: Counter = Counter()
        self._pair_fresh: dict[tuple[str, str], int] = {}
        for k, raw in enumerate(notes):
            ph = phrases_of(raw)
            for p in ph:
                key = _key(p)
                self._count[key] += 1
                self._fresh.setdefault(key, k)
                self._forms.setdefault(key, Counter())[p] += 1
            for a, b in zip(ph, ph[1:]):
                pair = (_key(a), _key(b))
                self._pairs[pair] += 1
                self._pair_fresh.setdefault(pair, k)

    def _form(self, key: str) -> str:
        return self._forms[key].most_common(1)[0][0]

    def tail(self, prefix: str) -> str:
        """Остаток самой привычной фразы, начинающейся с prefix ('' — нет такой)."""
        typed = _ws(prefix.lstrip())
        pk = typed.lower().replace('ё', 'е')
        if len(pk.strip()) < MIN_PREFIX:
            return ''
        found = [k for k, n in self._count.items()
                 if n >= MIN_USES and k.startswith(pk) and len(k) > len(pk)]
        if not found:
            return ''
        best = min(found, key=lambda k: (-self._count[k], self._fresh[k]))
        return self._form(best)[len(typed):]

    def next_phrase(self, prev: str) -> str:
        """Фраза, которая у врача обычно идёт после prev ('' — нет такой)."""
        pk = _key(prev)
        found = [b for (a, b), n in self._pairs.items() if a == pk and n >= MIN_USES]
        if not found:
            return ''
        best = min(found, key=lambda b: (-self._pairs[(pk, b)], self._pair_fresh[(pk, b)]))
        return self._form(best)


def continuation(text_before: str, habits: Habits) -> str:
    """Что показать серым после курсора: следующая фраза (сразу после запятой)
    или остаток текущей фразы."""
    line = text_before.rsplit('\n', 1)[-1]
    if re.search(r'[,;]\s*$', line):
        before = phrases_of(line)
        if not before:
            return ''
        nxt = habits.next_phrase(before[-1])
        if not nxt:
            return ''
        return (' ' if re.search(r'[,;]$', line) else '') + nxt
    current = re.split(r'[,;]', line)[-1]
    return habits.tail(current)

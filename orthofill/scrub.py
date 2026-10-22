"""Вырезание ФИО из текста событий телеметрии (без зависимостей).

Тот же файл стоит на сервере (вторая линия). Признаки: фамилия с инициалами,
отчество, имя из списка частых имён; найденное вместе с соседними словами-
частями ФИО заменяется на «‹ФИО›». Ложное срабатывание дешевле пропуска."""
from __future__ import annotations

import re
from pathlib import Path

MARK = '‹ФИО›'

_SURN = r'[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?'
_INIT = r'[А-ЯЁ]\.(?:\s?[А-ЯЁ]\.)?'
_INITIALS = re.compile(rf'(?<![\w.]){_SURN}\s+{_INIT}(?!\w)|(?<![\w.]){_INIT}\s?{_SURN}(?!\w)')
_WORD = re.compile(r'[А-Яа-яЁё]+(?:-[А-Яа-яЁё]+)?')
# отчество во всех падежах: Иванович(а/у/ем/е), Ивановна (ы/е/у/ой), Ильич, Ильинична
_PATRONYMIC = re.compile(
    r'[а-яё]{3,}(?:(?:ович|евич)(?:а|у|ем|е)?|(?:овн|евн|ичн)(?:а|ы|е|у|ой)|ьич(?:а|у|ом|е)?)')
# фамилия маленькими буквами — только рядом с именем/отчеством
_SURNAME_LIKE = re.compile(r'[а-яё]{2,}(?:ов|ев|ёв|ин|ын|ова|ева|ёва|ина|ына|ский|ская|цкий|цкая|ко|ук|юк|енко)')
# имена, совпадающие с обычными словами, — только с заглавной буквы
_AMBIGUOUS = {'лев', 'вера', 'надежда', 'любовь', 'роза', 'лилия', 'слава', 'лада',
              'мила', 'майя', 'тома', 'ян', 'яна', 'марк', 'роман', 'влад', 'дина',
              'злата', 'кира', 'ева', 'лука', 'макс', 'лева', 'тоша', 'рома'}
_ENDINGS = ('ой', 'ей', 'ом', 'ем', 'ы', 'и', 'е', 'у', 'ю', 'а', 'я')


def _load_names() -> frozenset[str]:
    p = Path(__file__).with_name('names_ru.txt')
    try:
        lines = p.read_text(encoding='utf-8').splitlines()
    except OSError:
        return frozenset()
    return frozenset(_key(s) for s in lines if s.strip() and not s.startswith('#'))


def _key(w: str) -> str:
    return w.strip().lower().replace('ё', 'е')


NAMES = _load_names()


def _is_name(word: str) -> bool:
    k = _key(word)
    cands = {k}
    for end in _ENDINGS:
        if k.endswith(end) and len(k) - len(end) >= 3:
            stem = k[:-len(end)]
            cands |= {stem, stem + 'а', stem + 'я', stem + 'й', stem + 'ь'}
    for c in cands:
        if c in NAMES and len(c) >= 3:
            if c in _AMBIGUOUS and not word[:1].isupper():
                continue
            return True
    return False


def _is_patronymic(word: str) -> bool:
    return bool(_PATRONYMIC.fullmatch(_key(word)))


def scrub_text(text: str, keep: frozenset[str] = frozenset()) -> tuple[str, int]:
    """Текст без ФИО и сколько замен сделано. ``keep`` — слова врача/пресета
    (нижний регистр), их не трогаем."""
    if not text:
        return text, 0
    count = 0

    def _init_sub(m: re.Match) -> str:
        nonlocal count
        if any(_key(w) in keep for w in _WORD.findall(m.group(0))):
            return m.group(0)
        count += 1
        return MARK

    text = _INITIALS.sub(_init_sub, text)

    words = list(_WORD.finditer(text))
    kinds = []
    for m in words:
        w = m.group(0)
        if _key(w) in keep:
            kinds.append('')
        elif _is_name(w):
            kinds.append('N')
        elif _is_patronymic(w):
            kinds.append('P')
        elif w[:1].isupper():
            kinds.append('C')
        elif _SURNAME_LIKE.fullmatch(_key(w)):
            kinds.append('s')
        else:
            kinds.append('')

    def joined(i: int, j: int) -> bool:      # между словами только пробелы
        return text[words[i].end():words[j].start()].isspace()

    seeds = [i for i, k in enumerate(kinds)
             if k == 'N' or (k == 'P' and (words[i].group(0)[:1].isupper()
                                          or (i > 0 and kinds[i - 1] == 'N' and joined(i - 1, i))))]
    spans: list[tuple[int, int]] = []
    for i in seeds:
        if spans and spans[-1][0] <= i <= spans[-1][1]:
            continue
        lo = hi = i
        while lo > 0 and joined(lo - 1, lo) and kinds[lo - 1] in ('N', 'P', 'C', 's'):
            lo -= 1
        while hi + 1 < len(words) and joined(hi, hi + 1) and kinds[hi + 1] in ('N', 'P', 'C', 's'):
            hi += 1
        spans.append((lo, hi))
    for lo, hi in reversed(spans):
        text = text[:words[lo].start()] + MARK + text[words[hi].end():]
        count += 1
    return text, count


def scrub_event(ev: dict, keep: frozenset[str] = frozenset()) -> dict:
    """Копия события: все строки (и во вложенных списках/словарях) без ФИО;
    ``scrubbed`` — число замен, если они были."""
    total = 0

    def walk(v):
        nonlocal total
        if isinstance(v, str):
            s, n = scrub_text(v, keep)
            total += n
            return s
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [walk(x) for x in v]
        return v

    out = walk(ev)
    if total:
        out['scrubbed'] = out.get('scrubbed', 0) + total if isinstance(out.get('scrubbed'), int) else total
    return out

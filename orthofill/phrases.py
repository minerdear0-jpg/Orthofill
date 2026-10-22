"""Фразы врача (как SmartPhrase / SmartList в Epic): `.имя` раскрывается в
привычную фразу; на месте переменных частей — поля со списками значений.

Шаблон: `замена дуги {верх|низ|обе} {18х25|16х25} тма` — текст и поля
`{значение|значение|…}`, первое значение — самое частое. Значения — слова врача
из его же записей: разбор их понимает так же, как набранные руками."""
from __future__ import annotations

import re
from collections import Counter

Part = str | list[str]


def parse_template(template: str) -> list[Part]:
    """Шаблон → текст и поля (списки значений). ValueError — что не так."""
    out: list[Part] = []
    text, i = '', 0
    while i < len(template):
        ch = template[i]
        if ch == '{':
            end = template.find('}', i)
            if end < 0:
                raise ValueError('не закрыта «{»')
            values = [v.strip() for v in template[i + 1:end].split('|') if v.strip()]
            if not values:
                raise ValueError('пустое поле «{}»')
            if text:
                out.append(text)
                text = ''
            out.append(values)
            i = end + 1
        elif ch == '}':
            raise ValueError('лишняя «}»')
        else:
            text += ch
            i += 1
    if text:
        out.append(text)
    return out


def render(parts: list[Part], values: list[str | None] | None = None) -> str:
    """Текст фразы: в полях — выбранные значения (None — первое, самое частое)."""
    out, k = [], 0
    for p in parts:
        if isinstance(p, list):
            v = values[k] if values and k < len(values) and values[k] is not None else p[0]
            out.append(v)
            k += 1
        else:
            out.append(p)
    return ''.join(out)


def field_spans(parts: list[Part], values: list[str | None] | None = None) -> list[tuple[int, int]]:
    """Где в тексте фразы стоят поля: [(начало, конец)] по символам."""
    spans, pos, k = [], 0, 0
    for p in parts:
        if isinstance(p, list):
            v = values[k] if values and k < len(values) and values[k] is not None else p[0]
            spans.append((pos, pos + len(v)))
            pos += len(v)
            k += 1
        else:
            pos += len(p)
    return spans


# ---------- привычные формы из истории ----------
MIN_FORM_USES = 5
_SLOT = re.compile(r'^(?:\d+(?:[хx×*/]\d+)?|верх\w*|низ\w*|нижн\w*|обе|обеих|обоих|вч|нч)$', re.I)


def _words(text: str) -> list[str]:
    return text.split()


def shape_of(phrase_or_template: str) -> str:
    """Форма фразы: переменные части (числа, челюсти, поля шаблона) — «{}»."""
    t = re.sub(r'\{[^}]*\}', '{}', phrase_or_template)
    return ' '.join('{}' if w == '{}' or _SLOT.match(w) else w.lower().replace('ё', 'е')
                    for w in _words(t))


def propose(notes: list[str], existing) -> list[tuple[str, str, int]]:
    """Формы, которые врач пишет ≥ 5 раз с разными числами/челюстями →
    (имя, шаблон, сколько раз). Уже существующие фразы не предлагаются."""
    from .habits import phrases_of
    forms: dict[str, list[list[str]]] = {}
    for raw in notes:
        for ph in phrases_of(raw):
            words = _words(ph)
            if not any(_SLOT.match(w) for w in words) or all(_SLOT.match(w) for w in words):
                continue
            forms.setdefault(shape_of(ph), []).append(words)
    have = {shape_of(p.template) for p in existing}
    names = {p.name for p in existing}
    out = []
    for shape, uses in forms.items():
        if len(uses) < MIN_FORM_USES or shape in have:
            continue
        slots = [i for i, w in enumerate(shape.split()) if w == '{}']
        values = [Counter(u[i] for u in uses) for i in slots]
        if all(len(v) < 2 for v in values):
            continue                        # без вариантов — это привычка, а не фраза
        base = uses[0]
        parts = []
        for i, w in enumerate(base):
            if i in slots:
                vals = values[slots.index(i)]
                parts.append('{' + '|'.join(v for v, _ in vals.most_common()) + '}')
            else:
                parts.append(w)
        name = next(w for w in shape.split() if w != '{}').strip('.,;:')
        unique, n = name, 2
        while unique in names:
            unique, n = f'{name}{n}', n + 1
        names.add(unique)
        out.append((unique, ' '.join(parts), len(uses)))
    return sorted(out, key=lambda x: -x[2])

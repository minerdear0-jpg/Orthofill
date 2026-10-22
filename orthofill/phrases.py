"""Фразы врача (как SmartPhrase / SmartList в Epic): `.имя` раскрывается в
привычную фразу; на месте переменных частей — поля со списками значений.

Шаблон: `замена дуги {верх|низ|обе} {18х25|16х25} тма` — текст и поля
`{значение|значение|…}`, первое значение — самое частое. Значения — слова врача
из его же записей: разбор их понимает так же, как набранные руками."""
from __future__ import annotations

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

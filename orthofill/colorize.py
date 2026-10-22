"""0.5 beta 7: раскраска строки оболочки (без Tk).

Строка «Раздел › Группа › лист» → куски (начало, конец, вид): раздел — `sec:<номер
раздела в пресете>` (свой постоянный цвет), группа — `grp`, то, что пойдёт в
протокол, — `leaf`, разделитель — `sep`, набранное после последнего « › » — `typed`.
Уровни, которых нет в дереве, остаются без вида."""
from __future__ import annotations

from .shell import SEP, _ws, children_of
from .workbook import Workbook

# приглушённые, различимые; текст на белом читается
SECTION_COLORS = ('#4d6a8a', '#2f7a6a', '#9a5b2e', '#6b4fa0', '#5a6b2f', '#7a4f5a')


def section_color(k: int) -> str:
    return SECTION_COLORS[(k - 1) % len(SECTION_COLORS)]


def line_spans(wb: Workbook, line: str) -> list[tuple[int, int, str]]:
    sep = SEP.strip()
    if sep not in line:
        return []
    parts: list[tuple[int, int]] = []           # куски между «›», без крайних пробелов
    seps: list[int] = []
    start = 0
    for i, ch in enumerate(line + sep):
        if ch == sep or i == len(line):
            s, e = start, min(i, len(line))
            while s < e and line[s] == ' ':
                s += 1
            while e > s and line[e - 1] == ' ':
                e -= 1
            parts.append((s, e))
            if i < len(line):
                seps.append(i)
            start = i + 1
    sections = {s.id: k for k, s in enumerate(wb.sections, 1)}
    spans: list[tuple[int, int, str]] = [(i, i + 1, 'sep') for i in seps]
    parent = None
    found = True
    for k, (s, e) in enumerate(parts):
        last = k == len(parts) - 1
        hit = None
        if found and s < e:
            text = _ws(line[s:e])
            hit = next((c for c in children_of(wb, parent) if _ws(c.text) == text), None)
        if hit is None:
            found = False
            if last and s < e:
                spans.append((s, e, 'typed'))
            continue
        if hit.id in sections:
            kind = f'sec:{sections[hit.id]}'
        elif hit.children:
            kind = 'grp'
        else:
            kind = 'leaf'
        spans.append((s, e, kind))
        parent = hit.id
    return sorted(spans)

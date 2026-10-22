"""0.5 beta 7: связь записи и протокола (без Tk).

У каждой готовой строки записи-пути — номер (номер строки в поле записи); у строки
протокола — номера строк записи, из которых она, или «откуда» она взялась сама:
«всегда», «по умолч.», «по условию», «из слов», «ваш текст»."""
from __future__ import annotations

from .engine import _effective_when
from .shell import is_leaf, parse_line
from .text import norm
from .workbook import Workbook, is_cancel

# цвет кружка по номеру строки, по кругу; белые цифры читаются на каждом
CHIP_COLORS = ('#2a78d6', '#13875f', '#c4521f', '#6250d6',
               '#c2477a', '#0f7a7a', '#8a6d00', '#5a6b2f')

_WHEN = {'always': 'всегда', 'condition': 'по условию'}


def chip_color(n: int) -> str:
    return CHIP_COLORS[(n - 1) % len(CHIP_COLORS)]


def note_lines(wb: Workbook, raw: str) -> dict[int, str]:
    """Номер строки записи → код листа, для готовых строк-путей (без «нет»)."""
    out: dict[int, str] = {}
    for n, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        path = parse_line(wb, line)
        if path and is_leaf(wb, path) and not is_cancel(wb.by_id[path[-1]]):
            out[n] = path[-1]
    return out


def row_sources(wb: Workbook, lines, note: dict[int, str]) -> list[tuple[list[int], str]]:
    """Для каждой строки холста (canvas.CanvasLine): номера строк записи и «откуда»."""
    by_code: dict[str, list[int]] = {}
    for n, code in note.items():
        by_code.setdefault(code, []).append(n)
    when = _effective_when(wb)
    complaint = {s.id for s in wb.sections if norm(s.text).startswith('жалоб')}
    out: list[tuple[list[int], str]] = []
    for line in lines:
        row = line.row
        if line.kind == 'own' or line.replaces:
            out.append(([], 'ваш текст'))
            continue
        if row is None or line.kind != 'row' or row.section:
            out.append(([], ''))
            continue
        nums = sorted({n for c in row.codes for n in by_code.get(c, [])})
        if nums:
            out.append((nums, ''))
            continue
        items = [wb.by_id[c] for c in row.codes if c in wb.by_id]
        first = items[0] if items else None
        if any(it.star for it in items):
            src = 'всегда'
        elif len(items) > 1 or (first is not None and first.parent in complaint):
            src = 'по умолч.'          # вариант группы или жалоба — не из записи
        elif first is not None:
            src = _WHEN.get(when.get(first.id, ''), 'из слов')
        else:
            src = ''
        out.append(([], src))
    return out

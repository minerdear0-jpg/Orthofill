"""Предсказание в оболочке (0.5 b2): порядок — файл врача, набор — история.

Порядок строк не угадывается: следующий кандидат — пункт после строки над
курсором в порядке xlsx (по кругу). История говорит только, какие пункты врач
обычно пишет («★») и какие варианты выбирает чаще (выше в списке)."""
from __future__ import annotations

from dataclasses import dataclass

from .pathstats import USUAL_MIN, PathStats
from .shell import Path
from .workbook import Workbook


@dataclass
class Prediction:
    path: Path
    source: str         # 'usual' — первый обычный по файлу · 'and' — сосед группы «И» · 'file'
    usual: bool


def rank(paths: list[Path], stats: PathStats) -> list[Path]:
    """Частые (≥ 2) — сверху по убыванию, остальные — порядок файла."""
    def key(ip):
        i, p = ip
        n = stats.count.get(p[-1], 0)
        return (-(n if n >= USUAL_MIN else 0), i)
    return [p for _, p in sorted(enumerate(paths), key=key)]


def _units(wb: Workbook) -> list[Path]:
    """Пункты разделов по порядку файла: группа (путь до неё) или отдельный пункт."""
    return [(s.id, it.id) for s in wb.sections for it in s.children]


def predict(wb: Workbook, note_paths: list[Path], stats: PathStats,
            limit: int = 12) -> list[Prediction]:
    units = _units(wb)
    used = {p[1] for p in note_paths if len(p) > 1}
    start = 0
    if note_paths and len(note_paths[-1]) > 1:
        last = note_paths[-1][1]
        idx = next((i for i, u in enumerate(units) if u[1] == last), None)
        if idx is not None:
            start = idx + 1
    order = [u for u in units[start:] + units[:start] if u[1] not in used]
    out: list[Prediction] = []
    # «И»-соседи последней строки (родитель известен), если врач их обычно пишет
    if note_paths and len(note_paths[-1]) == 3:
        sec, grp, leaf = note_paths[-1]
        g = wb.by_id.get(grp)
        if g is not None and g.combine == 'and':
            taken = {p[-1] for p in note_paths if len(p) == 3 and p[1] == grp}
            for c in g.children:
                if c.id not in taken and stats.usual(c.id):
                    out.append(Prediction((sec, grp, c.id), 'and', True))
    rest = [Prediction(u, 'file', stats.usual(u[1])) for u in order]
    first = next((p for p in rest if p.usual), None)
    if first is not None and not out:
        rest.remove(first)
        out.append(Prediction(first.path, 'usual', True))
    out += rest
    return out[:limit]

"""Обычный набор врача (0.5 b2): какие пункты он пишет и как часто.

Порядок строк не изучается — его задал врач в xlsx. Источники: строки-пути
оболочки (точно) и записи через запятую, протокол которых врач подтвердил и
скопировал (пункты протокола без умолчаний пустой записи)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .shell import is_leaf, parse_line
from .workbook import Workbook

USUAL = 0.3         # доля записей, с которой пункт — «обычный»
USUAL_MIN = 2       # и не меньше стольких записей


@dataclass
class PathStats:
    count: dict[str, int] = field(default_factory=dict)   # код → в скольких записях
    notes: int = 0

    def usual(self, code: str) -> bool:
        n = self.count.get(code, 0)
        return n >= USUAL_MIN and self.notes > 0 and n / self.notes >= USUAL


def _leaf_codes(wb: Workbook, lines) -> list[str]:
    return [c for c, _ in lines
            if c in wb.by_id and not wb.by_id[c].children and wb.by_id[c].level > 1]


def note_codes(wb: Workbook, raw: str, copied: str | None,
               base: set[str] | None = None) -> list[str]:
    """Коды листов записи по порядку: строки-пути — как написаны; запись через
    запятую — только подтверждённая, без умолчаний пустой записи."""
    lines = [line for line in (raw or '').splitlines() if line.strip()]
    if any('›' in line for line in lines):
        out = []
        for line in lines:
            path = parse_line(wb, line)
            if path and is_leaf(wb, path) and path[-1] not in out:
                out.append(path[-1])
        return out
    if not copied or not (raw or '').strip():
        return []
    from .engine import build_protocol
    if base is None:
        base = _base(wb)
    return [c for c in _leaf_codes(wb, build_protocol(wb, raw).lines) if c not in base]


def _base(wb: Workbook) -> set[str]:
    """Листы протокола пустой записи — умолчания, их врач не говорил."""
    from .engine import build_protocol
    return set(_leaf_codes(wb, build_protocol(wb, '').lines))


def collapse(entries: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
    """Та же запись, подтверждённая подряд ещё раз (исправил опечатку, сменил пресет)
    — одна; подтверждена копией, если копия была хоть у одной из них."""
    out: list[tuple[str, str | None]] = []
    for raw, copied in entries:
        key = (raw or '').strip()
        if out and out[-1][0].strip() == key:
            if copied and not out[-1][1]:
                out[-1] = (out[-1][0], copied)
            continue
        out.append((raw or '', copied))
    return out


def add_codes(st: PathStats, wb: Workbook, codes: list[str]) -> None:
    """Учесть одну запись: лист, его группа и раздел — по разу."""
    if not codes:
        return
    st.notes += 1
    seen: set[str] = set()
    for c in codes:
        while c and c not in seen and c in wb.by_id:
            seen.add(c)
            c = wb.by_id[c].parent
    for c in seen:
        st.count[c] = st.count.get(c, 0) + 1


def build_stats(wb: Workbook, entries: list[tuple[str, str | None]]) -> PathStats:
    st = PathStats()
    base = _base(wb)
    for raw, copied in collapse(entries):
        codes = note_codes(wb, raw, copied, base)
        if not codes:
            continue
        st.notes += 1
        seen: set[str] = set()
        for c in codes:
            while c and c not in seen and c in wb.by_id:       # лист, его группа и раздел
                seen.add(c)
                c = wb.by_id[c].parent
        for c in seen:
            st.count[c] = st.count.get(c, 0) + 1
    return st

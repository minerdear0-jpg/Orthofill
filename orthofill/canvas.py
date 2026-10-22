"""Холст протокола (0.5 b3): собранные строки + правки врача + скелет.

Протокол пересобирается при каждой правке записи, а правки врача — отдельный
слой, привязанный к месту (коду собранной строки выше): свой текст встаёт после
неё, правленая строка — вместо неё, удалённая — не возвращается. Скелет —
блоки, которых ещё нет: живёт только в окне, в буфер и журнал не попадает."""
from __future__ import annotations

from dataclasses import dataclass, field

from .render import Row

PLACEHOLDER = ' ' * 48          # строка-заглушка скелета (фон тегом)
MOVED = 'место своего текста изменилось (строки над ним больше нет) — проверьте'


@dataclass(frozen=True)
class OwnLine:
    anchor: str | None          # код собранной строки выше (None — начало протокола)
    text: str
    replaces: bool = False      # правленая собранная строка — вместо неё


@dataclass
class Edits:
    own: list[OwnLine] = field(default_factory=list)
    removed: set[str] = field(default_factory=set)

    def __bool__(self) -> bool:
        return bool(self.own or self.removed)


@dataclass
class CanvasLine:
    text: str
    kind: str                   # row · own · skeleton · skeleton_next
    code: str | None            # строка протокола / якорь своего текста / блок скелета
    row: Row | None = None
    replaces: bool = False


def _key(row: Row) -> str:
    return row.codes[0]


def compose(rows: list[Row], edits: Edits, skeleton: list[tuple[str, bool]],
            order: dict[str, int], section_of: dict[str, str]
            ) -> tuple[list[CanvasLine], list[str]]:
    warnings: list[str] = []
    repl = {o.anchor: o for o in edits.own if o.replaces}
    lines: list[CanvasLine] = []
    for r in rows:
        k = _key(r)
        if k in edits.removed:
            continue
        if k in repl:
            lines.append(CanvasLine(repl[k].text, 'own', k, r, replaces=True))
        else:
            lines.append(CanvasLine(r.text, 'row', k, r))
    present = {l.code for l in lines if l.kind == 'row' or l.replaces}
    for o in edits.own:
        if o.replaces:
            continue
        own = CanvasLine(o.text, 'own', o.anchor)
        if o.anchor is None:
            at = sum(1 for l in lines if l.kind == 'own' and l.code is None and not l.replaces)
            lines.insert(at, own)
            continue
        if o.anchor in present:
            i = next(i for i, l in enumerate(lines)
                     if l.code == o.anchor and (l.kind == 'row' or l.replaces))
        else:
            sec = section_of.get(o.anchor)
            same = [i for i, l in enumerate(lines)
                    if (l.kind == 'row' or l.replaces) and section_of.get(l.code) == sec]
            i = same[-1] if same else len(lines) - 1
            if MOVED not in warnings:
                warnings.append(MOVED)
        i += 1
        while i < len(lines) and lines[i].kind == 'own' and not lines[i].replaces:
            i += 1                                   # после своих строк этого же места
        lines.insert(i, own)
    for code, nxt in skeleton:
        pos = order.get(code, 10 ** 9)
        at = next((i for i, l in enumerate(lines)
                   if (l.kind == 'row' or l.replaces) and order.get(l.code, -1) > pos), len(lines))
        lines.insert(at, CanvasLine(PLACEHOLDER, 'skeleton_next' if nxt else 'skeleton', code))
    return lines, warnings


def capture(lines: list[tuple[str, str | None, str | None]], shown: list[str],
            removed_before: set[str] | frozenset = frozenset()) -> Edits:
    """Правки врача по тому, что сейчас в поле: (текст, код собранной строки,
    её исходный текст). shown — коды строк последней отрисовки."""
    own: list[OwnLine] = []
    seen: set[str] = set()
    anchor: str | None = None
    for text, code, original in lines:
        if code is not None:
            seen.add(code)
            if text != original:
                if text.strip():
                    own.append(OwnLine(code, text, replaces=True))
                else:
                    seen.discard(code)              # строку стёрли — удалена
            anchor = code
            continue
        if not text.strip() or (original == PLACEHOLDER and text == PLACEHOLDER):
            continue
        own.append(OwnLine(anchor, text.strip() if original == PLACEHOLDER else text))
    removed = set(removed_before) | {c for c in shown if c not in seen}
    return Edits(own, removed)


def confirm_text(lines: list[CanvasLine]) -> str:
    """Текст для буфера и журнала — без скелета."""
    return '\n'.join(l.text for l in lines if l.kind not in ('skeleton', 'skeleton_next'))

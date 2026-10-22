"""Холст протокола (0.5 b3): собранные строки + правки врача + скелет.

Протокол пересобирается при каждой правке записи, а правки врача — отдельный
слой, привязанный к месту (коду собранной строки выше): свой текст встаёт после
неё, правленая строка — вместо неё, удалённая — не возвращается. Скелет —
блоки, которых ещё нет: живёт только в окне, в буфер и журнал не попадает."""
from __future__ import annotations

import difflib
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
    """Строка протокола — по всем её кодам: соседние варианты одной группы
    («Перепел», «Лиса») — разные строки."""
    return '|'.join(row.codes)


def _sec(key: str | None, section_of: dict[str, str]) -> str | None:
    return section_of.get(key.split('|')[0]) if key else None


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
        if o.replaces and o.anchor in present:
            continue
        if o.replaces:          # строки больше нет (пункт сменился) — правка остаётся своим текстом
            o = OwnLine(o.anchor, o.text)
        own = CanvasLine(o.text, 'own', o.anchor)
        if o.anchor is None:
            at = sum(1 for l in lines if l.kind == 'own' and l.code is None and not l.replaces)
            lines.insert(at, own)
            continue
        if o.anchor in present:
            i = next(i for i, l in enumerate(lines)
                     if l.code == o.anchor and (l.kind == 'row' or l.replaces))
        else:
            sec = _sec(o.anchor, section_of)
            same = [i for i, l in enumerate(lines)
                    if (l.kind == 'row' or l.replaces) and _sec(l.code, section_of) == sec]
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
                   if (l.kind == 'row' or l.replaces)
                   and order.get(l.code.split('|')[0], -1) > pos), len(lines))
        lines.insert(at, CanvasLine(PLACEHOLDER, 'skeleton_next' if nxt else 'skeleton', code))
    return lines, warnings


def capture(prev: list[CanvasLine], texts: list[str],
            removed_before: set[str] | frozenset = frozenset()) -> Edits:
    """Правки врача: построчное сравнение того, что сейчас в поле (texts), с
    последней отрисовкой (prev). Не зависит от тегов Tk (их теряют отмена, набор
    в начале строки, перенос строки посередине)."""
    old = [l.text for l in prev]
    pairs: list[tuple[str, CanvasLine | None]] = []
    gone: list[CanvasLine] = []
    sm = difflib.SequenceMatcher(None, old, texts, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            pairs += [(texts[j1 + k], prev[i1 + k]) for k in range(i2 - i1)]
        elif op == 'delete':
            gone += prev[i1:i2]
        elif op == 'insert':
            pairs += [(t, None) for t in texts[j1:j2]]
        else:                                   # replace: по похожести, порядок сохраняется
            i = i1
            for j in range(j1, j2):
                best, at = 0.0, None
                for k in range(i, i2):
                    r = difflib.SequenceMatcher(None, old[k], texts[j], autojunk=False).ratio()
                    if r > best:
                        best, at = r, k
                if at is not None and best >= 0.5:
                    gone += prev[i:at]
                    pairs.append((texts[j], prev[at]))
                    i = at + 1
                else:
                    pairs.append((texts[j], None))
            gone += prev[i:i2]
    own: list[OwnLine] = []
    removed = set(removed_before)
    anchor: str | None = None
    for text, src in pairs:
        t = text.rstrip()
        is_row = src is not None and (src.kind == 'row' or src.replaces)
        if is_row:
            original = (src.row.text if src.row else src.text).rstrip()
            if t == original:
                pass                            # собранная строка как есть
            elif t:
                own.append(OwnLine(src.code, t, replaces=True))
            else:
                removed.add(src.code)           # строку стёрли
            anchor = src.code
        elif t:
            own.append(OwnLine(anchor, t))      # свой текст (и набранный в скелет)
    for src in gone:
        if src.kind == 'row' or src.replaces:
            removed.add(src.code)
    return Edits(own, removed)


def confirm_text(lines: list[CanvasLine]) -> str:
    """Текст для буфера и журнала — без скелета."""
    return '\n'.join(l.text for l in lines if l.kind not in ('skeleton', 'skeleton_next'))

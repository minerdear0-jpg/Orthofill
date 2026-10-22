"""Коды ID_CLASS пресета. Код задаёт место пункта: раздел `4`, группа или
отдельный пункт `4b`, вариант `4b7` (вариант без своей группы — `4h1` —
считается отдельным пунктом раздела). Поэтому смена кода — это перенос.

Любая смена описывается таблицей «старый код → новый» (CodeMap) и применяется
разом (`apply_map`): пункты, их порядок и дети, варианты по умолчанию, строки
эталонов и слова врача."""
from __future__ import annotations

import string

from .workbook import _CODE_RE, Workbook, _level

CodeMap = dict[str, str]

_LETTERS = string.ascii_lowercase
_KIND = {1: 'раздел', 2: 'группа или пункт', 3: 'вариант'}


def inside(code: str, anc: str) -> bool:
    """code — внутри anc: раздела `4` (всё `4…`) или группы `4b` (варианты `4b1`,
    `4b10`). У варианта детей нет: `4b10` не внутри `4b1`."""
    if code == anc:
        return False
    if len(anc) == 1:
        return code[0] == anc
    return len(anc) == 2 and len(code) > 2 and code[:2] == anc


def _descendants(wb: Workbook, code: str) -> list[str]:
    return [it.id for it in wb.items if inside(it.id, code)]


def next_code(wb: Workbook, parent: str | None, level: int, taken: set[str] = frozenset()) -> str:
    """Свободный код нового пункта: раздел — следующая цифра; группа/пункт —
    первая свободная буква раздела; вариант — наибольший номер группы + 1.
    taken — коды, которые нельзя давать заново (удалённые, но ещё в эталонах):
    иначе строка эталона молча привязалась бы к новому, чужому пункту."""
    codes = {it.id for it in wb.items} | set(taken)
    if level == 1:
        return str(max((int(c) for c in codes if len(c) == 1), default=0) + 1)
    if level == 2:
        used = {c[1] for c in codes if len(c) >= 2 and c[0] == parent}
        return parent + next(c for c in _LETTERS if c not in used)
    nums = [int(c[2:]) for c in codes if len(c) > 2 and c[:2] == parent]
    return f'{parent}{max(nums, default=0) + 1}'


def code_error(wb: Workbook, old: str, new: str) -> str | None:
    """None — код можно поставить; иначе — что не так, словами."""
    if new == old:
        return None
    if not _CODE_RE.fullmatch(new):
        return 'код не по формату (1, 1a, 1a1)'
    if _level(new) != _level(old):
        return f'другой уровень: «{old}» — {_KIND[_level(old)]}, «{new}» — {_KIND[_level(new)]}'
    if new in wb.by_id:
        return f'код «{new}» уже занят'
    if _level(new) == 3 and new[:2] not in wb.by_id and not wb.by_id[old].orphan:
        return f'нет группы «{new[:2]}»'
    if _level(new) >= 2 and new[0] not in wb.by_id:
        return f'нет раздела «{new[0]}»'
    if _level(new) == 2:
        taken = [i for i in _descendants(wb, new) if i not in _descendants(wb, old)]
        if taken:
            return f'буква «{new}» занята пунктами {", ".join(taken)}'
    return None


def rename_map(wb: Workbook, old: str, new: str) -> CodeMap:
    """old → new вместе со всеми пунктами внутри (у группы — варианты)."""
    m = {old: new}
    for code in _descendants(wb, old):
        m[code] = new + code[len(old):]
    return m


def swap_map(a: str, b: str, wb: Workbook) -> CodeMap:
    return {**rename_map(wb, a, b), **rename_map(wb, b, a)}


def renumber_map(wb: Workbook, parent: str) -> CodeMap:
    """Коды детей по текущему порядку: варианты 1, 2, 3…; группы и пункты
    раздела a, b, c… (буквы вариантов-сирот раздела пропускаются, сироты не
    перенумеровываются). Только изменившиеся коды."""
    item = wb.by_id[parent]
    if item.level == 1:
        kids = [c for c in item.children if not c.orphan]
        orphan_letters = {c.id[1] for c in item.children if c.orphan}
        letters = [c for c in _LETTERS if c not in orphan_letters]
        new_codes = [parent + letters[k] for k in range(len(kids))]
    else:
        kids = list(item.children)
        new_codes = [f'{parent}{k + 1}' for k in range(len(kids))]
    m: CodeMap = {}
    for kid, code in zip(kids, new_codes):
        if kid.id != code:
            m.update(rename_map(wb, kid.id, code))
    return m


def _parent_of(code: str, groups: set[str]) -> tuple[str | None, bool]:
    """(родитель, сирота) по коду: вариант без своей группы — пункт раздела."""
    if len(code) == 1:
        return None, False
    if len(code) == 2:
        return code[0], False
    return (code[:2], False) if code[:2] in groups else (code[0], True)


def apply_map(wb: Workbook, m: CodeMap) -> None:
    """Применить смену кодов разом (обмен 4d1↔4d2 не сталкивается)."""
    if not m:
        return
    old_parent = {it.id: it.parent for it in wb.items}
    for it in wb.items:
        it.id = m.get(it.id, it.id)
    ids = {it.id for it in wb.items}
    groups = {it.id for it in wb.items if len(it.id) == 2 and (it.children or it.method)}
    groups |= {c[:2] for c in ids if len(c) > 2 and c[:2] in ids}
    moved = []
    for it in wb.items:
        parent, orphan = _parent_of(it.id, groups)
        before = old_parent.get(next((o for o, n in m.items() if n == it.id), it.id))
        if before is not None and m.get(before, before) != parent:
            moved.append(it)
        it.parent, it.orphan = parent, orphan
        it.level = 2 if orphan else _level(it.id)
    # перенесённый пункт — после последнего пункта нового родителя
    for it in moved:
        block = [x for x in wb.items if x is it or inside(x.id, it.id)]
        rest = [x for x in wb.items if x not in block]
        tail = max((k for k, x in enumerate(rest)
                    if x.id == it.parent or inside(x.id, it.parent)), default=len(rest) - 1)
        wb.items[:] = rest[:tail + 1] + block + rest[tail + 1:]
    rebuild(wb)
    for it in wb.items:
        if it.default:
            it.default = m.get(it.default, it.default)
    for case in wb.references:
        case.lines[:] = [(m.get(c, c), t) for c, t in case.lines]
    for e in wb.dictionary:
        e.code = m.get(e.code, e.code)
    from .logic import remap
    for it in wb.items:
        it.condition = remap(it.condition, m)
    wb.not_together[:] = sorted({tuple(sorted((m.get(a, a), m.get(b, b))))
                                 for a, b in wb.not_together})


def rebuild(wb: Workbook) -> None:
    """by_id, дети и разделы — заново по wb.items."""
    wb.by_id.clear()
    wb.by_id.update({it.id: it for it in wb.items})
    for it in wb.items:
        it.children = []
    for it in wb.items:
        if it.parent in wb.by_id:
            wb.by_id[it.parent].children.append(it)
    wb.sections[:] = [it for it in wb.items if it.level == 1]

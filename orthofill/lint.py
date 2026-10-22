"""Проверка классификатора пресета: что в нём, скорее всего, ошибка врача или
ИТ-специалиста. Работает над данными, без окна; окно и «Подробнее» только
показывают находки."""
from __future__ import annotations

from dataclasses import dataclass

from .addition import _choices, row_text
from .text import norm
from .workbook import Item, Workbook

JAW_FIX = 'jaw_order'       # у этой находки есть исправление: поменять коды местами
LEVEL_LABELS = {'error': 'Ошибка', 'warning': 'Предупреждение', 'info': 'Сведение'}


@dataclass
class Finding:
    code: str               # код пункта или коды через запятую
    kind: str               # dup_row | dup_in_group | jaw_order | gap | empty_group
    level: str              # error | warning | info
    message: str


def _title(it: Item) -> str:
    return ' '.join(it.text.split()).rstrip(':').strip()


def _num(it: Item) -> int:
    return int(it.id[2:])


def _jaws(group: Item) -> tuple[Item, Item] | None:
    """(первый вариант «нижн», первый «верхн») — если в группе есть оба."""
    up = next((c for c in group.children if 'верхн' in norm(c.text)), None)
    low = next((c for c in group.children if 'нижн' in norm(c.text)), None)
    return (low, up) if up and low else None


def lint(wb: Workbook) -> list[Finding]:
    out: list[Finding] = []
    groups = [it for it in wb.items if it.children and it.level == 2]

    rows: dict[str, list[str]] = {}
    for it, g in _choices(wb):
        rows.setdefault(' '.join(row_text(it, g).split()), []).append(it.id)
    for text, codes in rows.items():
        if len(codes) > 1:
            out.append(Finding(','.join(codes), 'dup_row', 'error',
                               f'одинаковые строки протокола: {", ".join(codes)} — «{text[:60]}»'))

    for g in groups:
        seen: dict[str, list[str]] = {}
        for c in g.children:
            seen.setdefault(' '.join(norm(c.text).split()), []).append(c.id)
        for codes in seen.values():
            if len(codes) > 1:
                out.append(Finding(','.join(codes), 'dup_in_group', 'error',
                                   f'одинаковые варианты в группе «{_title(g)}»: {", ".join(codes)}'))

    jaws = {g.id: _jaws(g) for g in groups}
    jaws = {k: v for k, v in jaws.items() if v}
    upper_first = sum(_num(up) < _num(low) for low, up in jaws.values())
    lower_first = len(jaws) - upper_first
    if upper_first != lower_first:
        usual_upper_first = upper_first > lower_first
        for gid, (low, up) in jaws.items():
            if (_num(up) < _num(low)) != usual_upper_first:
                g = wb.by_id[gid]
                out.append(Finding(f'{low.id},{up.id}', 'jaw_order', 'warning',
                                   f'«{_title(g)}»: верхняя челюсть под номером {_num(up)}, '
                                   f'нижняя под {_num(low)} — в остальных группах наоборот'))

    for g in groups:
        nums = sorted(_num(c) for c in g.children)
        missing = [n for n in range(1, (nums[-1] if nums else 0) + 1) if n not in nums]
        if missing:
            out.append(Finding(g.id, 'gap', 'info',
                               f'«{_title(g)}»: пропущен номер '
                               f'{", ".join(g.id + str(n) for n in missing)}'))

    for it in wb.items:
        if it.level == 2 and not it.orphan and not it.children and it.method:
            out.append(Finding(it.id, 'empty_group', 'warning', f'«{_title(it)}»: группа без вариантов'))

    out += _logic(wb)
    out += _cancels(wb)

    order = {it.id: k for k, it in enumerate(wb.items)}
    return sorted(out, key=lambda f: order.get(f.code.split(',')[0], 0))


def _cancels(wb: Workbook) -> list[Finding]:
    """Ветка «нет» нужна, только если пункт появляется сам: группа с вариантом
    по умолчанию или пункт «всегда»/по условию."""
    out = []
    if not any(it.cancel for it in wb.items):
        return out
    from .engine import build_protocol
    base = {c for c, _ in build_protocol(wb, '').lines}     # умолчания — и правила движка
    for it in wb.items:
        if it.cancel is None:
            continue
        shows_itself = (it.default is not None or it.id in base if it.children
                        else it.when in (None, 'always') or it.condition is not None
                        or it.id in base)
        if not shows_itself:
            out.append(Finding(it.id, 'cancel_useless', 'warning',
                               f'«{_title(it)}»: ветка «нет» лишняя — без строки пункт и так '
                               f'не выводится'))
    return out


def _logic(wb: Workbook) -> list[Finding]:
    """Находки логики полей (0.2 beta 5)."""
    from .engine import effective_condition, rule_kind
    from .logic import has_positive, refs
    out: list[Finding] = []
    for it in wb.items:
        cond = it.condition
        if cond:
            gone = sorted(refs(cond) - set(wb.by_id))
            if gone:
                out.append(Finding(it.id, 'bad_ref', 'error',
                                   f'условие «{_title(it)}» ссылается на удалённый {", ".join(gone)}'))
        if it.when == 'condition':
            cond = effective_condition(it, wb)
            if cond is None:
                out.append(Finding(it.id, 'no_condition', 'warning',
                                   f'«{_title(it)}»: «по условию», но условия нет — '
                                   f'строка не выводится никогда'))
            elif not has_positive(cond):
                out.append(Finding(it.id, 'from_nothing', 'error',
                                   f'«{_title(it)}»: в условии только «НЕ» — строка выводилась '
                                   f'бы из ничего; добавьте строку без «НЕ»'))
        if it.combine == 'and' and it.children and \
                rule_kind(it) not in (None, 'elastics', 'adjust'):
            out.append(Finding(it.id, 'and_unsupported', 'warning',
                               f'«{_title(it)}»: сочетание «И» не действует для правила '
                               f'«{rule_kind(it)}» — выводится один вариант'))
    for a, b in wb.not_together:
        x, y = wb.by_id.get(a), wb.by_id.get(b)
        if x and y and x.level == y.level == 3 and not x.orphan and x.parent == y.parent \
                and wb.by_id[x.parent].combine != 'and':
            out.append(Finding(f'{a},{b}', 'pair_in_group', 'error',
                               f'«не вместе» {a} и {b}: варианты одной группы и так не бывают '
                               f'вместе — пара лишняя'))
    return out

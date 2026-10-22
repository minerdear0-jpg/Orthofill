"""Протокол из строк-путей оболочки (0.5): ничего не разбирается и не угадывается.

Каждая строка — точный путь по дереву пресета; лист-вариант выбирает вариант
своей группы, лист-пункт выводит пункт, «нет» отменяет родителя. Всё остальное
— как у движка: варианты по умолчанию, «всегда», условия (И/ИЛИ/НЕ), пары
«не вместе», вид строк протокола."""
from __future__ import annotations

from .engine import (Protocol, _check_pairs, _Ctx, _effective_when, build_protocol,
                     effective_condition)
from .logic import Facts, evaluate
from .render import render_rows
from .shell import is_leaf, parse_line
from .text import norm
from .workbook import Item, Workbook, is_cancel


def shell_protocol(wb: Workbook, raw: str) -> Protocol:
    ctx = _Ctx('', wb)
    picks: dict[str, list[Item]] = {}          # группа → выбранные варианты (порядок строк)
    singles: list[str] = []                    # отдельные пункты по строкам
    cancelled: set[str] = set()
    for n, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        path = parse_line(wb, line)
        if path is None or not is_leaf(wb, path):
            ctx.warn(f'строка {n} не понята: «{line.strip()[:40]}»')
            continue
        leaf = wb.by_id[path[-1]]
        parent = wb.by_id.get(leaf.parent) if leaf.parent else None
        if is_cancel(leaf):
            cancelled.add(leaf.parent)
        elif leaf.level == 3 and parent is not None and leaf in parent.children:
            if leaf not in picks.setdefault(parent.id, []):
                picks[parent.id].append(leaf)
        elif leaf.id not in singles:
            singles.append(leaf.id)

    # умолчания — те же, что у врача на пустой записи сейчас (вариант по умолчанию
    # пресета или правило: «этап — рабочий», «явка через 4 недели»)
    base: dict[str, list[Item]] = {}
    for code, _ in build_protocol(wb, '').lines:
        it = wb.by_id.get(code)
        if it is not None and it.level == 3 and it.parent:
            base.setdefault(it.parent, []).append(it)
        elif it is not None and it.parent in wb.by_id and wb.by_id[it.parent].level == 1:
            base.setdefault(it.parent, []).append(it)     # жалоба по умолчанию
    complaint = {s.id for s in wb.sections if norm(s.text).startswith('жалоб')}
    chosen: dict[str, list[Item]] = {}
    for s in wb.sections:
        if s.id in complaint:
            said = [c for c in s.children if c.id in singles]
            if said:
                chosen[s.id] = said
                if len(said) > 1:
                    ctx.flag(s.id, 'выбрано несколько жалоб — проверьте')
            elif s.id not in cancelled and base.get(s.id):
                ctx.default('жалоб нет')
                chosen[s.id] = base[s.id][:1]
            continue
        for g in s.children:
            if not g.children:
                continue
            sel = picks.get(g.id, [])
            if sel and g.id in cancelled:
                msg = f'«{" ".join(g.text.split())[:40]}»: отменено строкой «нет» — проверьте'
                ctx.warn(msg)
                ctx.flag(g.id, msg)
            if len(sel) > 1 and g.combine != 'and':
                msg = f'«{" ".join(g.text.split())[:40]}»: выбрано несколько вариантов — проверьте'
                ctx.warn(msg)
                ctx.flag(g.id, msg)
            if sel:
                chosen[g.id] = sel
                ctx.picked[g.id] = (sel, True)
            elif g.id not in cancelled and base.get(g.id):
                target = base[g.id]
                ctx.default(f'{g.text.strip()} {", ".join(t.text.strip() for t in target)}')
                chosen[g.id] = target
                ctx.picked[g.id] = (target, False)

    known = {g: {c.id for c in sel} for g, (sel, rec) in ctx.picked.items() if rec and sel}
    mentioned = set(singles) | {g for g in picks} | {c.id for sel in picks.values() for c in sel}
    facts = Facts(known, mentioned)
    when = _effective_when(wb)

    lines: list[tuple[str, str]] = []
    for section in wb.sections:
        out: list[tuple[str, str]] = []
        if section.id in complaint:
            out += [(c.id, c.text) for c in chosen.get(section.id, [])]
        else:
            for item in section.children:
                if item.children:
                    sel = chosen.get(item.id)
                    if sel:
                        out.append((item.id, item.text))
                        out += [(c.id, c.text) for c in sel]
                elif _shown(item, when.get(item.id, 'mentioned'), singles, cancelled, facts, ctx):
                    out.append((item.id, item.text))
        if out:
            lines += [(section.id, section.text)] + out
    _check_pairs(wb, lines, ctx)
    return Protocol(lines, ctx.warnings, ctx.defaults, render_rows(wb, lines, ctx.flags), [])


def _shown(item: Item, when: str, singles: list[str], cancelled: set[str],
           facts: Facts, ctx: _Ctx) -> bool:
    cond = effective_condition(item, ctx.wb)
    ok = evaluate(cond, facts) is True
    if item.id in singles:
        if item.id in cancelled:
            msg = f'«{" ".join(item.text.split())[:40]}»: отменено строкой «нет» — проверьте'
            ctx.warn(msg)
            ctx.flag(item.id, msg)
        if cond is not None and not ok:
            ctx.flag(item.id, 'по условию этой строки быть не должно — проверьте')
        return True
    if item.id in cancelled:
        return False
    if when == 'always':
        return ok
    if when == 'mentioned':
        return False
    return cond is not None and ok

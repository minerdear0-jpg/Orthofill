"""Условия пунктов пресета: «показывать строку, если …».

Дерево (хранится как JSON): узел-группа `{"all": [...]}` / `{"any": [...]}`;
узел-строка `{"field": код, "is": код варианта}` или `{"field": код,
"mentioned": true}`; у любого узла может быть `"not": true`.

Вычисление трёхзначное (как NULL в SQL): да / нет / неизвестно. Поле-группа
«известно», только если вариант выбран по записи (не по умолчанию); НЕ от
«неизвестно» — «неизвестно». Строка протокола выводится только при «да» —
так условие не выведет того, что не следует из записи.

Текст для листа xlsx «Настройки»: `2b = 2b2 И НЕ 4p`, `4p упомянут`,
`(2b = 2b1 ИЛИ 2b = 2b2) И 4d`."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

Node = dict


@dataclass
class Facts:
    known: dict[str, set[str]] = field(default_factory=dict)   # группа → варианты из записи
    # упомянутые группы и пункты: множество (да/нет) или что-то с .get(код) → да/нет/None
    mentioned: object = field(default_factory=set)


# ---------- вычисление ----------
def evaluate(node: Node | None, facts: Facts) -> bool | None:
    """True / False / None (неизвестно). Нет условия — True."""
    if node is None:
        return True
    if 'all' in node or 'any' in node:
        vals = [evaluate(n, facts) for n in node.get('all', node.get('any', []))]
        if 'all' in node:
            res = False if False in vals else None if None in vals else True
        else:
            res = True if True in vals else None if None in vals else False
    elif node.get('mentioned'):
        get = getattr(facts.mentioned, 'get', None)
        res = get(node['field']) if get else node['field'] in facts.mentioned
    else:
        known = facts.known.get(node['field'])
        res = None if known is None else node['is'] in known
    if node.get('not') and res is not None:
        res = not res
    return res


# ---------- обход ----------
def _rows(node: Node):
    if 'all' in node or 'any' in node:
        for n in node.get('all', node.get('any', [])):
            yield from _rows(n)
    else:
        yield node


def refs(node: Node | None) -> set[str]:
    """Все коды условия: поля и варианты."""
    out: set[str] = set()
    for r in _rows(node) if node else ():
        out.add(r['field'])
        if 'is' in r:
            out.add(r['is'])
    return out


def remap(node: Node | None, m: dict[str, str]) -> Node | None:
    """Копия условия с кодами по таблице «старый → новый»."""
    if node is None:
        return None
    if 'all' in node or 'any' in node:
        key = 'all' if 'all' in node else 'any'
        out = {key: [remap(n, m) for n in node[key]]}
    else:
        out = {'field': m.get(node['field'], node['field'])}
        if 'is' in node:
            out['is'] = m.get(node['is'], node['is'])
        else:
            out['mentioned'] = True
    if node.get('not'):
        out['not'] = True
    return out


def is_simple(node: Node | None) -> bool:
    """Одна связка на весь блок и только строки — такое правится в окне."""
    if node is None:
        return True
    key = 'all' if 'all' in node else 'any' if 'any' in node else None
    return key is not None and not node.get('not') and \
        all('all' not in n and 'any' not in n for n in node[key])


def has_positive(node: Node | None) -> bool:
    """В условии есть строка без НЕ, которая обязана быть верной: иначе «по
    условию» выводило бы строку из ничего («НЕ 4p упомянут» верно почти всегда)."""
    if node is None or node.get('not'):
        return False
    if 'all' in node:
        return any(has_positive(n) for n in node['all'])
    if 'any' in node:
        return bool(node['any']) and all(has_positive(n) for n in node['any'])
    return True


# ---------- текст ----------
_TOKEN = re.compile(r'\s*(\(|\)|=|[^\s()=]+)')


def _tokens(text: str) -> list[str]:
    out, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        out.append(m.group(1))
        pos = m.end()
        while pos < len(text) and text[pos].isspace():
            pos += 1
    return out


def parse(text: str, codes: set[str]) -> Node | None:
    """Текст ячейки «Условие» → дерево. ValueError — что не так, словами."""
    toks = [t for t in _tokens(text or '')]
    if not toks:
        return None
    pos = 0

    def peek() -> str | None:
        return toks[pos] if pos < len(toks) else None

    def word(t: str | None, *ws: str) -> bool:
        return t is not None and t.lower() in ws

    def take() -> str:
        nonlocal pos
        pos += 1
        return toks[pos - 1]

    def code(t: str) -> str:
        c = t.strip().lower()
        if c not in codes:
            raise ValueError(f'не знаю код {c}')
        return c

    def expr() -> Node:
        parts = [and_expr()]
        while word(peek(), 'или'):
            take()
            parts.append(and_expr())
        return parts[0] if len(parts) == 1 else {'any': parts}

    def and_expr() -> Node:
        parts = [neg()]
        while word(peek(), 'и'):
            take()
            parts.append(neg())
        return parts[0] if len(parts) == 1 else {'all': parts}

    def neg() -> Node:
        negate = False
        if word(peek(), 'не'):
            take()
            negate = True
        if peek() == '(':
            take()
            node = expr()
            if peek() != ')':
                raise ValueError('не закрыта скобка')
            take()
        elif peek() is None:
            raise ValueError('условие оборвано')
        else:
            f = code(take())
            if peek() == '=':
                take()
                if peek() is None:
                    raise ValueError(f'после «{f} =» нужен код варианта')
                node = {'field': f, 'is': code(take())}
            else:
                if word(peek(), 'упомянут', 'упомянута', 'упомянуто'):
                    take()
                elif peek() not in (None, ')') and not word(peek(), 'и', 'или'):
                    raise ValueError(f'ожидаю «=» или «И»/«ИЛИ» после «{f}»')
                node = {'field': f, 'mentioned': True}
        if negate:
            node = dict(node, **{'not': True})
        return node

    node = expr()
    if peek() is not None:
        raise ValueError('лишняя скобка' if peek() == ')' else f'не понимаю «{peek()}»')
    if 'all' not in node and 'any' not in node:
        node = {'all': [node]}
    return node


def format(node: Node | None, top: bool = True) -> str:
    """Дерево → текст ячейки «Условие» (скобки — только где нужны)."""
    if node is None:
        return ''
    neg = 'НЕ ' if node.get('not') else ''
    if 'all' in node or 'any' in node:
        key = 'all' if 'all' in node else 'any'
        joiner = ' И ' if key == 'all' else ' ИЛИ '
        parts = [format(n, top=False) for n in node[key]]
        inner = joiner.join(parts)
        if len(parts) == 1 and not neg:
            return inner
        return inner if top and not neg else f'{neg}({inner})'
    if 'is' in node:
        return f'{neg}{node["field"]} = {node["is"]}'
    return f'{neg}{node["field"]}'

"""Оболочка (0.5): строка записи — путь по дереву пресета, как команда Cisco IOS.

Набранные слова — фильтры «И» по ещё не выбранной части пути на любом уровне
(порядок слов — не убывающая глубина). Слово подходит к узлу по началу любого
его слова, по общему началу ≥ 3 букв (формы слова), по числам (16 ≈ 0.016,
16х25 ≈ 0.016×0.025) или как синоним врача. Смысла не угадываем: нет
совпадения — нет кандидата; неоднозначно — варианты."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .workbook import Item, Workbook

SEP = ' › '
Path = tuple[str, ...]

_WORD = re.compile(r'[a-zа-я]+|\d+(?:[.,]\d+)?')
_NUM = re.compile(r'\d+(?:[.,]\d+)?')


@dataclass
class Resolution:
    leaves: list[Path]          # подходящие пути до конечных узлов (порядок файла)
    common: Path                # общий префикс — до него разворачивает Tab
    choices: list[Path]         # что показать списком
    bad_word: int | None        # первое слово, после которого кандидатов нет


def _key(s: str) -> str:
    return s.lower().replace('ё', 'е')


def _ws(s: str) -> str:
    return ' '.join(s.split())


def _num(s: str) -> str:
    """0.016 → 16, 0.025 → 25, 6 → 6: размер дуги — по значащим цифрам."""
    s = s.replace(',', '.')
    if '.' in s:
        s = s.split('.', 1)[1]
    return s.lstrip('0') or '0'


class _Node:
    __slots__ = ('words', 'nums')

    def __init__(self, text: str):
        toks = _WORD.findall(_key(text))
        self.words = [t for t in toks if not t[0].isdigit()]
        self.nums = [_num(t) for t in toks if t[0].isdigit()]


def children_of(wb: Workbook, code: str | None) -> list[Item]:
    """Ветки узла: разделы (None) → пункты → варианты + «нет»."""
    if code is None:
        return list(wb.sections)
    it = wb.by_id[code]
    out = list(it.children)
    if it.cancel and it.cancel in wb.by_id:
        out.append(wb.by_id[it.cancel])
    return out


def is_leaf(wb: Workbook, path: Path) -> bool:
    """Строка готова: последний узел — без вариантов (лист, «нет», пункт)."""
    return bool(path) and path[-1] in wb.by_id and not wb.by_id[path[-1]].children \
        and wb.by_id[path[-1]].level > 1


def format_path(wb: Workbook, path: Path) -> str:
    return SEP.join(_ws(wb.by_id[c].text) for c in path)


def parse_line(wb: Workbook, line: str) -> Path | None:
    """Строка — точный путь по дереву (тексты уровней совпадают с пунктами)."""
    if SEP.strip() not in line:
        return None
    parts = [_ws(p) for p in line.strip().split(SEP.strip())]
    if not all(parts):
        return None
    path: list[str] = []
    for part in parts:
        hit = next((c for c in children_of(wb, path[-1] if path else None)
                    if _ws(c.text) == part), None)
        if hit is None:
            return None
        path.append(hit.id)
    return tuple(path)


def split_line(wb: Workbook, line: str) -> tuple[Path | None, str]:
    """Строка в работе: (выбранные уровни — всё до последнего « › »; набранное
    после него). Уровни, которые не находятся в дереве, — None."""
    sep = SEP.strip()
    if sep not in line:
        return (), line
    head, _, typed = line.rpartition(sep)
    parts = [_ws(p) for p in head.split(sep)]
    path: list[str] = []
    for part in parts:
        hit = next((c for c in children_of(wb, path[-1] if path else None)
                    if _ws(c.text) == part), None)
        if hit is None:
            return None, typed.lstrip()
        path.append(hit.id)
    return tuple(path), typed.lstrip()


def _endpoints(wb: Workbook, start: Path) -> list[Path]:
    """Все конечные пути внутри start, в порядке файла."""
    out: list[Path] = []

    def walk(path: Path):
        kids = children_of(wb, path[-1] if path else None)
        if path and not wb.by_id[path[-1]].children and wb.by_id[path[-1]].level > 1:
            out.append(path)
        for c in kids:
            walk(path + (c.id,))
    walk(start)
    return out


def _token_matches(tok: str, node: _Node, code: str, synonyms: dict[str, str]) -> bool:
    syn = synonyms.get(tok)
    if syn is not None and syn == code:
        return True
    if any(w.startswith(tok) and syn_code == code for w, syn_code in synonyms.items()):
        return True
    if tok[0].isdigit():
        more = bool(re.search(r'[хx×*/]$', tok))            # «16х» — дальше ещё число
        seq = [_num(n) for n in _NUM.findall(tok.replace(',', '.'))]
        nums = node.nums
        for i in range(len(nums) - len(seq) + 1):
            if all((nums[i + k] == seq[k]) if k < len(seq) - 1 or more
                   else nums[i + k].startswith(seq[k]) for k in range(len(seq))):
                if not more or i + len(seq) < len(nums):
                    return True
        return False
    for w in node.words:
        if w.startswith(tok):
            return True
        n = 0
        while n < min(len(w), len(tok)) and w[n] == tok[n]:
            n += 1
        if n >= 3 and n >= len(tok) - 1:                    # «дуга» → «дуги»
            return True
    return False


def _tokens(typed: str) -> list[str]:
    return [t for t in _key(typed).split() if t]


def resolve(wb: Workbook, done: Path, typed: str, synonyms: dict[str, str]) -> Resolution:
    toks = _tokens(typed)
    syn = {_key(w): c for w, c in synonyms.items()}
    nodes = {it.id: _Node(it.text) for it in wb.items}
    paths = _endpoints(wb, done)
    if not toks:
        common = _common(paths) if paths else done
        nxt = children_of(wb, common[-1] if common else None) if not is_leaf(wb, common) else []
        return Resolution(paths, common, [common + (c.id,) for c in nxt], None)
    leaves: list[Path] = []
    choices: list[Path] = []
    best = 0
    for p in paths:
        pos, matched, last_at = len(done), 0, -1
        for t in toks:
            while pos < len(p) and not _token_matches(t, nodes[p[pos]], p[pos], syn):
                pos += 1
            if pos >= len(p):
                break
            matched += 1
            last_at = pos
        best = max(best, matched)
        if matched == len(toks):
            leaves.append(p)
            ch = p[:last_at + 1]
            if ch not in choices:
                choices.append(ch)
    common = _common(leaves) if leaves else done
    return Resolution(leaves, common, choices, None if leaves else best)


def _common(paths: list[Path]) -> Path:
    first = paths[0]
    n = len(first)
    for p in paths[1:]:
        k = 0
        while k < min(n, len(p)) and p[k] == first[k]:
            k += 1
        n = k
    return first[:n]

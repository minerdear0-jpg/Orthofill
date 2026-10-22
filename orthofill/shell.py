"""Оболочка (0.5): строка записи — путь по дереву пресета, как команда Cisco IOS.

Набранные слова — фильтры «И» по ещё не выбранной части пути на любом уровне
(порядок слов — не убывающая глубина). Слово подходит к узлу по началу любого
его слова, по общему началу ≥ 3 букв (формы слова), по числам (16 ≈ 0.016,
16х25 ≈ 0.016×0.025) или как синоним врача. Смысла не угадываем: нет
совпадения — нет кандидата; неоднозначно — варианты."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .canon import canon, layout_swap
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
    rest: list[str] = field(default_factory=list)   # слова, совпавшие ниже common (Tab их сохраняет)


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


_LETTERS = re.compile(r"[^\W\d_]+(?:[-.'’][^\W\d_]+)*")


class _Node:
    """Слова узла в приведённом виде (canon) + пары соседних слов слитно
    («фото протокол» ↔ «фотопротокол»); числа — значащими цифрами."""
    __slots__ = ('words', 'nums')

    def __init__(self, text: str):
        low = _key(text)
        words = [canon(w) for w in _LETTERS.findall(low)]
        self.words = words + [a + b for a, b in zip(words, words[1:])]
        self.nums = [_num(t) for t in _NUM.findall(low)]


def _nodes(wb: Workbook) -> dict[str, _Node]:
    """Приведённые слова узлов — один раз на пресет (пока тексты не менялись)."""
    key = tuple((it.id, it.text) for it in wb.items)
    cached = wb.__dict__.get('_shell_nodes')
    if cached is None or cached[0] != key:
        cached = (key, {it.id: _Node(it.text) for it in wb.items})
        wb.__dict__['_shell_nodes'] = cached
    return cached[1]


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


_NUMTOK = re.compile(r'[.,]?\d')


def _is_num(tok: str) -> bool:
    return bool(_NUMTOK.match(tok))


def _num_matches(tok: str, node: _Node) -> bool:
    more = bool(re.search(r'[хx×*/]$', tok))            # «16х» — дальше ещё число
    seq = [_num(n) for n in _NUM.findall(tok.replace(',', '.'))]
    nums = node.nums
    if not seq:
        return False
    for i in range(len(nums) - len(seq) + 1):
        if all((nums[i + k] == seq[k]) if k < len(seq) - 1 or more
               else nums[i + k].startswith(seq[k]) for k in range(len(seq))):
            if not more or i + len(seq) < len(nums):
                return True
    return False


def _match_run(toks: list[str], i: int, node: _Node, code: str,
               synonyms: dict[str, str]) -> int:
    """Сколько набранных слов, начиная с i, покрывает узел (0 — не подходит).
    Числа — по одному; слова — и склейкой соседних («cu ni ti» → «кунити»)."""
    tok = toks[i]
    if _is_num(tok):
        return 1 if _num_matches(tok, node) else 0
    if any(w.startswith(tok) and c == code for w, c in synonyms.items()):
        return 1
    best = 0
    for w in node.words:
        glued, k = '', i
        while k < len(toks) and not _is_num(toks[k]):
            glued += toks[k]
            if not w.startswith(glued):
                break
            best = max(best, k - i + 1)
            k += 1
        if best == 0:
            n = 0
            while n < min(len(w), len(tok)) and w[n] == tok[n]:
                n += 1
            if n >= 3 and n >= len(tok) - 1:                # «дуга» → «дуги»
                best = 1
    return best


def _prep(typed: str, swap: bool = False) -> list[str]:
    """Набранные слова: числа — как есть, слова — в приведённом виде
    (swap — в другой раскладке)."""
    out = []
    for t in typed.split():
        if _is_num(t):
            out.append(_key(t))
        else:
            out.append(canon(layout_swap(t)) if swap else canon(t))
    return [t for t in out if t]


def resolve(wb: Workbook, done: Path, typed: str, synonyms: dict[str, str]) -> Resolution:
    r = _resolve(wb, done, typed, _prep(typed), synonyms)
    if not r.leaves and typed.strip():                   # не та раскладка — только если
        alt = _prep(typed, swap=True)                    # как набрано ничего не нашлось
        if alt != _prep(typed):
            r2 = _resolve(wb, done, typed, alt, synonyms)
            if r2.leaves:
                return r2
    return r


def _resolve(wb: Workbook, done: Path, typed: str, toks: list[str],
             synonyms: dict[str, str]) -> Resolution:
    syn = {canon(w): c for w, c in synonyms.items()}
    nodes = _nodes(wb)
    paths = _endpoints(wb, done)
    if not toks:
        common = _common(paths) if paths else done
        nxt = children_of(wb, common[-1] if common else None) if not is_leaf(wb, common) else []
        return Resolution(paths, common, [common + (c.id,) for c in nxt], None)
    leaves: list[Path] = []
    choices: list[Path] = []
    first_at: list[int] = []
    best = 0
    for p in paths:
        pos, i, last_at, at = len(done), 0, -1, []
        while i < len(toks):
            c = 0
            while pos < len(p):
                c = _match_run(toks, i, nodes[p[pos]], p[pos], syn)
                if c:
                    break
                pos += 1
            if not c:
                break
            at += [pos] * c
            last_at = pos
            i += c
        best = max(best, i)
        if i == len(toks):
            if not leaves:
                first_at = at
            leaves.append(p)
            ch = p[:last_at + 1]
            if ch not in choices:
                choices.append(ch)
    common = _common(leaves) if leaves else done
    raw = [t for t in typed.split() if _prep(t)]
    rest = [t for t, a in zip(raw, first_at) if a >= len(common)]
    return Resolution(leaves, common, choices, None if leaves else best, rest)


def _common(paths: list[Path]) -> Path:
    first = paths[0]
    n = len(first)
    for p in paths[1:]:
        k = 0
        while k < min(n, len(p)) and p[k] == first[k]:
            k += 1
        n = k
    return first[:n]

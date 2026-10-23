"""Оболочка (0.5): строка записи — путь по дереву пресета, как команда Cisco IOS.

Набранные слова — фильтры «И» по ещё не выбранной части пути на любом уровне
(порядок слов — не убывающая глубина). Слово подходит к узлу по началу любого
его слова, по общему началу ≥ 3 букв (формы слова), по числам (16 ≈ 0.016,
16х25 ≈ 0.016×0.025) или как синоним врача. Смысла не угадываем: нет
совпадения — нет кандидата; неоднозначно — варианты."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .canon import canon, is_latin, layout_swap
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
    counts: dict[Path, int] = field(default_factory=dict)   # сколько подходящих значений за вариантом
    starts: set[Path] = field(default_factory=set)          # варианты, чьё значение начинается с набранного
    rests: dict[Path, list[str]] = field(default_factory=dict)  # выбрали ветку — эти слова остаются в строке


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
    """Слова узла в приведённом виде (canon) с пометкой «латиница в пресете»;
    слова через дефис — и целиком, и частями; пары соседних слов (первое от 3
    букв) — для слитного набора; числа — значащими цифрами."""
    __slots__ = ('words', 'pairs', 'nums', 'plain')

    def __init__(self, text: str):
        # римские цифры («по I классу») — числа, не буквы (иначе «I» = союз «и»)
        romans = [_ROMAN[r] for r in _ROMAN_RE.findall(text)]
        low = _key(_ROMAN_RE.sub(' ', text))
        words: list[tuple[str, bool]] = []
        plain: list[str] = []
        for chunk in _LETTERS.findall(low):
            lat = is_latin(chunk)
            whole = canon(chunk)
            words.append((whole, lat))
            plain.append(whole)
            parts = re.split(r"[-.'’]", chunk)
            if len(parts) > 1:
                words += [(canon(p), is_latin(p)) for p in parts if p]
        self.words = words
        self.plain = plain              # слова по порядку, без частей — для точного имени
        self.pairs = [(a, b) for a, b in zip(plain, plain[1:]) if len(a) >= 3]
        self.nums = [_num(t) for t in _NUM.findall(low)] + romans


_ROMAN = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5', 'VI': '6'}
_ROMAN_RE = re.compile(r'(?<![A-Za-zА-Яа-яЁё])(III|II|IV|VI|I|V)(?![A-Za-zА-Яа-яЁё])')


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
_SIZESEP = {'х', 'x', '×', '*', '/'}


def _is_num(tok: str) -> bool:
    return bool(_NUMTOK.match(tok))


@dataclass
class _Tok:
    text: str               # приведённое слово (число — как набрано)
    raws: list[int]         # из каких набранных слов (номера)
    num: bool
    latin: bool             # набрано латиницей


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


def _fits(glued: str, w: str, latin_typed: bool, latin_word: bool) -> bool:
    """Набранное подходит к слову узла: начало слова. Набрано латиницей, а слово
    в пресете русское — только целиком («perepel» = «перепел», но «ni» ≠ «нижней»)."""
    if latin_typed and not latin_word:
        return glued == w and len(w) >= 3       # «s» ≠ предлог «с»
    return w.startswith(glued)


def _match_run(toks: list[_Tok], i: int, node: _Node, code: str,
               synonyms: dict[str, set[str]]) -> int:
    """Сколько набранных слов, начиная с i, покрывает узел (0 — не подходит).
    Числа — по одному; слова — и склейкой соседних («cu ni ti» → «кунити»)."""
    tok = toks[i]
    if any(w.startswith(tok.text) and code in codes for w, codes in synonyms.items()):
        return 1
    if tok.num:
        return 1 if _num_matches(tok.text, node) else 0
    best = 0
    for w, wlat in node.words:
        glued, k, lat = '', i, False
        while k < len(toks) and not toks[k].num:
            if k > i and (len(toks[k].text) < 2 or len(toks[i].text) < 2):
                break                           # клеим кусочки от 2 букв («cu ni ti»), не «ду г»
            glued += toks[k].text
            lat = lat or toks[k].latin
            if not _fits(glued, w, lat, wlat):
                if lat and not wlat and w.startswith(glued):
                    k += 1                      # латиница по русскому слову — ждём целого
                    continue
                break
            best = max(best, k - i + 1)
            k += 1
        if best == 0 and not tok.latin:
            n = 0
            while n < min(len(w), len(tok.text)) and w[n] == tok.text[n]:
                n += 1
            if n >= 3 and n >= len(tok.text) - 1:           # «дуга» → «дуги»
                best = 1
    for a, b in node.pairs:                     # «фотопротокол» по «фото протокол»
        glued, k = '', i
        while k < len(toks) and not toks[k].num:
            if k > i and (len(toks[k].text) < 2 or len(toks[i].text) < 2):
                break
            glued += toks[k].text
            if not (a + b).startswith(glued):
                break
            if len(glued) >= len(a) + 2 and not any(t.latin for t in toks[i:k + 1]):
                best = max(best, k - i + 1)
            k += 1
    return best


def _prep(typed: str, swap: bool = False) -> list[_Tok]:
    """Набранные слова: «16 х 25» — одно число; слова — в приведённом виде;
    swap — латинские слова от 3 букв в другой раскладке («kbufnehyfz»)."""
    raw = typed.split()
    out: list[_Tok] = []
    i = 0
    while i < len(raw):
        t = raw[i]
        if (_is_num(t) and i + 2 < len(raw) and raw[i + 1].lower() in _SIZESEP
                and _is_num(raw[i + 2])):
            out.append(_Tok(_key(t + 'х' + raw[i + 2]), [i, i + 1, i + 2], True, False))
            i += 3
            continue
        if _is_num(t):
            out.append(_Tok(_key(t), [i], True, False))
        elif t.upper() in _ROMAN and t.isascii():      # набрали «ii» — это II
            out.append(_Tok(_ROMAN[t.upper()], [i], True, False))
        else:
            lat = is_latin(t)
            if swap and lat and len(t) >= 3:
                c, lat = canon(layout_swap(t)), False
            else:
                c = canon(t)
            if c:
                out.append(_Tok(c, [i], False, lat))
        i += 1
    return out


def resolve(wb: Workbook, done: Path, typed: str, synonyms: dict[str, str]) -> Resolution:
    r = _resolve(wb, done, typed, _prep(typed), synonyms)
    if not r.leaves and typed.strip():          # не та раскладка: только латинские слова
        alt = _prep(typed, swap=True)           # от 3 букв и только если как набрано — ничего
        if [t.text for t in alt] != [t.text for t in _prep(typed)]:
            r2 = _resolve(wb, done, typed, alt, synonyms)
            if r2.leaves:
                return r2
    return r


def _resolve(wb: Workbook, done: Path, typed: str, toks: list[_Tok],
             synonyms: dict[str, str]) -> Resolution:
    syn: dict[str, set[str]] = {}
    for w, c in synonyms.items():
        syn.setdefault(canon(w), set()).add(c)
    nodes = _nodes(wb)
    paths = _endpoints(wb, done)
    exact = _exact(nodes, paths, done, toks)
    if exact:                                   # набрано точное имя узла — только внутри него
        paths = [p for p in paths if exact & set(p[len(done):])]
    if not toks:
        common = _common(paths) if paths else done
        nxt = children_of(wb, common[-1] if common else None) if not is_leaf(wb, common) else []
        return Resolution(paths, common, [common + (c.id,) for c in nxt], None)
    leaves: list[Path] = []
    ats: dict[Path, list[int]] = {}
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
            ats[p] = at
    common = _common(leaves) if leaves else done
    choices, counts, starts = _fork(nodes, leaves, common, toks)
    raw_words = typed.split()
    rests = {}
    for ch in choices:                          # слова, совпавшие ниже выбранной ветки
        at = ats[next(p for p in leaves if p[:len(ch)] == ch)]
        rests[ch] = [raw_words[j] for t, a in zip(toks, at) if a >= len(ch) for j in t.raws]
    raw = typed.split()
    rest = [raw[j] for t, a in zip(toks, first_at) if a >= len(common) for j in t.raws]
    if leaves and not rest and len(common) > len(done):     # всё набранное — в общем: его и дописать
        choices, counts, rests = [common], {common: len(leaves)}, {common: []}
        starts = {common} if starts else set()
    bad = None if leaves else (toks[best].raws[0] if best < len(toks) else len(raw) - 1)
    return Resolution(leaves, common, choices, bad, rest, counts, starts, rests)


def _fork(nodes: dict[str, _Node], leaves: list[Path], common: Path, toks: list[_Tok]):
    """Варианты на развилке — уровень сразу после общего (как в fish): ветка, за
    которой одно подходящее значение, — сразу это значение. Число значений за
    вариантом и «начинается с набранного» (первое слово значения)."""
    first = toks[0].text if toks and not toks[0].num else None
    under: dict[Path, list[Path]] = {}
    for p in leaves:
        under.setdefault(p[:len(common) + 1], []).append(p)
    choices: list[Path] = []
    counts: dict[Path, int] = {}
    starts: set[Path] = set()
    for key, ps in under.items():
        ch = ps[0] if len(ps) == 1 else key
        choices.append(ch)
        counts[ch] = len(ps)
        if first and any(nodes[p[-1]].plain[:1] and nodes[p[-1]].plain[0].startswith(first)
                         for p in ps):
            starts.add(ch)
    return choices, counts, starts


def _exact(nodes: dict[str, _Node], paths: list[Path], done: Path, toks: list[_Tok]) -> set[str]:
    """Узлы, имя которых набрано целиком (только слова, без чисел): «лечение» —
    раздел «Лечение:». Совпало несколько — все (ничего не угадываем)."""
    if not toks or any(t.num for t in toks):
        return set()
    want = [t.text for t in toks]
    codes = {c for p in paths for c in p[len(done):]}
    return {c for c in codes if not nodes[c].nums and nodes[c].plain == want}


def _common(paths: list[Path]) -> Path:
    first = paths[0]
    n = len(first)
    for p in paths[1:]:
        k = 0
        while k < min(n, len(p)) and p[k] == first[k]:
            k += 1
        n = k
    return first[:n]

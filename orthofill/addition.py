"""«Добавить пункт»: поиск варианта/пункта пресета и вставка его строки в протокол,
который врач, возможно, уже поправил руками (правки сохраняются)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parse import detect_material
from .render import join_group
from .text import norm
from .workbook import Item, Workbook

# Набрано в английской раскладке: «gthtgtk» → «перепел»
_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
_RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
_EN_RU = str.maketrans(_EN, _RU)


@dataclass
class SearchHit:
    code: str
    label: str                        # текст варианта / пункта, без кода
    where: str                        # «Лечение → Юстировка дуги»
    spans: list[tuple[int, int]] = field(default_factory=list)   # что совпало в label


def _ws(text: str) -> str:
    return ' '.join(text.split())


def _title(text: str) -> str:
    return _ws(text).rstrip(':').strip()


def _choices(wb: Workbook) -> list[tuple[Item, Item | None]]:
    """(пункт, его группа) — варианты групп и отдельные пункты разделов."""
    out = []
    for section in wb.sections:
        for it in section.children:
            if it.children:
                out += [(c, it) for c in it.children]
            else:
                out.append((it, None))
    return out


def _where(wb: Workbook, item: Item, group: Item | None) -> str:
    section = wb.by_id.get(item.id[0])
    parts = [_title(section.text)] if section else []
    if group is not None:
        parts.append(_title(group.text))
    return ' → '.join(parts)


def _num_key(n: str) -> str:
    """«0.018×0.025"» → «18x25»: так врач пишет размеры дуг."""
    n = re.sub(r'0[.,]0?(\d{2})', r'\1', n)
    return re.sub(r'(?<=\d)\s*[xх×*/]\s*(?=\d)', 'x', n)


def _query_words(query: str) -> list[str]:
    q = _num_key(norm(query))
    return [w for w in q.split() if re.search(r'[а-яa-z0-9]', w)]


def _match(label: str, words: list[str]) -> list[tuple[int, int]] | None:
    n = norm(label)
    if any(re.search(r'\d', w) or detect_material(w) for w in words):   # дуги — как пишет врач
        key, mat = _num_key(n), detect_material(n)
        ok = all((detect_material(w) is not None and detect_material(w) == mat)
                 or re.search(r'(?<![а-яa-z0-9])' + re.escape(w), key) for w in words)
        return [] if ok else None
    spans = []
    for w in words:
        m = re.search(r'(?<![а-яa-z0-9])' + re.escape(w), n)
        if m is None:
            return None
        spans.append(m.span())
    return spans if len(n) == len(label) else []


def search_items(wb: Workbook, query: str, limit: int = 7) -> list[SearchHit]:
    """Все слова запроса — по началу слов текста; выше: совпадение с начала
    текста, пункты со словами врача, короче текст. Пустой запрос — пункты,
    к которым уже привязаны слова врача."""
    taught = {_ws(e.item_text) for e in wb.dictionary}
    choices = _choices(wb)
    words = _query_words(query)
    if not words:
        return [SearchHit(it.id, _ws(it.text), _where(wb, it, g))
                for it, g in choices if _ws(it.text) in taught][:limit]

    def run(ws: list[str]) -> list[tuple[tuple, SearchHit]]:
        found = []
        for it, g in choices:
            label = _ws(it.text)
            spans = _match(label, ws)
            if spans is None:
                continue
            key = (0 if norm(label).startswith(ws[0]) else 1,
                   0 if label in taught else 1, len(label))
            found.append((key, SearchHit(it.id, label, _where(wb, it, g), spans)))
        return found

    found = run(words)
    if not found and re.search(r'[a-z]', ' '.join(words)):
        found = run(_query_words(' '.join(words).translate(_EN_RU)))
    return [h for _, h in sorted(found, key=lambda x: x[0])][:limit]


def row_text(item: Item, group: Item | None) -> str:
    return join_group(group.text, item.text) if group is not None else _ws(item.text)


def _known_lines(wb: Workbook) -> dict[str, str]:
    """Текст строки протокола → код пункта (вариант для склейки «группа + вариант»)."""
    out: dict[str, str] = {}
    for it, g in _choices(wb):
        out.setdefault(row_text(it, g), it.id)
    return {_ws(k): v for k, v in out.items()}


def _is_head(line: str, section: Item) -> bool:
    """Заголовок раздела, даже если врач убрал двоеточие или приписал строку:
    «Лечение», «Лечение:», «Лечение: осмотр.»."""
    t, ln = norm(_title(section.text)), norm(_ws(line))
    return ln.rstrip(':').strip() == t or ln.startswith(t + ':')


def insert_item(wb: Workbook, text: str, code: str) -> tuple[str, int]:
    """Вставить строку пункта в текст протокола → (новый текст, номер строки).
    Пункт уже есть — текст не меняется (номер его строки). Невправленая строка
    другого варианта той же группы заменяется, где бы она ни стояла. Иначе
    строка встаёт в свой раздел по порядку пресета; нет заголовка раздела —
    раздел добавляется на своё место."""
    item = wb.by_id[code]
    group = wb.by_id.get(item.parent) if item.level == 3 and not item.orphan else None
    section = wb.by_id[code[0]]
    row = row_text(item, group)
    lines = text.splitlines()

    same = next((i for i, ln in enumerate(lines) if _ws(ln) == _ws(row)), None)
    if same is not None:
        return text, same
    if group is not None:
        siblings = {_ws(join_group(group.text, c.text)) for c in group.children if c is not item}
        for i, ln in enumerate(lines):
            if _ws(ln) in siblings:
                lines[i] = row
                return '\n'.join(lines), i

    def head_of(ln: str) -> Item | None:
        return next((s for s in wb.sections if _is_head(ln, s)), None)

    h = next((i for i, ln in enumerate(lines) if _is_head(ln, section)), None)
    if h is not None:
        end = next((i for i in range(h + 1, len(lines)) if head_of(lines[i])), len(lines))
        # на своё место по порядку пресета: перед первой строкой раздела, чей пункт
        # идёт позже; строки, которые врач переписал (не узнаются), пропускаются
        order = {it.id: k for k, it in enumerate(wb.items)}
        known = _known_lines(wb)
        at = next((i for i in range(h + 1, end)
                   if order.get(known.get(_ws(lines[i]), ''), -1) > order[code]), end)
        lines.insert(at, row)
        return '\n'.join(lines), at

    later = wb.sections[wb.sections.index(section) + 1:]
    at = next((i for i, ln in enumerate(lines) if head_of(ln) in later), len(lines))
    lines[at:at] = [_ws(section.text), row]
    return '\n'.join(lines), at + 1

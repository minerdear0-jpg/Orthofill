"""Черновик пресета для редактора: правки над копией в памяти, отмена/возврат,
журнал операций.

Журнал нужен при сохранении: пункты пишутся из черновика, а эталоны и словарь
берутся текущие из базы (главное окно могло выучить слово или сохранить эталон,
пока черновик был открыт) — и на них заново повторяются операции черновика
(`replay`): смены кодов, переименования, удаления."""
from __future__ import annotations

import copy
from typing import Any

from . import engine
from .codes import (CodeMap, apply_map, code_error, inside, next_code, rebuild, rename_map,
                    renumber_map, swap_map)
from .presets import PresetStore
from .workbook import DictEntry, Item, ReferenceCase, Workbook

Op = tuple[Any, ...]
# ('codes', CodeMap) · ('text', code, old, new) · ('del_item', codes, texts)
# ('del_ref', case_id) · ('accept_ref', case_id, lines) · ('del_word', word) · ('import',)


def _ws(text: str) -> str:
    return ' '.join(text.split())


class Draft:
    def __init__(self, wb: Workbook, preset_id: int):
        self.preset_id = preset_id
        self.wb = copy.deepcopy(wb)
        self.ops: list[Op] = []
        self.imported: Workbook | None = None
        self._undo: list[tuple] = []
        self._redo: list[tuple] = []

    # ---------- отмена ----------
    @property
    def changed(self) -> int:
        """Сколько правок после открытия / последнего сохранения."""
        return len(self._undo)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _state(self) -> tuple:
        return copy.deepcopy(self.wb), list(self.ops), self.imported

    def _restore(self, state: tuple) -> None:
        self.wb, self.ops, self.imported = state

    def _begin(self) -> None:
        """Перед каждой командой: снимок для отмены (пресет ~200 пунктов — дёшево)."""
        self._undo.append(self._state())
        self._redo.clear()

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self._state())
            self._restore(self._undo.pop())

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self._state())
            self._restore(self._redo.pop())

    def mark_saved(self) -> None:
        self.ops, self.imported = [], None
        self._undo.clear()
        self._redo.clear()

    # ---------- пункты ----------
    def _subtree(self, code: str) -> list[Item]:
        return [it for it in self.wb.items if it.id == code or inside(it.id, code)]

    def add(self, parent: str | None, after: str | None, text: str, level: int) -> str:
        """Новый пункт со свободным кодом — после after (с его вариантами) или
        в конец родителя. Возвращает код."""
        self._begin()
        code = next_code(self.wb, parent, level, self._reserved())
        item = Item(code, text, level, parent)
        items = self.wb.items
        anchor = after if after in self.wb.by_id else parent
        if anchor is None:
            at = len(items)
        else:
            block = self._subtree(anchor)
            if anchor == parent and parent is not None:     # в конец родителя
                block = self._subtree(parent)
            at = items.index(block[-1]) + 1
        items.insert(at, item)
        rebuild(self.wb)
        return code

    def _reserved(self) -> set[str]:
        """Коды, которые новому пункту давать нельзя: удалённые в этом черновике
        и те, что ещё стоят в эталонах и словаре."""
        out = {c for op in self.ops if op[0] == 'del_item' for c in op[1]}
        out |= {c for r in self.wb.references for c, _ in r.lines if c}
        out |= {e.code for e in self.wb.dictionary if e.code}
        return out

    def impact(self, code: str) -> tuple[int, int]:
        """(сколько эталонов, сколько слов врача) затронет удаление пункта."""
        codes = {it.id for it in self._subtree(code)}
        refs = sum(any(c in codes for c, _ in case.lines) for case in self.wb.references)
        words = sum(e.code in codes for e in self.wb.dictionary)
        return refs, words

    def delete(self, code: str) -> None:
        """Удалить пункт с вариантами. Строки эталонов сохраняют код — сверка
        покажет ✗; слова врача, привязанные к пункту, удаляются."""
        self._begin()
        gone = self._subtree(code)
        codes = tuple(it.id for it in gone)
        texts = tuple(_ws(it.text) for it in gone)
        self.wb.items[:] = [it for it in self.wb.items if it.id not in codes]
        for it in self.wb.items:
            if it.default in codes:
                it.default = None
        self.wb.dictionary[:] = _drop_words(self.wb.dictionary, codes, texts)
        self.wb.not_together[:] = [p for p in self.wb.not_together
                                   if p[0] not in codes and p[1] not in codes]
        rebuild(self.wb)
        self.ops.append(('del_item', codes, texts))

    def move(self, code: str, delta: int) -> bool:
        """↑↓ среди детей своего родителя; коды не меняются."""
        it = self.wb.by_id[code]
        sibs = self.wb.sections if it.parent is None else self.wb.by_id[it.parent].children
        k = sibs.index(it)
        j = k + delta
        if not 0 <= j < len(sibs):
            return False
        self._begin()
        a, b = (sibs[j], it) if delta < 0 else (it, sibs[j])   # b встаёт перед a
        first, second = self._subtree(a.id), self._subtree(b.id)
        items = self.wb.items
        start = items.index(first[0])
        rest = [x for x in items if x not in first and x not in second]
        items[:] = rest[:start] + second + first + rest[start:]
        rebuild(self.wb)
        return True

    def set_text(self, code: str, text: str) -> None:
        """Новый текст пункта. Угаданное по старому тексту (способ выбора группы,
        «когда» пункта) сперва закрепляется — переименование не меняет поведение.
        Строки эталонов и слова врача с прежним текстом переписываются."""
        it = self.wb.by_id[code]
        if _ws(text) == _ws(it.text):
            return
        self._begin()
        if it.children and it.method is None:
            it.method = engine._guess_kind(it) or 'words'
        if it.level == 2 and not it.children and not it.orphan and it.when is None:
            it.when = engine._effective_when(self.wb)[code]
        if it.orphan and it.when is None:       # угаданное по названию условие — закрепить
            cond = engine.guess_condition(it, self.wb)
            if cond and it.condition is None:
                it.condition = cond
            it.when = 'condition' if cond else 'mentioned'
        old = it.text
        it.text = text
        _retext(self.wb.references, self.wb.dictionary, code, old, text)
        self.ops.append(('text', code, old, text))

    def set_prop(self, code: str, name: str, value) -> None:
        if name not in ('method', 'when', 'default', 'words'):
            raise ValueError(name)
        self._begin()
        setattr(self.wb.by_id[code], name, value)

    def set_code(self, code: str, new: str) -> str | None:
        """Ошибка словами или None. Код соседа занят — вызывающий спрашивает
        «Поменять местами?» и зовёт swap."""
        err = code_error(self.wb, code, new)
        if err or new == code:
            return err
        self._codes(rename_map(self.wb, code, new))
        return None

    # ---------- логика (0.2 beta 5) ----------
    def set_condition(self, code: str, node: dict | None) -> None:
        self._begin()
        self.wb.by_id[code].condition = node

    def set_combine(self, code: str, value: str | None) -> None:
        self._begin()
        self.wb.by_id[code].combine = value

    def add_pair(self, a: str, b: str) -> None:
        pair = tuple(sorted((a, b)))
        if a == b or pair in self.wb.not_together:
            return
        self._begin()
        self.wb.not_together[:] = sorted(self.wb.not_together + [pair])

    def remove_pair(self, a: str, b: str) -> None:
        pair = tuple(sorted((a, b)))
        if pair in self.wb.not_together:
            self._begin()
            self.wb.not_together.remove(pair)

    def referrers(self, code: str) -> list[str]:
        """Пункты, чьи условия ссылаются на код (или пункты внутри него)."""
        from .logic import refs
        inner = {code} | {it.id for it in self.wb.items if inside(it.id, code)}
        return [it.id for it in self.wb.items if it.condition and refs(it.condition) & inner]

    # ---------- фразы врача (0.3 beta 3) ----------
    def add_phrase(self, name: str, template: str) -> str | None:
        """Добавить или заменить фразу. Ошибка шаблона — текстом, без правки."""
        from .phrases import parse_template
        from .workbook import Phrase
        name = name.strip().lstrip('.')
        if not name:
            return 'нужно имя фразы'
        try:
            parse_template(template)
        except ValueError as e:
            return str(e)
        self._begin()
        old = next((p for p in self.wb.phrases if p.name == name), None)
        if old is not None:
            old.template = template.strip()
        else:
            self.wb.phrases.append(Phrase(name, template.strip()))
        self.ops.append(('phrase_set', name))
        return None

    def delete_phrase(self, name: str) -> None:
        if any(p.name == name for p in self.wb.phrases):
            self._begin()
            self.wb.phrases[:] = [p for p in self.wb.phrases if p.name != name]
            self.ops.append(('phrase_del', name))

    def swap(self, a: str, b: str) -> None:
        self._codes(swap_map(a, b, self.wb))

    def renumber(self, parent: str) -> None:
        m = renumber_map(self.wb, parent)
        if m:
            self._codes(m)

    def _codes(self, m: CodeMap) -> None:
        self._begin()
        apply_map(self.wb, m)
        self.ops.append(('codes', m))

    # ---------- эталоны, слова, импорт ----------
    def delete_reference(self, case_id: str) -> None:
        self._begin()
        self.wb.references[:] = [r for r in self.wb.references if r.case_id != case_id]
        self.ops.append(('del_ref', case_id))

    def accept_reference(self, case_id: str) -> None:
        """Строки эталона := то, что программа строит сейчас по черновику."""
        case = next(r for r in self.wb.references if r.case_id == case_id)
        self._begin()
        case.lines[:] = list(engine.protocol_for(self.wb, case.raw).lines)
        self.ops.append(('accept_ref', case_id, list(case.lines)))

    def delete_word(self, word: str) -> None:
        self._begin()
        w = PresetStore.norm_word(word)
        self.wb.dictionary[:] = [e for e in self.wb.dictionary if PresetStore.norm_word(e.word) != w]
        self.ops.append(('del_word', w))

    def import_wb(self, wb: Workbook) -> None:
        """Пресет из xlsx целиком заменяет черновик (одна отменяемая правка)."""
        self._begin()
        name = self.wb.name
        self.wb = copy.deepcopy(wb)
        self.wb.name = name
        self.imported = wb
        self.ops.append(('import',))

    def check(self) -> list[engine.CaseResult]:
        return engine.check_references(self.wb)

    # ---------- сохранение ----------
    def replay(self, references: list[ReferenceCase],
               dictionary: list[DictEntry]) -> tuple[list[ReferenceCase], list[DictEntry]]:
        """Повторить журнал операций над эталонами и словарём из базы. После
        импорта xlsx — эталоны и словарь черновика (из файла) как есть."""
        if any(op[0] == 'import' for op in self.ops):
            return copy.deepcopy(self.wb.references), copy.deepcopy(self.wb.dictionary)
        refs, words = copy.deepcopy(references), copy.deepcopy(dictionary)
        for op in self.ops:
            kind = op[0]
            if kind == 'codes':
                m = op[1]
                for case in refs:
                    case.lines[:] = [(m.get(c, c), t) for c, t in case.lines]
                for e in words:
                    e.code = m.get(e.code, e.code)
            elif kind == 'text':
                _retext(refs, words, *op[1:])
            elif kind == 'del_item':
                words = _drop_words(words, op[1], op[2])
            elif kind == 'del_ref':
                refs = [r for r in refs if r.case_id != op[1]]
            elif kind == 'accept_ref':
                for r in refs:
                    if r.case_id == op[1]:
                        r.lines[:] = list(op[2])
            elif kind == 'del_word':
                words = [e for e in words if PresetStore.norm_word(e.word) != op[1]]
        return refs, words


def _retext(refs: list[ReferenceCase], words: list[DictEntry], code: str, old: str, new: str) -> None:
    for case in refs:
        case.lines[:] = [(c, new if c == code and _ws(t) == _ws(old) else t) for c, t in case.lines]
    for e in words:
        if _ws(e.item_text) == _ws(old) and e.code in (code, ''):
            e.item_text = new


def _drop_words(words: list[DictEntry], codes, texts) -> list[DictEntry]:
    return [e for e in words
            if e.code not in codes and not (not e.code and _ws(e.item_text) in texts)]

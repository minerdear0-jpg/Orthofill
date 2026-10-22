"""Логика окна без tkinter — чтобы её можно было проверить тестами."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import difflib
import re
import time
import traceback

from .diag import DiagLog, text_diff
from .engine import Protocol, build_protocol, check_references, rule_warnings
from .parse import extract_facts
from .vocab import signature, unknown_words
from .addition import SearchHit, insert_item, row_text, search_items
from .draft import Draft
from .journal import Journal
from .lint import LEVEL_LABELS, lint
from .presets import PresetStore
from .workbook import Workbook, WorkbookError, lines_for_reference, load_workbook_file
from .xlsx_export import export_workbook

NO_PRESETS = 'Пресетов нет — импортируйте xlsx'

WIDE_MIN_WIDTH = 900

# «Что пошло не так?» — варианты для врача
CASE_KINDS = {
    'me': 'Я',
    'program': 'Программа',
    'classifier': 'Классификатор',
    'unknown': 'Не знаю',
}
# Повторный Ctrl+Enter с похожей записью вскоре после первого — врач поправил запись,
# а не перешёл к следующему пациенту
NOTE_FIX_SECONDS = 120
NOTE_FIX_SIMILARITY = 0.6


def layout_mode(width: int) -> str:
    return 'wide' if width >= WIDE_MIN_WIDTH else 'narrow'


@dataclass
class GenerateResult:
    text: str
    status: str
    warnings: list[str]
    defaults_line: str
    copied: bool
    rows: list = field(default_factory=list)     # render.Row — для вида в окне
    unknown: list = field(default_factory=list)  # [(начало, конец, слово)] непонятые слова записи


@dataclass
class AddResult:
    text: str
    line: int
    status: str
    code: str
    candidates: list[str]
    learned: str | None = None


def _clean_word(word: str) -> str:
    """Слово/фраза врача из записи: знаки препинания и переносы — пробелы."""
    return re.sub(r'[,;:.!?()«»"\n\r\t]+', ' ', word)


def _fmt_line(line: tuple[str, str]) -> str:
    code, text = line
    return f'{code or "—"}  {text[:90]}'


class Controller:
    def __init__(self, journal: Journal, clipboard: Callable[[str], None]):
        self.journal = journal
        self.clipboard = clipboard
        self.presets = PresetStore(journal)
        self.preset_id: int | None = None
        self.workbook: Workbook | None = None
        self.file_status = NO_PRESETS
        self.details: list[str] = []
        self.draft: Draft | None = None
        self.last_protocol: Protocol | None = None
        self.last_entry_id: int | None = None
        self._last_shown = ''      # текст, выданный программой или уже скопированный
        self._last_raw = ''        # запись, по которой сформирован last_protocol
        self.diag_dir = journal.db_path.parent / 'diagnostics'
        self._diag = DiagLog(self.diag_dir)
        self.diagnostics = False
        self.last_copy_edited = False
        self._last_generate_at = 0.0
        self.last_learn_broke: list[str] = []

    # ---------- диагностика ----------
    def set_diagnostics(self, enabled: bool) -> None:
        if enabled:
            self.diagnostics = True
            self._log('diagnostics_on')
        else:
            self._log('diagnostics_off')
            self.diagnostics = False
        self.journal.set_setting('diagnostics', '1' if enabled else '0')

    def _log(self, event: str, **data) -> None:
        if self.diagnostics:
            self._diag.write(event, **data)

    def _log_error(self, where: str, e: Exception) -> None:
        self._log('error', where=where, error=f'{type(e).__name__}: {e}',
                  traceback=''.join(traceback.format_exception(e)))

    def _preset_ref(self) -> dict | None:
        return {'id': self.preset_id, 'name': self.workbook.name} if self.workbook else None

    # ---------- пресеты ----------
    def whats_new_pending(self) -> bool:
        """Эта версия запущена впервые и «Что нового» ещё не открывали."""
        from . import VERSION_LABEL
        return self.journal.get_setting('seen_version') != VERSION_LABEL

    def mark_whats_new_seen(self) -> None:
        from . import VERSION_LABEL
        self.journal.set_setting('seen_version', VERSION_LABEL)

    def startup(self) -> None:
        self.diagnostics = self.journal.get_setting('diagnostics') == '1'
        saved = self.journal.get_setting('preset_id')
        if saved and saved.isdigit() and self.presets.exists(int(saved)):
            self._activate(int(saved))
            return
        existing = self.presets.list()
        if existing:
            self._activate(existing[0].id)
            return
        last = self.journal.get_setting('last_file')     # база 0.1: файл → пресет
        if last and Path(last).exists():
            self.import_xlsx(Path(last))                 # ошибки не роняют запуск
        else:
            self.file_status = NO_PRESETS

    def _activate(self, preset_id: int) -> None:
        self.preset_id = preset_id
        self.workbook = self.presets.load(preset_id)
        self.journal.snapshot(self.workbook)       # entries.sha256 → снимок пресета
        self.journal.set_setting('preset_id', str(preset_id))
        self.last_protocol, self._last_raw, self._last_shown = None, '', ''
        self.last_entry_id = None
        self._refresh_status()

    def import_xlsx(self, path: Path, update_id: int | None = None) -> None:
        """Новый пресет из файла или обновление пресета update_id. Файл с ошибками
        пресеты не трогает: текущий остаётся рабочим, причины — в details."""
        path = Path(path)
        try:
            wb = load_workbook_file(path)
        except WorkbookError as e:
            self.details, self.file_status = [str(e)], f'✗ {e}'
            self._log('import', file=path.name, status=self.file_status, details=self.details)
            return
        except Exception as e:     # непредвиденное — показать, а не упасть молча
            self.details, self.file_status = [repr(e)], f'✗ Ошибка: {e}'
            self._log_error('import', e)
            return
        if wb.problems:
            self.details = ([f'Ошибка: {p}' for p in wb.problems] +
                            [f'Предупреждение: {w}' for w in wb.warnings])
            self.file_status = f'✗ ошибки в файле: {len(wb.problems)} — подробнее'
            self._log('import', file=path.name, status=self.file_status, details=self.details)
            return
        try:
            if update_id is not None:
                self.presets.update(update_id, wb)
                pid = update_id
                if self.draft is not None and self.draft.preset_id == update_id:
                    self.draft = None       # черновик — по старому пресету
            else:
                pid = self.presets.create(wb)
            self._activate(pid)
        except Exception as e:     # транзакция откатилась — пресеты как были
            self.details, self.file_status = [repr(e)], f'✗ Ошибка: {e}'
            self._log_error('import', e)
            return
        self._log('import', file=path.name, sha256=wb.sha256, preset=self._preset_ref(),
                  update=update_id is not None, items=len(wb.items),
                  references=len(wb.references), dictionary_added=len(wb.dictionary),
                  status=self.file_status, details=self.details)

    def needs_export_before_update(self, preset_id: int) -> bool:
        return any(p.id == preset_id and p.dirty for p in self.presets.list())

    def export_xlsx(self, path: Path, preset_id: int | None = None) -> str:
        """Выгрузить текущий пресет (или preset_id — из редактора)."""
        path = Path(path)
        if preset_id is not None and preset_id != self.preset_id:
            wb, pid = self.presets.load(preset_id), preset_id
        else:
            wb, pid = self.workbook, self.preset_id
        if wb is None:
            return 'Сначала импортируйте пресет (xlsx)'
        try:
            export_workbook(wb, path)
        except PermissionError:
            return 'Файл открыт в Excel или нет прав на запись — закройте его и повторите'
        except Exception as e:
            self._log_error('export', e)
            return f'✗ Ошибка: {e}'
        self.presets.mark_exported(pid, path.name)
        self._log('export', file=path.name, preset=self._preset_ref(),
                  items=len(wb.items), references=len(wb.references),
                  dictionary=len(wb.dictionary))
        return f'Выгружено: {path.name}'

    def switch_preset(self, preset_id: int) -> None:
        before = self._preset_ref()
        self._activate(preset_id)
        self._log('preset_switch', **{'from': before, 'to': self._preset_ref()})

    def _refresh_status(self) -> None:
        wb = self.workbook
        details = [f'Ошибка: {p}' for p in wb.problems]
        if wb.problems:
            self.details = details + [f'Предупреждение: {w}' for w in wb.warnings]
            self.file_status = f'✗ ошибки в файле: {len(wb.problems)} — подробнее'
            return
        results = check_references(wb)
        ok = sum(r.ok for r in results)
        for r in results:
            if r.own_lines:
                details.append(f'эталон {r.case_id}: свои строки врача — {r.own_lines} '
                               f'(не проверяются)')
            if r.ok:
                continue
            details.append(f'Не совпадает эталон {r.case_id}:')
            details += [f'   нет в результате: {_fmt_line(x)}' for x in r.missing]
            details += [f'   лишнее в результате: {_fmt_line(x)}' for x in r.extra]
            if not r.missing and not r.extra:
                details.append('   отличается порядок строк')
        details += [f'Предупреждение: {w}' for w in wb.warnings + rule_warnings(wb)]
        details += [f'{LEVEL_LABELS[f.level]} классификатора: {f.message}' for f in lint(wb)]
        self.details = details
        n = len(wb.items)
        self.file_status = (f'✓ пунктов: {n} · эталоны {ok}/{len(results)}'
                            if ok == len(results) else
                            f'⚠ эталоны {ok}/{len(results)} — подробнее')

    # ---------- протокол ----------
    def generate(self, raw: str, copy: bool = True) -> GenerateResult:
        """copy=False — пересобрать без копирования (смена пресета)."""
        def fail(status):
            return GenerateResult('', status, [], '', False)
        if self.workbook is None:
            return fail('Сначала импортируйте пресет (xlsx)')
        if not raw.strip():
            return fail('Введите краткую запись')
        try:
            p = build_protocol(self.workbook, raw)
        except Exception as e:
            self._log_error('generate', e)
            return fail(f'✗ Ошибка: {e}')
        prev_raw, prev_at = self._last_raw, self._last_generate_at
        if (self.diagnostics and prev_raw and raw.strip() != prev_raw.strip()
                and time.monotonic() - prev_at <= NOTE_FIX_SECONDS
                and difflib.SequenceMatcher(None, prev_raw, raw).ratio() >= NOTE_FIX_SIMILARITY):
            self._log('note_changed', before=prev_raw, after=raw,
                      seconds=round(time.monotonic() - prev_at))
        self.last_protocol, self._last_raw = p, raw
        self._last_generate_at = time.monotonic()
        self.last_copy_edited = False
        self.last_entry_id = self.journal.log_generate(raw, p, self.workbook.sha256,
                                                       self.preset_id)
        if copy:
            self.clipboard(p.text)
            self.journal.log_copy(self.last_entry_id, p.text)
        self._last_shown = p.text
        if p.dictionary_hits:
            self.presets.count_hits(self.preset_id, p.dictionary_hits)
            for e in self.workbook.dictionary:
                if e.word in p.dictionary_hits:
                    e.hits += 1
        self._last_sig = signature(p)       # для подчёркивания — считается потом (find_unknown)
        if self.diagnostics:
            facts = extract_facts(raw)
            self._log('generate', entry_id=self.last_entry_id, raw=raw,
                      raw_norm=facts['raw_norm'], facts=facts,
                      lines=p.lines, warnings=p.warnings, defaults=p.defaults,
                      preset=self._preset_ref(), sha256=self.workbook.sha256,
                      dictionary_hits=p.dictionary_hits)
        defaults = f'по умолчанию: {", ".join(p.defaults)}' if p.defaults else ''
        status = 'Скопировано в буфер' if copy else 'Протокол пересобран (в буфер не копировался)'
        return GenerateResult(p.text, status, p.warnings, defaults, copy, p.rows)

    # ---------- «Добавить пункт» и словарь врача ----------
    def search(self, query: str) -> list[SearchHit]:
        return search_items(self.workbook, query) if self.workbook else []

    def find_unknown(self) -> list[tuple[int, int, str]]:
        """Непонятые слова последней записи (самопроверка). Отдельно от generate:
        окно вызывает это после показа протокола — Ctrl+Enter не ждёт."""
        if self.workbook is None or self.last_protocol is None:
            return []
        try:
            found = unknown_words(self.workbook, self._last_raw, getattr(self, '_last_sig', None))
        except Exception as e:      # подчёркивание — подсказка, протокол важнее
            self._log_error('unknown_words', e)
            return []
        self._log('unknown', entry_id=self.last_entry_id, words=[w for *_, w in found])
        return found

    def word_candidates(self, raw: str) -> list[str]:
        """Непонятые слова записи — последнее написанное первым."""
        out = []
        found = (self.find_unknown() if raw.strip() == self._last_raw.strip()
                 else unknown_words(self.workbook, raw))
        for *_, w in reversed(found):
            if w not in out:
                out.append(w)
        return out

    def add_item(self, current_text: str, code: str, word: str | None = None) -> AddResult:
        """Вставить пункт в протокол (правки врача целы) и сразу скопировать.
        word — подчёркнутое слово, с которого начали: оно запоминается сразу."""
        wb = self.workbook
        new, line = insert_item(wb, current_text, code)
        item = wb.by_id[code]
        group = wb.by_id.get(item.parent) if item.level == 3 and not item.orphan else None
        label = row_text(item, group)
        if new == current_text:
            status = f'«{label}» уже в протоколе'
            if word:
                status += '. ' + self.learn(word, code)
            return AddResult(new, line, status, code, [],
                             self.presets.norm_word(_clean_word(word)) if word else None)
        replaced = len(new.splitlines()) == len(current_text.splitlines())
        self.copy(new)
        section = wb.by_id.get(code[0])
        where = section.text.strip().rstrip(':') if section else ''
        status = f'✓ Добавлено: {label} → {where}. Протокол скопирован.'
        self._log('add_item', code=code, text=item.text, replaced=replaced, word=word,
                  raw=self._last_raw, preset=self._preset_ref())
        learned = None
        if word:
            status += ' ' + self.learn(word, code)
            learned = self.presets.norm_word(_clean_word(word))
        candidates = [] if word else self.word_candidates(self._last_raw)
        return AddResult(new, line, status, code, candidates, learned)

    def learn(self, word: str, code: str) -> str:
        w = self.presets.norm_word(_clean_word(word))
        if not w:
            return 'Выберите слово'
        item = self.workbook.by_id[code]
        group = self.workbook.by_id.get(item.parent) if item.level == 3 and not item.orphan else None
        before = {r.case_id: r.ok for r in check_references(self.workbook)}
        self.presets.learn(self.preset_id, w, item.text, code)
        self._reload()
        after = {r.case_id: r.ok for r in check_references(self.workbook)}
        self.last_learn_broke = [c for c, ok in before.items() if ok and not after.get(c, True)]
        self._log('learn', word=w, code=code, item_text=item.text, raw=self._last_raw,
                  broke=self.last_learn_broke, preset=self._preset_ref())
        if self.last_learn_broke:
            nums = ', '.join(self.last_learn_broke)
            return f'Запомнено «{w}», но после этого не совпадает эталон {nums} — проверьте или отмените'
        return f'Запомнено: «{w}» → {row_text(item, group)}'

    def unlearn(self, word: str) -> str:
        w = self.presets.norm_word(_clean_word(word))
        self.presets.unlearn(self.preset_id, w)
        self._reload()
        self.last_learn_broke = []
        self._log('learn_undo', word=w, preset=self._preset_ref())
        return f'Отменено: «{w}»'

    def skip_learning(self, code: str) -> None:
        self._log('learn_skip', code=code, raw=self._last_raw, preset=self._preset_ref())

    # ---------- редактор пресета ----------
    def open_draft(self, preset_id: int | None = None) -> Draft:
        """Черновик пресета для редактора — один на программу."""
        pid = self.preset_id if preset_id is None else preset_id
        if self.draft is None or self.draft.preset_id != pid:
            self.draft = Draft(self.presets.load(pid), pid)
        return self.draft

    def editing_unsaved(self, preset_id: int | None) -> bool:
        d = self.draft
        return d is not None and d.preset_id == preset_id and d.changed > 0

    def save_draft(self) -> str:
        d = self.draft
        before = self.presets.load(d.preset_id)
        codes = _composed_codes(d.ops, [it.id for it in before.items])
        old = {codes[it.id]: it for it in before.items if codes[it.id] is not None}
        new = d.wb.by_id
        added = sum(c not in old for c in new)
        deleted = sum(c not in new for c in old)
        changed = sum(1 for c, it in old.items() if c in new and
                      (it.text, it.method, it.when, it.default, it.words) !=
                      (new[c].text, new[c].method, new[c].when, new[c].default, new[c].words))
        self.presets.save_draft(d.preset_id, d)
        results = check_references(d.wb)
        ok = sum(r.ok for r in results)
        self._log('preset_saved', preset=d.preset_id, added=added, deleted=deleted,
                  changed=changed, codes={o: n for o, n in codes.items() if n and n != o},
                  refs_ok=ok, refs_total=len(results))
        if d.preset_id == self.preset_id:
            self._reload()
        return f'Пресет «{d.wb.name}» сохранён · эталоны {ok}/{len(results)}'

    def _reload(self) -> None:
        self.workbook = self.presets.load(self.preset_id)
        self.journal.snapshot(self.workbook)
        self._refresh_status()

    def needs_confirm_regenerate(self, current_text: str) -> bool:
        cur = current_text.strip()
        return bool(cur) and cur != self._last_shown.strip()

    def copy(self, text: str) -> str:
        self.clipboard(text)
        self._last_shown = text
        if self.last_entry_id is not None:
            self.journal.log_copy(self.last_entry_id, text)
        if self.last_protocol is not None:
            generated = self.last_protocol.text
            diff = text_diff(generated, text) if text.strip() != generated.strip() else ''
            self.last_copy_edited = bool(diff)
            self._log('copy', entry_id=self.last_entry_id, raw=self._last_raw,
                      generated=generated, copied=text, edited=bool(diff), diff=diff)
        return 'Скопировано в буфер'

    def mark_case(self, kind: str, corrected_text: str, corrected_raw: str | None = None,
                  comment: str = '') -> str:
        """«Отметить ошибку»: пишется в диагностику всегда, даже без галочки —
        это явное действие врача."""
        if self.last_protocol is None or self.workbook is None:
            return 'Сначала сформируйте протокол'
        generated = self.last_protocol.text
        self._diag.write(
            'case', kind=kind, kind_label=CASE_KINDS[kind],
            entry_id=self.last_entry_id, raw=self._last_raw,
            facts=extract_facts(self._last_raw),
            generated=generated, lines=self.last_protocol.lines,
            warnings=self.last_protocol.warnings, defaults=self.last_protocol.defaults,
            corrected=corrected_text, diff=text_diff(generated, corrected_text),
            corrected_raw=corrected_raw if kind == 'me' else None,
            comment=comment.strip(), preset=self._preset_ref(), sha256=self.workbook.sha256)
        return 'Спасибо, случай сохранён'

    def save_reference(self, raw: str, final_text: str) -> str:
        wb = self.workbook
        if wb is None or self.last_protocol is None:
            return 'Сначала сформируйте протокол'
        if raw.strip() != self._last_raw.strip():
            return 'Запись изменена — сформируйте протокол заново'
        lines = lines_for_reference(wb, self.last_protocol, final_text)
        try:
            case_id = self.presets.add_reference(self.preset_id, raw.strip(), lines)
        except Exception as e:
            self._log_error('save_reference', e)
            return f'✗ Ошибка: {e}'
        if self.last_entry_id is not None:
            self.journal.mark_reference(self.last_entry_id, case_id)
        self._log('save_reference', entry_id=self.last_entry_id, case_id=case_id,
                  raw=raw.strip(), lines=lines, preset=self._preset_ref())
        self.workbook = self.presets.load(self.preset_id)
        self.journal.snapshot(self.workbook)
        self._refresh_status()
        return f'Эталон {case_id} сохранён в пресет «{wb.name}»'


def _composed_codes(ops, codes: list[str]) -> dict[str, str | None]:
    """Прежний код → итоговый после всех смен кодов черновика (None — удалён)."""
    cur: dict[str, str | None] = {c: c for c in codes}
    for op in ops:
        if op[0] == 'codes':
            cur = {o: (op[1].get(n, n) if n else None) for o, n in cur.items()}
        elif op[0] == 'del_item':
            cur = {o: (None if n in op[1] else n) for o, n in cur.items()}
    return cur

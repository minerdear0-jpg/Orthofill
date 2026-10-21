"""Логика окна без tkinter — чтобы её можно было проверить тестами."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import difflib
import time
import traceback

from .diag import DiagLog, text_diff
from .engine import Protocol, build_protocol, check_references, rule_warnings
from .parse import extract_facts
from .journal import Journal
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
        self.last_protocol: Protocol | None = None
        self.last_entry_id: int | None = None
        self._last_shown = ''      # текст, выданный программой или уже скопированный
        self._last_raw = ''        # запись, по которой сформирован last_protocol
        self.diag_dir = journal.db_path.parent / 'diagnostics'
        self._diag = DiagLog(self.diag_dir)
        self.diagnostics = False
        self.last_copy_edited = False
        self._last_generate_at = 0.0

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

    def export_xlsx(self, path: Path) -> str:
        path = Path(path)
        if self.workbook is None:
            return 'Сначала импортируйте пресет (xlsx)'
        try:
            export_workbook(self.workbook, path)
        except PermissionError:
            return 'Файл открыт в Excel или нет прав на запись — закройте его и повторите'
        except Exception as e:
            self._log_error('export', e)
            return f'✗ Ошибка: {e}'
        self.presets.mark_exported(self.preset_id, path.name)
        self._log('export', file=path.name, preset=self._preset_ref(),
                  items=len(self.workbook.items), references=len(self.workbook.references),
                  dictionary=len(self.workbook.dictionary))
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
            if r.ok:
                continue
            details.append(f'Не совпадает эталон {r.case_id}:')
            details += [f'   нет в результате: {_fmt_line(x)}' for x in r.missing]
            details += [f'   лишнее в результате: {_fmt_line(x)}' for x in r.extra]
            if not r.missing and not r.extra:
                details.append('   отличается порядок строк')
        details += [f'Предупреждение: {w}' for w in wb.warnings + rule_warnings(wb)]
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
        if self.diagnostics:
            facts = extract_facts(raw)
            self._log('generate', entry_id=self.last_entry_id, raw=raw,
                      raw_norm=facts['raw_norm'], facts=facts,
                      lines=p.lines, warnings=p.warnings, defaults=p.defaults,
                      preset=self._preset_ref(), sha256=self.workbook.sha256)
        defaults = f'по умолчанию: {", ".join(p.defaults)}' if p.defaults else ''
        status = 'Скопировано в буфер' if copy else 'Протокол пересобран (в буфер не копировался)'
        return GenerateResult(p.text, status, p.warnings, defaults, copy)

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

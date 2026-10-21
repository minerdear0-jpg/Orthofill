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
from .workbook import (FileLockedError, Workbook, WorkbookError, append_reference,
                       lines_for_reference, load_workbook_file)

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
        self.workbook: Workbook | None = None
        self.file_status = 'Файл не открыт'
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

    # ---------- файл ----------
    def startup(self) -> None:
        self.diagnostics = self.journal.get_setting('diagnostics') == '1'
        last = self.journal.get_setting('last_file')
        if not last:
            return
        if Path(last).exists():
            self.open_file(Path(last))
        else:
            self.file_status = 'Файл не найден — откройте файл классификатора'

    def open_file(self, path: Path) -> None:
        path = Path(path)
        try:
            wb = load_workbook_file(path)
        except WorkbookError as e:
            self.workbook, self.details = None, [str(e)]
            self.file_status = f'✗ {e}'
            return
        except Exception as e:     # непредвиденное — показать, а не упасть молча
            self.workbook, self.details = None, [repr(e)]
            self.file_status = f'✗ Ошибка: {e}'
            self._log_error('open_file', e)
            return
        self.workbook = wb
        self.journal.set_setting('last_file', str(path))
        self.journal.snapshot(wb)
        self._refresh_status()
        self._log('open_file', file=wb.path.name, path=str(wb.path), sha256=wb.sha256,
                  status=self.file_status, details=self.details)

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
    def generate(self, raw: str) -> GenerateResult:
        def fail(status):
            return GenerateResult('', status, [], '', False)
        if self.workbook is None:
            return fail('Сначала откройте файл классификатора')
        if self.workbook.problems:
            return fail('Файл содержит ошибки — откройте «подробнее»')
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
        self.last_entry_id = self.journal.log_generate(raw, p, self.workbook.sha256)
        self.clipboard(p.text)
        self.journal.log_copy(self.last_entry_id, p.text)
        self._last_shown = p.text
        if self.diagnostics:
            facts = extract_facts(raw)
            self._log('generate', entry_id=self.last_entry_id, raw=raw,
                      raw_norm=facts['raw_norm'], facts=facts,
                      lines=p.lines, warnings=p.warnings, defaults=p.defaults,
                      file=self.workbook.path.name, sha256=self.workbook.sha256)
        defaults = f'по умолчанию: {", ".join(p.defaults)}' if p.defaults else ''
        return GenerateResult(p.text, 'Скопировано в буфер', p.warnings, defaults, True)

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
            comment=comment.strip(), file=self.workbook.path.name, sha256=self.workbook.sha256)
        return 'Спасибо, случай сохранён'

    def save_reference(self, raw: str, final_text: str) -> str:
        wb = self.workbook
        if wb is None or self.last_protocol is None:
            return 'Сначала сформируйте протокол'
        if raw.strip() != self._last_raw.strip():
            return 'Запись изменена — сформируйте протокол заново'
        lines = lines_for_reference(wb, self.last_protocol, final_text)
        try:
            case_id = append_reference(wb.path, raw.strip(), lines)
        except FileLockedError as e:
            return str(e)
        except Exception as e:
            self._log_error('save_reference', e)
            return f'✗ Ошибка: {e}'
        if self.last_entry_id is not None:
            self.journal.mark_reference(self.last_entry_id, case_id)
        self._log('save_reference', entry_id=self.last_entry_id, case_id=case_id,
                  raw=raw.strip(), lines=lines, file=wb.path.name)
        self.open_file(wb.path)
        return f'Эталон {case_id} сохранён в {wb.path.name}'

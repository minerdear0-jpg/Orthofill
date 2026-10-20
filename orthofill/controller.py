"""Логика окна без tkinter — чтобы её можно было проверить тестами."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .engine import Protocol, build_protocol, check_references, rule_warnings
from .journal import Journal
from .workbook import (FileLockedError, Workbook, WorkbookError, append_reference,
                       lines_for_reference, load_workbook_file)

WIDE_MIN_WIDTH = 900


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

    # ---------- файл ----------
    def startup(self) -> None:
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
        self.workbook = wb
        self.journal.set_setting('last_file', str(path))
        self.journal.snapshot(wb)
        self._refresh_status()

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
        p = build_protocol(self.workbook, raw)
        self.last_protocol = p
        self.last_entry_id = self.journal.log_generate(raw, p, self.workbook.sha256)
        self.clipboard(p.text)
        self.journal.log_copy(self.last_entry_id, p.text)
        self._last_shown = p.text
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
        return 'Скопировано в буфер'

    def save_reference(self, raw: str, final_text: str) -> str:
        wb = self.workbook
        if wb is None or self.last_protocol is None:
            return 'Сначала сформируйте протокол'
        lines = lines_for_reference(wb, self.last_protocol, final_text)
        try:
            case_id = append_reference(wb.path, raw.strip(), lines)
        except FileLockedError as e:
            return str(e)
        if self.last_entry_id is not None:
            self.journal.mark_reference(self.last_entry_id, case_id)
        self.open_file(wb.path)
        return f'Эталон {case_id} сохранён в {wb.path.name}'

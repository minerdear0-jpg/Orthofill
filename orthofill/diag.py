"""Диагностика: события работы программы в JSONL (одна строка — одно событие).

Файлы diagnostics/diag-ГГГГ-ММ-ДД.jsonl рядом с базой. Пишется, только пока
врач включил галочку «Диагностика». Нужна, чтобы собрать реальные записи,
на которых программа ошибается, и передать их разработчику."""
from __future__ import annotations

import difflib
import json
from datetime import datetime
from pathlib import Path

from . import __version__
from .buildinfo import build_id


class DiagLog:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def write(self, event: str, **data) -> None:
        now = datetime.now()
        record = {'ts': now.isoformat(timespec='seconds'), 'version': __version__,
                  'build': build_id(),
                  'event': event, **data}
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self.folder / f'diag-{now:%Y-%m-%d}.jsonl'
            with path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
        except OSError:
            pass   # диагностика не должна мешать работе врача


def text_diff(generated: str, final: str) -> str:
    """Построчная разница «выдала программа» → «скопировал врач»."""
    return '\n'.join(difflib.unified_diff(
        generated.splitlines(), final.splitlines(),
        fromfile='программа', tofile='врач', lineterm=''))

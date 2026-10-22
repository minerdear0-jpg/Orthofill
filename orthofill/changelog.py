"""Журнал изменений (CHANGELOG.md) для окна «О программе» → «Что нового».

Понимает только то, что в нём пишем мы сами: «## версия — дата», пункты «- …»
(перенос строки внутри пункта — с отступом) и **жирный**."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Release:
    title: str                                   # «0.2 beta 3 — 22.10.2026»
    lines: list[str] = field(default_factory=list)

    @property
    def version(self) -> str:
        return self.title.split(' — ')[0].strip()


def parse(text: str) -> list[Release]:
    """Разделы «## …» в порядке файла (новые — сверху); текст до первого — пропускается."""
    out: list[Release] = []
    for raw in text.splitlines():
        line = raw.strip()
        if raw.startswith('## '):
            out.append(Release(line[3:].strip()))
        elif not out or not line:
            continue
        elif raw[:1].isspace() and out[-1].lines:      # продолжение пункта
            out[-1].lines[-1] += ' ' + line
        else:
            out[-1].lines.append(line)
    return out


def spans(line: str) -> list[tuple[str, bool]]:
    """«a **b** c» → [('a ', False), ('b', True), (' c', False)]."""
    parts = re.split(r'\*\*(.+?)\*\*', line)
    return [(p, i % 2 == 1) for i, p in enumerate(parts) if p]

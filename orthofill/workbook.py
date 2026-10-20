"""Файл врача (xlsx): классификатор (A–B) и эталоны (C–F)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

HEADER = 'ID_CLASS'
_CODE_RE = re.compile(r'\d|\d[a-zа-я]|\d[a-zа-я]\d+')


class WorkbookError(Exception):
    """Файл нельзя использовать: нет, не xlsx, нет строки заголовка."""


@dataclass
class Item:
    id: str
    text: str
    level: int                      # 1 раздел, 2 пункт, 3 вариант
    parent: str | None
    orphan: bool = False            # вариант без своей группы (4h1)
    children: list['Item'] = field(default_factory=list)


@dataclass
class ReferenceCase:
    case_id: str
    raw: str
    lines: list[tuple[str, str]]    # (код или '', текст) как в E/F


@dataclass
class Workbook:
    path: Path
    sha256: str
    items: list[Item]
    by_id: dict[str, Item]
    sections: list[Item]
    references: list[ReferenceCase]
    problems: list[str]             # с ними работать нельзя
    warnings: list[str]


def clean_code(value) -> str:
    s = str(value).strip().lower()
    if re.fullmatch(r'\d+\.0', s):
        s = s[:-2]
    return s


def clean_text(value) -> str:
    if value is None:
        return ''
    return re.sub(r'<br\s*/?>', ' ', str(value), flags=re.I).strip()


def _open_sheet(path: Path):
    if not path.exists():
        raise WorkbookError(f'Файл не найден: {path}')
    try:
        return load_workbook(path, data_only=True).worksheets[0]
    except Exception as e:  # повреждён / не xlsx
        raise WorkbookError(f'Не удалось открыть {path.name}: {e}') from e


def find_header_row(ws) -> int:
    for (cell,) in ws.iter_rows(min_col=1, max_col=1):
        if cell.value is not None and str(cell.value).strip().upper() == HEADER:
            return cell.row
    raise WorkbookError(f'В файле нет строки заголовка с «{HEADER}» в колонке A')


def _row_values(ws, header_row):
    for row in ws.iter_rows(min_row=header_row + 1, max_col=6, values_only=True):
        yield tuple(row) + (None,) * (6 - len(row))


def _level(code: str) -> int:
    return 1 if len(code) == 1 else 2 if len(code) == 2 else 3


def load_workbook_file(path: str | Path) -> Workbook:
    path = Path(path)
    ws = _open_sheet(path)
    header = find_header_row(ws)

    items: list[Item] = []
    by_id: dict[str, Item] = {}
    problems: list[str] = []
    warnings: list[str] = []
    labels: dict[str, list[str]] = {}
    references: list[ReferenceCase] = []

    for rownum, (a, b, c, d, e, f) in enumerate(_row_values(ws, header), start=header + 1):
        # --- классификатор
        if a is not None and str(a).strip():
            code = clean_code(a)
            text = clean_text(b)
            if not _CODE_RE.fullmatch(code):
                problems.append(f'строка {rownum}: код «{code}» не по формату (1, 1a, 1a1)')
            elif code in by_id:
                problems.append(f'строка {rownum}: код «{code}» повторяется')
            elif not text:
                problems.append(f'строка {rownum}: у кода «{code}» нет текста')
            else:
                lvl = _level(code)
                parent = None if lvl == 1 else code[:2] if lvl == 3 else code[0]
                it = Item(code, text, lvl, parent)
                items.append(it)
                by_id[code] = it
                labels.setdefault(text, []).append(code)
        # --- эталоны
        if c is not None and str(c).strip():
            references.append(ReferenceCase(clean_code(c), clean_text(d), []))
        elif references and f is not None and str(f).strip():
            code = clean_code(e) if e is not None and str(e).strip() else ''
            references[-1].lines.append((code, clean_text(f)))

    # Вариант без своей группы — самостоятельный пункт раздела
    for it in items:
        if it.level == 3 and it.parent not in by_id:
            it.level, it.parent, it.orphan = 2, it.id[0], True
    for it in items:
        if it.parent in by_id:
            by_id[it.parent].children.append(it)
        elif it.parent is not None:
            problems.append(f'код «{it.id}»: нет раздела «{it.parent}»')

    for text, codes in labels.items():
        if len(codes) > 1:
            warnings.append(f'одинаковый текст у {", ".join(codes)}: «{text[:60]}»')

    return Workbook(
        path=path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        items=items,
        by_id=by_id,
        sections=[it for it in items if it.level == 1],
        references=references,
        problems=problems,
        warnings=warnings,
    )

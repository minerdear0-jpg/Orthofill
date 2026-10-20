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


# ---------- «Сохранить как эталон» ----------
class FileLockedError(Exception):
    """Файл открыт в Excel (или нет прав на запись)."""

    def __init__(self):
        super().__init__('Закройте файл в Excel и повторите')


def _ws_key(text: str) -> str:
    return ' '.join(text.split())


def lines_for_reference(wb: Workbook, generated, final_text: str) -> list[tuple[str, str]]:
    """Строки протокола, который врач оставил, → (код, текст) для колонок E/F.

    Строка совпала с выданной программой → её код и текст; совпала с текстом
    пункта классификатора → код пункта; своя строка врача → ('', текст)."""
    unused = list(generated.lines)
    item_by_text: dict[str, Item] = {}
    for it in wb.items:
        item_by_text.setdefault(_ws_key(it.text), it)
    out = []
    for line in final_text.splitlines():
        key = _ws_key(line)
        if not key:
            continue
        hit = next((g for g in unused if _ws_key(g[1]) == key), None)
        if hit:
            unused.remove(hit)
            out.append(hit)
        elif key in item_by_text:
            it = item_by_text[key]
            out.append((it.id, it.text))
        else:
            out.append(('', line.strip()))
    return out


def append_reference(path: Path, raw: str, lines: list[tuple[str, str]]) -> str:
    """Дописать эталон в колонки C–F после последней занятой строки.
    Перед записью — резервная копия <имя>.bak.xlsx. Возвращает номер эталона."""
    import shutil

    from openpyxl import load_workbook as _load

    path = Path(path)
    try:
        xl = _load(path)
        ws = xl.worksheets[0]
        header = find_header_row(ws)
        last, max_id = header, 0
        for row in ws.iter_rows(min_row=header + 1, min_col=3, max_col=6):
            if any(c.value is not None and str(c.value).strip() for c in row):
                last = row[0].row
            c = row[0].value
            if c is not None and re.fullmatch(r'\d+(\.0)?', str(c).strip()):
                max_id = max(max_id, int(float(c)))
        case_id = str(max_id + 1)
        r = last + 1
        ws.cell(r, 3, int(case_id))
        ws.cell(r, 4, raw)
        for i, (code, text) in enumerate(lines, start=1):
            ws.cell(r + i, 5, code or None)
            ws.cell(r + i, 6, text)
        shutil.copy2(path, path.with_name(f'{path.stem}.bak.xlsx'))
        xl.save(path)
    except PermissionError as e:
        raise FileLockedError() from e
    return case_id

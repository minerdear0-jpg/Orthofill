"""Файл врача (xlsx): классификатор (A–B) и эталоны (C–F)."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from .methods import METHOD_LABELS, WHEN_LABELS

HEADER = 'ID_CLASS'
SETTINGS_SHEET = 'Настройки'
DICTIONARY_SHEET = 'Словарь'
SETTINGS_HEADER = ['Код', 'Способ выбора', 'Когда в протоколе', 'По умолчанию', 'Слова']
DICTIONARY_HEADER = ['Слово', 'Пункт', 'Код', 'Добавлено', 'Сработало раз']
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
    # Свойства пресета (None — угадать, см. engine.guess_settings)
    method: str | None = None       # группа: способ выбора варианта (ключ METHOD_LABELS)
    when: str | None = None         # отдельный пункт: 'always' | 'mentioned'
    default: str | None = None      # группа: код варианта, если врач не написал
    words: list[str] = field(default_factory=list)   # доп. слова упоминания


@dataclass
class ReferenceCase:
    case_id: str
    raw: str
    lines: list[tuple[str, str]]    # (код или '', текст) как в E/F


@dataclass
class DictEntry:
    """Слово врача → пункт пресета (по тексту пункта; код — подсказка)."""
    word: str
    item_text: str
    code: str
    added: str = ''
    hits: int = 0


@dataclass
class Workbook:
    path: Path | None
    sha256: str
    items: list[Item]
    by_id: dict[str, Item]
    sections: list[Item]
    references: list[ReferenceCase]
    problems: list[str]             # с ними работать нельзя
    warnings: list[str]
    name: str = ''                  # имя пресета
    source: str = ''                # файл, из которого пресет импортирован
    dictionary: list[DictEntry] = field(default_factory=list)


def clean_code(value) -> str:
    s = str(value).strip().lower()
    if re.fullmatch(r'\d+\.0', s):
        s = s[:-2]
    return s


def clean_text(value) -> str:
    if value is None:
        return ''
    return re.sub(r'<br\s*/?>', ' ', str(value), flags=re.I).strip()


def _open_book(path: Path):
    if not path.exists():
        raise WorkbookError(f'Файл не найден: {path}')
    try:
        return load_workbook(path, data_only=True)
    except Exception as e:  # повреждён / не xlsx
        raise WorkbookError(f'Не удалось открыть {path.name}: {e}') from e


def find_header_row(ws) -> int:
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None and str(cell.value).strip().upper() == HEADER:
                if cell.column == 1:
                    return cell.row
                raise WorkbookError(
                    f'Строка заголовка {HEADER} найдена в колонке {cell.column_letter}, '
                    f'а должна быть в A (строка {cell.row})')
    raise WorkbookError(f'Не найдена строка заголовка: в колонке A должно стоять {HEADER} '
                        f'(проверьте первые строки файла)')


def _row_values(ws, header_row):
    for row in ws.iter_rows(min_row=header_row + 1, max_col=6, values_only=True):
        yield tuple(row) + (None,) * (6 - len(row))


def _level(code: str) -> int:
    return 1 if len(code) == 1 else 2 if len(code) == 2 else 3


def load_workbook_file(path: str | Path) -> Workbook:
    path = Path(path)
    book = _open_book(path)
    ws = book.worksheets[0]
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

    if SETTINGS_SHEET in book.sheetnames:
        problems += _read_settings(book[SETTINGS_SHEET], by_id)
    dictionary = (_read_dictionary(book[DICTIONARY_SHEET])
                  if DICTIONARY_SHEET in book.sheetnames else [])

    return Workbook(
        path=path,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        items=items,
        by_id=by_id,
        sections=[it for it in items if it.level == 1],
        references=references,
        problems=problems,
        warnings=warnings,
        name=path.stem,
        source=path.name,
        dictionary=dictionary,
    )


def _split_words(value) -> list[str]:
    return [w.strip() for w in re.split(r'[,;\n]', str(value or '')) if w.strip()]


def _read_settings(ws, by_id: dict[str, Item]) -> list[str]:
    """Лист «Настройки»: Код | Способ выбора | Когда в протоколе | По умолчанию | Слова."""
    method_of = {v: k for k, v in METHOD_LABELS.items()}
    when_of = {v: k for k, v in WHEN_LABELS.items()}
    problems = []
    for rownum, row in enumerate(ws.iter_rows(min_row=2, max_col=5, values_only=True), start=2):
        code, method, when, default, words = tuple(row) + (None,) * (5 - len(row))
        if code is None or not str(code).strip():
            continue
        where = f'{SETTINGS_SHEET}, строка {rownum}'
        it = by_id.get(clean_code(code))
        if it is None:
            problems.append(f'{where}: пункта «{clean_code(code)}» нет в классификаторе')
            continue
        if method:
            if str(method).strip() not in method_of:
                problems.append(f'{where}: способ выбора «{method}» не знаю')
            else:
                it.method = method_of[str(method).strip()]
        if when:
            if str(when).strip() not in when_of:
                problems.append(f'{where}: «{when}» — нужно «всегда» или «если упомянут»')
            else:
                it.when = when_of[str(when).strip()]
        if default:
            it.default = clean_code(default)
        it.words = _split_words(words)
    return problems


def _read_dictionary(ws) -> list[DictEntry]:
    out = []
    for row in ws.iter_rows(min_row=2, max_col=5, values_only=True):
        word, item_text, code, added, hits = tuple(row) + (None,) * (5 - len(row))
        if word is None or not str(word).strip():
            continue
        out.append(DictEntry(str(word).strip(), clean_text(item_text),
                             clean_code(code) if code is not None else '',
                             str(added or ''), int(hits or 0)))
    return out


# ---------- «Сохранить как эталон» ----------
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

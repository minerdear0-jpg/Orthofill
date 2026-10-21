import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ORDER = ROOT / "order.xlsx"


@pytest.fixture
def order_xlsx(tmp_path) -> Path:
    """Копия order.xlsx во временной папке — оригинал тесты не трогают."""
    dst = tmp_path / "order.xlsx"
    shutil.copy(ORDER, dst)
    return dst


def _insert_rows(path: Path, rows) -> None:
    """Вставить пункты (код, текст) в A/B после последней строки их группы/раздела."""
    import openpyxl
    from orthofill.workbook import clean_code

    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[0]
    for code, text in rows:
        prefix = code[:2] if len(code) > 2 else code[0]
        last = max(c.row for (c,) in ws.iter_rows(min_col=1, max_col=1)
                   if c.value is not None and clean_code(c.value).startswith(prefix))
        ws.insert_rows(last + 1)
        ws.cell(last + 1, 1, code)
        ws.cell(last + 1, 2, text)
    wb.save(path)


@pytest.fixture
def order_xlsx_with(order_xlsx):
    """order_xlsx_with(("4f7", "Слон"), ...) -> Workbook с добавленными пунктами."""
    from orthofill.workbook import load_workbook_file

    def make(*rows):
        _insert_rows(order_xlsx, rows)
        return load_workbook_file(order_xlsx)
    return make


@pytest.fixture
def store(tmp_path):
    from orthofill.journal import Journal
    from orthofill.presets import PresetStore
    return PresetStore(Journal(tmp_path / "j.db"))


@pytest.fixture
def clip():
    return []


@pytest.fixture
def ctl(tmp_path, clip):
    from orthofill.controller import Controller
    from orthofill.journal import Journal
    return Controller(Journal(tmp_path / "j.db"), clip.append)

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

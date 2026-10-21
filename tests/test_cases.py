"""Регрессионные случаи — данными (tests/cases/*.json), чтобы их могла прогнать
и будущая реализация на другом языке. Формат — см. любой файл в tests/cases;
необязательные поля файла: extra_rows (пункты пресета), dictionary ([слово,
текст пункта]); случая: codes_in/codes_not_in, warnings_*, defaults_*, unknown."""
import json
import shutil

import pytest

from conftest import ROOT, _insert_rows
from orthofill.engine import build_protocol
from orthofill.workbook import DictEntry, load_workbook_file

CASE_FILES = sorted((ROOT / "tests" / "cases").glob("*.json"))


def _load():
    for f in CASE_FILES:
        data = json.loads(f.read_text(encoding="utf-8"))
        for case in data["cases"]:
            yield pytest.param(data, case, id=f"{f.stem}:{case['raw'][:40]}")


@pytest.fixture(scope="module")
def presets(tmp_path_factory):
    cache = {}

    def get(data):
        key = (data["preset_xlsx"], json.dumps(data.get("extra_rows", [])),
               json.dumps(data.get("dictionary", [])))
        if key not in cache:
            dst = tmp_path_factory.mktemp("case") / "preset.xlsx"
            shutil.copy(ROOT / data["preset_xlsx"], dst)
            if data.get("extra_rows"):
                _insert_rows(dst, [tuple(r) for r in data["extra_rows"]])
            wb = load_workbook_file(dst)
            wb.dictionary = [DictEntry(w, t, "") for w, t in data.get("dictionary", [])]
            cache[key] = wb
        return cache[key]
    return get


@pytest.mark.parametrize("data, case", list(_load()))
def test_case(presets, data, case):
    p = build_protocol(presets(data), case["raw"])
    codes = [c for c, _ in p.lines]
    note = case.get("note", "")
    for c in case.get("codes_in", []):
        assert c in codes, f"{note}: нет {c}"
    for c in case.get("codes_not_in", []):
        assert c not in codes, f"{note}: лишнее {c}"
    for key, items, negate in (("warnings_contain", p.warnings, False),
                               ("warnings_not_contain", p.warnings, True),
                               ("defaults_contain", p.defaults, False),
                               ("defaults_not_contain", p.defaults, True)):
        for sub in case.get(key, []):
            hit = any(sub in x.lower() for x in items)
            assert hit != negate, f"{note}: {key} «{sub}» в {items}"

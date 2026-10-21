"""Непонятые слова — самопроверкой: без слова протокол не меняется."""
import json

import pytest

from conftest import ROOT, _insert_rows
from orthofill.vocab import unknown_words
from orthofill.workbook import DictEntry, load_workbook_file


def test_unknown_words(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    raw = "активация, лигатурная, изгиб 12 зуб торк, квакозябра"
    found = unknown_words(wb, raw)
    assert [w for *_, w in found] == ["квакозябра"]
    s, e, w = found[0]
    assert raw[s:e] == "квакозябра"


def test_repeated_stem_checked_together(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    assert unknown_words(wb, "система лигатур этап нивелирование, замена лигатур") == []


def test_known_by_dictionary(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.dictionary = [DictEntry("квакозябра", "Лиса", "4f2")]
    assert unknown_words(wb, "лигатурная, квакозябра") == []


def _case_params():
    for f in sorted((ROOT / "tests" / "cases").glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        for case in data["cases"]:
            yield pytest.param(data, case, id=f"{f.stem}:{case['raw'][:40]}")


@pytest.mark.parametrize("data, case", list(_case_params()))
def test_real_notes_have_no_false_unknowns(tmp_path, data, case):
    import shutil
    dst = tmp_path / "p.xlsx"
    shutil.copy(ROOT / data["preset_xlsx"], dst)
    if data.get("extra_rows"):
        _insert_rows(dst, [tuple(r) for r in data["extra_rows"]])
    wb = load_workbook_file(dst)
    wb.dictionary = [DictEntry(w, t, "") for w, t in data.get("dictionary", [])]
    assert [w for *_, w in unknown_words(wb, case["raw"])] == case.get("unknown", [])


def test_short_preset_stems_do_not_hide_words(order_xlsx):
    """I3: «приклеен», «треснул», «слетела» не прячутся за «при», «тре», «сле»."""
    wb = load_workbook_file(order_xlsx)
    words = [w for *_, w in unknown_words(wb, "лигатурная, приклеен, треснул, слетела")]
    assert words == ["приклеен", "треснул", "слетела"]
    assert unknown_words(wb, "активация, лигатурная, гигиена удовлетворительная") == []


def test_reuses_given_signature(order_xlsx, monkeypatch):
    """I5: подпись протокола из generate не пересчитывается."""
    import orthofill.vocab as v
    from orthofill.engine import build_protocol
    wb = load_workbook_file(order_xlsx)
    raw = "лигатурная, квакозябра"
    base = v.signature(build_protocol(wb, raw))
    calls = []
    real = v.build_protocol
    monkeypatch.setattr(v, "build_protocol", lambda *a: (calls.append(1), real(*a))[1])
    assert [w for *_, w in v.unknown_words(wb, raw, base)] == ["квакозябра"]
    assert len(calls) == 1                         # только для одной группы слов

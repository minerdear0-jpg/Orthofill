import os
import sqlite3
from pathlib import Path

from orthofill import journal as jmod
from orthofill.engine import build_protocol
from orthofill.journal import Journal, data_dir
from orthofill.workbook import load_workbook_file


def test_generate_and_copy_roundtrip(tmp_path, order_xlsx):
    wb = load_workbook_file(order_xlsx)
    p = build_protocol(wb, "резинки бегемот")
    j = Journal(tmp_path / "orthofill.db")
    eid = j.log_generate("резинки бегемот", p, wb.sha256)
    j.log_copy(eid, "исправленный текст")
    j.mark_reference(eid, "2")
    row = sqlite3.connect(tmp_path / "orthofill.db").execute(
        "select raw, generated, warnings_json, sha256, copied_text, copied_at, reference_case_id "
        "from entries where id=?", (eid,)).fetchone()
    assert row[0] == "резинки бегемот" and row[1] == p.text
    assert "эластики упомянуты" in row[2] and row[3] == wb.sha256
    assert row[4] == "исправленный текст" and row[5] and row[6] == "2"


def test_snapshot_once_per_sha(tmp_path, order_xlsx):
    wb = load_workbook_file(order_xlsx)
    j = Journal(tmp_path / "j.db")
    j.snapshot(wb)
    j.snapshot(wb)
    rows = sqlite3.connect(tmp_path / "j.db").execute(
        "select sha256, file_name, content_json from classifier_snapshots").fetchall()
    assert len(rows) == 1 and rows[0][1] == "order.xlsx" and "Перепел" in rows[0][2]


def test_settings(tmp_path):
    j = Journal(tmp_path / "s.db")
    assert j.get_setting("last_file") is None and j.get_setting("x", "d") == "d"
    j.set_setting("last_file", "C:/a.xlsx")
    j.set_setting("last_file", "C:/b.xlsx")
    assert Journal(tmp_path / "s.db").get_setting("last_file") == "C:/b.xlsx"


def test_data_dir_fallback(tmp_path, monkeypatch):
    ro = tmp_path / "ro"
    ro.mkdir()
    monkeypatch.setattr(jmod, "_app_dir", lambda: ro)
    monkeypatch.setattr(jmod, "_writable", lambda p: False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    d = data_dir()
    assert d == tmp_path / "local" / "Orthofill" and d.is_dir()


def test_data_dir_app_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(jmod, "_app_dir", lambda: tmp_path)
    assert data_dir() == tmp_path

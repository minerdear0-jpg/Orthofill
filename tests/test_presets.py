"""Пресеты в SQLite: создание, обновление, загрузка, эталоны, миграция базы 0.1."""
import sqlite3

import pytest

from orthofill.engine import build_protocol, rule_kind
from orthofill.journal import Journal
from orthofill.workbook import DictEntry, load_workbook_file

RAW = "лигатурная, замена дуги верх 16х25 нити, перепел, явка 6 нед"


def test_create_load_same_protocol(store, order_xlsx):
    wb = load_workbook_file(order_xlsx)
    pid = store.create(wb)
    wb2 = store.load(pid)
    assert build_protocol(wb2, RAW).lines == build_protocol(load_workbook_file(order_xlsx), RAW).lines
    assert wb2.name == "order" and wb2.source == "order.xlsx" and wb2.path is None
    assert len(wb2.sha256) == 64 and [r.lines for r in wb2.references] == [r.lines for r in wb.references]


def test_settings_survive(store, order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.by_id["5d"].default = "5d3"
    wb.by_id["4b"].words = ["дуг"]
    wb2 = store.load(store.create(wb))
    assert wb2.by_id["5d"].default == "5d3" and wb2.by_id["4b"].words == ["дуг"]
    # угаданное не хранится (None), но разбор угадывает его сам
    assert wb2.by_id["3f"].method is None and wb2.by_id["4a"].when is None
    assert rule_kind(wb2.by_id["3f"]) == "hygiene"


def test_unique_names(store, order_xlsx):
    store.create(load_workbook_file(order_xlsx))
    store.create(load_workbook_file(order_xlsx))
    assert [p.name for p in store.list()] == ["order", "order (2)"]


def test_add_reference_sets_dirty_and_number(store, order_xlsx):
    pid = store.create(load_workbook_file(order_xlsx))
    assert not store.list()[0].dirty
    assert store.add_reference(pid, "лигатурная", [("1", "Жалобы: активация")]) == "2"
    assert store.list()[0].dirty
    assert store.load(pid).references[-1].lines == [("1", "Жалобы: активация")]
    store.mark_exported(pid)
    assert not store.list()[0].dirty


def test_update_replaces_items_keeps_dictionary(store, order_xlsx, order_xlsx_with):
    wb = load_workbook_file(order_xlsx)
    wb.dictionary = [DictEntry("торк", "Изгиб третьего порядка", "4g3")]
    pid = store.create(wb)
    new = order_xlsx_with(("4f7", "Слон"))
    new.dictionary = [DictEntry("слоник", "Слон", "4f7")]
    store.update(pid, new)
    wb2 = store.load(pid)
    assert "4f7" in wb2.by_id
    assert sorted(e.word for e in wb2.dictionary) == ["слоник", "торк"]


def test_update_same_word_file_wins(store, order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.dictionary = [DictEntry("торк", "Изгиб второго порядка", "4g2")]
    pid = store.create(wb)
    new = load_workbook_file(order_xlsx)
    new.dictionary = [DictEntry("торк", "Изгиб третьего порядка", "4g3")]
    store.update(pid, new)
    assert [(e.word, e.code) for e in store.load(pid).dictionary] == [("торк", "4g3")]


def test_update_with_problems_keeps_preset(store, order_xlsx, monkeypatch):
    pid = store.create(load_workbook_file(order_xlsx))
    before = store.load(pid)
    bad = load_workbook_file(order_xlsx)
    bad.items[-1].text = None               # NOT NULL — сбой посреди записи
    with pytest.raises(Exception):
        store.update(pid, bad)
    after = store.load(pid)
    assert [(i.id, i.text) for i in after.items] == [(i.id, i.text) for i in before.items]
    assert len(after.references) == len(before.references)


def test_exists(store, order_xlsx):
    pid = store.create(load_workbook_file(order_xlsx))
    assert store.exists(pid) and not store.exists(pid + 100)


V1_SCHEMA = """
CREATE TABLE classifier_snapshots (sha256 TEXT PRIMARY KEY, file_name TEXT, loaded_at TEXT, content_json TEXT);
CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, raw TEXT, generated TEXT,
    warnings_json TEXT, defaults_json TEXT, sha256 TEXT, copied_text TEXT, copied_at TEXT, reference_case_id TEXT);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
PRAGMA user_version = 1;
"""


def test_migrates_v1_db(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(V1_SCHEMA)
    con.execute("INSERT INTO entries (raw) VALUES ('лигатурная')")
    con.execute("INSERT INTO settings VALUES ('last_file', 'C:/a.xlsx')")
    con.commit()
    con.close()
    j = Journal(db)
    assert j._db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert j._db.execute("SELECT raw FROM entries").fetchone()[0] == "лигатурная"
    assert j.get_setting("last_file") == "C:/a.xlsx"
    j._db.execute("SELECT preset_id FROM entries")      # столбец появился
    Journal(db)                                          # повторное открытие не падает


# ---------- 0.2 beta 3: словарь ----------
def test_learn_unlearn_hits(store, order_xlsx):
    pid = store.create(load_workbook_file(order_xlsx))
    store.learn(pid, "  Торк ", "Изгиб третьего порядка", "4g3")
    wb = store.load(pid)
    assert [(e.word, e.item_text, e.code, e.hits) for e in wb.dictionary] == \
           [("торк", "Изгиб третьего порядка", "4g3", 0)]
    assert store.list()[0].dirty
    store.count_hits(pid, ["торк"])
    store.count_hits(pid, ["торк"])
    assert store.load(pid).dictionary[0].hits == 2
    store.unlearn(pid, "торк")
    assert store.load(pid).dictionary == []


def test_learn_same_word_replaces(store, order_xlsx):
    pid = store.create(load_workbook_file(order_xlsx))
    store.learn(pid, "торк", "Изгиб второго порядка", "4g2")
    store.learn(pid, "ТОРК", "Изгиб третьего порядка", "4g3")
    assert [(e.word, e.code) for e in store.load(pid).dictionary] == [("торк", "4g3")]

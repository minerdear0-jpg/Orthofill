"""Память программы (SQLite): журнал записей и протоколов, пресеты (см.
presets.py и docs/presets-schema.md), снимки классификатора, настройки."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

DB_NAME = 'orthofill.db'

_SCHEMA = """
CREATE TABLE IF NOT EXISTS classifier_snapshots (
    sha256 TEXT PRIMARY KEY, file_name TEXT, loaded_at TEXT, content_json TEXT);
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT, raw TEXT, generated TEXT,
    warnings_json TEXT, defaults_json TEXT, sha256 TEXT,
    copied_text TEXT, copied_at TEXT, reference_case_id TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""

# Версия 2 (0.2): пресеты. Описание — docs/presets-schema.md
_SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
    source TEXT, source_sha256 TEXT, imported_at TEXT, created_at TEXT,
    dirty INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS preset_items (
    preset_id INTEGER NOT NULL, pos INTEGER NOT NULL, code TEXT NOT NULL, text TEXT NOT NULL,
    level INTEGER NOT NULL, parent TEXT, orphan INTEGER NOT NULL DEFAULT 0,
    method TEXT, when_ TEXT, default_code TEXT, words_json TEXT,
    PRIMARY KEY (preset_id, code));
CREATE TABLE IF NOT EXISTS reference_cases (
    preset_id INTEGER NOT NULL, pos INTEGER NOT NULL, case_id TEXT NOT NULL, raw TEXT,
    PRIMARY KEY (preset_id, case_id));
CREATE TABLE IF NOT EXISTS reference_lines (
    preset_id INTEGER NOT NULL, case_id TEXT NOT NULL, pos INTEGER NOT NULL,
    code TEXT, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dictionary (
    preset_id INTEGER NOT NULL, word TEXT NOT NULL, item_text TEXT NOT NULL, code TEXT,
    added TEXT, hits INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (preset_id, word));
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, preset_id INTEGER, at TEXT, file_name TEXT,
    sha256 TEXT, items INTEGER, references_ INTEGER);
CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, preset_id INTEGER, at TEXT, file_name TEXT);
"""
# Версия 3 (0.2 beta 5): логика пунктов — сочетание, условие, пары «не вместе»
_SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS not_together (
    preset_id INTEGER NOT NULL, a TEXT NOT NULL, b TEXT NOT NULL,
    PRIMARY KEY (preset_id, a, b));
"""
# Версия 4 (0.3 beta 3): фразы врача (SmartPhrase)
_SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS phrases (
    preset_id INTEGER NOT NULL, pos INTEGER NOT NULL, name TEXT NOT NULL,
    template TEXT NOT NULL, uses INTEGER NOT NULL DEFAULT 0, created_at TEXT,
    PRIMARY KEY (preset_id, name));
"""
SCHEMA_VERSION = 4


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _app_dir() -> Path:
    """Папка программы: рядом с exe в сборке, корень проекта при разработке."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _writable(p: Path) -> bool:
    try:
        with tempfile.TemporaryFile(dir=p):
            return True
    except OSError:
        return False


def data_dir() -> Path:
    d = _app_dir()
    if _writable(d):
        return d
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
    d = Path(base) / 'Orthofill'
    d.mkdir(parents=True, exist_ok=True)
    return d


class Journal:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self._db = sqlite3.connect(self.db_path)
        self._db.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """База 0.1 (версия 1) → 2: пресеты; 2 → 3: логика пунктов. Журнал и
        настройки не трогаются."""
        if self._db.execute('PRAGMA user_version').fetchone()[0] >= SCHEMA_VERSION:
            return
        with self._db:
            cols = {r[1] for r in self._db.execute('PRAGMA table_info(entries)')}
            if 'preset_id' not in cols:
                self._db.execute('ALTER TABLE entries ADD COLUMN preset_id INTEGER')
            self._db.executescript(_SCHEMA_V2)
            cols = {r[1] for r in self._db.execute('PRAGMA table_info(preset_items)')}
            for col in ('combine', 'condition_json'):
                if col not in cols:
                    self._db.execute(f'ALTER TABLE preset_items ADD COLUMN {col} TEXT')
            self._db.executescript(_SCHEMA_V3)
            self._db.executescript(_SCHEMA_V4)
            self._db.execute(f'PRAGMA user_version = {SCHEMA_VERSION}')

    def _exec(self, sql: str, args=()) -> sqlite3.Cursor:
        with self._db:
            return self._db.execute(sql, args)

    def snapshot(self, wb) -> None:
        content = json.dumps(
            {'items': [[it.id, it.text] for it in wb.items],
             'references': [[r.case_id, r.raw, r.lines] for r in wb.references]},
            ensure_ascii=False)
        self._exec('INSERT OR IGNORE INTO classifier_snapshots VALUES (?,?,?,?)',
                   (wb.sha256, wb.source or (wb.path.name if wb.path else ''), _now(), content))

    def log_generate(self, raw: str, protocol, sha256: str, preset_id: int | None = None) -> int:
        cur = self._exec(
            'INSERT INTO entries (created_at, raw, generated, warnings_json, defaults_json, sha256,'
            ' preset_id) VALUES (?,?,?,?,?,?,?)',
            (_now(), raw, protocol.text, json.dumps(protocol.warnings, ensure_ascii=False),
             json.dumps(protocol.defaults, ensure_ascii=False), sha256, preset_id))
        return cur.lastrowid

    def log_copy(self, entry_id: int, text: str) -> None:
        self._exec('UPDATE entries SET copied_text=?, copied_at=? WHERE id=?',
                   (text, _now(), entry_id))

    def mark_reference(self, entry_id: int, case_id: str) -> None:
        self._exec('UPDATE entries SET reference_case_id=? WHERE id=?', (case_id, entry_id))

    def raw_words(self, preset_id: int | None, limit: int = 2000) -> dict[str, int]:
        """Слова прошлых записей пресета → сколько раз встречались (для подсказок)."""
        from .hints import words_of
        out: dict[str, int] = {}
        for (raw,) in self._db.execute(
                'SELECT raw FROM entries WHERE preset_id IS ? ORDER BY id DESC LIMIT ?',
                (preset_id, limit)):
            for w in words_of(raw or ''):
                out[w] = out.get(w, 0) + 1
        return out

    def raw_notes(self, preset_id: int | None, limit: int = 2000) -> list[str]:
        """Записи пресета из журнала, новые первыми (для привычек ввода). Та же
        запись, подтверждённая подряд ещё раз (исправил опечатку — Ctrl+Enter), —
        одна: иначе фраза, написанная однажды, считалась бы привычной."""
        out: list[str] = []
        for (raw,) in self._db.execute(
                'SELECT raw FROM entries WHERE preset_id IS ? ORDER BY id DESC LIMIT ?',
                (preset_id, limit)):
            raw = (raw or '').strip()
            if not out or out[-1] != raw:
                out.append(raw)
        return out

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self._db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._exec('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, value))

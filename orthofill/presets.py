"""Пресеты — бизнес-логика типа карточки в SQLite (таблицы — journal._SCHEMA_V2,
описание — docs/presets-schema.md). Движок работает с объектом Workbook;
PresetStore собирает его из базы и записывает в базу при импорте xlsx."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .journal import Journal, _now
from .workbook import DictEntry, Item, ReferenceCase, Workbook


@dataclass
class PresetInfo:
    id: int
    name: str
    source: str
    imported_at: str
    dirty: bool             # есть эталоны/слова, которых нет в выгруженном xlsx


class PresetStore:
    def __init__(self, journal: Journal):
        self.journal = journal
        self._db = journal._db

    # ---------- список ----------
    def list(self) -> list[PresetInfo]:
        rows = self._db.execute(
            'SELECT id, name, source, imported_at, dirty FROM presets ORDER BY name').fetchall()
        return [PresetInfo(i, n, s or '', t or '', bool(d)) for i, n, s, t, d in rows]

    def exists(self, preset_id: int) -> bool:
        return self._db.execute('SELECT 1 FROM presets WHERE id=?', (preset_id,)).fetchone() is not None

    def _free_name(self, name: str) -> str:
        taken = {r[0] for r in self._db.execute('SELECT name FROM presets')}
        if name not in taken:
            return name
        k = 2
        while f'{name} ({k})' in taken:
            k += 1
        return f'{name} ({k})'

    # ---------- импорт ----------
    def create(self, wb: Workbook, name: str | None = None) -> int:
        name = self._free_name(name or wb.name or (Path(wb.path).stem if wb.path else 'Пресет'))
        with self._db:
            cur = self._db.execute(
                'INSERT INTO presets (name, source, source_sha256, imported_at, created_at, dirty)'
                ' VALUES (?,?,?,?,?,0)', (name, wb.source, wb.sha256, _now(), _now()))
            pid = cur.lastrowid
            self._write(pid, wb, keep_dictionary=False)
        return pid

    def update(self, preset_id: int, wb: Workbook) -> None:
        """Заменить пункты и эталоны; словарь пресета сохраняется, слова из файла
        добавляются (одинаковое слово — из файла). Всё или ничего."""
        with self._db:
            self._db.execute('UPDATE presets SET source=?, source_sha256=?, imported_at=?, dirty=0'
                             ' WHERE id=?', (wb.source, wb.sha256, _now(), preset_id))
            self._write(preset_id, wb, keep_dictionary=True)

    def _write(self, pid: int, wb: Workbook, keep_dictionary: bool) -> None:
        """Пишутся только явно заданные свойства; угаданные — None (их угадывает
        build_protocol по текущим эталонам)."""
        db = self._db
        for table in ('preset_items', 'reference_cases', 'reference_lines'):
            db.execute(f'DELETE FROM {table} WHERE preset_id=?', (pid,))
        if not keep_dictionary:
            db.execute('DELETE FROM dictionary WHERE preset_id=?', (pid,))
        for pos, it in enumerate(wb.items):
            db.execute('INSERT INTO preset_items VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (pid, pos, it.id, it.text, it.level, it.parent, int(it.orphan),
                        it.method, it.when, it.default,
                        json.dumps(it.words, ensure_ascii=False) if it.words else None))
        for pos, case in enumerate(wb.references):
            self._insert_case(pid, pos, case.case_id, case.raw, case.lines)
        for e in wb.dictionary:
            db.execute('INSERT OR REPLACE INTO dictionary VALUES (?,?,?,?,?,?)',
                       (pid, e.word, e.item_text, e.code, e.added or _now(), e.hits))
        db.execute('INSERT INTO imports (preset_id, at, file_name, sha256, items, references_)'
                   ' VALUES (?,?,?,?,?,?)',
                   (pid, _now(), wb.source, wb.sha256, len(wb.items), len(wb.references)))

    def _insert_case(self, pid, pos, case_id, raw, lines) -> None:
        self._db.execute('INSERT INTO reference_cases VALUES (?,?,?,?)', (pid, pos, case_id, raw))
        self._db.executemany('INSERT INTO reference_lines VALUES (?,?,?,?,?)',
                             [(pid, case_id, k, code, text) for k, (code, text) in enumerate(lines)])

    # ---------- загрузка ----------
    def load(self, preset_id: int) -> Workbook:
        db = self._db
        name, source = db.execute('SELECT name, source FROM presets WHERE id=?',
                                  (preset_id,)).fetchone()
        items, by_id = [], {}
        for code, text, level, parent, orphan, method, when, default, words in db.execute(
                'SELECT code, text, level, parent, orphan, method, when_, default_code, words_json'
                ' FROM preset_items WHERE preset_id=? ORDER BY pos', (preset_id,)):
            it = Item(code, text, level, parent, bool(orphan), method=method, when=when,
                      default=default, words=json.loads(words) if words else [])
            items.append(it)
            by_id[code] = it
        for it in items:
            if it.parent in by_id:
                by_id[it.parent].children.append(it)
        refs = []
        for case_id, raw in db.execute('SELECT case_id, raw FROM reference_cases'
                                       ' WHERE preset_id=? ORDER BY pos', (preset_id,)).fetchall():
            lines = [(c or '', t) for c, t in db.execute(
                'SELECT code, text FROM reference_lines WHERE preset_id=? AND case_id=?'
                ' ORDER BY pos', (preset_id, case_id))]
            refs.append(ReferenceCase(case_id, raw or '', lines))
        dictionary = [DictEntry(w, t, c or '', a or '', h) for w, t, c, a, h in db.execute(
            'SELECT word, item_text, code, added, hits FROM dictionary WHERE preset_id=?'
            ' ORDER BY word', (preset_id,))]
        content = json.dumps(
            {'items': [[i.id, i.text, i.method, i.when, i.default, i.words] for i in items],
             'references': [[r.case_id, r.raw, r.lines] for r in refs]}, ensure_ascii=False)
        return Workbook(path=None, sha256=hashlib.sha256(content.encode()).hexdigest(),
                        items=items, by_id=by_id,
                        sections=[it for it in items if it.level == 1],
                        references=refs, problems=[], warnings=[],
                        name=name, source=source or '', dictionary=dictionary)

    # ---------- эталоны, выгрузка ----------
    def add_reference(self, preset_id: int, raw: str, lines: list[tuple[str, str]]) -> str:
        db = self._db
        ids = [r[0] for r in db.execute('SELECT case_id FROM reference_cases WHERE preset_id=?',
                                        (preset_id,))]
        case_id = str(max([int(i) for i in ids if i.isdigit()], default=0) + 1)
        pos = db.execute('SELECT COALESCE(MAX(pos), -1) + 1 FROM reference_cases WHERE preset_id=?',
                         (preset_id,)).fetchone()[0]
        with db:
            self._insert_case(preset_id, pos, case_id, raw, lines)
            db.execute('UPDATE presets SET dirty=1 WHERE id=?', (preset_id,))
        return case_id

    def mark_exported(self, preset_id: int, file_name: str = '') -> None:
        with self._db:
            self._db.execute('UPDATE presets SET dirty=0 WHERE id=?', (preset_id,))
            self._db.execute('INSERT INTO exports (preset_id, at, file_name) VALUES (?,?,?)',
                             (preset_id, _now(), file_name))

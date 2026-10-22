"""Пресеты — бизнес-логика типа карточки в SQLite (таблицы — journal._SCHEMA_V2,
описание — docs/presets-schema.md). Движок работает с объектом Workbook;
PresetStore собирает его из базы и записывает в базу при импорте xlsx."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .journal import Journal, _now
from .workbook import DictEntry, Item, Phrase, ReferenceCase, Workbook, normalize_references


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
        if not keep_dictionary:
            db.execute('DELETE FROM dictionary WHERE preset_id=?', (pid,))
        self._write_items(pid, wb.items, wb.not_together, wb.phrases)
        self._write_references(pid, wb.references)
        self._write_dictionary(pid, wb.dictionary)
        db.execute('INSERT INTO imports (preset_id, at, file_name, sha256, items, references_)'
                   ' VALUES (?,?,?,?,?,?)',
                   (pid, _now(), wb.source, wb.sha256, len(wb.items), len(wb.references)))

    def _write_items(self, pid: int, items, pairs=(), phrases=()) -> None:
        """Пункты пресета, пары «не вместе» и фразы врача (живут вместе с пунктами)."""
        self._db.execute('DELETE FROM preset_items WHERE preset_id=?', (pid,))
        for pos, it in enumerate(items):
            self._db.execute(
                'INSERT INTO preset_items (preset_id, pos, code, text, level, parent, orphan,'
                ' method, when_, default_code, words_json, combine, condition_json)'
                ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (pid, pos, it.id, it.text, it.level, it.parent, int(it.orphan),
                 it.method, it.when, it.default,
                 json.dumps(it.words, ensure_ascii=False) if it.words else None,
                 it.combine,
                 json.dumps(it.condition, ensure_ascii=False) if it.condition else None))
        self._db.execute('DELETE FROM not_together WHERE preset_id=?', (pid,))
        self._db.executemany('INSERT OR IGNORE INTO not_together VALUES (?,?,?)',
                             [(pid, *sorted(p)) for p in pairs])
        self._db.execute('DELETE FROM phrases WHERE preset_id=?', (pid,))
        self._db.executemany('INSERT OR REPLACE INTO phrases VALUES (?,?,?,?,?,?)',
                             [(pid, k, ph.name, ph.template, ph.uses, _now())
                              for k, ph in enumerate(phrases)])

    def _write_references(self, pid: int, references) -> None:
        for table in ('reference_cases', 'reference_lines'):
            self._db.execute(f'DELETE FROM {table} WHERE preset_id=?', (pid,))
        for pos, case in enumerate(references):
            self._insert_case(pid, pos, case.case_id, case.raw, case.lines)

    def _write_dictionary(self, pid: int, dictionary) -> None:
        for e in dictionary:
            self._db.execute('INSERT OR REPLACE INTO dictionary VALUES (?,?,?,?,?,?)',
                             (pid, e.word, e.item_text, e.code, e.added or _now(), e.hits))

    # ---------- редактор ----------
    def save_draft(self, preset_id: int, draft) -> None:
        """Пункты — из черновика; эталоны и словарь — текущие из базы (главное
        окно могло их пополнить) с повтором правок черновика. Одна транзакция;
        в журнал импортов не пишется; пресет — «есть то, чего нет в xlsx»."""
        refs, words = draft.replay(self._load_references(preset_id),
                                   self._load_dictionary(preset_id))
        with self._db:
            self._write_items(preset_id, draft.wb.items, draft.wb.not_together, draft.wb.phrases)
            self._write_references(preset_id, refs)
            self._db.execute('DELETE FROM dictionary WHERE preset_id=?', (preset_id,))
            self._write_dictionary(preset_id, words)
            self._db.execute('UPDATE presets SET dirty=1 WHERE id=?', (preset_id,))
        draft.wb.references, draft.wb.dictionary = refs, words
        draft.mark_saved()

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
        for (code, text, level, parent, orphan, method, when, default, words, combine,
             cond) in db.execute(
                'SELECT code, text, level, parent, orphan, method, when_, default_code, words_json,'
                ' combine, condition_json FROM preset_items WHERE preset_id=? ORDER BY pos',
                (preset_id,)):
            it = Item(code, text, level, parent, bool(orphan), method=method, when=when,
                      default=default, words=json.loads(words) if words else [],
                      combine=combine, condition=json.loads(cond) if cond else None)
            items.append(it)
            by_id[code] = it
        for it in items:
            if it.parent in by_id:
                by_id[it.parent].children.append(it)
        refs = self._load_references(preset_id)
        dictionary = self._load_dictionary(preset_id)
        pairs = [tuple(p) for p in db.execute(
            'SELECT a, b FROM not_together WHERE preset_id=? ORDER BY a, b', (preset_id,))]
        phrases = [Phrase(n, t, u) for n, t, u in db.execute(
            'SELECT name, template, uses FROM phrases WHERE preset_id=? ORDER BY pos', (preset_id,))]
        content = json.dumps(
            {'items': [[i.id, i.text, i.method, i.when, i.default, i.words, i.combine,
                        i.condition] for i in items],
             'references': [[r.case_id, r.raw, r.lines] for r in refs],
             'not_together': pairs,
             'phrases': [[p.name, p.template] for p in phrases]}, ensure_ascii=False)
        wb = Workbook(path=None, sha256=hashlib.sha256(content.encode()).hexdigest(),
                      items=items, by_id=by_id,
                      sections=[it for it in items if it.level == 1],
                      references=refs, problems=[], warnings=[],
                      name=name, source=source or '', dictionary=dictionary,
                      not_together=pairs, phrases=phrases)
        normalize_references(wb)          # эталоны, сохранённые в 0.2 beta 1
        return wb

    def _load_references(self, preset_id: int) -> list[ReferenceCase]:
        db = self._db
        refs = []
        for case_id, raw in db.execute('SELECT case_id, raw FROM reference_cases'
                                       ' WHERE preset_id=? ORDER BY pos', (preset_id,)).fetchall():
            lines = [(c or '', t) for c, t in db.execute(
                'SELECT code, text FROM reference_lines WHERE preset_id=? AND case_id=?'
                ' ORDER BY pos', (preset_id, case_id))]
            refs.append(ReferenceCase(case_id, raw or '', lines))
        return refs

    def _load_dictionary(self, preset_id: int) -> list[DictEntry]:
        return [DictEntry(w, t, c or '', a or '', h) for w, t, c, a, h in self._db.execute(
            'SELECT word, item_text, code, added, hits FROM dictionary WHERE preset_id=?'
            ' ORDER BY word', (preset_id,))]

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

    # ---------- фразы врача ----------
    def add_phrase(self, preset_id: int, phrase) -> None:
        with self._db:
            pos = self._db.execute('SELECT COALESCE(MAX(pos), -1) + 1 FROM phrases WHERE preset_id=?',
                                   (preset_id,)).fetchone()[0]
            self._db.execute('INSERT OR REPLACE INTO phrases VALUES (?,?,?,?,?,?)',
                             (preset_id, pos, phrase.name, phrase.template, phrase.uses, _now()))
            self._db.execute('UPDATE presets SET dirty=1 WHERE id=?', (preset_id,))

    def count_phrase_use(self, preset_id: int, name: str) -> None:
        with self._db:
            self._db.execute('UPDATE phrases SET uses = uses + 1 WHERE preset_id=? AND name=?',
                             (preset_id, name))

    # ---------- словарь врача ----------
    @staticmethod
    def norm_word(word: str) -> str:
        from .text import norm
        return ' '.join(norm(word).split())

    def learn(self, preset_id: int, word: str, item_text: str, code: str) -> None:
        with self._db:
            self._db.execute('INSERT OR REPLACE INTO dictionary VALUES (?,?,?,?,?,0)',
                             (preset_id, self.norm_word(word), item_text, code, _now()))
            self._db.execute('UPDATE presets SET dirty=1 WHERE id=?', (preset_id,))

    def unlearn(self, preset_id: int, word: str) -> None:
        with self._db:
            self._db.execute('DELETE FROM dictionary WHERE preset_id=? AND word=?',
                             (preset_id, self.norm_word(word)))
            self._db.execute('UPDATE presets SET dirty=1 WHERE id=?', (preset_id,))

    def count_hits(self, preset_id: int, words: list[str]) -> None:
        with self._db:
            self._db.executemany('UPDATE dictionary SET hits = hits + 1 WHERE preset_id=? AND word=?',
                                 [(preset_id, self.norm_word(w)) for w in words])

    def mark_exported(self, preset_id: int, file_name: str = '') -> None:
        with self._db:
            self._db.execute('UPDATE presets SET dirty=0 WHERE id=?', (preset_id,))
            self._db.execute('INSERT INTO exports (preset_id, at, file_name) VALUES (?,?,?)',
                             (preset_id, _now(), file_name))

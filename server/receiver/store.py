"""Хранение событий: SQLite (WAL), повтор по id не задваивается."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    rowid INTEGER PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    install TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '',
    received TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_event_ts ON events(event, ts);
CREATE INDEX IF NOT EXISTS events_received ON events(received);
"""

# метрики скорости: (событие, поле) → имя метрики
_SPEED = [('session_start', 'startup_ms', 'startup_ms'),
          ('perf', 'preview_ms_med', 'preview_ms'),
          ('perf', 'hints_ms_med', 'hints_ms'),
          ('perf', 'unknown_ms_med', 'unknown_ms')]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(self, install: str, events: list[dict]) -> tuple[int, int]:
        """(принято, повторы). install — если в событии его нет."""
        received = _now()
        accepted = 0
        with self._lock, self._db:
            for e in events:
                cur = self._db.execute(
                    'INSERT OR IGNORE INTO events(id, install, ts, event, version, received, data)'
                    ' VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (str(e['id']), str(e.get('install') or install), str(e.get('ts', '')),
                     str(e.get('event', '')), str(e.get('version', '')), received,
                     json.dumps(e, ensure_ascii=False)))
                accepted += cur.rowcount
        return accepted, len(events) - accepted

    def count(self) -> int:
        return self._db.execute('SELECT COUNT(*) FROM events').fetchone()[0]

    def last_rowid(self) -> int:
        return self._db.execute('SELECT COALESCE(MAX(rowid), 0) FROM events').fetchone()[0]

    def feed(self, since_rowid: int, limit: int = 200) -> list[dict]:
        """Новые события после since_rowid (по порядку); since=0 — последние limit."""
        if since_rowid <= 0:
            rows = self._db.execute(
                'SELECT rowid, received, data FROM events ORDER BY rowid DESC LIMIT ?',
                (limit,)).fetchall()[::-1]
        else:
            rows = self._db.execute(
                'SELECT rowid, received, data FROM events WHERE rowid > ? ORDER BY rowid LIMIT ?',
                (since_rowid, limit)).fetchall()
        return [{**json.loads(d), '_row': r, '_received': rec} for r, rec, d in rows]

    def events(self, type_: str = '', since_rowid: int = 0, limit: int = 10000):
        q = 'SELECT rowid, data FROM events WHERE rowid > ?'
        args: list = [since_rowid]
        if type_:
            q += ' AND event = ?'
            args.append(type_)
        q += ' ORDER BY rowid LIMIT ?'
        args.append(limit)
        for r, d in self._db.execute(q, args):
            yield {**json.loads(d), '_row': r}

    def _since(self, days: int) -> str:
        return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    def usage(self, days: int) -> list[dict]:
        """По дням (день врача — по его времени ts): записей и сколько раз
        пользовался каждой функцией."""
        out: dict[str, dict] = {}
        rows = self._db.execute(
            'SELECT substr(ts, 1, 10), event, data FROM events WHERE ts >= ? AND event IN '
            "('note_confirm', 'hint', 'habit', 'smartphrase', 'add_search', 'protocol_edit', "
            "'key_noop', 'unknown', 'error')", (self._since(days),))
        for day, event, data in rows:
            d = out.setdefault(day, {'day': day, 'notes': 0, 'edited': 0, 'hints': 0,
                                     'hints_shown': 0, 'hints_erased': 0, 'habits': 0,
                                     'phrases': 0, 'adds': 0, 'keep_edit': 0,
                                     'key_noop': 0, 'errors': 0})
            e = json.loads(data)
            act = e.get('action')
            if event == 'note_confirm':
                d['notes'] += 1
                d['edited'] += 1 if e.get('edited_lines') else 0
            elif event == 'hint':
                key = {'accepted': 'hints', 'shown': 'hints_shown', 'erased': 'hints_erased'}.get(act)
                if key:
                    d[key] += 1
            elif event == 'habit' and act in ('accepted', 'word'):
                d['habits'] += 1
            elif event == 'smartphrase' and act == 'expanded':
                d['phrases'] += 1
            elif event == 'add_search' and e.get('chosen'):
                d['adds'] += 1
            elif event == 'protocol_edit' and e.get('live_bar') == 'keep':
                d['keep_edit'] += 1
            elif event == 'key_noop':
                d['key_noop'] += 1
            elif event == 'error':
                d['errors'] += 1
        return [out[k] for k in sorted(out)]

    def speed(self, days: int) -> list[dict]:
        """Медиана и 95-й процентиль по версии, установке и метрике."""
        groups: dict[tuple[str, str, str], list[float]] = {}
        rows = self._db.execute(
            "SELECT version, install, event, data FROM events WHERE ts >= ? AND event IN "
            "('session_start', 'perf')", (self._since(days),))
        for version, install, event, data in rows:
            e = json.loads(data)
            for ev, field, metric in _SPEED:
                v = e.get(field)
                if ev == event and isinstance(v, (int, float)):
                    groups.setdefault((version, install, metric), []).append(float(v))
        out = []
        for (version, install, metric), xs in sorted(groups.items()):
            xs.sort()
            n = len(xs)
            out.append({'version': version, 'install': install, 'metric': metric, 'n': n,
                        'med': xs[n // 2], 'p95': xs[min(n - 1, int(0.95 * n))]})
        return out

    def online(self, minutes: int = 10) -> list[dict]:
        """Кто присылал события за последние minutes минут."""
        since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec='seconds')
        rows = self._db.execute(
            'SELECT install, MAX(received), COUNT(*) FROM events WHERE received >= ? GROUP BY install',
            (since,)).fetchall()
        out = []
        for install, last, n in rows:
            doc = self._db.execute(
                "SELECT json_extract(data, '$.doctor'), version FROM events WHERE install = ?"
                ' ORDER BY rowid DESC LIMIT 1', (install,)).fetchone()
            out.append({'install': install, 'doctor': doc[0] or '', 'version': doc[1],
                        'last': last, 'events': n})
        return out

    def purge(self, days: int = 180) -> int:
        before = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec='seconds')
        with self._lock, self._db:
            return self._db.execute('DELETE FROM events WHERE received < ?', (before,)).rowcount

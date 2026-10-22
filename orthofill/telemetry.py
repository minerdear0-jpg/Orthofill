"""Телеметрия: события → файл-очередь → фоновая отправка на сервер заказчика.

Окно только кладёт событие в память (``put`` — мгновенно). Фоновый поток
вырезает ФИО, дописывает события в файл-очередь (сегменты ``seg-*.jsonl``) и
отправляет сегменты по одному ``POST /v1/events``; принятый сегмент удаляется.
Нет сети — повтор с растущей паузой; переполнение — старые сегменты в
``overflow/`` (не удаляются). Доверие — только сертификату из
``telemetry.json``."""
from __future__ import annotations

import json
import queue
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .scrub import scrub_event

CONFIG_NAME = 'telemetry.json'

ERR_NET = 'нет связи'
ERR_CERT = 'сертификат не совпадает'
ERR_KEY = 'ключ не принят'


@dataclass
class TelemetryConfig:
    url: str
    key: str
    cert: str
    doctor: str = ''


@dataclass
class TelemetryStatus:
    sent: int
    queued: int
    last_ok: str | None
    error: str
    overflowed: int = 0


def _parse_config(p: Path) -> TelemetryConfig:
    data = json.loads(p.read_text(encoding='utf-8'))
    url = str(data.get('url', '')).strip().rstrip('/')
    key = str(data.get('key', '')).strip()
    cert = str(data.get('cert', ''))
    if not url.startswith('https://'):
        raise ValueError('адрес должен начинаться с https://')
    if not key or not key.isascii() or not key.isprintable():
        raise ValueError('нет ключа или ключ не латиницей')
    if 'BEGIN CERTIFICATE' not in cert:
        raise ValueError('нет сертификата сервера')
    return TelemetryConfig(url, key, cert, str(data.get('doctor', '') or ''))


def load_config(app_dir: Path, data_dir: Path, bundle_dir: Path | None) -> TelemetryConfig | None:
    """Первый найденный ``telemetry.json``: рядом с exe → папка данных →
    встроенный в сборку. ``load_config.error`` — почему файл не принят."""
    load_config.error = ''
    for d in (app_dir, data_dir, bundle_dir):
        if d is None:
            continue
        p = Path(d) / CONFIG_NAME
        if not p.is_file():
            continue
        try:
            return _parse_config(p)
        except (OSError, ValueError, AttributeError) as e:
            load_config.error = f'{p}: {e}'
            return None
    return None


load_config.error = ''


def _ssl_context(cert: str) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cadata=cert)    # только этот сертификат
    ctx.verify_flags |= ssl.VERIFY_X509_STRICT
    ctx.check_hostname = True
    return ctx


class Telemetry:
    flush_every = 5.0       # с — как часто отправлять
    flush_count = 100       # столько событий в памяти — отправить сразу
    batch = 500             # событий в сегменте (= в одном запросе)
    max_bytes = 50 * 1024 * 1024
    timeout = 10.0
    backoff_min = 5.0
    backoff_max = 300.0

    def __init__(self, cfg: TelemetryConfig, spool_dir: Path,
                 keep: Callable[[], frozenset[str]] = frozenset):
        self.cfg = cfg
        self.dir = Path(spool_dir)
        self.keep = keep
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._ctx = _ssl_context(cfg.cert)
        self._sent = 0
        self._last_ok: str | None = None
        self._error = ''
        self._delay = 0.0
        self._next_try = 0.0
        self._open: Path | None = None
        self._open_lines = 0
        self._spooled = 0
        self._overflowed = 0
        self._recover()

    # ---------- файл-очередь ----------
    def _recover(self) -> None:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            for p in self.dir.glob('seg-*.jsonl.open'):     # прошлый запуск не закрыл
                p.rename(p.with_suffix(''))
            self._spooled = sum(self._lines(p) for p in self._segments())
            over = self.dir / 'overflow'
            if over.is_dir():
                self._overflowed = sum(self._lines(p) for p in over.glob('*.jsonl'))
        except OSError:
            pass

    @staticmethod
    def _lines(p: Path) -> int:
        try:
            with p.open('rb') as f:
                return sum(1 for line in f if line.strip())
        except OSError:
            return 0

    def _segments(self) -> list[Path]:
        return sorted(self.dir.glob('seg-*.jsonl'))

    def _roll(self) -> None:
        if self._open is not None:
            try:
                self._open.rename(self._open.with_suffix(''))
            except OSError:
                pass
            self._open, self._open_lines = None, 0

    def _drain(self) -> None:
        """Память → файл-очередь (с вырезанием ФИО)."""
        with self._lock:
            wrote = False
            while True:
                try:
                    rec = self._q.get_nowait()
                except queue.Empty:
                    break
                try:
                    keep = self.keep()
                except Exception:
                    keep = frozenset()
                line = json.dumps(scrub_event(rec, keep), ensure_ascii=False, default=str)
                try:
                    if self._open is None:
                        self.dir.mkdir(parents=True, exist_ok=True)
                        self._open = self.dir / f'seg-{time.time_ns():020d}.jsonl.open'
                    with self._open.open('a', encoding='utf-8') as f:
                        f.write(line + '\n')
                    self._open_lines += 1
                    self._spooled += 1
                    wrote = True
                except OSError:
                    self._q.put(rec)           # диск недоступен — останется в памяти
                    break
                if self._open_lines >= self.batch:
                    self._roll()
            if wrote:
                self._trim()

    def _trim(self) -> None:
        """Очередь больше лимита — старшие сегменты в overflow/ (не удаляются)."""
        try:
            files = self._segments() + ([self._open] if self._open else [])
            total = sum(p.stat().st_size for p in files if p.exists())
            over = self.dir / 'overflow'
            for p in self._segments():
                if total <= self.max_bytes:
                    break
                size, n = p.stat().st_size, self._lines(p)
                over.mkdir(exist_ok=True)
                p.rename(over / p.name)
                total -= size
                self._spooled -= n
                self._overflowed += n
        except OSError:
            pass

    # ---------- отправка ----------
    def _send(self, seg: Path) -> bool:
        try:
            raw = seg.read_text(encoding='utf-8').splitlines()
        except OSError:
            return False
        events = []
        for line in raw:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    pass
        body = json.dumps({'events': events}, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(
            self.cfg.url + '/v1/events', data=body, method='POST',
            headers={'Content-Type': 'application/json',
                     'Authorization': f'Bearer {self.cfg.key}'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self._ctx) as r:
                r.read(4096)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                self._fail(ERR_KEY)
            elif e.code == 429:
                try:
                    wait = float(e.headers.get('Retry-After', ''))
                except ValueError:
                    wait = self.backoff_min
                self._fail(f'сервер занят ({e.code})', wait)
            else:
                self._fail(f'сервер ответил {e.code}')
            return False
        except urllib.error.URLError as e:
            self._fail(ERR_CERT if isinstance(e.reason, ssl.SSLCertVerificationError) else ERR_NET)
            return False
        except ssl.SSLCertVerificationError:
            self._fail(ERR_CERT)
            return False
        except (OSError, ValueError):
            self._fail(ERR_NET)
            return False
        with self._lock:
            try:
                seg.unlink()
            except OSError:
                pass
            self._spooled -= len(raw)
            self._sent += len(events)
        self._error, self._delay = '', 0.0
        self._last_ok = datetime.now().isoformat(timespec='seconds')
        return True

    def _fail(self, error: str, wait: float | None = None) -> None:
        self._error = error
        self._delay = min(self.backoff_max, max(self.backoff_min, self._delay * 2))
        self._next_try = time.monotonic() + (wait if wait is not None else self._delay)

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self.flush_every)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self._drain()
                if time.monotonic() < self._next_try:
                    continue
                with self._lock:
                    if not self._segments() and self._open_lines:
                        self._roll()
                for seg in self._segments():
                    if self._stop.is_set() or not self._send(seg):
                        break
            except Exception:                  # телеметрия не должна ронять программу
                self._fail(ERR_NET)

    # ---------- снаружи ----------
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name='telemetry', daemon=True)
            self._thread.start()

    def put(self, record: dict) -> None:
        rec = dict(record)
        rec.setdefault('id', uuid.uuid4().hex)
        self._q.put(rec)
        if self._q.qsize() >= self.flush_count:
            self._wake.set()

    def close(self, timeout: float = 0.5) -> None:
        self._stop.set()
        self._wake.set()
        self._drain()
        with self._lock:
            self._roll()
        if self._thread is not None:
            self._thread.join(timeout)

    def status(self) -> TelemetryStatus:
        return TelemetryStatus(self._sent, self._spooled + self._q.qsize(),
                               self._last_ok, self._error, self._overflowed)

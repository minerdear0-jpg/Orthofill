"""Счётчики набора одной записи (без Tk и без текста): сколько нажатий,
Backspace, вставок, пауз дольше 2 с и сколько времени от первой клавиши до
подтверждения. Уходит в событие телеметрии note_confirm."""
from __future__ import annotations

import time

PAUSE = 2.0      # с — пауза «задумался/ищет»


class NoteStats:
    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.first: float | None = None
        self.last: float | None = None
        self.counts = {'char': 0, 'backspace': 0, 'delete': 0, 'paste': 0}
        self.pauses = 0

    @property
    def started(self) -> bool:
        return self.first is not None

    def key(self, kind: str, t: float | None = None) -> None:
        t = time.monotonic() if t is None else t
        if self.first is None:
            self.first = t
        elif self.last is not None and t - self.last > PAUSE:
            self.pauses += 1
        self.last = t
        if kind in self.counts:
            self.counts[kind] += 1

    def summary(self, now: float | None = None) -> dict:
        if self.first is None:
            return {}
        now = time.monotonic() if now is None else now
        c = self.counts
        return {'ms': round((now - self.first) * 1000), 'keys': sum(c.values()),
                'chars': c['char'], 'backspaces': c['backspace'], 'deletes': c['delete'],
                'pastes': c['paste'], 'pauses_2s': self.pauses}

"""Ограничения приёмника: частота запросов по IP и блок за подбор ключа/пароля."""
from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    """Не больше per_min запросов за 60 с с одного адреса."""

    def __init__(self, per_min: int, clock=time.monotonic):
        self.per_min, self.clock = per_min, clock
        self._hits: dict[str, deque] = {}

    def check(self, ip: str) -> float:
        """0 — можно; иначе сколько секунд подождать."""
        now = self.clock()
        q = self._hits.setdefault(ip, deque())
        while q and now - q[0] >= 60:
            q.popleft()
        if len(q) >= self.per_min:
            return max(1.0, 60 - (now - q[0]))
        q.append(now)
        if len(self._hits) > 10000:              # память не растёт от чужих сканеров
            for k in [k for k, v in self._hits.items() if not v]:
                del self._hits[k]
        return 0.0


class FailGuard:
    """fail_max неудач (ключ/пароль) за window с — адрес блокируется на block с."""

    def __init__(self, fail_max: int, window: float, block: float, clock=time.monotonic):
        self.fail_max, self.window, self.block, self.clock = fail_max, window, block, clock
        self._fails: dict[str, deque] = {}
        self._blocked: dict[str, float] = {}

    def blocked(self, ip: str) -> bool:
        until = self._blocked.get(ip)
        if until is None:
            return False
        if self.clock() >= until:
            del self._blocked[ip]
            return False
        return True

    def fail(self, ip: str) -> None:
        now = self.clock()
        q = self._fails.setdefault(ip, deque())
        q.append(now)
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.fail_max:
            self._blocked[ip] = now + self.block
            q.clear()

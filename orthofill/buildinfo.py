"""Код сборки: какой именно код запущен у врача.

В exe — из orthofill/_build.py, который пишет build.ps1 перед сборкой.
При запуске из папки проекта — короткий хеш git (+изм, если есть
незакоммиченные правки). Иначе — «dev»."""
from __future__ import annotations

import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def build_id() -> str:
    mod = sys.modules.get('orthofill._build')
    if mod is None:
        try:
            from . import _build as mod  # type: ignore[no-redef]
        except ImportError:
            mod = None
    if mod is not None:
        return mod.BUILD
    if getattr(sys, 'frozen', False):
        return 'dev'
    root = Path(__file__).resolve().parent.parent
    flags = 0x08000000 if sys.platform == 'win32' else 0   # CREATE_NO_WINDOW
    try:
        sha = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=root,
                             capture_output=True, text=True, timeout=5,
                             creationflags=flags).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'],
                               cwd=root, capture_output=True, text=True, timeout=5,
                               creationflags=flags).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 'dev'
    if not sha:
        return 'dev'
    return f'{sha}+изм' if dirty else sha

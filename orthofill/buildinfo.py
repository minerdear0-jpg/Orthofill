"""Код сборки: какой именно код запущен у врача.

В exe — из orthofill/_build.py, который пишет build.ps1 перед сборкой.
При запуске из папки проекта — короткий хеш git (+изм, если есть
незакоммиченные правки); без установленного git — хеш из файлов .git;
из ZIP-архива GitHub (ни git, ни .git) — хеш, который GitHub подставил в
orthofill/_commit.txt (атрибут export-subst в .gitattributes). Иначе — «dev»."""
from __future__ import annotations

import subprocess
import sys
from functools import lru_cache
from pathlib import Path


def git_head_from_files(root: Path) -> str | None:
    """Короткий хеш текущего коммита прямо из .git — без установленного git."""
    git = Path(root) / '.git'
    try:
        head = (git / 'HEAD').read_text(encoding='utf-8').strip()
    except OSError:
        return None
    if not head.startswith('ref:'):
        return head[:7] or None                     # detached HEAD
    ref = head[4:].strip()
    try:
        return (git / ref).read_text(encoding='utf-8').strip()[:7] or None
    except OSError:
        pass
    try:                                            # ветка упакована в packed-refs
        for line in (git / 'packed-refs').read_text(encoding='utf-8').splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0][:7]
    except OSError:
        pass
    return None


def head_from_archive(root: Path) -> str | None:
    """Хеш из orthofill/_commit.txt: в ZIP с GitHub там код коммита, в рабочей
    папке — неподставленный шаблон «$Format:%h$»."""
    try:
        sha = (Path(root) / 'orthofill' / '_commit.txt').read_text(encoding='utf-8').strip()
    except OSError:
        return None
    return sha if sha and not sha.startswith('$') else None


def _git_command(root: Path) -> str | None:
    flags = 0x08000000 if sys.platform == 'win32' else 0   # CREATE_NO_WINDOW
    try:
        sha = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=root,
                             capture_output=True, text=True, timeout=5,
                             creationflags=flags).stdout.strip()
        if not sha:
            return None
        dirty = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'],
                               cwd=root, capture_output=True, text=True, timeout=5,
                               creationflags=flags).stdout.strip()
    except (OSError, subprocess.SubprocessError):   # git не установлен
        return None
    return f'{sha}+изм' if dirty else sha


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
    return (_git_command(root) or git_head_from_files(root) or head_from_archive(root)
            or 'dev')

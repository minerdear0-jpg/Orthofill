import re
import subprocess
import sys
import tomllib

import orthofill
from conftest import ROOT


def test_version():
    assert orthofill.__version__ == "0.5.0b1"
    assert orthofill.VERSION_LABEL == "0.5 beta 1"


def test_pyproject_version_matches():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == orthofill.__version__


import shutil

import pytest


@pytest.mark.skipif(shutil.which("git") is None or not (ROOT / ".git").exists(),
                    reason="git не установлен или проект без .git")
def test_build_id_from_git():
    from orthofill import buildinfo
    buildinfo.build_id.cache_clear()
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    assert buildinfo.build_id().startswith(sha)


def test_build_id_from_build_module(monkeypatch):
    import types
    from orthofill import buildinfo
    buildinfo.build_id.cache_clear()
    monkeypatch.setitem(sys.modules, "orthofill._build",
                        types.SimpleNamespace(BUILD="abc1234 · 2026-10-21"))
    assert buildinfo.build_id() == "abc1234 · 2026-10-21"
    buildinfo.build_id.cache_clear()


def test_window_title_has_version_and_build():
    from orthofill import buildinfo
    from orthofill.ui import window_title
    assert window_title() == f"Orthofill 0.5 beta 1 · сборка {buildinfo.build_id()}"
    assert re.match(r"Orthofill 0\.5 beta 1 · сборка \S+", window_title())


def test_diag_events_have_build(tmp_path):
    import json
    from orthofill import buildinfo
    from orthofill.diag import DiagLog
    DiagLog(tmp_path).write("x")
    (f,) = tmp_path.glob("*.jsonl")
    ev = json.loads(f.read_text(encoding="utf-8"))
    assert ev["version"] == "0.5.0b1" and ev["build"] == buildinfo.build_id()


def make_git_dir(root, branch="feature/x", sha="0123456789abcdef0123", packed=False):
    git = root / ".git"
    (git / "refs" / "heads" / "feature").mkdir(parents=True)
    (git / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
    if packed:
        (git / "packed-refs").write_text(f"# pack-refs\n{sha} refs/heads/{branch}\n")
    else:
        (git / "refs" / "heads" / branch).write_text(sha + "\n")
    return root


def test_git_head_from_files(tmp_path):
    from orthofill.buildinfo import git_head_from_files
    assert git_head_from_files(make_git_dir(tmp_path)) == "0123456"


def test_git_head_from_packed_refs(tmp_path):
    from orthofill.buildinfo import git_head_from_files
    assert git_head_from_files(make_git_dir(tmp_path, packed=True)) == "0123456"


def test_git_head_detached(tmp_path):
    from orthofill.buildinfo import git_head_from_files
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("fedcba9876543210\n")
    assert git_head_from_files(tmp_path) == "fedcba9"


def test_no_git_at_all(tmp_path):
    from orthofill.buildinfo import git_head_from_files
    assert git_head_from_files(tmp_path) is None


def test_build_id_without_git_executable(monkeypatch):
    import subprocess as sp
    from orthofill import buildinfo

    def missing(*a, **k):
        raise FileNotFoundError(2, "Не удается найти указанный файл")
    monkeypatch.setattr(buildinfo.subprocess, "run", missing)
    buildinfo.build_id.cache_clear()
    expected = buildinfo.git_head_from_files(ROOT) or buildinfo.head_from_archive(ROOT) or "dev"
    assert buildinfo.build_id() == expected
    buildinfo.build_id.cache_clear()


def test_head_from_archive_file(tmp_path):
    """ZIP с GitHub (без git и .git): хеш, подставленный GitHub в orthofill/_commit.txt."""
    from orthofill.buildinfo import head_from_archive
    (tmp_path / 'orthofill').mkdir()
    f = tmp_path / 'orthofill' / '_commit.txt'
    f.write_text('a6b2943\n', encoding='utf-8')
    assert head_from_archive(tmp_path) == 'a6b2943'
    f.write_text('$Format:%h$\n', encoding='utf-8')     # не из архива — не подставлено
    assert head_from_archive(tmp_path) is None
    assert head_from_archive(tmp_path / 'нет') is None


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="в ZIP-архиве шаблон уже подставлен")
def test_archive_file_is_substituted_by_git():
    attrs = (ROOT / '.gitattributes').read_text(encoding='utf-8')
    assert 'orthofill/_commit.txt export-subst' in attrs
    assert (ROOT / 'orthofill' / '_commit.txt').read_text(encoding='utf-8').strip() == '$Format:%h$'

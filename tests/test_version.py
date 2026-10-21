import re
import subprocess
import sys
import tomllib

import orthofill
from conftest import ROOT


def test_version():
    assert orthofill.__version__ == "0.1.0b2"
    assert orthofill.VERSION_LABEL == "0.1 beta 2"


def test_pyproject_version_matches():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == orthofill.__version__


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
    assert window_title() == f"Orthofill 0.1 beta 2 · сборка {buildinfo.build_id()}"
    assert re.match(r"Orthofill 0\.1 beta 2 · сборка \S+", window_title())


def test_diag_events_have_build(tmp_path):
    import json
    from orthofill import buildinfo
    from orthofill.diag import DiagLog
    DiagLog(tmp_path).write("x")
    (f,) = tmp_path.glob("*.jsonl")
    ev = json.loads(f.read_text(encoding="utf-8"))
    assert ev["version"] == "0.1.0b2" and ev["build"] == buildinfo.build_id()

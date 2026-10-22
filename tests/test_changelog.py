"""«Что нового»: журнал изменений CHANGELOG.md → окно «О программе»."""
from conftest import ROOT

import orthofill
from orthofill.changelog import Release, parse, spans

SAMPLE = """# Что нового в Orthofill

Вступление — не показывается.

## 0.2 beta 2 — 22.10.2026

**Протокол удобно проверять.**

- Одна мысль — одна строка;
  продолжение пункта.
- Разделы — **жирным**.

## 0.1 beta — 21.10.2026

- Первая версия.
"""


def test_parse_releases_newest_first():
    rel = parse(SAMPLE)
    assert [r.title for r in rel] == ['0.2 beta 2 — 22.10.2026', '0.1 beta — 21.10.2026']
    assert rel[0].version == '0.2 beta 2'
    assert rel[1].lines == ['- Первая версия.']


def test_wrapped_bullet_joined_and_blank_lines_dropped():
    assert parse(SAMPLE)[0].lines == [
        '**Протокол удобно проверять.**',
        '- Одна мысль — одна строка; продолжение пункта.',
        '- Разделы — **жирным**.',
    ]


def test_spans_bold():
    assert spans('Разделы — **жирным**, да') == [
        ('Разделы — ', False), ('жирным', True), (', да', False)]
    assert spans('просто') == [('просто', False)]


def test_parse_empty_or_garbage():
    assert parse('') == []
    assert parse('нет заголовков\n- пункт') == []


def test_changelog_top_is_current_version():
    """Журнал нельзя забыть: верхний раздел — версия программы."""
    rel = parse((ROOT / 'CHANGELOG.md').read_text(encoding='utf-8'))
    assert rel and rel[0].version == orthofill.VERSION_LABEL


def test_changelog_in_build():
    ps = (ROOT / 'build.ps1').read_text(encoding='utf-8-sig')
    assert "'CHANGELOG.md;.'" in ps
    assert 'Copy-Item CHANGELOG.md' in ps


def test_release_is_dataclass():
    assert Release('x', []).version == 'x'

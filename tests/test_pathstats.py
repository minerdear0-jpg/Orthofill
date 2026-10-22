"""0.5 beta 2: обычный набор врача из журнала."""
import pytest

from orthofill.pathstats import build_stats, note_codes
from orthofill.shell import format_path
from orthofill.workbook import load_workbook_file


@pytest.fixture
def wb(order_xlsx):
    return load_workbook_file(order_xlsx)


def _note(wb, *paths):
    return '\n'.join(format_path(wb, p) for p in paths)


def test_shell_lines_counted(wb):
    a = _note(wb, ('2', '2b', '2b2'), ('4', '4b', '4b5'))
    b = _note(wb, ('2', '2b', '2b2'))
    entries = [(a, None), (a, None), (b, None), (b, None),
               (_note(wb, ('4', '4f', '4f1')), None)]
    st = build_stats(wb, entries)
    assert st.notes == 5 and st.count['4b5'] == 2 and st.count['4b'] == 2 and st.count['2'] == 4
    assert st.usual('4b5') and st.usual('2b2')
    assert not st.usual('4f1')                  # 1 из 5


def test_comma_only_confirmed(wb):
    assert note_codes(wb, 'лигатурная, перепел', None) == []
    codes = note_codes(wb, 'лигатурная, перепел', 'скопировано')
    assert '4f1' in codes and '2c2' not in codes          # 2c2 — умолчание пустой записи


def test_stats_skip_missing_codes(wb):
    line = _note(wb, ('4', '4f', '4f1'))
    wb.by_id['4f1'].text = 'Перепёлка'
    st = build_stats(wb, [(line, None)])
    assert st.notes == 0 and '4f1' not in st.count


def test_stats_cached(ctl, order_xlsx, monkeypatch):
    import orthofill.pathstats as ps
    ctl.import_xlsx(order_xlsx)
    calls = []
    real = ps.build_stats
    monkeypatch.setattr(ps, 'build_stats', lambda *a: calls.append(1) or real(*a))
    ctl.path_stats()
    ctl.path_stats()
    assert len(calls) == 1
    ctl.generate('лигатурная')
    ctl.path_stats()
    assert len(calls) == 2

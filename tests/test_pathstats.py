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
    entries = [(a, None), (b, None), (a, None), (b, None),
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
    ctl.generate('лигатурная')
    calls = []
    real = ps.note_codes
    monkeypatch.setattr(ps, 'note_codes', lambda *a, **k: calls.append(1) or real(*a, **k))
    ctl.path_stats()
    n = len(calls)
    ctl.path_stats()
    assert n >= 1 and len(calls) == n          # без новых записей — ничего не разбирается
    ctl.generate('лигатурная, лиса')
    ctl.path_stats()
    assert len(calls) > n


def _bulk(ctl, n, raw='лигатурная, перепел', copied='скопировано'):
    from datetime import datetime
    ctl.journal._db.executemany(
        'INSERT INTO entries (created_at, raw, generated, copied_text, preset_id) VALUES (?,?,?,?,?)',
        [(datetime.now().isoformat(), f'{raw}, явка {i % 7 + 2} нед', '', copied, ctl.preset_id)
         for i in range(n)])
    ctl.journal._db.commit()


def test_stats_never_block_long(ctl, order_xlsx):
    """Итоговая проверка: 2000 записей — ~10 с пересчёта на нажатие. Теперь
    частями: каждый вызов — не дольше бюджета, потом досчитывается."""
    import time
    ctl.import_xlsx(order_xlsx)
    _bulk(ctl, 120)
    t0 = time.perf_counter()
    st = ctl.path_stats()
    assert time.perf_counter() - t0 < 0.25
    for _ in range(200):
        if not ctl.path_stats_pending():
            break
        ctl.path_stats()
    st = ctl.path_stats()
    assert not ctl.path_stats_pending() and st.notes == 120 and st.count['4f1'] == 120


def test_new_entry_is_incremental(ctl, order_xlsx, monkeypatch):
    import orthofill.pathstats as ps
    ctl.import_xlsx(order_xlsx)
    _bulk(ctl, 30)
    while ctl.path_stats_pending():
        ctl.path_stats()
    calls = []
    real = ps.note_codes
    monkeypatch.setattr(ps, 'note_codes', lambda *a, **k: calls.append(1) or real(*a, **k))
    ctl.generate('лигатурная, лиса')
    ctl.path_stats()
    assert len(calls) == 1                     # только новая запись


def test_repeated_confirmation_counts_once(wb):
    from orthofill.shell import format_path
    line = format_path(wb, ('4', '4f', '4f1'))
    st = build_stats(wb, [(line, None), (line, None), (line, 'x'),
                          (format_path(wb, ('4', '4f', '4f2')), None)])
    assert st.notes == 2 and st.count['4f1'] == 1

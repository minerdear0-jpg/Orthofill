"""0.5 beta 2: порядок — файл врача, набор — история."""
import time

import pytest

from orthofill.pathstats import PathStats
from orthofill.predict import predict, rank
from orthofill.workbook import load_workbook_file


@pytest.fixture
def wb(order_xlsx):
    return load_workbook_file(order_xlsx)


def _stats(notes, **count):
    return PathStats(dict(count), notes)


def test_rank_frequent_first(wb):
    paths = [('4', '4b', c.id) for c in wb.by_id['4b'].children]
    out = rank(paths, PathStats({'4b5': 5, '4b18': 2, '4b2': 1}, 5))
    assert [p[-1] for p in out][:4] == ['4b5', '4b18', '4b1', '4b2']


def test_first_line_usual(wb):
    p = predict(wb, [], _stats(5, **{'2': 5, '2b': 5, '2b2': 5}))
    assert p[0].path == ('2', '2b') and p[0].source == 'usual' and p[0].usual


def test_first_line_file_order_without_history(wb):
    p = predict(wb, [], PathStats())
    assert p[0].path == ('1', '1a') and p[0].source == 'file'


def test_after_leaf_next_group_by_file(wb):
    p = predict(wb, [('2', '2b', '2b2')], PathStats())
    assert p[0].path == ('2', '2c') and p[0].source == 'file'


def test_skips_unusual(wb):
    p = predict(wb, [('2', '2b', '2b2')], _stats(5, **{'4': 5, '4b': 5, '4b5': 5}))
    assert p[0].path == ('4', '4b') and p[0].source == 'usual'
    c = next(x for x in p if x.path == ('2', '2c'))
    assert not c.usual


def test_and_siblings_first(wb):
    wb.by_id['4g'].combine = 'and'
    p = predict(wb, [('4', '4g', '4g1')], _stats(4, **{'4g2': 3, '4g': 4, '4': 4}))
    assert p[0].path == ('4', '4g', '4g2') and p[0].source == 'and'


def test_or_no_siblings(wb):
    p = predict(wb, [('4', '4f', '4f1')], _stats(4, **{'4f2': 3, '4f': 4}))
    assert all(x.path[-1] != '4f2' for x in p)


def test_predict_after_out_of_order(wb):
    p = predict(wb, [('4', '4b', '4b5'), ('2', '2b', '2b2')], PathStats(), limit=200)
    assert p[0].path == ('2', '2c')
    assert all(x.path[1] not in ('4b', '2b') for x in p)


def test_no_cancel_nodes(order_xlsx_with):
    wb = order_xlsx_with(('4j1', 'нет'))
    assert all(x.path[-1] != '4j1' for x in predict(wb, [], PathStats(), limit=200))


def test_predict_fast(wb):
    st = PathStats({it.id: 50 for it in wb.items}, 2000)
    paths = [('4', '4b', c.id) for c in wb.by_id['4b'].children]
    start = time.perf_counter()
    for _ in range(100):
        predict(wb, [('2', '2b', '2b2')], st)
        rank(paths, st)
    assert time.perf_counter() - start < 2.0


# ---------- 0.5 b3: скелет ----------
from orthofill.predict import skeleton_blocks  # noqa: E402


def test_skeleton_usual_missing(wb):
    st = _stats(5, **{'2': 5, '2c': 5, '4': 5, '4b': 5})
    blocks = skeleton_blocks(wb, {'2', '2b', '2b2', '4', '4b', '4b5'}, [('2', '2b', '2b2')], st)
    assert [c for c, _ in blocks] == ['2c']


def test_skeleton_next_flag(wb):
    st = _stats(5, **{'4': 5, '4f': 5})
    blocks = dict(skeleton_blocks(wb, {'2', '2b', '2b2'}, [('2', '2b', '2b2')], st))
    assert blocks['4f'] is True and list(blocks.values()).count(True) == 1


def test_skeleton_without_history(wb):
    blocks = skeleton_blocks(wb, {'2', '2b', '2b2'}, [('2', '2b', '2b2')], PathStats())
    assert blocks == [('2c', True)]

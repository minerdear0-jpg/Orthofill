"""0.5 beta 1: ветка «нет» — отмена пункта (не вариант)."""
from orthofill.engine import build_protocol
from orthofill.lint import lint
from orthofill.workbook import is_cancel


def test_cancel_child_not_a_variant(order_xlsx_with):
    wb = order_xlsx_with(('4j1', 'нет'))
    assert wb.by_id['4j'].cancel == '4j1' and wb.by_id['4j'].children == []
    assert is_cancel(wb.by_id['4j1'])
    codes = [c for c, _ in build_protocol(wb, 'лигатурная, фото').lines]
    assert '4j' in codes and '4j1' not in codes


def test_cancel_in_group(order_xlsx_with):
    wb = order_xlsx_with(('4f7', 'Нет.'))
    g = wb.by_id['4f']
    assert g.cancel == '4f7' and len(g.children) == 6


def test_cancel_roundtrip(order_xlsx_with, store, tmp_path):
    from orthofill.xlsx_export import export_workbook
    from orthofill.workbook import load_workbook_file
    wb = order_xlsx_with(('4j1', 'нет'))
    pid = store.create(wb)
    loaded = store.load(pid)
    assert loaded.by_id['4j'].cancel == '4j1' and loaded.by_id['4j'].children == []
    out = tmp_path / 'out.xlsx'
    export_workbook(loaded, out)
    assert load_workbook_file(out).by_id['4j'].cancel == '4j1'


def test_lint_cancel_useless(order_xlsx_with):
    wb = order_xlsx_with(('4f7', 'нет'))          # эластики: без умолчания — отменять нечего
    wb.by_id['4f'].default = None
    assert any(f.kind == 'cancel_useless' and f.code == '4f' for f in lint(wb))


def test_draft_add_cancel(order_xlsx, ctl):
    ctl.import_xlsx(order_xlsx)
    d = ctl.open_draft()
    d.add('4j', None, 'нет', 3)
    assert ctl.draft.wb.by_id['4j'].cancel is not None
    ctl.save_draft()
    assert ctl.workbook.by_id['4j'].cancel is not None and ctl.workbook.by_id['4j'].children == []


def test_add_item_search_skips_cancel(order_xlsx_with):
    from orthofill.addition import search_items
    wb = order_xlsx_with(('4j1', 'нет'))
    assert all(h.code != '4j1' for h in search_items(wb, 'нет'))


def test_lint_cancel_rule_default_is_useful(order_xlsx_with):
    """Умолчание группы — от правила движка (не из столбца): «нет» нужна."""
    wb = order_xlsx_with(('5d9', 'нет'))
    assert wb.by_id['5d'].default is None
    assert not any(f.kind == 'cancel_useless' and f.code == '5d' for f in lint(wb))

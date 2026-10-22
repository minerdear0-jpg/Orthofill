"""Проверка классификатора: повторы строк, порядок челюстей, пропуски номеров."""
from conftest import ORDER

from orthofill.lint import lint
from orthofill.workbook import load_workbook_file


def test_aktiv_jaw_order(order_xlsx_with):
    wb = order_xlsx_with(('4p', 'Эластическая цепочка'), ('4p1', 'на нижней челюсти.'),
                         ('4p2', 'на верхней челюсти.'))
    f = [x for x in lint(wb) if x.kind == 'jaw_order']
    assert [(x.code, x.level) for x in f] == [('4p1,4p2', 'warning')]
    assert 'Эластическая цепочка' in f[0].message


def test_same_variant_text_in_different_groups_is_fine():
    assert not [x for x in lint(load_workbook_file(ORDER)) if x.kind.startswith('dup')]


def test_dup_in_group(order_xlsx_with):
    wb = order_xlsx_with(('4d4', 'на верхней челюсти.'))
    assert [(x.kind, x.code, x.level) for x in lint(wb) if x.kind.startswith('dup')] == \
        [('dup_row', '4d1,4d4', 'error'), ('dup_in_group', '4d1,4d4', 'error')]


def test_gap(order_xlsx_with):
    wb = order_xlsx_with(('4d5', 'на зубе.'))
    assert ('gap', '4d', 'info') in [(x.kind, x.code, x.level) for x in lint(wb)]


def test_empty_group(order_xlsx_with):
    wb = order_xlsx_with(('4q', 'Пустая группа'))
    wb.by_id['4q'].method = 'words'
    assert ('empty_group', '4q') in [(x.kind, x.code) for x in lint(wb)]


def test_clean_order_has_no_errors():
    assert not [x for x in lint(load_workbook_file(ORDER)) if x.level == 'error']


def test_details_show_findings(ctl, order_xlsx_with):
    wb = order_xlsx_with(('4d4', 'на верхней челюсти.'))
    ctl.import_xlsx(wb.path)
    assert any('одинаковые строки' in d for d in ctl.details)
    assert not any('одинаковый текст у' in d for d in ctl.details)


def test_lint_logic(order_xlsx_with):
    wb = order_xlsx_with()
    wb.by_id['4a'].when, wb.by_id['4a'].condition = 'condition', {'all': [{'field': '4p', 'mentioned': True}]}
    wb.by_id['4j'].when, wb.by_id['4j'].condition = 'condition', {'all': [{'field': '2b', 'is': '2b1', 'not': True}]}
    wb.by_id['5a'].when = 'condition'
    wb.not_together = [('4d1', '4d2'), ('4h1', '4h2')]
    wb.by_id['3f'].combine = 'and'
    wb.by_id['4f'].combine = 'and'
    found = {(f.kind, f.code, f.level) for f in lint(wb)}
    assert {('bad_ref', '4a', 'error'), ('from_nothing', '4j', 'error'),
            ('no_condition', '5a', 'warning'), ('pair_in_group', '4d1,4d2', 'error'),
            ('and_unsupported', '3f', 'warning')} <= found
    assert not {f for f in found if f[1] in ('4f', '4h1,4h2')}

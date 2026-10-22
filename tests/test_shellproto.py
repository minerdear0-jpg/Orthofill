"""0.5 beta 1: протокол из строк-путей (без разбора и угадывания)."""
import pytest

from orthofill.engine import check_references
from orthofill.shell import format_path
from orthofill.shellproto import shell_protocol
from orthofill.workbook import ReferenceCase, load_workbook_file


@pytest.fixture
def wb(order_xlsx):
    return load_workbook_file(order_xlsx)


def _note(wb, *paths):
    return '\n'.join(format_path(wb, p) for p in paths)


def codes(p):
    return [c for c, _ in p.lines]


def test_paths_build_protocol(wb):
    p = shell_protocol(wb, _note(wb, ('2', '2b', '2b2'), ('2', '2c', '2c2'),
                                 ('4', '4b', '4b5'), ('4', '4f', '4f1')))
    c = codes(p)
    for code in ('2b', '2b2', '2c', '2c2', '4b', '4b5', '4f', '4f1'):
        assert code in c
    assert c.index('2b2') < c.index('4b5') < c.index('4f1')
    assert not [w for w in p.warnings if 'не понята' in w]


def test_defaults_still_apply(wb):
    from orthofill.engine import build_protocol
    empty, old = shell_protocol(wb, ''), build_protocol(wb, '')
    assert codes(empty) == codes(old)               # пустая запись — как сейчас у врача
    assert '1a' in codes(empty) and '2c2' in codes(empty) and empty.defaults


def test_cancel_removes_default(order_xlsx_with):
    wb = order_xlsx_with(('4j1', 'нет'))
    wb.by_id['4j'].when = 'always'
    assert '4j' in codes(shell_protocol(wb, ''))
    assert '4j' not in codes(shell_protocol(wb, _note(wb, ('4', '4j', '4j1'))))


def test_comma_note_in_shell_warns(wb):
    p = shell_protocol(wb, 'лигатурная, перепел\nдуга верх 16х25')
    bad = [w for w in p.warnings if 'не понята' in w]
    assert len(bad) == 2 and '4f1' not in codes(p) and '1a' in codes(p)


def test_renamed_item_line_warns(wb):
    line = _note(wb, ('4', '4f', '4f1'))
    wb.by_id['4f1'].text = 'Перепёлка'
    p = shell_protocol(wb, line)
    assert '4f1' not in codes(p) and any('строка 1 не понята' in w for w in p.warnings)


def test_two_or_variants_flagged(wb):
    p = shell_protocol(wb, _note(wb, ('4', '4f', '4f1'), ('4', '4f', '4f2')))
    assert '4f1' in codes(p) and '4f2' in codes(p)
    assert any(r.check for r in p.rows if '4f1' in r.codes or '4f2' in r.codes)
    assert any('несколько' in w for w in p.warnings)


def test_cancel_and_pick_conflict(order_xlsx_with):
    wb = order_xlsx_with(('4f7', 'нет'))
    p = shell_protocol(wb, _note(wb, ('4', '4f', '4f7'), ('4', '4f', '4f1')))
    assert '4f1' in codes(p) and any('отменено строкой «нет»' in w for w in p.warnings)


def test_and_group_collects(wb):
    g = wb.by_id['4g']
    g.combine = 'and'
    a, b = g.children[0], g.children[1]
    p = shell_protocol(wb, _note(wb, (g.id[0], g.id, a.id), (g.id[0], g.id, b.id)))
    assert a.id in codes(p) and b.id in codes(p)
    assert not any('несколько' in w for w in p.warnings)


def test_reference_with_paths_checked(wb):
    raw = _note(wb, ('2', '2b', '2b2'), ('4', '4f', '4f1'))
    lines = shell_protocol(wb, raw).lines
    wb.references.append(ReferenceCase('99', raw, list(lines)))
    res = check_references(wb)[-1]
    assert res.ok


def test_controller_shell_mode(ctl, order_xlsx, tmp_path):
    import shutil
    ctl.import_xlsx(order_xlsx)
    a = ctl.preset_id
    other = tmp_path / 'b.xlsx'
    shutil.copy(order_xlsx, other)
    ctl.import_xlsx(other)
    b = ctl.preset_id
    ctl._activate(a)
    ctl.set_shell_mode(True)
    assert ctl.shell_mode
    note = _note(ctl.workbook, ('4', '4f', '4f1'))
    assert '4f1' in [c for r in ctl.preview(note).rows for c in r.codes]
    ctl.generate(note)
    assert '4f1' in [c for c, _ in ctl.last_protocol.lines]
    assert ctl.find_unknown('лигатурная') == [(0, len('лигатурная'), 'лигатурная')]
    ctl._activate(b)
    assert not ctl.shell_mode
    ctl._activate(a)
    assert ctl.shell_mode

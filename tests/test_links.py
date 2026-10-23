"""0.5 beta 7: связь записи и протокола — номера строк и «откуда» (без Tk)."""
from orthofill.canvas import CanvasLine
from orthofill.links import CHIP_COLORS, chip_color, note_lines, row_sources
from orthofill.shell import format_path
from orthofill.shellproto import shell_protocol
from orthofill.workbook import load_workbook_file


def _raw(wb, *paths):
    return '\n'.join(format_path(wb, p) for p in paths)


def _lines(wb, raw, own=()):
    rows = shell_protocol(wb, raw).rows
    lines = [CanvasLine(r.text, 'row', '|'.join(r.codes), r) for r in rows]
    lines += [CanvasLine(t, 'own', None) for t in own]
    lines.append(CanvasLine(' ' * 48, 'skeleton', '5'))
    return lines


def _by_code(lines, srcs):
    return {l.code: s for l, s in zip(lines, srcs) if l.code}


def test_note_lines(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    raw = _raw(wb, ('2', '2b', '2b2'), ('4', '4b', '4b5')) + '\nне путь\n\n' + \
        _raw(wb, ('4', '4f', '4f1')) + '\n' + format_path(wb, ('4', '4f')) + ' › '
    assert note_lines(wb, raw) == {1: '2b2', 2: '4b5', 5: '4f1'}


def test_numbers_and_sources(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    raw = _raw(wb, ('2', '2b', '2b2'), ('4', '4b', '4b5'), ('4', '4f', '4f1'))
    lines = _lines(wb, raw, own=['Жалуется на боль слева.'])
    srcs = row_sources(wb, lines, note_lines(wb, raw))
    by = _by_code(lines, srcs)
    assert by['2b|2b2'] == ([1], '') and by['4b|4b5'] == ([2], '') and by['4f|4f1'] == ([3], '')
    assert by['2a'] == ([], 'всегда')
    assert by['5d|5d2'] == ([], 'по умолч.') and by['2c|2c2'] == ([], 'по умолч.')
    assert by['1a'] == ([], 'по умолч.')            # жалоба по умолчанию
    assert by['4h1'] == ([], 'по условию')
    assert by['2'] == ([], '')                      # заголовок раздела
    own = next(s for l, s in zip(lines, srcs) if l.kind == 'own')
    skel = next(s for l, s in zip(lines, srcs) if l.kind == 'skeleton')
    assert own == ([], 'ваш текст') and skel == ([], '')


def test_and_group_two_numbers(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.by_id['4f'].combine = 'and'
    raw = _raw(wb, ('4', '4f', '4f1'), ('2', '2b', '2b2'), ('4', '4f', '4f2'))
    lines = _lines(wb, raw)
    by = _by_code(lines, row_sources(wb, lines, note_lines(wb, raw)))
    assert by['4f|4f1'] == ([1], '') and by['4f|4f2'] == ([3], '')


def test_same_item_twice_two_numbers(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    raw = _raw(wb, ('4', '4b', '4b5'), ('2', '2b', '2b2'), ('4', '4b', '4b5'))
    lines = _lines(wb, raw)
    by = _by_code(lines, row_sources(wb, lines, note_lines(wb, raw)))
    assert by['4b|4b5'] == ([1, 3], '')


def test_star_source_is_always(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.by_id['4j'].star = True
    lines = _lines(wb, '')
    by = _by_code(lines, row_sources(wb, lines, {}))
    assert by['4j'] == ([], 'всегда')


def test_chip_color_cycles():
    assert len(CHIP_COLORS) == 8
    assert chip_color(1) == CHIP_COLORS[0] and chip_color(9) == CHIP_COLORS[0]
    assert chip_color(2) != chip_color(1)

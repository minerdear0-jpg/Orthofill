"""0.5 beta 7: раскраска строки оболочки — спаны по уровням (без Tk)."""
from orthofill.colorize import SECTION_COLORS, line_spans, section_color
from orthofill.shell import SEP, format_path
from orthofill.workbook import load_workbook_file


def _kinds(line, spans):
    return [(line[s:e], k) for s, e, k in spans]


def test_spans_full_path(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    line = format_path(wb, ('2', '2b', '2b2'))
    assert _kinds(line, line_spans(wb, line)) == [
        ('Анамнез: активация', 'sec:2'), ('›', 'sep'), ('Тип системы', 'grp'),
        ('›', 'sep'), ('вестибулярная лигатурная.', 'leaf')]


def test_spans_single_item(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    line = format_path(wb, ('4', '4j'))
    assert [k for _, _, k in line_spans(wb, line)] == ['sec:4', 'sep', 'leaf']


def test_spans_typed_tail(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    line = format_path(wb, ('4', '4f')) + SEP + 'пер'
    assert _kinds(line, line_spans(wb, line))[-3:] == [
        ('Назначены межчелюстные эластики', 'grp'), ('›', 'sep'), ('пер', 'typed')]


def test_spans_unknown_level_plain(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    line = 'Лечение:' + SEP + 'чего нет' + SEP + 'дальше'
    kinds = _kinds(line, line_spans(wb, line))
    assert kinds[0] == ('Лечение:', 'sec:4') and ('чего нет', 'grp') not in kinds
    assert all(t != 'чего нет' for t, _ in kinds)


def test_no_sep_no_spans(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    assert line_spans(wb, 'лигатурная') == [] and line_spans(wb, '') == []


def test_section_color_stable(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    a = line_spans(wb, format_path(wb, ('4', '4j')))[0][2]
    b = line_spans(wb, format_path(wb, ('4', '4f', '4f1')))[0][2]
    assert a == b == 'sec:4'
    assert section_color(1) == SECTION_COLORS[0] and section_color(7) == SECTION_COLORS[0]

"""Словарь врача в разборе записи: раньше правил, с отрицаниями, по тексту пункта."""
from orthofill.engine import build_protocol
from orthofill.workbook import DictEntry, load_workbook_file


def ids(p):
    return [c for c, _ in p.lines]


def wb_with(order_xlsx, *pairs):
    wb = load_workbook_file(order_xlsx)
    wb.dictionary = [DictEntry(w, t, "") for w, t in pairs]
    return wb


def test_dictionary_selects_variant(order_xlsx):
    p = build_protocol(wb_with(order_xlsx, ("квакозябра", "Изгиб третьего порядка")),
                       "лигатурная, изгиб 12 зуб квакозябра")
    assert "4g3" in ids(p) and p.dictionary_hits == ["квакозябра"]
    assert not any(r.check for r in p.rows if "4g3" in r.codes)


def test_dictionary_beats_rule_no_duplicate(order_xlsx):
    p = build_protocol(wb_with(order_xlsx, ("лиса", "Медведь")), "лигатурная, лиса")
    assert "4f3" in ids(p) and "4f2" not in ids(p)


def test_dictionary_respects_negation(order_xlsx):
    wb = wb_with(order_xlsx, ("квакозябра", "Изгиб третьего порядка"))
    assert "4g3" not in ids(build_protocol(wb, "лигатурная, без квакозябры"))
    assert "4g3" not in ids(build_protocol(wb, "лигатурная, квакозябра отменена"))


def test_dictionary_single_item(order_xlsx_with):
    wb = order_xlsx_with(("4o", "Подвязывание зуба короткой металлической лигатурой."))
    wb.dictionary = [DictEntry("подвязал 13", "Подвязывание зуба короткой металлической лигатурой.", "4o")]
    assert "4o" in ids(build_protocol(wb, "лигатурная, подвязал 13"))
    assert "4o" not in ids(build_protocol(wb, "лигатурная"))


def test_dictionary_phrase_with_layout(order_xlsx):
    wb = wb_with(order_xlsx, ("18х25 тма", 'на верхней челюсти 0.018×0.025" TMA'))
    assert "4b16" in ids(build_protocol(wb, "лигатурная, 18x25 ТМА"))


def test_dictionary_missing_item_warns(order_xlsx):
    p = build_protocol(wb_with(order_xlsx, ("квакозябра", "Изгиб четвёртого порядка")),
                       "лигатурная, квакозябра")
    assert p.warnings.count("слово «квакозябра» больше не находит пункт") == 1


def test_dictionary_unused_word_no_warning(order_xlsx):
    p = build_protocol(wb_with(order_xlsx, ("квакозябра", "Изгиб четвёртого порядка")), "лигатурная")
    assert not any("квакозябра" in w for w in p.warnings) and p.dictionary_hits == []

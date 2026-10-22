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


# ---------- итоговое ревью 0.2b3 ----------
CHAIN = [("4p", "Эластическая цепочка без шага"), ("4p1", " на нижней челюсти."),
         ("4p2", "на верхней челюсти.")]


def test_same_text_items_resolved_by_code(order_xlsx_with):
    """C1: «на верхней челюсти.» у 4d1, 4e1, 4p2 — слово врача для 4p2 не выбирает 4d1."""
    wb = order_xlsx_with(*CHAIN)
    wb.dictionary = [DictEntry("квакозябра", "на верхней челюсти.", "4p2")]
    p = build_protocol(wb, "самолигируемая, квакозябра")
    assert "4p2" in ids(p) and "4d1" not in ids(p) and "4e1" not in ids(p)


def test_same_text_without_code_is_not_guessed(order_xlsx_with):
    wb = order_xlsx_with(*CHAIN)
    wb.dictionary = [DictEntry("квакозябра", "на верхней челюсти.", "")]
    p = build_protocol(wb, "самолигируемая, квакозябра")
    assert not {"4d1", "4e1", "4p2"} & set(ids(p))
    assert any("квакозябра" in w for w in p.warnings)


def test_short_word_matches_whole_word_only(order_xlsx):
    """C2: «гиг» не срабатывает внутри «гигиена»."""
    wb = wb_with(order_xlsx, ("гиг", "Гигиена полости рта неудовлетворительная. "))
    p = build_protocol(wb, "лигатурная, гигиена удовлетворительная")
    assert "3f1" in ids(p) and "3f2" not in ids(p)
    assert "3f2" in ids(build_protocol(wb, "лигатурная, гиг"))


def test_word_with_number_needs_boundary(order_xlsx):
    wb = wb_with(order_xlsx, ("явка 6", "8 недель."))
    assert "5d4" not in ids(build_protocol(wb, "лигатурная, явка 60 дней"))
    assert "5d4" in ids(build_protocol(wb, "лигатурная, явка 6"))


def test_long_word_by_stem_still_works(order_xlsx):
    wb = wb_with(order_xlsx, ("квакозябра", "Изгиб третьего порядка"))
    assert "4g3" in ids(build_protocol(wb, "лигатурная, квакозябры"))
    assert "4g3" not in ids(build_protocol(wb, "лигатурная, квакозябрамания"))


def test_phrase_with_spaced_section(order_xlsx):
    wb = wb_with(order_xlsx, ("18х25 тма", 'на верхней челюсти 0.018×0.025" TMA'))
    assert "4b16" in ids(build_protocol(wb, "лигатурная, 18 * 25 TMA"))


def test_dictionary_for_complaint_and_orphan(order_xlsx):
    """I2: слово для жалобы и для «сиротского» пункта действительно влияет."""
    wb = wb_with(order_xlsx, ("отвал", "на отклеивание брекета."),
                 ("квакозябра", "Контроль положения дуги, окклюзионных контактов, закрытия клипс."))
    p = build_protocol(wb, "лигатурная, отвал, квакозябра")
    assert "1b" in ids(p) and "4h2" in ids(p)


def test_two_words_one_group_warns_any_order(order_xlsx):
    for pairs in ((("мишка", "Медведь"), ("кисонька", "Лиса")),
                  (("кисонька", "Лиса"), ("мишка", "Медведь"))):
        p = build_protocol(wb_with(order_xlsx, *pairs), "лигатурная, мишка, кисонька")
        assert "4f3" in ids(p) and "4f2" not in ids(p)
        assert any("несколько слов врача" in w for w in p.warnings)

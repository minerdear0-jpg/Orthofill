"""«Добавить пункт»: поиск по пресету и вставка в протокол с правками врача."""
from orthofill.addition import insert_item, search_items
from orthofill.engine import build_protocol
from orthofill.workbook import DictEntry, load_workbook_file


def test_search_variant_with_where(order_xlsx):
    hits = search_items(load_workbook_file(order_xlsx), "третьего")
    assert hits[0].code == "4g3" and hits[0].label == "Изгиб третьего порядка"
    assert hits[0].where == "Лечение → Юстировка дуги"
    assert all(h.code not in ("4", "4g") for h in hits)


def test_search_spans(order_xlsx):
    h = search_items(load_workbook_file(order_xlsx), "трет")[0]
    assert [h.label[s:e] for s, e in h.spans] == ["трет"]


def test_search_layout_and_ranking(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    assert search_items(wb, "gthtgtk")[0].label == "Перепел"            # раскладка
    a = [h.code for h in search_items(wb, "на верхней")]
    wb.dictionary = [DictEntry("шестнашка", 'на верхней челюсти 0.016" NiTi', "4b2")]
    b = [h.code for h in search_items(wb, "на верхней")]
    assert a[0] != "4b2" and b[0] == "4b2"


def test_search_empty_query_lists_dictionary_items(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    assert search_items(wb, "") == []
    wb.dictionary = [DictEntry("торк", "Изгиб третьего порядка", "4g3")]
    assert [h.code for h in search_items(wb, "")] == ["4g3"]


def test_insert_keeps_edits_and_replaces_variant(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    text = build_protocol(wb, "лигатурная, явка 4 нед").text.replace("осмотр.", "осмотр, жалоб нет.")
    new, line = insert_item(wb, text, "5d4")
    assert "осмотр, жалоб нет." in new
    assert "Явка на следующую активацию через 4 недели." not in new
    assert new.splitlines()[line] == "Явка на следующую активацию через 8 недель."


def test_insert_does_not_replace_edited_variant(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    text = build_protocol(wb, "лигатурная").text.replace("через 4 недели.", "через 4 недели, контроль.")
    new, _ = insert_item(wb, text, "5d4")
    assert "через 4 недели, контроль." in new and "через 8 недель." in new


def test_insert_into_section_end(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    text = build_protocol(wb, "лигатурная").text
    new, line = insert_item(wb, text, "4g3")
    out = new.splitlines()
    assert out[line] == "Юстировка дуги: Изгиб третьего порядка."
    assert out.index("Лечение:") < line < out.index("Рекомендации:")


def test_insert_restores_missing_section(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    lines = build_protocol(wb, "лигатурная").text.splitlines()
    i, j = lines.index("Лечение:"), lines.index("Рекомендации:")
    text = "\n".join(lines[:i] + lines[j:])                       # врач стёр «Лечение»
    new, line = insert_item(wb, text, "4g3")
    out = new.splitlines()
    assert out.index("Лечение:") < line < out.index("Рекомендации:")
    assert out[line] == "Юстировка дуги: Изгиб третьего порядка."


def test_insert_single_item(order_xlsx_with):
    wb = order_xlsx_with(("4o", "Подвязывание зуба короткой металлической лигатурой."))
    new, line = insert_item(wb, build_protocol(wb, "лигатурная").text, "4o")
    assert new.splitlines()[line] == "Подвязывание зуба короткой металлической лигатурой."


def test_insert_in_preset_order(order_xlsx):
    """Смоук 0.2b3: юстировка вставала в конец «Лечения», после динамики."""
    wb = load_workbook_file(order_xlsx)
    text = build_protocol(wb, "лигатурная, замена дуги верх 18х25 нити").text
    new, line = insert_item(wb, text, "4g3")
    out = new.splitlines()
    dyn = next(i for i, ln in enumerate(out) if ln.startswith("Динамика лечения"))
    wire = next(i for i, ln in enumerate(out) if ln.startswith("Смена дуги"))
    assert wire < line < dyn


# ---------- итоговое ревью 0.2b3 ----------
def test_insert_existing_item_is_not_duplicated(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    text = build_protocol(wb, "лигатурная").text
    new, line = insert_item(wb, text, "4a")
    assert new == text and text.splitlines()[line] == "осмотр."


def test_insert_tolerant_header(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    text = build_protocol(wb, "лигатурная").text.replace("Лечение:\nосмотр.", "Лечение: осмотр.")
    new, _ = insert_item(wb, text, "4g3")
    assert new.count("Лечение") == 1 and "Юстировка дуги: Изгиб третьего порядка." in new


def test_insert_replaces_sibling_without_header(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    text = build_protocol(wb, "лигатурная").text.replace("Рекомендации:\n", "")
    new, _ = insert_item(wb, text, "5d4")
    assert "через 4 недели." not in new and "через 8 недель." in new


def test_search_wire_like_doctor_writes(order_xlsx):
    """I6: «18х25 тма», «16 niti» находят дуги."""
    wb = load_workbook_file(order_xlsx)
    assert search_items(wb, "18х25 тма")[0].code in ("4b16", "4c16")
    assert {h.code for h in search_items(wb, "16 niti")} >= {"4b2", "4c2"}

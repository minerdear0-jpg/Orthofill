"""Свойства групп и пунктов как данные: способ выбора, «всегда», по умолчанию, слова."""
from orthofill.engine import METHOD_LABELS, build_protocol, guess_settings, rule_kind
from orthofill.workbook import load_workbook_file


def ids(p):
    return [c for c, _ in p.lines]


def test_guess_methods(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    guess_settings(wb)
    assert wb.by_id["3f"].method == "hygiene" and wb.by_id["4f"].method == "elastics"
    assert wb.by_id["4b"].method == "wire" and wb.by_id["5d"].method == "visit"


def test_guess_new_group_is_words(order_xlsx_with):
    wb = order_xlsx_with(("4z", "Ретейнер"), ("4z1", "несъёмный установлен."))
    guess_settings(wb)
    assert wb.by_id["4z"].method == "words"


def test_guess_when_majority(order_xlsx_with):
    wb = order_xlsx_with(("4o", "Подвязывание зуба короткой металлической лигатурой."))
    guess_settings(wb)
    assert wb.by_id["4a"].when == "always" and wb.by_id["4o"].when == "mentioned"


def test_guess_keeps_explicit(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.by_id["3f"].method = "words"
    wb.by_id["4a"].when = "mentioned"
    guess_settings(wb)
    assert wb.by_id["3f"].method == "words" and wb.by_id["4a"].when == "mentioned"


def test_method_overrides_guess(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.by_id["3f"].method = "words"
    assert rule_kind(wb.by_id["3f"]) is None


def test_when_mentioned_hides_single(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.by_id["4j"].when = "mentioned"
    assert "4j" not in ids(build_protocol(wb, "лигатурная"))
    assert "4j" in ids(build_protocol(wb, "лигатурная, фотопротокол"))


def test_default_variant(order_xlsx):
    wb = load_workbook_file(order_xlsx)
    wb.by_id["5d"].default = "5d3"          # 6 недель, если врач не написал
    assert ("5d3", "6 недель.") in build_protocol(wb, "лигатурная").lines


def test_extra_words(order_xlsx_with):
    wb = order_xlsx_with(("4z", "Ретейнер"), ("4z1", "несъёмный установлен."))
    wb.by_id["4z"].words = ["ретайн"]
    assert "4z1" in ids(build_protocol(wb, "ретайнер несъемный установлен"))


def test_labels_unique():
    assert len(set(METHOD_LABELS.values())) == len(METHOD_LABELS)

from orthofill.text import norm, stem_in, word_stem


def test_norm_mixed_layout():
    assert norm("СuNiTi") == "cuniti"
    assert norm("нижнeй") == "нижней"


def test_norm_spacing_and_br():
    assert norm("  Ёлка<br>– 0.016×0.025 ") == "елка - 0.016x0.025"


def test_stem_in():
    assert stem_in(word_stem("Перепел"), norm("ношение перепела"))
    assert stem_in(word_stem("Лиса"), norm("эластики лису"))
    assert stem_in(word_stem("Слон"), norm("резинки слон"))
    assert not stem_in(word_stem("Зебра"), norm("перепел"))

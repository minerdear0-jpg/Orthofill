"""Контроллер: добавить пункт, научить слову, отменить, сверка после обучения."""


def test_add_learn_then_recognized(ctl, clip, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    raw = "лигатурная, изгиб 12 зуб квакозябра"
    r = ctl.generate(raw)
    assert [w for *_, w in r.unknown] == ["квакозябра"]
    res = ctl.add_item(r.text, "4g3")
    assert "Юстировка дуги: Изгиб третьего порядка." in res.text and clip[-1] == res.text
    assert res.candidates == ["квакозябра"] and res.learned is None
    assert ctl.learn("квакозябра", "4g3") == "Запомнено: «квакозябра» → Изгиб третьего порядка"
    ctl.generate(raw)
    assert "4g3" in [c for c, _ in ctl.last_protocol.lines]
    assert ctl.generate(raw).unknown == []


def test_add_for_word_learns_in_one_step(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    raw = "лигатурная, изгиб 12 зуб квакозябра"
    res = ctl.add_item(ctl.generate(raw).text, "4g3", word="квакозябра")
    assert res.learned == "квакозябра" and "Запомнено" in res.status
    assert [e.word for e in ctl.workbook.dictionary] == ["квакозябра"]


def test_learn_that_breaks_reference_warns(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    msg = ctl.learn("перепел", "4f3")             # эталон 1: «перепел» → 4f1
    assert "не совпадает эталон 1" in msg and ctl.last_learn_broke == ["1"]
    assert ctl.unlearn("перепел") == "Отменено: «перепел»"
    assert ctl.file_status.startswith("✓")


def test_learn_phrase_normalized(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.learn("18х25,\nТМА", "4b16")
    assert [e.word for e in ctl.workbook.dictionary] == ["18х25 тма"]


def test_learn_empty_word(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert ctl.learn("  ", "4g3") == "Выберите слово"


def test_unlearn(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.learn("квакозябра", "4g3")
    ctl.unlearn("квакозябра")
    assert ctl.workbook.dictionary == []
    ctl.generate("лигатурная, квакозябра")
    assert "4g3" not in [c for c, _ in ctl.last_protocol.lines]


def test_hits_counted(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.learn("квакозябра", "4g3")
    ctl.generate("лигатурная, квакозябра")
    ctl.generate("лигатурная, квакозябра")
    assert ctl.workbook.dictionary[0].hits == 2


def test_learning_marks_preset_dirty(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.learn("квакозябра", "4g3")
    assert ctl.needs_export_before_update(ctl.preset_id)


def test_word_candidates_last_first(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert ctl.word_candidates("лигатурная, квакозябра, бармаглот") == ["бармаглот", "квакозябра"]

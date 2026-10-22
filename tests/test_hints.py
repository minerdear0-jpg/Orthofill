"""Подсказки в записи: кандидаты по началу слова."""


def test_sources_and_order(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.learn('торк', '4g3')
    ctl.generate('лигатурная, торцевание')          # слово из прошлых записей
    hs = ctl.hints('тор')
    assert [(h.word, h.kind) for h in hs][:2] == [('торк', 'doctor'), ('торцевание', 'history')]
    assert 'третьего порядка' in hs[0].becomes and hs[1].becomes == ''


def test_item_words(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    h = next(h for h in ctl.hints('пере') if h.word == 'перепел')
    assert h.kind == 'item' and 'Перепел' in h.becomes


def test_common_item_word_has_no_becomes(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    h = next(h for h in ctl.hints('верхн') if h.word == 'верхней')
    assert h.kind == 'item' and h.becomes == ''


def test_wrong_layout(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.learn('торк', '4g3')
    assert ctl.hints('njh')[0].word == 'торк'


def test_no_exact_and_short(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert ctl.hints('пе') == []                       # меньше 3 букв
    assert all(h.word != 'перепел' for h in ctl.hints('перепел'))
    assert len(ctl.hints('на ')) == 0


def test_history_counts_per_preset(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    for _ in range(3):
        ctl.generate('лигатурная, ирригатор, 18')
    words = ctl.journal.raw_words(ctl.preset_id)
    assert words['ирригатор'] == 3 and 'на' not in words and '18' not in words
    assert ctl.journal.raw_words(ctl.preset_id + 99) == {}


def test_history_ranked_by_frequency(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.generate('ирригатор')
    for _ in range(2):
        ctl.generate('ирригация')
    assert [h.word for h in ctl.hints('ирри')][:2] == ['ирригация', 'ирригатор']


def test_index_refreshes_after_learning(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert not any(h.word == 'торк' for h in ctl.hints('тор'))
    ctl.learn('торк', '4g3')
    assert ctl.hints('тор')[0].word == 'торк'

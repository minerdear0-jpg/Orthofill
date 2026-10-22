"""0.3 beta 1: живой протокол и токены — на настоящем Tk (нужен дисплей)."""
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


@pytest.fixture
def live(app):
    app.live_delay, app.unknown_delay = 20, 40
    app.copied = []
    app.ctl.clipboard = app.copied.append
    return app


def _type(app, text):
    app.raw_txt.focus_force()
    app.raw_txt.insert('insert', text)
    app.root.update()


def _wait(app, ms=120):
    app.root.after(ms)
    app.root.update()
    app.root.after(10)
    app.root.update()


def _out(app):
    return app.out_txt.get('1.0', 'end-1c')


def test_live_rebuild_after_pause(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    assert 'Перепел' in _out(live) and not live.copied
    assert 'Ctrl+Enter' in live.status_lbl['text']


def test_debounce_one_rebuild(live, monkeypatch):
    calls = []
    orig = live.ctl.preview
    monkeypatch.setattr(live.ctl, 'preview', lambda *a, **k: calls.append(1) or orig(*a, **k))
    live.live_delay = 300                       # как у врача: пауза в наборе
    for ch in 'лигатурная, перепел, явка 6 недель, гигиена неуд':
        live.raw_txt.insert('end', ch)
        live.root.update()
    _wait(live, 450)
    assert len(calls) == 1


def test_hand_edit_freezes_live(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    _type(live, ', лиса')
    _wait(live)
    assert 'моя правка' in _out(live) and live.live_frozen and live.live_bar.winfo_manager()


def test_update_button_unfreezes(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    _type(live, ', юстировка изгиб первого')
    _wait(live)
    live._live_update_now()
    assert 'моя правка' not in _out(live) and 'первого порядка' in _out(live)
    assert not live.live_frozen and not live.live_bar.winfo_manager()


def test_keep_button_does_not_nag(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    _type(live, ', перепел')
    _wait(live)
    live._live_keep()
    assert 'вручную' in live.live_label['text'] and not live.live_keep_btn.winfo_manager()
    _type(live, ', лиса')
    _wait(live)
    # не спрашивает заново, но напоминание остаётся; правка цела
    assert 'вручную' in live.live_label['text'] and not live.live_keep_btn.winfo_manager()
    assert 'моя правка' in _out(live)


def test_confirm_copies_edited(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    live.generate()
    assert live.copied and live.copied[-1].endswith('моя правка')


def test_confirm_copies_live(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    n = live.ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
    live.generate()
    assert live.copied[-1] == _out(live) and 'Перепел' in live.copied[-1]
    assert live.ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0] == n + 1
    assert not live.live_frozen


def test_empty_note_clears_protocol(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.raw_txt.delete('1.0', 'end')
    live.root.update()
    _wait(live)
    assert _out(live) == ''


def test_live_unknown_underline(live):
    _type(live, 'лигатурная, квакозябра')
    _wait(live, 200)
    assert live.raw_txt.tag_ranges('unknown')


# ---------- Task 4: токены ----------
def _accept(app, text):
    _type(app, text)
    app.hint_box.update()
    app.root.update()
    assert app.hint_box.accept()
    app.root.update()


def test_accept_coded_hint_makes_token(live):
    live.ctl.learn('торк', '4g3')
    _accept(live, 'лигатурная, тор')
    assert live.tokens() == [('торк', '4g3')]
    assert 'token' in live.raw_txt.tag_names('1.13')


def test_uncoded_hint_is_plain_text(live):
    _accept(live, 'на верхн')
    assert live.tokens() == []


def test_typing_inside_token_unbinds(live):
    live.ctl.learn('торк', '4g3')
    _accept(live, 'тор')
    live.raw_txt.insert('1.2', 'х')
    live.root.update()
    assert live.tokens() == [] and not live.raw_txt.tag_ranges('token')


def test_typing_after_token_keeps_it(live):
    live.ctl.learn('торк', '4g3')
    _accept(live, 'тор')
    _type(live, ', перепел')
    assert live.tokens() == [('торк', '4g3')]


def test_delete_part_unbinds(live):
    live.ctl.learn('торк', '4g3')
    _accept(live, 'тор')
    live.raw_txt.delete('end-2c', 'end-1c')
    live.root.update()
    assert live.tokens() == []


def test_token_feeds_live_protocol(live):
    live.ctl.learn('торк', '4g3')
    _accept(live, 'лигатурная, тор')
    _wait(live)
    assert 'третьего порядка' in _out(live) and not live.copied


def test_add_for_word_binds_not_inserts(live):
    _type(live, 'лигатурная, квакозябра')
    _wait(live, 200)
    assert live.raw_txt.tag_ranges('unknown')
    live._open_add_for_word('квакозябра')
    live.add_entry.insert(0, 'третьего')
    live._on_add_query()
    live._add_selected(0)
    _wait(live)
    assert 'третьего порядка' in _out(live) and not live.copied
    assert any(e.word == 'квакозябра' for e in live.ctl.workbook.dictionary)
    assert live.tokens() == [('квакозябра', '4g3')]


# ---------- итоговая проверка ----------
def test_added_line_is_a_hand_edit(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    live.add_entry.insert(0, 'третьего')
    live._on_add_query()
    live._add_selected(0)
    _type(live, ', явка 4 нед')
    _wait(live)
    assert 'третьего порядка' in _out(live) and live.live_frozen


def test_keep_leaves_indicator_and_empty_note_unfreezes(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    _type(live, ', перепел')
    _wait(live)
    live._live_keep()
    assert live.live_bar.winfo_manager() and 'вручную' in live.live_label['text']
    live.raw_txt.delete('1.0', 'end')
    live.root.update()
    _wait(live)
    assert not live.live_frozen and _out(live) == '' and not live.live_bar.winfo_manager()


def test_fast_confirm_after_edit_warns(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.out_txt.insert('end', '\nмоя правка')
    live.raw_txt.insert('end', ', перепел')
    live.root.update()
    live.generate()
    assert 'исправленный' in live.status_lbl['text'] and 'не вошл' in live.status_lbl['text']
    assert live.mark_prompt.winfo_manager()


def test_copy_on_draft_confirms(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.generate()
    _type(live, ', перепел')
    _wait(live)
    n = live.ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
    live.copy()
    assert live.ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0] == n + 1
    assert live.ctl._last_raw.endswith('перепел')


def test_mark_case_on_draft_asks_confirm(live):
    _type(live, 'лигатурная')
    _wait(live)
    live.mark_case()
    assert 'Ctrl+Enter' in live.status_lbl['text']


def test_switch_preset_does_not_log_draft(live):
    _type(live, 'лигатурная, перепел')
    _wait(live)
    n = live.ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
    other = next(p.id for p in live.ctl.presets.list() if p.id != live.ctl.preset_id)
    live.switch_to(other)
    live.root.update()
    assert live.ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0] == n
    assert 'Перепел' in _out(live) and 'Ctrl+Enter' in live.status_lbl['text']


def test_tokens_cleared_on_preset_switch(live):
    live.ctl.learn('торк', '4g3')
    _accept(live, 'тор')
    other = next(p.id for p in live.ctl.presets.list() if p.id != live.ctl.preset_id)
    live.switch_to(other)
    assert live.tokens() == [] and not live.raw_txt.tag_ranges('token')


def test_only_doctor_words_become_tokens(live):
    _accept(live, 'перепе')
    assert live.tokens() == []


def test_bind_word_keeps_unlearn_and_marks(live):
    _type(live, 'лигатурная, класс 1, квакозябра')
    _wait(live, 200)
    live._open_add_for_word('квакозябра')
    live.add_entry.insert(0, 'третьего')
    live._on_add_query()
    live._add_selected(0)
    assert live.unlearn_btn.winfo_manager()


def test_import_does_not_freeze(live, order_xlsx):
    _type(live, 'лигатурная')
    _wait(live)
    live.import_xlsx_path(order_xlsx, update=True)
    _type(live, ', перепел')
    _wait(live)
    assert not live.live_frozen and 'Перепел' in _out(live)


def test_appending_to_token_unbinds(live):
    live.ctl.learn('торк', '4g3')
    _accept(live, 'тор')
    _type(live, 'ование')
    assert live.tokens() == []


def test_accepted_tail_feeds_live_protocol(live):
    for raw in ('активация, лигатурная, замена дуги верх 18х25 тма, явка 6 нед',
                'активация, лигатурная, замена дуги верх 18х25 тма, перепел'):
        live.ctl.generate(raw)
    _type(live, 'лигатурная, замена ду')
    live.hint_box.update()
    live.root.update()
    assert live.hint_box.accept_phrase()
    live.root.update()                          # событие «запись изменилась»
    _wait(live)
    assert '0.018×0.025" TMA' in _out(live)

"""0.3 beta 1: токены записи и черновик протокола."""
import json

import pytest
from conftest import ORDER

from orthofill.engine import build_protocol
from orthofill.workbook import load_workbook_file


@pytest.fixture
def wb():
    return load_workbook_file(ORDER)


def codes(p):
    return [c for c, _ in p.lines]


def _events(ctl):
    return [json.loads(line) for f in sorted(ctl.diag_dir.glob('diag-*.jsonl'))
            for line in f.read_text(encoding='utf-8').splitlines()]


# ---------- Task 1 ----------
def test_token_selects_item_for_this_note_only(wb):
    p = build_protocol(wb, 'лигатурная, квакозябра', tokens=[('квакозябра', '4g3')])
    assert '4g3' in codes(p) and not wb.dictionary
    assert '4g3' not in codes(build_protocol(wb, 'лигатурная, квакозябра'))


def test_token_respects_negation(wb):
    assert '4g3' not in codes(build_protocol(wb, 'лигатурная, без квакозябры',
                                             tokens=[('квакозябры', '4g3')]))


def test_token_with_unknown_code_is_ignored(wb):
    p = build_protocol(wb, 'лигатурная, квакозябра', tokens=[('квакозябра', '9z9')])
    assert '9z9' not in codes(p)


def test_hint_codes(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.learn('торк', '4g3')
    assert ctl.hints('тор')[0].code == '4g3'
    assert next(h for h in ctl.hints('пере') if h.word == 'перепел').code == '4f1'
    assert next(h for h in ctl.hints('верхн') if h.word == 'верхней').code == ''


# ---------- Task 2 ----------
def test_preview_writes_nothing(ctl, order_xlsx, clip):
    ctl.import_xlsx(order_xlsx)
    ctl.set_diagnostics(True)
    n = ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0]
    r = ctl.preview('лигатурная, перепел')
    assert r.text and not r.copied and not clip and 'черновик' in r.status
    assert ctl.journal._db.execute('SELECT COUNT(*) FROM entries').fetchone()[0] == n
    assert not [e for e in _events(ctl) if e['event'] == 'generate']


def test_preview_with_tokens(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    r = ctl.preview('лигатурная, квакозябра', tokens=[('квакозябра', '4g3')])
    assert 'третьего порядка' in r.text


def test_confirm_with_edited_text(ctl, order_xlsx, clip):
    ctl.import_xlsx(order_xlsx)
    ctl.generate('лигатурная', text='мой протокол')
    assert clip[-1] == 'мой протокол'
    row = ctl.journal._db.execute('SELECT copied_text FROM entries ORDER BY id DESC').fetchone()
    assert row[0] == 'мой протокол'


def test_add_item_does_not_copy(ctl, order_xlsx, clip):
    ctl.import_xlsx(order_xlsx)
    r = ctl.generate('лигатурная')
    clip.clear()
    res = ctl.add_item(r.text, '4g3')
    assert not clip and 'Ctrl+Enter' in res.status


def test_bind_word_learns(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    status = ctl.bind_word('квакозябра', '4g3')
    assert 'квакозябра' in status and any(e.word == 'квакозябра' for e in ctl.workbook.dictionary)


def test_tokens_in_diagnostics(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.set_diagnostics(True)
    ctl.generate('лигатурная, квакозябра', tokens=[('квакозябра', '4g3')])
    ev = [e for e in _events(ctl) if e['event'] == 'generate'][-1]
    assert ev['tokens'] == [['квакозябра', '4g3']] and '4g3' in [c for c, _ in ev['lines']]


def test_find_unknown_for_draft_skips_tokens(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    raw = 'лигатурная, квакозябра, бармаглот'
    ctl.preview(raw, tokens=[('квакозябра', '4g3')])
    words = [w for *_, w in ctl.find_unknown(raw, tokens=[('квакозябра', '4g3')])]
    assert words == ['бармаглот']

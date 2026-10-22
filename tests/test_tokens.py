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

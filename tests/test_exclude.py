"""0.5 beta 6: «Ошибка → Исключить» — случай с тем, что и откуда."""
import json
import time

import pytest

import orthofill.controller as controller_mod
from orthofill.shell import format_path


def _events(ctl):
    out = []
    for p in sorted(ctl.diag_dir.glob('*.jsonl')):
        out += [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
    return out


def _case(ctl, kind='exclude'):
    return [e for e in _events(ctl) if e['event'] == 'case' and e.get('kind') == kind][-1]


def test_exclude_written_without_diagnostics(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert not ctl.diagnostics
    cid = ctl.exclude_case([('4f', '4f1')], 'лигатурная, перепел', ['Назначены межчелюстные эластики: Перепел'])
    e = _case(ctl)
    assert e['case_id'] == cid and e['raw'] == 'лигатурная, перепел'
    assert e['excluded'][0]['code'] == '4f1' and e['excluded'][0]['text'].endswith('Перепел')
    assert e['mode'] == 'comma' and e['lines']


def test_exclude_merged_row_codes(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.exclude_case([('4f', '4f1')], 'лигатурная, перепел', ['Эластики: Перепел'])
    x = _case(ctl)['excluded'][0]
    assert x['code'] == '4f1' and x['group'] == '4f'


def test_source_kinds(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    assert ctl.line_source('1a', 'лигатурная') == 'default'
    assert ctl.line_source('4f1', 'лигатурная, перепел') == 'note'
    wb = ctl.workbook
    wb.by_id['4j'].when = 'always'
    assert ctl.line_source('4j', 'лигатурная') in ('always', 'default')
    ctl.set_shell_mode(True)
    raw = format_path(wb, ('4', '4f', '4f1'))
    assert ctl.line_source('4f1', raw) == 'path'


def test_condition_source(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    it = ctl.workbook.by_id['4j']
    it.when, it.condition = 'condition', {'all': [{'field': '4f', 'mentioned': True}]}
    assert ctl.line_source('4j', 'перепел') == 'condition'


def test_undo_event(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    cid = ctl.exclude_case([('4f', '4f1')], 'перепел', ['Перепел'])
    ctl.exclude_undo(cid)
    assert _case(ctl, 'exclude_undo')['case_id'] == cid


def test_exclude_goes_to_telemetry_when_on(ctl, order_xlsx, monkeypatch):
    from orthofill.telemetry import TelemetryConfig
    from telemetry_server import FakeReceiver, cert_pem
    rx = FakeReceiver()
    try:
        cfg = TelemetryConfig(url=rx.url, key='k1', cert=cert_pem())
        monkeypatch.setattr(controller_mod, 'find_telemetry_config', lambda: cfg)
        ctl.import_xlsx(order_xlsx)
        ctl.set_diagnostics(True)
        ctl.telemetry.flush_every = 0.05
        ctl.telemetry._wake.set()
        ctl.exclude_case([('4f', '4f1')], 'перепел', ['Перепел'])
        end = time.monotonic() + 5
        while time.monotonic() < end and not any(e.get('kind') == 'exclude' for e in rx.events):
            time.sleep(0.05)
        assert any(e.get('kind') == 'exclude' for e in rx.events)
        ctl.set_diagnostics(False)
    finally:
        rx.stop()

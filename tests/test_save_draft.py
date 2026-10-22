"""Сохранение черновика: пункты из редактора, эталоны и словарь — из базы
с повтором правок редактора (ничто из главного окна не теряется)."""
import json


def _events(ctl):
    return [json.loads(line) for f in sorted(ctl.diag_dir.glob('diag-*.jsonl'))
            for line in f.read_text(encoding='utf-8').splitlines()]


def test_save_keeps_main_window_writes(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    d = ctl.open_draft()
    d.swap('4d1', '4d2')
    ctl.learn('верхлиг', '4d1')                      # главное окно, пока черновик открыт
    ctl.presets.add_reference(ctl.preset_id, 'запись', [('4a', 'осмотр.')])
    ctl.save_draft()
    wb = ctl.presets.load(ctl.preset_id)
    assert next(e for e in wb.dictionary if e.word == 'верхлиг').code == '4d2'
    assert len(wb.references) == 2
    assert wb.by_id['4d2'].text == 'на верхней челюсти.'


def test_save_replays_composed_code_changes(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.learn('лигверх', '4d1')
    d = ctl.open_draft()
    d.set_code('4d', '4i')
    d.set_code('4i1', '4i4')
    ctl.save_draft()
    assert next(e for e in ctl.workbook.dictionary if e.word == 'лигверх').code == '4i4'
    assert ('4i3', 'на обеих челюстях.') in ctl.workbook.references[0].lines


def test_saved_event_and_dirty(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    ctl.set_diagnostics(True)
    d = ctl.open_draft()
    d.add('4d', '4d3', 'на зубе.', 3)
    d.set_code('4e2', '4e3')
    d.set_text('4a', 'Осмотр.')
    status = ctl.save_draft()
    assert 'сохранён' in status and 'эталоны 1/1' in status
    assert ctl.presets.list()[0].dirty
    ev = [e for e in _events(ctl) if e['event'] == 'preset_saved'][-1]
    assert (ev['added'], ev['deleted'], ev['changed']) == (1, 0, 1)
    assert ev['codes'] == {'4e2': '4e3'}
    assert (ev['refs_ok'], ev['refs_total']) == (1, 1)


def test_draft_after_save_is_clean_and_reused(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    d = ctl.open_draft()
    d.set_text('4a', 'Осмотр.')
    assert ctl.editing_unsaved(ctl.preset_id)
    ctl.save_draft()
    assert d.changed == 0 and not d.ops and not ctl.editing_unsaved(ctl.preset_id)
    assert ctl.open_draft() is d
    assert ctl.workbook.by_id['4a'].text == 'Осмотр.'


def test_save_writes_no_import_row(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    n = ctl.journal._db.execute('SELECT COUNT(*) FROM imports').fetchone()[0]
    ctl.open_draft().set_text('4a', 'Осмотр.')
    ctl.save_draft()
    assert ctl.journal._db.execute('SELECT COUNT(*) FROM imports').fetchone()[0] == n

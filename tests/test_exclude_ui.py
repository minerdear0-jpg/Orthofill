"""0.5 beta 6: «Ошибка → Исключить» из строки протокола (окно)."""
import json
import os
import sys

import pytest

from orthofill.shell import format_path

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


def _out(app):
    return app.out_txt.get('1.0', 'end-1c')


def _line(app, needle):
    i = app.out_txt.search(needle, '1.0', 'end')
    assert i, needle
    return int(i.split('.')[0])


def _cases(app, kind='exclude'):
    out = []
    for p in sorted(app.ctl.diag_dir.glob('*.jsonl')):
        out += [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
    return [e for e in out if e['event'] == 'case' and e.get('kind') == kind]


def _comma(app, raw='лигатурная, перепел'):
    app.raw_txt.insert('1.0', raw)
    app._live_show()
    app.root.update()


@pytest.fixture
def sh(app):
    app.ctl.set_shell_mode(True)
    app.shell_var.set(True)
    app._apply_shell_mode()
    app.raw_txt.insert('1.0', format_path(app.ctl.workbook, ('4', '4b', '4b5')) + '\n'
                       + format_path(app.ctl.workbook, ('4', '4f', '4f1')))
    app._live_show()
    app.root.update()
    return app


def _labels(menu):
    end = menu.index('end')
    return [menu.entrycget(i, 'label') for i in range(end + 1) if menu.type(i) in ('command', 'cascade')]


def test_menu_has_error_submenu(app):
    _comma(app)
    n = _line(app, 'Перепел')
    m = app._protocol_menu(f'{n}.2')
    assert 'Ошибка' in _labels(m)
    sub = app._error_menu
    assert _labels(sub)[0].startswith('Исключить') and 'Другое…' in _labels(sub)
    assert sub.entrycget(0, 'state') == 'normal'


def test_exclude_comma_mode(app):
    clip = []
    app.ctl.clipboard = clip.append
    _comma(app)
    n = _line(app, 'Перепел')
    app._exclude(f'{n}.0', f'{n}.end')
    assert 'Перепел' not in _out(app) and _cases(app)[-1]['excluded'][0]['code'] == '4f1'
    app.generate('ctrl_enter')
    assert 'Перепел' not in clip[-1]


def test_exclude_shell_mode(sh):
    n = _line(sh, 'Перепел')
    sh._exclude(f'{n}.0', f'{n}.end')
    assert 'Перепел' not in _out(sh) and '4f|4f1' in sh.ctl.canvas_edits.removed
    assert _cases(sh)[-1]['excluded'][0]['source'] == 'path'


def test_exclude_partial_selection_whole_lines(sh):
    a, b = _line(sh, 'Смена дуги'), _line(sh, 'Перепел')
    sh._exclude(f'{a}.10', f'{b}.3')
    out = _out(sh)
    assert 'Смена дуги' not in out and 'Перепел' not in out
    codes = [x['code'] for x in _cases(sh)[-1]['excluded']]
    assert '4b5' in codes and '4f1' in codes


def test_exclude_survives_rebuild(sh):
    n = _line(sh, 'Перепел')
    sh._exclude(f'{n}.0', f'{n}.end')
    sh.raw_txt.insert('end', '\n' + format_path(sh.ctl.workbook, ('4', '4g', '4g3')))
    sh._live_show()
    assert 'Перепел' not in _out(sh) and 'третьего' in _out(sh)


def test_undo_exclude(sh):
    n = _line(sh, 'Перепел')
    sh._exclude(f'{n}.0', f'{n}.end')
    assert sh.exclude_bar.winfo_manager()
    sh._undo_exclude()
    assert 'Перепел' in _out(sh) and _cases(sh, 'exclude_undo')
    assert not sh.exclude_bar.winfo_manager()


def test_undo_exclude_comma(app):
    _comma(app)
    before = _out(app)
    n = _line(app, 'Перепел')
    app._exclude(f'{n}.0', f'{n}.end')
    app._undo_exclude()
    assert _out(app) == before


def test_exclude_disabled_on_own_and_skeleton(sh):
    n = _line(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.end', '\nСвоё')
    sh._canvas_capture()
    sh._live_show()
    k = _line(sh, 'Своё')
    assert sh._rows_at(f'{k}.0', f'{k}.end') == []
    r = sh.out_txt.tag_ranges('skeleton_next') or sh.out_txt.tag_ranges('skeleton')
    if r:
        s = int(str(r[0]).split('.')[0])
        assert sh._rows_at(f'{s}.0', f'{s}.end') == []


def test_other_opens_mark_dialog(app, monkeypatch):
    called = []
    monkeypatch.setattr(app, 'mark_case', lambda: called.append(1))
    _comma(app)
    n = _line(app, 'Перепел')
    m = app._protocol_menu(f'{n}.2')
    sub = app._error_menu
    i = _labels(sub).index('Другое…')
    sub.invoke(i)
    assert called


def test_exclude_last_line_comma(app):
    _comma(app)
    before = _out(app)
    last = int(app.out_txt.index('end-1c').split('.')[0])
    text = app.out_txt.get(f'{last}.0', f'{last}.end')
    if not app._rows_at(f'{last}.0', f'{last}.end'):
        pytest.skip('последняя строка — не пункт')
    app._exclude(f'{last}.0', f'{last}.end')
    assert not _out(app).endswith('\n') and text not in _out(app)
    app._undo_exclude()
    assert _out(app) == before

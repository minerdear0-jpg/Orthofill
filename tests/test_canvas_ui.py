"""0.5 beta 3: холст протокола в окне (режим «Оболочка»)."""
import os
import sys

import pytest

from orthofill.shell import format_path

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


@pytest.fixture
def sh(app):
    app.ctl.set_shell_mode(True)
    app._apply_shell_mode()
    app.live_delay = 30
    return app


def _wait(app, ms=120):
    app.root.after(ms)
    app.root.update()


def _note(app, *paths):
    t = app.raw_txt
    t.delete('1.0', 'end')
    t.insert('1.0', '\n'.join(format_path(app.ctl.workbook, p) for p in paths))
    app._live_show()
    app.root.update()


def _out(app):
    return app.out_txt.get('1.0', 'end-1c')


def _line_of(app, needle):
    t = app.out_txt
    idx = t.search(needle, '1.0', 'end')
    assert idx, needle
    return int(idx.split('.')[0])


def test_skeleton_shown(sh):
    _note(sh, ('2', '2b', '2b2'))
    assert sh.out_txt.tag_ranges('skeleton_next')
    assert sh.out_txt.tag_ranges('row')


def test_own_text_survives_new_line(sh):
    _note(sh, ('4', '4b', '4b5'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.end', '\nЖалуется на боль слева')
    sh._canvas_capture()
    _note(sh, ('4', '4b', '4b5'), ('4', '4f', '4f1'))
    out = _out(sh)
    assert 'Жалуется на боль слева' in out and 'Перепел' in out
    n2 = _line_of(sh, 'Жалуется')
    assert 'Смена дуги' in sh.out_txt.get(f'{n2 - 1}.0', f'{n2 - 1}.end')


def test_deleted_row_stays_deleted(sh):
    _note(sh, ('4', '4f', '4f1'))
    n = _line_of(sh, 'Перепел')
    sh.out_txt.delete(f'{n}.0', f'{n + 1}.0')
    sh._canvas_capture()
    _note(sh, ('4', '4f', '4f1'), ('4', '4b', '4b5'))
    assert 'Перепел' not in _out(sh) and 'Смена дуги' in _out(sh)


def test_edited_row_kept(sh):
    _note(sh, ('4', '4b', '4b5'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.end', ' (верхний зуб 1.3 пропущен)')
    sh._canvas_capture()
    _note(sh, ('4', '4b', '4b5'), ('4', '4f', '4f1'))
    assert '(верхний зуб 1.3 пропущен)' in _out(sh)


def test_skeleton_never_copied(sh):
    clip = []
    sh.ctl.clipboard = clip.append
    _note(sh, ('2', '2b', '2b2'))
    n = _line_of(sh, 'лигатурная')
    sh.out_txt.insert(f'{n}.end', '\nСвоё')
    sh._canvas_capture()
    sh._live_show()
    sh.generate('ctrl_enter')
    assert clip and 'Своё' in clip[-1]
    assert not any(line.strip() == '' and len(line) >= 40 for line in clip[-1].split('\n'))
    assert '      ' * 4 not in clip[-1]


def test_typing_into_skeleton_is_own(sh):
    _note(sh, ('2', '2b', '2b2'))
    r = sh.out_txt.tag_ranges('skeleton_next')
    n = int(str(r[0]).split('.')[0])
    sh.out_txt.delete(f'{n}.0', f'{n}.end')
    sh.out_txt.insert(f'{n}.0', 'Этап — уточнить на следующем визите')
    sh._canvas_capture()
    sh._live_show()
    assert 'Этап — уточнить на следующем визите' in _out(sh)


def test_undo_in_canvas(sh):
    _note(sh, ('4', '4b', '4b5'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.end', '\nВременное')
    sh.out_txt.edit_separator()
    sh.out_txt.edit_undo()
    sh._canvas_capture()
    sh._live_show()
    assert 'Временное' not in _out(sh) and not sh.ctl.canvas_edits


def test_no_freeze_bar_in_shell(sh):
    _note(sh, ('4', '4b', '4b5'))
    sh.out_txt.insert('end', '\nСвоё')
    sh.raw_txt.insert('end', '\n')
    sh._schedule_live()
    _wait(sh)
    assert not sh.live_bar.winfo_manager() and not sh.live_frozen
    assert 'Своё' in _out(sh)


def test_highlight_follows_shell_cursor(sh):
    _note(sh, ('2', '2b', '2b2'), ('4', '4b', '4b5'))
    sh.raw_txt.mark_set('insert', '2.3')
    sh._canvas_highlight()
    r = sh.out_txt.tag_ranges('hl')
    assert r and 'Смена дуги' in sh.out_txt.get(r[0], r[1])


def test_new_patient_clears_edits(sh):
    _note(sh, ('4', '4b', '4b5'))
    sh.out_txt.insert('end', '\nСвоё')
    sh._canvas_capture()
    assert sh.ctl.canvas_edits
    sh.raw_txt.delete('1.0', 'end')
    sh._live()
    assert not sh.ctl.canvas_edits


def test_comma_mode_unchanged(app):
    app.live_delay = 30
    app.raw_txt.insert('1.0', 'лигатурная')
    app._live_show()
    app.out_txt.insert('end', '\nправка')
    app.raw_txt.insert('end', ', перепел')
    app._schedule_live()
    _wait(app)
    assert app.live_frozen and app.live_bar.winfo_manager()
    assert not app.out_txt.tag_ranges('skeleton') and not app.out_txt.tag_ranges('skeleton_next')

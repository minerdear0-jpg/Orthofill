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


def test_note_confirm_canvas_counts(sh, monkeypatch):
    seen = []
    monkeypatch.setattr(sh.ctl, 'track', lambda e, **d: seen.append((e, d)))
    _note(sh, ('4', '4b', '4b5'), ('4', '4f', '4f1'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.end', '\nДвадцать символов!!!')   # 20 символов
    m = _line_of(sh, 'Перепел')
    sh.out_txt.insert(f'{m}.end', ' — по 2 часа')
    k = _line_of(sh, 'фотопротокол')
    sh.out_txt.delete(f'{k}.0', f'{k + 1}.0')
    sh.generate('ctrl_enter')
    d = [d for e, d in seen if e == 'note_confirm'][-1]
    assert d['own_chars'] == 20 and d['replaced'] == 1 and d['removed'] == 1
    assert 'Двадцать' not in repr(seen)


# ---------- итоговая проверка 0.5b3 ----------
def test_split_row_with_enter_loses_nothing(sh):
    _note(sh, ('4', '4b', '4b5'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.5', '\n')
    sh._canvas_capture()
    _note(sh, ('4', '4b', '4b5'), ('4', '4f', '4f1'))
    out = _out(sh)
    assert 'Смена\n' in out and ' дуги на верхней' in out


def test_paste_multiline_mid_row(sh):
    _note(sh, ('4', '4b', '4b5'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.3', 'AAA\nBBB\nCCC')
    sh._canvas_capture()
    sh._live_show()
    out = _out(sh)
    assert 'СмеAAA' in out and 'BBB' in out and 'CCCна дуги' in out


def test_sibling_edit_not_copied(sh):
    _note(sh, ('4', '4f', '4f1'), ('4', '4f', '4f2'))
    n = _line_of(sh, 'Перепел')
    sh.out_txt.insert(f'{n}.end', ' XX')
    sh._canvas_capture()
    sh._live_show()
    out = _out(sh)
    assert out.count('XX') == 1 and 'Лиса' in out


def test_undo_delete_before_rebuild(sh):
    _note(sh, ('4', '4f', '4f1'))
    t = sh.out_txt
    n = _line_of(sh, 'Перепел')
    t.edit_separator()
    t.delete(f'{n}.0', f'{n + 1}.0')
    t.edit_separator()
    t.edit_undo()
    sh._canvas_capture()
    _note(sh, ('4', '4f', '4f2'))
    out = _out(sh)
    assert 'Лиса' in out and 'Перепел' not in out and not sh.ctl.canvas_edits


def test_typing_at_row_start_follows_warning(sh):
    _note(sh, ('4', '4b', '4b5'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.0', '! ')
    sh._canvas_capture()
    sh._live_show()
    assert '! Смена дуги' in _out(sh)


def test_removed_row_returns_after_retyping_line(sh):
    _note(sh, ('4', '4f', '4f1'))
    n = _line_of(sh, 'Перепел')
    sh.out_txt.delete(f'{n}.0', f'{n + 1}.0')
    sh._canvas_capture()
    _note(sh, ('4', '4b', '4b5'))                       # строку эластиков стёрли
    _note(sh, ('4', '4b', '4b5'), ('4', '4f', '4f1'))   # и написали снова
    assert 'Перепел' in _out(sh)


def test_next_patient_select_all_clears(sh):
    _note(sh, ('4', '4b', '4b5'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.end', '\nЖалуется на боль слева')
    sh._canvas_capture()
    sh.generate('ctrl_enter')
    t = sh.raw_txt
    t.tag_add('sel', '1.0', 'end-1c')
    t.delete('sel.first', 'sel.last')
    t.insert('1.0', format_path(sh.ctl.workbook, ('4', '4f', '4f1')))
    sh.root.update()
    sh._live()
    assert 'Жалуется' not in _out(sh) and not sh.ctl.canvas_edits


def test_skeleton_not_seen_as_hand_edit(sh):
    _note(sh, ('2', '2b', '2b2'))
    assert not sh.ctl.needs_confirm_regenerate(sh._protocol_text())


def test_preset_switch_clears_edits(sh):
    _note(sh, ('4', '4b', '4b5'))
    sh.out_txt.insert('end', '\nСвоё')
    sh._canvas_capture()
    other = next(p.id for p in sh.ctl.presets.list() if p.id != sh.ctl.preset_id)
    sh.switch_to(other)
    assert not sh.ctl.canvas_edits


def test_rebuild_without_capture_keeps_own(sh):
    _note(sh, ('4', '4b', '4b5'))
    n = _line_of(sh, 'Смена дуги')
    sh.out_txt.insert(f'{n}.end', '\nСвоё после импорта')
    sh._show_protocol(sh.ctl.preview(sh.raw_txt.get('1.0', 'end-1c')).rows)   # путь без захвата
    assert 'Своё после импорта' in _out(sh)


def test_own_text_without_rows_kept(sh, monkeypatch):
    import orthofill.ui as uim
    _note(sh, ('4', '4b', '4b5'))
    monkeypatch.setattr(sh.ctl, 'preview', lambda raw, tokens=(): type(
        'R', (), {'rows': [], 'status': '', 'warnings': [], 'defaults_line': '', 'text': ''})())
    sh._live_show()
    sh.out_txt.insert('1.0', 'Своё без строк')
    sh._canvas_capture()
    sh._live_show()
    assert 'Своё без строк' in _out(sh)


def test_shift_tab_never_leaves_field(sh):
    assert sh.shell_box._shift_tab() == 'break'

"""Окно редактора пресета — на настоящем Tk (нужен дисплей)."""
import os
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
    reason="нужен дисплей")


def test_open_on_item_and_search(app):
    ed = app.open_editor('4d2')
    assert ed.tree.selection() == ('4d2',)
    assert ed.tree.item('4d', 'open')
    ed.search.insert(0, '18х25 верх')
    ed._on_search()
    assert ed.tree.selection()[0].startswith('4b')


def test_search_next_hit(app):
    ed = app.open_editor()
    ed.search.insert(0, 'на верхней')
    ed._on_search()
    first = ed.tree.selection()[0]
    ed._next_hit()
    assert ed.tree.selection()[0] != first


def test_codes_and_live_check(app):
    ed = app.open_editor('4d')
    assert ed.tree.set('4d1', 'code') == '4d1'
    assert ed.status_lbl['text'].startswith('эталоны 1/1')
    ed.select('4a')
    ed.delete_selected(confirm=False)
    assert ed.status_lbl['text'].startswith('эталоны 0/1')      # сама, без кнопки
    assert not ed.tree.exists('4a')


def test_add_variant_and_rename(app):
    ed = app.open_editor('4d3')
    ed.add_variant()
    code = ed.tree.selection()[0]
    assert code == '4d4'
    ed.set_text_field('на зубе.')
    ed.commit_text()
    assert ed.draft.wb.by_id['4d4'].text == 'на зубе.'
    assert 'Изменено: 2' in ed.changed_lbl['text']
    assert 'на зубе.' in ed.tree.item('4d4', 'text')


def test_add_item_to_section(app):
    ed = app.open_editor('4a')
    ed.add_item()
    assert ed.tree.selection() == ('4i',)


def test_code_conflict_offers_swap(app, monkeypatch):
    ed = app.open_editor('4d1')
    monkeypatch.setattr(app, '_choice', lambda *a, **k: 'swap')
    ed.set_code_field('4d2')
    ed.commit_code()
    assert ed.draft.wb.by_id['4d2'].text == 'на верхней челюсти.'
    assert ed.tree.selection() == ('4d2',)


def test_code_error_shown(app):
    ed = app.open_editor('4d1')
    ed.set_code_field('4x1')
    ed.commit_code()
    assert 'нет группы' in ed.code_err['text']
    assert '4d1' in ed.draft.wb.by_id


def test_group_props(app):
    ed = app.open_editor('3f')
    assert ed.method_var.get() == 'норма / не норма (гигиена)'
    ed.default_var.set('Гигиена полости рта неудовлетворительная.')
    ed._on_default()
    assert ed.draft.wb.by_id['3f'].default == '3f2'


def test_undo_in_window(app):
    ed = app.open_editor('4a')
    ed.set_text_field('Осмотр.')
    ed.commit_text()
    ed.undo()
    assert ed.draft.wb.by_id['4a'].text == 'осмотр.'
    assert ed.text_field() == 'осмотр.'


def test_one_editor_window(app):
    assert app.open_editor('4a') is app.open_editor('4d1')


def test_default_label_depends_on_rule(app):
    ed = app.open_editor('3f')                     # гигиена: правило само решает
    assert ed.default_var.get() == '— как решит правило —'
    ed.select('4f')                                # эластики: по словам
    ed.method_var.set('по словам записи'); ed._on_method()
    assert ed.default_var.get().startswith('— не выводить')


# ---------- Task 6: эталоны, слова, проверка, сохранение ----------
def test_check_shows_broken_reference(app):
    ed = app.open_editor('4a')
    ed.delete_selected(confirm=False)
    assert ed.notebook.tab(ed.refs_page, 'text') == 'Эталоны (1)'
    first = ed.refs_tab.get_children()[0]
    assert ed.refs_tab.item(first, 'text').startswith('✗')
    kids = [ed.refs_tab.item(k, 'text') for k in ed.refs_tab.get_children(first)]
    assert any('нет: осмотр.' in k for k in kids)


def test_accept_reference_from_tab(app):
    ed = app.open_editor('4a')
    ed.delete_selected(confirm=False)
    ed.refs_tab.selection_set(ed.refs_tab.get_children()[0])
    ed.accept_reference()
    assert ed.refs_tab.item(ed.refs_tab.get_children()[0], 'text').startswith('✓')


def test_save_asks_when_references_broken(app, monkeypatch):
    asked = []
    monkeypatch.setattr(app, '_choice', lambda t, text, b: asked.append(text) or 'cancel')
    ed = app.open_editor('4a')
    ed.delete_selected(confirm=False)
    ed.save()
    assert asked and 'Сломано эталонов: 1 из 1' in asked[0]
    assert ed.draft.changed                          # не сохранено


def test_close_with_unsaved_asks(app, monkeypatch):
    monkeypatch.setattr(app, '_choice', lambda *a, **k: 'cancel')
    ed = app.open_editor('4d3')
    ed.add_variant()
    ed.close()
    assert ed.top.winfo_exists()


def test_close_discard(app, monkeypatch):
    monkeypatch.setattr(app, '_choice', lambda *a, **k: 'discard')
    ed = app.open_editor('4d3')
    ed.add_variant()
    ed.close()
    assert not ed.top.winfo_exists()
    assert '4d4' not in app.ctl.workbook.by_id
    assert app.open_editor('4d3').draft.changed == 0


def test_lint_tab_swaps_jaws(app_with_p):
    ed = app_with_p.open_editor()
    assert ed.notebook.tab(ed.lint_page, 'text') == 'Проверка (1)'
    ed.fix_finding(next(f for f in ed.findings if f.kind == 'jaw_order'))
    assert ed.draft.wb.by_id['4p1'].text == 'на верхней челюсти.'
    assert ed.notebook.tab(ed.lint_page, 'text') == 'Проверка (0)'


def test_words_tab_delete(app):
    app.ctl.learn('осм', '4a')
    ed = app.open_editor('4a')
    assert ed.notebook.tab(ed.words_page, 'text') == 'Слова врача (1)'
    ed.words_tab.selection_set(ed.words_tab.get_children()[0])
    ed.delete_word()
    assert ed.notebook.tab(ed.words_page, 'text') == 'Слова врача (0)'


def test_saved_preset_rebuilds_protocol_without_copy(app, monkeypatch):
    copied = []
    app.raw_txt.insert('1.0', 'активация, рабочий')
    app.generate()
    monkeypatch.setattr(app.ctl, 'clipboard', copied.append)
    ed = app.open_editor('4a')
    ed.set_text_field('Осмотр полости рта.')
    ed.commit_text()
    ed.save()
    assert 'Осмотр полости рта.' in app.out_txt.get('1.0', 'end')
    assert not copied
    assert 'сохранён' in app.status_lbl['text']
    assert ed.draft.changed == 0 and ed.changed_lbl['text'] == ''


def test_import_in_editor_is_undoable(app, order_xlsx_with):
    wb2 = order_xlsx_with(('4d4', 'на зубе.'))
    ed = app.open_editor('4d')
    ed.import_path(wb2.path)
    assert ed.tree.exists('4d4')
    ed.undo()
    assert not ed.tree.exists('4d4')


def test_export_asks_to_save_first(app, monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(app, '_choice', lambda t, text, b: asked.append(text) or 'cancel')
    ed = app.open_editor('4a')
    ed.set_text_field('Осмотр.')
    ed.commit_text()
    ed.export_path(tmp_path / 'x.xlsx')
    assert asked and 'Сначала сохранить' in asked[0] and not (tmp_path / 'x.xlsx').exists()


def test_ctrl_o_in_editor_does_not_import(app, monkeypatch):
    called = []
    monkeypatch.setattr(app, 'import_xlsx', lambda: called.append(1))
    ed = app.open_editor('4a')

    class E:
        keysym, keycode, state, widget = 'Cyrillic_shcha', 32, 4, ed.tree
    app._on_ctrl_key(E())
    assert not called


# ---------- итоговая проверка ----------
def _shown(ed):
    """Окно редактора на экране, разделитель встал, поля справа пересобраны."""
    ed.top.deiconify()
    if not ed.tree.winfo_viewable():
        ed.tree.wait_visibility()
    ed.top.after(300)
    ed.top.update()


def _click(ed, code):
    """Настоящий щелчок мышью по строке дерева (окно должно быть на экране)."""
    _shown(ed)
    ed.tree.see(code)
    ed.top.update()
    x, y, w, h = ed.tree.bbox(code)
    ed.tree.event_generate('<ButtonPress-1>', x=x + w // 2, y=y + h // 2)
    ed.tree.event_generate('<ButtonRelease-1>', x=x + w // 2, y=y + h // 2)
    ed.top.update()


def test_focus_out_commits_to_edited_item(app):
    ed = app.open_editor('4d1')
    _shown(ed)
    ed.text_box.focus_force(); ed.top.update()
    ed.set_text_field('ПРАВКА')
    _click(ed, '4d2')
    assert ed.draft.wb.by_id['4d1'].text == 'ПРАВКА'
    assert ed.draft.wb.by_id['4d2'].text == 'на нижней челюсти.'


def test_code_focus_out_commits_to_edited_item(app):
    ed = app.open_editor('4d1')
    _shown(ed)
    ed.code_entry.focus_force(); ed.top.update()
    ed.set_code_field('4d9')
    _click(ed, '4d3')
    assert '4d9' in ed.draft.wb.by_id and ed.draft.wb.by_id['4d9'].text == 'на верхней челюсти.'
    assert '4d3' in ed.draft.wb.by_id


def test_close_commits_typed_text_and_asks(app, monkeypatch):
    asked = []
    monkeypatch.setattr(app, '_choice', lambda t, text, b: asked.append(text) or 'cancel')
    ed = app.open_editor('4a')
    ed.set_text_field('Осмотр.')                 # набрано, но не подтверждено
    ed.close()
    assert asked and ed.top.winfo_exists()


def test_editor_follows_current_preset(app):
    ed = app.open_editor('4a')
    other = next(p.id for p in app.ctl.presets.list() if p.id != app.ctl.preset_id)
    app.switch_to(other)
    ed2 = app.open_editor('4a')
    assert ed2.draft.preset_id == other


def test_editor_with_unsaved_other_preset_is_not_reused(app, monkeypatch):
    asked = []
    monkeypatch.setattr(app, '_choice', lambda t, text, b: asked.append(text) or 'cancel')
    ed = app.open_editor('4d3')
    ed.add_variant()
    first = ed.draft.preset_id
    other = next(p.id for p in app.ctl.presets.list() if p.id != first)
    app.switch_to(other)
    ed2 = app.open_editor('4a')
    assert asked and 'несохранённ' in asked[0]
    assert ed2.draft.preset_id == first and ed2.draft.changed


def test_save_keeps_hand_edited_protocol(app):
    app.raw_txt.insert('1.0', 'активация, рабочий')
    app.generate()
    app.out_txt.insert('end', '\nмоя строка')
    ed = app.open_editor('5a')
    ed.set_text_field('Продолжить лечение.')
    ed.commit_text()
    ed.save()
    assert 'моя строка' in app.out_txt.get('1.0', 'end')
    assert 'Ctrl+Enter' in app.status_lbl['text']


def test_main_close_asks_about_unsaved_editor(app, monkeypatch):
    monkeypatch.setattr(app, '_choice', lambda *a, **k: 'cancel')
    ed = app.open_editor('4d3')
    ed.add_variant()
    app.close()
    assert app.root.winfo_exists() and ed.top.winfo_exists()


# ---------- 0.2 beta 5: логика ----------
def test_logic_column_and_filter(app):
    ed = app.open_editor('4h1')
    assert ed.tree.set('4h1', 'logic') == 'если'          # угаданное условие
    ed.logic_only.set(True)
    ed.refresh()
    assert ed.tree.exists('4h1') and ed.tree.exists('4') and not ed.tree.exists('4a')
    ed.logic_only.set(False)
    ed.refresh()
    assert ed.tree.exists('4a')


def test_edit_condition_rows(app):
    ed = app.open_editor('4a')
    ed.when_var.set('по условию')
    ed._on_when()
    ed.add_cond_row()
    ed.cond_rows[0].field_var.set('2b  Тип системы')
    ed._on_cond_field(0)
    assert '= лигатурная' in ed.cond_rows[0].value_cb['values']
    ed.cond_rows[0].value_var.set('= лигатурная')
    ed.apply_condition()
    assert ed.draft.wb.by_id['4a'].condition == {'all': [{'field': '2b', 'is': '2b2'}]}
    assert ed.tree.set('4a', 'logic') == 'если' and '2b = 2b2' in ed.xlsx_lbl['text']
    ed.cond_rows[0].not_var.set(True)
    ed.apply_condition()
    assert ed.draft.wb.by_id['4a'].condition == {'all': [{'field': '2b', 'is': '2b2', 'not': True}]}
    ed.remove_cond_row(0)
    assert ed.draft.wb.by_id['4a'].condition is None


def test_complex_condition_is_read_only(app):
    ed = app.open_editor('4a')
    ed.draft.set_condition('4a', {'all': [{'any': [{'field': '2b', 'is': '2b1'},
                                                   {'field': '2b', 'is': '2b2'}]},
                                          {'field': '4j', 'mentioned': True}]})
    ed.refresh()
    ed.select('4a')
    assert not ed.cond_rows and 'правится в xlsx' in ed.cond_note['text']


def test_pairs(app):
    ed = app.open_editor('4h1')
    ed.add_pair('4h2')
    assert ('4h1', '4h2') in ed.draft.wb.not_together and ed.tree.set('4h2', 'logic').endswith('≠')
    assert ed.pairs_list == ['4h2'] and '4h2' in ed.xlsx_lbl['text']
    ed.remove_pair('4h2')
    assert not ed.draft.wb.not_together and ed.pairs_list == []


def test_combine(app):
    ed = app.open_editor('4f')
    ed.combine_var.set('И — все упомянутые варианты')
    ed._on_combine()
    assert ed.draft.wb.by_id['4f'].combine == 'and' and ed.tree.set('4f', 'logic') == 'И'


def test_broken_condition_shown(app, monkeypatch):
    asked = []
    monkeypatch.setattr(app, '_choice', lambda t, text, b: asked.append(text) or 'delete')
    ed = app.open_editor('4a')
    ed.draft.set_condition('4a', {'all': [{'field': '4e', 'mentioned': True}]})
    ed.refresh()
    ed.select('4e')
    ed.delete_selected()
    assert any('ссылаются условия: 4a' in a for a in asked)
    ed.select('4a')
    assert ed.tree.set('4a', 'logic').startswith('⚠')
    assert any('пункта нет' in r.field_var.get() for r in ed.cond_rows)


def test_reference_counter_for_item(app):
    ed = app.open_editor('4a')
    assert ed.refs_lbl['text'] == 'по эталонам: выводится в 1, ожидается в 1'
    ed.when_var.set('по условию')
    ed._on_when()                                      # условия нет → не выводится
    assert ed.refs_lbl['text'] == 'по эталонам: выводится в 0, ожидается в 1'


def test_props_scroll_in_narrow(app):
    ed = app.open_editor('4h1')
    ed.top.geometry('560x700')
    _shown(ed)
    ed.select('4h1')
    ed.top.update()
    assert ed.props_canvas.bbox('all')[3] > ed.props_canvas.winfo_height()

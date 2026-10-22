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

"""Черновик пресета: команды, отмена, закрепление угаданного, журнал операций."""
import pytest
from conftest import ORDER

from orthofill import engine
from orthofill.draft import Draft
from orthofill.workbook import DictEntry, ReferenceCase, load_workbook_file


@pytest.fixture
def d():
    return Draft(load_workbook_file(ORDER), 1)


def test_draft_is_a_copy():
    wb = load_workbook_file(ORDER)
    d = Draft(wb, 1)
    d.set_text('4a', 'Другое.')
    assert wb.by_id['4a'].text == 'осмотр.'


def test_undo_redo(d):
    code = d.add('4d', '4d3', 'на зубе.', 3)
    assert code == '4d4' and d.can_undo and d.changed == 1
    assert [c.id for c in d.wb.by_id['4d'].children][-1] == '4d4'
    d.undo()
    assert '4d4' not in d.wb.by_id and d.can_redo and d.changed == 0
    d.redo()
    assert '4d4' in d.wb.by_id


def test_new_command_clears_redo(d):
    d.add('4d', '4d3', 'на зубе.', 3)
    d.undo()
    d.set_text('4a', 'Осмотр.')
    assert not d.can_redo


def test_undo_drops_op_from_log(d):
    d.swap('4d1', '4d2')
    d.renumber('4b')                          # уже по порядку — операции нет
    d.swap('4b1', '4b2')
    d.swap('4e1', '4e2')
    d.undo()
    assert [o[0] for o in d.ops] == ['codes', 'codes']
    assert d.ops[0][1] == {'4d1': '4d2', '4d2': '4d1'}


def test_rename_freezes_guessed_method(d):
    g = d.wb.by_id['3f']
    before = engine.rule_kind(g)
    assert g.method is None and before == 'hygiene'
    d.set_text('3f', 'Чистота полости рта:')
    assert d.wb.by_id['3f'].method == 'hygiene'
    assert engine.rule_kind(d.wb.by_id['3f']) == 'hygiene'


def test_rename_freezes_guessed_when(d):
    when = engine._effective_when(d.wb)['4a']
    d.set_text('4a', 'Осмотр полости рта.')
    assert d.wb.by_id['4a'].when == when


def test_rename_rewrites_reference_lines_and_words(d):
    d.wb.dictionary.append(DictEntry('осм', 'осмотр.', '4a'))
    d.set_text('4a', 'Осмотр полости рта.')
    assert ('4a', 'Осмотр полости рта.') in d.wb.references[0].lines
    assert d.wb.dictionary[-1].item_text == 'Осмотр полости рта.'
    assert d.check()[0].ok


def test_delete_item_breaks_reference_visibly(d):
    d.wb.dictionary.append(DictEntry('осм', 'осмотр.', '4a'))
    assert d.impact('4a') == (1, 1)
    d.delete('4a')
    assert '4a' not in d.wb.by_id and not d.wb.dictionary
    r = d.check()[0]
    assert not r.ok and r.missing == [('4a', 'осмотр.')]


def test_delete_group_with_variants(d):
    d.wb.by_id['4k'].default = '4k1'
    d.delete('4k')
    assert not any(c.startswith('4k') for c in d.wb.by_id)
    assert d.impact('4d') == (1, 0)


def test_move_keeps_codes(d):
    assert d.move('4d2', -1)
    assert [c.id for c in d.wb.by_id['4d'].children] == ['4d2', '4d1', '4d3']
    items = [it.id for it in d.wb.items]
    assert items.index('4d2') < items.index('4d1')
    assert not d.move('4d2', -1)              # уже первый


def test_move_group_moves_its_variants(d):
    assert d.move('4e', -1)
    items = [it.id for it in d.wb.items]
    assert items.index('4e2') < items.index('4d')


def test_set_code_error_and_move(d):
    assert 'уже занят' in d.set_code('4e2', '4d1')
    assert d.set_code('4e2', '4d4') is None
    assert d.wb.by_id['4d4'].parent == '4d'


def test_set_prop(d):
    d.set_prop('4k', 'default', '4k2')
    d.set_prop('4a', 'words', ['осм'])
    assert d.wb.by_id['4k'].default == '4k2' and d.wb.by_id['4a'].words == ['осм']


def test_accept_and_delete_reference(d):
    d.delete('4a')
    d.accept_reference('1')
    assert d.check()[0].ok
    d.delete_reference('1')
    assert not d.wb.references


def test_import_replaces(d, order_xlsx_with):
    wb2 = order_xlsx_with(('4d4', 'на зубе.'))
    d.import_wb(wb2)
    assert '4d4' in d.wb.by_id and d.ops[-1][0] == 'import'


def test_replay_on_base(d):
    d.swap('4d1', '4d2')
    refs, words = d.replay([ReferenceCase('9', 'x', [('4d1', 'на верхней челюсти.')])],
                           [DictEntry('верх', 'на верхней челюсти.', '4d1')])
    assert refs[0].lines == [('4d2', 'на верхней челюсти.')] and words[0].code == '4d2'


def test_replay_composed_and_text(d):
    d.set_code('4d', '4i')
    d.set_code('4i1', '4i4')
    d.set_text('4i4', 'на верхней.')
    refs, words = d.replay([ReferenceCase('9', 'x', [('4d1', 'на верхней челюсти.')])],
                           [DictEntry('верх', 'на верхней челюсти.', '4d1'),
                            DictEntry('низ', 'на нижней челюсти.', '4d2')])
    assert refs[0].lines == [('4i4', 'на верхней.')]
    assert [(w.code, w.item_text) for w in words] == [('4i4', 'на верхней.'),
                                                       ('4i2', 'на нижней челюсти.')]


def test_replay_deletes(d):
    d.delete('4a')
    d.delete_word('осм')
    d.delete_reference('9')
    refs, words = d.replay([ReferenceCase('9', 'x', []), ReferenceCase('10', 'y', [])],
                           [DictEntry('осм', 'x', '3a'), DictEntry('о', 'осмотр.', '4a'),
                            DictEntry('гиг', 'y', '3f1')])
    assert [r.case_id for r in refs] == ['10'] and [w.word for w in words] == ['гиг']

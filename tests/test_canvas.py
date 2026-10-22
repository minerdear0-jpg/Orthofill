"""0.5 beta 3: модель холста — свой текст, замены, удаления, скелет."""
from orthofill.canvas import Edits, OwnLine, PLACEHOLDER, capture, compose, confirm_text
from orthofill.render import Row

ORDER = {c: i for i, c in enumerate(['2', '2b', '2b2', '2c', '2c2', '3', '3f', '3f1', '3k',
                                     '4', '4a', '4b', '4b5', '4f', '4f1', '4j'])}
SECTION = {c: c[0] for c in ORDER}


def rows(*keys):
    out = []
    for k in keys:
        out.append(Row(f'текст {k}', (k,), section=len(k) == 1))
    return out


def texts(lines):
    return [(l.kind, l.text) for l in lines]


def test_compose_rows_only():
    lines, warn = compose(rows('4', '4b', '4f'), Edits(), [], ORDER, SECTION)
    assert [l.code for l in lines] == ['4', '4b', '4f'] and all(l.kind == 'row' for l in lines)
    assert not warn


def test_own_follows_anchor():
    e = Edits([OwnLine('4b', 'Жалуется на боль слева')])
    lines, _ = compose(rows('4', '4a', '4b', '4f'), e, [], ORDER, SECTION)
    i = [l.code for l in lines].index('4b')
    assert lines[i + 1].kind == 'own' and lines[i + 1].text == 'Жалуется на боль слева'
    assert lines[i + 2].code == '4f'


def test_own_at_top():
    lines, _ = compose(rows('4', '4b'), Edits([OwnLine(None, 'Сверху')]), [], ORDER, SECTION)
    assert lines[0].kind == 'own' and lines[0].text == 'Сверху'


def test_replaced_row():
    e = Edits([OwnLine('4f', 'Эластики Перепел — по 2 часа', replaces=True)])
    lines, _ = compose(rows('4', '4b', '4f'), e, [], ORDER, SECTION)
    assert texts(lines)[2] == ('own', 'Эластики Перепел — по 2 часа') and lines[2].code == '4f'
    assert len(lines) == 3


def test_removed_stays_removed():
    lines, _ = compose(rows('4', '4b', '4j'), Edits(removed={'4j'}), [], ORDER, SECTION)
    assert '4j' not in [l.code for l in lines]


def test_anchor_gone_moves_to_section_end():
    e = Edits([OwnLine('4b', 'Своё')])
    lines, warn = compose(rows('3', '3f', '4', '4a', '4f'), e, [], ORDER, SECTION)
    assert lines[-1].text == 'Своё' and warn and 'проверьте' in warn[0]


def test_skeleton_positions():
    lines, _ = compose(rows('3', '3k', '4', '4b'), Edits(), [('3f', False), ('4f', True)],
                       ORDER, SECTION)
    kinds = [(l.kind, l.code) for l in lines]
    assert kinds == [('row', '3'), ('skeleton', '3f'), ('row', '3k'), ('row', '4'), ('row', '4b'),
                     ('skeleton_next', '4f')]


def test_skeleton_after_own_of_previous_row():
    e = Edits([OwnLine('4b', 'Своё')])
    lines, _ = compose(rows('4', '4b'), e, [('4f', True)], ORDER, SECTION)
    assert [l.kind for l in lines] == ['row', 'row', 'own', 'skeleton_next']


def _field(lines):
    """Как поле окна видит холст: (текст, код собранной строки, её исходный текст)."""
    out = []
    for l in lines:
        if l.kind in ('skeleton', 'skeleton_next'):
            out.append((l.text, None, PLACEHOLDER))
        elif l.kind == 'row' or l.replaces:
            out.append((l.text, l.code, l.row.text if l.row else None))
        else:
            out.append((l.text, None, None))
    return out


def test_capture_roundtrip():
    e = Edits([OwnLine('4b', 'Своё'), OwnLine('4f', 'Замена', replaces=True)], {'4j'})
    lines, _ = compose(rows('4', '4b', '4f'), e, [('3f', False)], ORDER, SECTION)
    shown = [l.code for l in lines if l.kind == 'row' or l.replaces]
    assert capture(_field(lines), shown, {'4j'}) == e


def test_capture_edit_and_insert():
    lines, _ = compose(rows('4', '4b', '4f'), Edits(), [], ORDER, SECTION)
    f = _field(lines)
    f[1] = ('текст 4b — изменено', '4b', 'текст 4b')
    f.insert(2, ('Своя строка', None, None))
    f.insert(0, ('Самая первая', None, None))
    e = capture(f, ['4', '4b', '4f'])
    assert OwnLine('4b', 'текст 4b — изменено', True) in e.own
    assert OwnLine('4b', 'Своя строка') in e.own and OwnLine(None, 'Самая первая') in e.own


def test_capture_removed():
    lines, _ = compose(rows('4', '4b', '4j'), Edits(), [], ORDER, SECTION)
    f = [x for x in _field(lines) if x[1] != '4j']
    assert capture(f, ['4', '4b', '4j']).removed == {'4j'}


def test_capture_typing_into_skeleton():
    lines, _ = compose(rows('4', '4b'), Edits(), [('4f', True)], ORDER, SECTION)
    f = _field(lines)
    f[-1] = ('Своё вместо скелета', None, PLACEHOLDER)
    assert capture(f, ['4', '4b']).own == [OwnLine('4b', 'Своё вместо скелета')]


def test_confirm_text_without_skeleton():
    e = Edits([OwnLine('4b', 'Своё')])
    lines, _ = compose(rows('4', '4b'), e, [('4f', True)], ORDER, SECTION)
    assert confirm_text(lines) == 'текст 4\nтекст 4b\nСвоё'

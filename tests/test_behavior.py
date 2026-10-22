from orthofill.behavior import NoteStats


def test_empty():
    assert NoteStats().summary() == {}


def test_counts_and_pauses():
    s = NoteStats()
    s.key('char', 10.0)
    s.key('char', 10.2)
    s.key('backspace', 10.4)
    s.key('char', 13.0)          # пауза 2,6 с
    s.key('paste', 13.1)
    out = s.summary(now=14.0)
    assert out == {'ms': 4000, 'keys': 5, 'chars': 2 + 1, 'backspaces': 1, 'deletes': 0,
                   'pastes': 1, 'pauses_2s': 1}


def test_reset():
    s = NoteStats()
    s.key('char', 1.0)
    s.reset()
    assert s.summary() == {} and not s.started

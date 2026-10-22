"""0.5 beta 7: отличающаяся часть вариантов карусели (без Tk)."""
from orthofill.distinct import diff_spans, distinct_labels

E1 = 'Слизистая оболочка губ, щёк, твёрдого и мягкого нёба, языка бледно-розовая, влажная, без видимых патологических изменений.'
E2 = 'Слизистая оболочка губ, щёк, твёрдого и мягкого нёба, языка бледно-розовая, влажная, в области выхода дуги - эрозия.'


def test_labels():
    assert distinct_labels([E1, E2]) == ['…без видимых патологических изменений.',
                                         '…в области выхода дуги - эрозия.']
    assert distinct_labels(['Перепел', 'Лиса', 'Медведь']) == ['Перепел', 'Лиса', 'Медведь']


def test_labels_short_common_kept():
    # общее начало короче 20 символов — как есть
    assert distinct_labels(['на верхней челюсти.', 'на нижней челюсти.']) == \
        ['на верхней челюсти.', 'на нижней челюсти.']


def test_labels_cut_at_word():
    a, b = 'Соотношение моляров справа по I классу', 'Соотношение моляров справа по II классу.'
    assert distinct_labels([a, b]) == ['…I классу', '…II классу.']


def test_labels_single_and_whitespace():
    assert distinct_labels([E1]) == [E1]
    assert distinct_labels([]) == []
    assert distinct_labels(['  ' + E1, E2]) == ['…без видимых патологических изменений.',
                                                '…в области выхода дуги - эрозия.']


def test_labels_one_is_prefix_of_other():
    a = 'Гигиена полости рта удовлетворительная'
    assert distinct_labels([a, a + ' в целом.']) == [a, a + ' в целом.']


def test_diff_spans():
    spans = diff_spans(E2, E1)
    assert [E2[s:e] for s, e in spans] == ['в области выхода дуги - эрозия.']
    assert diff_spans(E1, E1) == []
    s = diff_spans('удовлетворительное.', 'неудовлетворительно.')
    assert [('удовлетворительное.'[a:b]) for a, b in s] == ['удовлетворительное.']

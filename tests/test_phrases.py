"""0.3 beta 3: шаблоны фраз и поиск привычных форм."""
from orthofill.phrases import field_spans, parse_template, propose, render, shape_of
from orthofill.workbook import Phrase

TPL = 'замена дуги {верх|низ|обе} {18х25|16х25} тма'
NOTES = (['активация, замена дуги верх 18х25 тма, перепел'] * 1 +
         ['активация, замена дуги верх 18х25 тма'] +
         ['лигатурная, замена дуги низ 16х25 тма'] +
         ['активация, замена дуги верх 16х25 тма, явка 6 нед'] +
         ['рабочий, замена дуги верх 18х25 тма'] +
         ['активация, замена дуги низ 18х25 тма'])


def test_render_and_spans():
    parts = parse_template(TPL)
    assert render(parts) == 'замена дуги верх 18х25 тма'
    assert render(parts, ['низ', None]) == 'замена дуги низ 18х25 тма'
    assert field_spans(parts, ['низ', '16х25']) == [(12, 15), (16, 21)]


def test_propose_from_history():
    found = propose(NOTES, [])
    assert found[0][:2] == ('замена', 'замена дуги {верх|низ} {18х25|16х25} тма')
    assert found[0][2] == 6


def test_no_variation_no_proposal():
    assert propose(['активация, перепел'] * 6, []) == []


def test_needs_five():
    assert propose(NOTES[:4], []) == []


def test_existing_phrase_not_proposed_again():
    assert propose(NOTES, [Phrase('замена', TPL)]) == []


def test_name_taken_gets_number():
    found = propose(NOTES, [Phrase('замена', 'замена лигатур {верх|низ}')])
    assert found[0][0] == 'замена2'


def test_shape_of():
    assert shape_of('замена дуги верх 18х25 тма') == shape_of('замена дуги низ 16х25 тма')
    assert shape_of('замена дуги верх 18х25 тма') == shape_of(TPL)


def test_controller_proposal_and_hints(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    for raw in NOTES:
        ctl.generate(raw)
    prop = ctl.proposal(NOTES[-1])
    assert prop and prop[0] == 'замена'
    ctl.accept_proposal(prop)
    assert ctl.workbook.phrases[0].name == 'замена'
    assert ctl.proposal(NOTES[-1]) is None                  # уже фраза
    hs = ctl.phrase_hints('зам')
    assert hs[0].word == '.замена' and hs[0].becomes == 'замена дуги верх 18х25 тма'


def test_controller_decline(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    for raw in NOTES:
        ctl.generate(raw)
    prop = ctl.proposal(NOTES[-1])
    ctl.decline_proposal(prop)
    assert ctl.proposal(NOTES[-1]) is None


def test_proposal_only_for_phrase_in_this_note(ctl, order_xlsx):
    ctl.import_xlsx(order_xlsx)
    for raw in NOTES:
        ctl.generate(raw)
    assert ctl.proposal('активация, перепел') is None


def test_single_value_slot_is_plain_text():
    notes = [f'активация, замена дуги верх {n}х25 тма' for n in (16, 17, 18, 16, 18)]
    assert propose(notes, [])[0][1] == 'замена дуги верх {16х25|18х25|17х25} тма'

# -*- coding: utf-8 -*-
"""Разбор «грязной» записи врача. Новый случай — строка в WIRE_CASES."""
from orthofill.parse import extract_facts, parse_wire_from_label, parse_wire_from_raw
from orthofill.text import norm

U, L = 'upper', 'lower'

# raw → {челюсть: ((ширина, глубина|None), материал|None)}
WIRE_CASES = [
    # одна челюсть, разные разделители размера
    ("замена дуги на верху 18 25 нити",            {U: (('18', '25'), 'NiTi')}),
    ("замена дуги верх 16x25 niti",                {U: (('16', '25'), 'NiTi')}),
    ("замена дуги верх 16х25 нити",                {U: (('16', '25'), 'NiTi')}),  # х — кириллица
    ("замена дуги верх 16*25 нити",                {U: (('16', '25'), 'NiTi')}),
    ("замена дуги верх 16-25 нити",                {U: (('16', '25'), 'NiTi')}),
    ("замена дуги верх 16/25 нити",                {U: (('16', '25'), 'NiTi')}),
    ("замена дуги верх 16 на 25 нити",             {U: (('16', '25'), 'NiTi')}),
    ("замена дуги верх 0.016x0.025 NiTi",          {U: (('16', '25'), 'NiTi')}),
    ("замена дуги верх .016*.025 niti",            {U: (('16', '25'), 'NiTi')}),
    ("замена дуги верх 016х025 нити",              {U: (('16', '25'), 'NiTi')}),
    ("на нижнюю поставили дугу 19/25 сталь",       {L: (('19', '25'), 'SS')}),
    ("смена дуги н/ч 0,014 нити",                  {L: (('14', None), 'NiTi')}),
    ("замена дуги снизу 14 ni-ti",                 {L: (('14', None), 'NiTi')}),
    # смешанная раскладка: С/с, Т, Н кириллицей внутри латинского слова
    ("замена дуги верх 16x25 СuNiTi",              {U: (('16', '25'), 'CuNiTi')}),
    ("замена дуги верх 16x25 сuniti",              {U: (('16', '25'), 'CuNiTi')}),
    ("замена дуги верх 16x25 NiТi",                {U: (('16', '25'), 'NiTi')}),
    ("замена дуги верх 16x25 кунити",              {U: (('16', '25'), 'CuNiTi')}),
    ("замена дуги верх 17x25 тма",                 {U: (('17', '25'), 'TMA')}),
    ("замена дуги верх 19x25 сс",                  {U: (('19', '25'), 'SS')}),
    ("замена дуги верх 19x25 ss",                  {U: (('19', '25'), 'SS')}),
    # обе челюсти, одна дуга
    ("замена дуги обе 16*25 cuniti",               {U: (('16', '25'), 'CuNiTi'), L: (('16', '25'), 'CuNiTi')}),
    ("замена дуг на обеих челюстях 18 нити",       {U: (('18', None), 'NiTi'), L: (('18', None), 'NiTi')}),
    ("дуги верх и низ 16х25 нити",                 {U: (('16', '25'), 'NiTi'), L: (('16', '25'), 'NiTi')}),
    ("замена дуги 16 нити",                        {U: (('16', None), 'NiTi'), L: (('16', None), 'NiTi')}),
    # обе челюсти, разные дуги
    ("замена дуги верх 16х25 нити, низ 14 нити",   {U: (('16', '25'), 'NiTi'), L: (('14', None), 'NiTi')}),
    ("замена дуг: в/ч 0.016 niti, н/ч 0,014 niti", {U: (('16', None), 'NiTi'), L: (('14', None), 'NiTi')}),
    ("замена дуги верх 18 25 ss низ 16 25 нити",   {U: (('18', '25'), 'SS'), L: (('16', '25'), 'NiTi')}),
    ("замена дуги верх 16x25, низ 14, нити",       {U: (('16', '25'), 'NiTi'), L: (('14', None), 'NiTi')}),
    ("дуга верх 18 нити. низ 16 нити.",            {U: (('18', None), 'NiTi'), L: (('16', None), 'NiTi')}),
    ("замена дуги 16 нити верх, 14 нити низ",      {U: (('16', None), 'NiTi'), L: (('14', None), 'NiTi')}),
    ("верх 18x25 ss, низ 16x25 нити замена дуг",   {U: (('18', '25'), 'SS'), L: (('16', '25'), 'NiTi')}),
    # одна челюсть меняется, другая — нет
    ("замена дуги верх 18 нити, низ без изменений", {U: (('18', None), 'NiTi')}),
    # дуга не меняется / упомянута в другом смысле
    ("лигатурная, этап рабочий",                   {}),
    ("жалобы на выход дуги из замка",              {}),
    # соседние пункты не должны мешать
    ("замена дуги верх 18 25 нити, смена лигатур на нижней, явка через 4 недели",
                                                   {U: (('18', '25'), 'NiTi')}),
]

def test_wires():
    bad = []
    for raw, exp in WIRE_CASES:
        got = parse_wire_from_raw(norm(raw))
        if got != exp:
            bad.append(f"  {raw!r}\n    ждали    {exp}\n    получили {got}")
    assert not bad, "\n" + "\n".join(bad)

def test_labels_cyrillic_c():
    # в order.xlsx «СuNiTi» с кириллической С
    assert parse_wire_from_label('на верхней челюсти 0.016×0.025" СuNiTi') == \
        (U, ('16', '25'), 'CuNiTi')
    assert parse_wire_from_label('на нижней челюсти 0.014" NiTi') == (L, ('14', None), 'NiTi')


def test_missing_values_are_none():
    f = extract_facts("лигатурная, перепел")
    assert f['stage'] is None and f['weeks'] is None and f['hygiene'] is None
    assert f['mucosa'] is None and f['dynamics'] is None and f['bracket_state'] is None
    assert f['ligature_arches'] is None and f['mentions_elastics'] is False


def test_explicit_values():
    f = extract_facts("этап детализации, явка через 6 нед, гигиена неудовлетворительная, "
                      "эрозия, без динамики")
    assert (f['stage'], f['weeks'], f['hygiene'], f['mucosa'], f['dynamics']) == \
        ('detail', 6, 'unsatisfactory', 'erosion', 'no_dynamics')


def test_explicit_normal_values():
    f = extract_facts("гигиена удовлетворительная, брекет-система удовлетворительно, "
                      "динамика по плану, этап рабочий")
    assert (f['hygiene'], f['bracket_state'], f['dynamics'], f['stage']) == \
        ('satisfactory', 'satisfactory', 'plan', 'working')


def test_classes():
    assert extract_facts("класс по молярам 1 и клыкам")['classes'] == {'molar': 1, 'canine': None}
    assert extract_facts("1 класс по молярам, ii класс по клыкам")['classes'] == \
        {'molar': 1, 'canine': 2}


def test_elastics_mention():
    assert extract_facts("носить резинки слон")['mentions_elastics'] is True


def test_ligature_and_binding():
    f = extract_facts("лигатурная, смена лигатур на нижней, подвязывание на верхней")
    assert (f['ligature_change'], f['ligature_arches']) == (True, 'lower')
    assert (f['binding'], f['binding_arches']) == (True, 'upper')

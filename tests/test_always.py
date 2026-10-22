"""0.5 beta 7: обязательные строки — из идеальных результатов пресета (E–F); строка,
попавшая в результат примера из-за слов его записи, обязательной не делается."""
from orthofill.engine import _effective_when, build_protocol
from orthofill.workbook import ReferenceCase, load_workbook_file


def _wb(order_xlsx, *refs):
    wb = load_workbook_file(order_xlsx)
    wb.references[:] = [ReferenceCase(str(i), raw, [(c, '') for c in codes])
                        for i, (raw, codes) in enumerate(refs)]
    return wb


def test_in_ideal_result_not_said_is_always(order_xlsx):
    wb = _wb(order_xlsx, ('лигатурная', ['2a', '4j']))
    w = _effective_when(wb)
    assert w['2a'] == 'always' and w['4j'] == 'always'


def test_said_in_example_is_not_always(order_xlsx):
    """Фото в результате потому, что в записи примера «фото» — не обязательно."""
    wb = _wb(order_xlsx, ('лигатурная, фотопротокол', ['2a', '4j']))
    assert _effective_when(wb)['4j'] == 'mentioned' and _effective_when(wb)['2a'] == 'always'


def test_mixed_examples(order_xlsx):
    wb = _wb(order_xlsx, ('лигатурная, фотопротокол', ['2a', '4j']), ('лигатурная', ['2a']))
    assert _effective_when(wb)['4j'] == 'mentioned'
    wb = _wb(order_xlsx, ('лигатурная, фотопротокол', ['2a', '4j']), ('лигатурная', ['2a', '4j']))
    assert _effective_when(wb)['4j'] == 'always'


def test_explicit_when_wins(order_xlsx):
    wb = _wb(order_xlsx, ('лигатурная', ['2a', '4j']))
    wb.by_id['4j'].when = 'mentioned'
    assert _effective_when(wb)['4j'] == 'mentioned'


def test_cached_per_preset(order_xlsx, monkeypatch):
    import orthofill.engine as eng
    wb = _wb(order_xlsx, ('лигатурная, кэш', ['2a']))
    calls = []
    real = eng._Ctx
    monkeypatch.setattr(eng, '_Ctx', lambda *a, **k: calls.append(1) or real(*a, **k))
    _effective_when(wb)
    n = len(calls)
    _effective_when(wb)
    assert len(calls) == n


def test_doctor_presets_unchanged(order_xlsx):
    """Пресеты врача: текущий набор обязательных строк — как был."""
    wb = load_workbook_file(order_xlsx)
    assert '4j' in [c for c, _ in build_protocol(wb, '').lines]

"""Сборка протокола: правила привязаны к ТЕКСТУ пунктов классификатора,
поэтому врач может перенумеровать пункты и добавлять варианты без правки кода."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parse import extract_facts, parse_wire_from_label
from .text import norm, stem_in, word_stem
from .workbook import Item, ReferenceCase, Workbook

__all__ = ['Protocol', 'CaseResult', 'ReferenceCase', 'build_protocol',
           'check_references', 'rule_kind', 'rule_warnings']

# Тип группы по её тексту — первое совпадение
_KINDS = [
    ('system',   r'тип\w* систем'),
    ('stage',    r'^этап'),
    ('mucosa',   r'слизист'),
    ('hygiene',  r'гигиен'),
    ('relation', r'соотношени\w* (?:моляр|клык)'),
    ('bracket',  r'состояни\w* брекет'),
    ('wire',     r'смен\w* дуг'),
    ('ligature', r'(?:смен|замен)\w*.*лигатур'),
    ('binding',  r'подвяз'),
    ('elastics', r'эластик'),
    ('adjust',   r'юстиров'),
    ('dynamics', r'динамик'),
    ('visit',    r'явк'),
]
# Правила, без группы которых протокол заведомо неполон
_REQUIRED = {
    ('wire', 'upper'): 'дуга на верхней', ('wire', 'lower'): 'дуга на нижней',
    ('elastics', None): 'эластики', ('visit', None): 'явка',
    ('system', None): 'тип системы', ('stage', None): 'этап',
}


@dataclass
class Protocol:
    lines: list[tuple[str, str]]
    warnings: list[str] = field(default_factory=list)
    defaults: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n'.join(t for _, t in self.lines)


@dataclass
class CaseResult:
    case_id: str
    ok: bool
    missing: list[tuple[str, str]]
    extra: list[tuple[str, str]]


def rule_kind(group: Item) -> str | None:
    n = norm(group.text)
    for kind, rx in _KINDS:
        if re.search(rx, n):
            return kind
    return None


def _arch_of(group: Item) -> str | None:
    n = norm(group.text)
    return 'upper' if 'верхн' in n else 'lower' if 'нижн' in n else None


def rule_warnings(wb: Workbook) -> list[str]:
    found = set()
    for it in wb.items:
        if it.children:
            k = rule_kind(it)
            found.add((k, _arch_of(it) if k == 'wire' else None))
    return [f'в файле нет группы для правила «{name}»'
            for key, name in _REQUIRED.items() if key not in found]


# ---------- подбор варианта по словам ----------
def _option_stems(text: str) -> list[str]:
    """Основы слов варианта для общего подбора: слова от 5 букв без последней
    (короче — слишком много ложных совпадений: «зам(ка)» ~ «зам(ена)»)."""
    return [w[:-1] for w in re.findall(r'[а-яa-z]+', norm(text)) if len(w) >= 5]


def _best_by_words(options: list[Item], n: str) -> Item | None:
    best, score = None, 0
    for c in options:
        s = sum(stem_in(st, n) for st in _option_stems(c.text))
        if s > score:
            best, score = c, s
    return best


def _first(children: list[Item], pred) -> Item | None:
    return next((c for c in children if pred(norm(c.text))), None)


def _class_in(text: str) -> int | None:
    m = re.search(r'\b(i{1,3}|iv|[1-4])\s*класс', text)
    if not m:
        return None
    v = m.group(1)
    return {'i': 1, 'ii': 2, 'iii': 3, 'iv': 4}[v] if v[0] in 'iv' else int(v)


def _first_number(text: str) -> int | None:
    m = re.search(r'\d+', text)
    return int(m.group()) if m else None


class _Ctx:
    def __init__(self, raw: str):
        self.f = extract_facts(raw)
        self.n = self.f['raw_norm']
        self.warnings: list[str] = []
        self.defaults: list[str] = []

    def warn(self, msg: str):
        if msg not in self.warnings:
            self.warnings.append(msg)

    def default(self, label: str):
        if label not in self.defaults:
            self.defaults.append(label)


def _good_bad(children, value, ctx, default_label):
    if value == 'unsatisfactory':
        hit = _first(children, lambda t: 'неудовлетвор' in t)
        if hit:
            return hit
    if value is None:
        ctx.default(default_label)
    return _first(children, lambda t: 'удовлетвор' in t and 'неудовлетвор' not in t)


def _select(group: Item, ctx: _Ctx) -> Item | None:
    kind, ch, f = rule_kind(group), group.children, ctx.f

    if kind == 'system':
        st = f['system_type']
        if st == 'self_ligating':
            return _first(ch, lambda t: 'самолигир' in t)
        if st == 'ligature':
            return _first(ch, lambda t: 'лигатур' in t and 'самолигир' not in t)
        return None

    if kind == 'stage':
        keys = {'detail': 'детализ', 'initial': r'начальн|нивелир', 'working': 'рабоч'}
        if f['stage']:
            return _first(ch, lambda t: re.search(keys[f['stage']], t))
        hit = _best_by_words(ch, ctx.n)
        if hit:
            return hit
        ctx.default('этап рабочий')
        return _first(ch, lambda t: 'рабоч' in t)

    if kind == 'mucosa':
        if f['mucosa'] == 'erosion':
            hit = _first(ch, lambda t: 'эрози' in t)
            if hit:
                return hit
        if f['mucosa'] is None:
            ctx.default('слизистая в норме')
        return _first(ch, lambda t: 'без видимых' in t or 'норм' in t) or ch[0]

    if kind == 'hygiene':
        return _good_bad(ch, f['hygiene'], ctx, 'гигиена удовлетворительная')

    if kind == 'bracket':
        return _good_bad(ch, f['bracket_state'], ctx, 'брекет-система в порядке')

    if kind == 'relation':
        g = norm(group.text)
        cls = f['classes']['molar' if 'моляр' in g else 'canine']
        if cls is None:
            return None
        side = 'справа' if 'справа' in g else 'слева'
        return _first(ch, lambda t: side in t and _class_in(t) == cls)

    if kind == 'wire':
        arch = _arch_of(group)
        info = f['wires'].get(arch)
        if info is None:
            return None
        size, material = info
        jaw = 'верхней' if arch == 'upper' else 'нижней'
        if size is None:
            ctx.warn(f'дуга на {jaw}: размер не распознан — выберите вручную')
            return None
        for c in ch:
            la, ls, lm = parse_wire_from_label(c.text)
            if la in (arch, None) and ls == size and not (material and lm and material != lm):
                return c
        label = '×'.join(f'0.0{x}' for x in size if x) + '"'
        if material:
            label += f' {material}'
        ctx.warn(f'дуга на {jaw}: {label} нет в классификаторе')
        return None

    if kind == 'ligature':
        if not f['ligature_change']:
            return None
        arches = f['ligature_arches']
        if arches is None:
            ctx.default('лигатуры на обеих челюстях')
            arches = 'both'
        key = {'both': 'обе', 'upper': 'верхн', 'lower': 'нижн'}[arches]
        return _first(ch, lambda t: key in t)

    if kind == 'binding':
        arches = f['binding_arches']
        if not f['binding'] or arches not in ('upper', 'lower'):
            return None
        key = 'верхн' if arches == 'upper' else 'нижн'
        return _first(ch, lambda t: key in t)

    if kind == 'elastics':
        for c in ch:
            words = re.findall(r'[а-яa-z]+', norm(c.text))
            if words and all(stem_in(word_stem(w), ctx.n) for w in words if len(w) >= 3):
                return c
        if f['mentions_elastics']:
            ctx.warn('эластики упомянуты, но вариант не найден в классификаторе')
        return None

    if kind == 'adjust':
        stems = {1: 'перв', 2: 'втор', 3: 'трет'}
        for order in f['wire_adjustments']:
            hit = _first(ch, lambda t: stems[order] in t)
            if hit:
                return hit
        return None

    if kind == 'dynamics':
        if f['dynamics'] == 'no_dynamics':
            return _first(ch, lambda t: 'без' in t)
        if f['dynamics'] is None:
            ctx.default('динамика по плану')
        return _first(ch, lambda t: 'соответств' in t)

    if kind == 'visit':
        numbered = [(c, _first_number(c.text)) for c in ch]
        numbered = [(c, k) for c, k in numbered if k is not None]
        if not numbered:
            return None
        w = f['weeks']
        if w is None:
            ctx.default('явка 4 нед')
            w = 4
        exact = next((c for c, k in numbered if k == w), None)
        if exact:
            return exact
        nearest = min(numbered, key=lambda ck: abs(ck[1] - w))[0]
        ctx.warn(f'явка через {w} нед: такого варианта нет, выбрано «{nearest.text}»')
        return nearest

    # Группа, для которой правила нет (врач добавил новую): по словам записи
    return _best_by_words(ch, ctx.n)


def _select_complaint(section: Item, ctx: _Ctx) -> Item | None:
    ch, n = section.children, ctx.n
    known = [
        (r'отклеи|отвалил|отпал', 'отклеива'),
        (r'выход\w*\s+дуг|дуг\w*\s+выш|выскоч', 'выход'),
        (r'перелом\w*\s+дуг|слома\w*\s+дуг|дуг\w*\s+слома', 'перелом'),
    ]
    for raw_rx, option_key in known:
        if re.search(raw_rx, n):
            hit = _first(ch, lambda t: option_key in t)
            if hit:
                return hit
    default = _first(ch, lambda t: re.search(r'не\s+пред[ъь]явл', t)) or (ch[0] if ch else None)
    hit = _best_by_words([c for c in ch if c is not default], n)
    if hit:
        return hit
    ctx.default('жалоб нет')
    return default


def _orphan_applies(item: Item, ctx: _Ctx) -> bool:
    t, st = norm(item.text), ctx.f['system_type']
    if 'фиксаци' in t and 'лигатур' in t:
        return st != 'self_ligating'
    if 'клипс' in t:
        return st == 'self_ligating'
    return _best_by_words([item], ctx.n) is not None


def _render_modes(wb: Workbook) -> dict[str, str]:
    """Как эталоны выводят группу: join / separate / child_only."""
    modes: dict[str, str] = {}
    for case in wb.references:
        texts = {code: norm(text) for code, text in case.lines if code}
        for g in wb.items:
            if not g.children or g.id in modes:
                continue
            if g.id in texts:
                if texts[g.id] == norm(g.text):
                    modes[g.id] = 'separate'
                elif any(texts[g.id] == norm(g.text + ' ' + c.text) for c in g.children):
                    modes[g.id] = 'join'
            elif any(c.id in texts for c in g.children):
                modes[g.id] = 'child_only'
    return modes


def _render(group: Item, sel: Item, mode: str | None) -> list[tuple[str, str]]:
    if mode is None:
        mode = 'child_only' if group.text.rstrip().endswith(':') else 'separate'
    if mode == 'join':
        return [(group.id, f'{group.text.rstrip()} {sel.text}')]
    if mode == 'child_only':
        return [(sel.id, sel.text)]
    return [(group.id, group.text), (sel.id, sel.text)]


def build_protocol(wb: Workbook, raw: str) -> Protocol:
    ctx = _Ctx(raw)
    modes = _render_modes(wb)
    lines: list[tuple[str, str]] = []
    for section in wb.sections:
        out: list[tuple[str, str]] = []
        if norm(section.text).startswith('жалоб'):
            sel = _select_complaint(section, ctx)
            if sel:
                out.append((sel.id, sel.text))
        else:
            for item in section.children:
                if item.children:
                    sel = _select(item, ctx)
                    if sel:
                        out += _render(item, sel, modes.get(item.id))
                elif not item.orphan or _orphan_applies(item, ctx):
                    out.append((item.id, item.text))
        if out:
            lines += [(section.id, section.text)] + out
    return Protocol(lines, ctx.warnings, ctx.defaults)


def _key(line: tuple[str, str]) -> tuple[str, str]:
    return line[0], ' '.join(line[1].split())


def check_references(wb: Workbook) -> list[CaseResult]:
    results = []
    for case in wb.references:
        got = [_key(x) for x in build_protocol(wb, case.raw).lines]
        exp = [_key(x) for x in case.lines]
        results.append(CaseResult(
            case.case_id, got == exp,
            missing=[x for x in exp if x not in got],
            extra=[x for x in got if x not in exp]))
    return results

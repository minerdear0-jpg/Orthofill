"""Сборка протокола: правила привязаны к ТЕКСТУ пунктов классификатора,
поэтому врач может перенумеровать пункты и добавлять варианты без правки кода."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .methods import METHOD_LABELS
from .parse import arches_in, extract_facts, parse_wire_from_label
from .render import Row, render_rows
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
    """lines — модель: по строке «код → текст пункта» на каждый выбранный пункт
    (раздел, группа, вариант, отдельный пункт). rows — как это читается: группа
    и вариант одной строкой, пометки «проверьте»."""
    lines: list[tuple[str, str]]
    warnings: list[str] = field(default_factory=list)
    defaults: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)

    @property
    def text(self) -> str:
        return '\n'.join(r.text for r in self.rows)


@dataclass
class CaseResult:
    case_id: str
    ok: bool
    missing: list[tuple[str, str]]
    extra: list[tuple[str, str]]
    own_lines: int = 0              # строки врача, которые не проверяются


def _guess_kind(group: Item) -> str | None:
    n = norm(group.text)
    for kind, rx in _KINDS:
        if re.search(rx, n):
            return kind
    return None


def rule_kind(group: Item) -> str | None:
    """Способ выбора группы: заданный в пресете или угаданный по тексту.
    None — «по словам записи» (встроенного правила нет)."""
    kind = group.method or _guess_kind(group)
    return None if kind == 'words' else kind


def _guess_when(it: Item, refs: list[set[str]]) -> str:
    """«Всегда» — если пункт есть больше чем в половине эталонов (без эталонов — всегда)."""
    used = sum(it.id in r for r in refs)
    return 'always' if not refs or used * 2 > len(refs) else 'mentioned'


def _effective_when(wb: Workbook) -> dict[str, str]:
    """«Когда в протоколе» для отдельных пунктов: заданное или угаданное заново
    по текущим эталонам (угаданное не хранится — меняется с эталонами)."""
    refs = [{code for code, _ in case.lines} for case in wb.references if case.lines]
    return {it.id: it.when or _guess_when(it, refs) for it in wb.items
            if not it.children and it.level == 2 and not it.orphan}


def guess_settings(wb: Workbook) -> None:
    """Записать угаданные свойства в пункты как явные (для редактора и экспорта
    «как сейчас работает»). Разбор их не требует: build_protocol угадывает сам.
    Заданное явно не трогается."""
    refs = [{code for code, _ in case.lines} for case in wb.references if case.lines]
    for it in wb.items:
        if it.children:
            if it.method is None:
                it.method = _guess_kind(it) or 'words'
        elif it.level == 2 and not it.orphan and it.when is None:
            it.when = _guess_when(it, refs)


def _arch_of(group: Item) -> str | None:
    """Челюсть группы — из её текста, а если там не сказано («Смена дуги»),
    то из вариантов, когда все они про одну челюсть."""
    n = norm(group.text)
    if 'верхн' in n or 'нижн' in n:
        return 'upper' if 'верхн' in n else 'lower'
    found = {_arch_of(c) for c in group.children}
    return found.pop() if len(found) == 1 else None


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
    def __init__(self, raw: str, wb: Workbook | None = None):
        self.f = extract_facts(raw)
        self.n = self.f['raw_norm']
        self.wb = wb
        self.warnings: list[str] = []
        self.defaults: list[str] = []
        # пункты без вариантов, которые попали в протокол только по записи
        self.mentioned_singles: list[Item] = []
        # «проверьте»: код группы/раздела → причины; current — группа, которую выбираем
        self.flags: dict[str, list[str]] = {}
        self.current: str | None = None

    def flag(self, code: str, reason: str):
        reasons = self.flags.setdefault(code, [])
        if reason not in reasons:
            reasons.append(reason)

    def warn(self, msg: str):
        if msg not in self.warnings:
            self.warnings.append(msg)
        if self.current:                  # предупреждение про эту группу — её строка «проверьте»
            self.flag(self.current, msg)

    def default(self, label: str):
        if label not in self.defaults:
            self.defaults.append(label)


def _good_bad(children, value, ctx, default_label, topic):
    if value == 'unknown':
        ctx.warn(f'{topic}: значение не распознано — выберите вручную')
        return None
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
        if f['mucosa'] == 'unknown':
            ctx.warn('слизистая: значение не распознано — выберите вручную')
            return None
        if f['mucosa'] == 'erosion':
            hit = _first(ch, lambda t: 'эрози' in t)
            if hit:
                return hit
        if f['mucosa'] is None:
            ctx.default('слизистая в норме')
        return _first(ch, lambda t: 'без видимых' in t or 'норм' in t) or ch[0]

    if kind == 'hygiene':
        return _good_bad(ch, f['hygiene'], ctx, 'гигиена удовлетворительная', 'гигиена')

    if kind == 'bracket':
        return _good_bad(ch, f['bracket_state'], ctx, 'брекет-система в порядке',
                         'брекет-система')

    if kind == 'relation':
        g = norm(group.text)
        cls = f['classes']['molar' if 'моляр' in g else 'canine']
        if cls is None:
            return None
        if f['classes_sided']:
            ctx.warn('класс по сторонам (справа/слева) не поддерживается — '
                     'проверьте соотношение моляров и клыков')
        side = 'справа' if 'справа' in g else 'слева'
        hit = _first(ch, lambda t: side in t and _class_in(t) == cls)
        if hit and not re.search(r'справа|слева', ctx.n):
            ctx.flag(group.id, 'сторона не указана — проставлены обе')
        return hit

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
                if not material and lm:
                    ctx.default(f'материал дуги {lm}')
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
        if not f['binding']:
            return None
        if any('подвяз' in norm(it.text) for it in ctx.mentioned_singles):
            return None         # «подвязывание зуба короткой лигатурой» — свой пункт
        if arches not in ('upper', 'lower'):
            ctx.warn('подвязывание: челюсть не распознана — выберите вручную')
            return None
        key = 'верхн' if arches == 'upper' else 'нижн'
        return _first(ch, lambda t: key in t)

    if kind == 'elastics':
        hits = []
        for c in ch:
            words = [w for w in re.findall(r'[а-яa-z]+', norm(c.text)) if len(w) >= 3]
            if words and all(stem_in(word_stem(w), ctx.n) for w in words):
                if not _cancelled(ctx.n, word_stem(words[0])):
                    hits.append(c)
        if len(hits) > 1:
            names = ', '.join(f'«{c.text}»' for c in hits)
            ctx.warn(f'эластики: несколько вариантов ({names}) — в протокол попал только первый')
        if hits:
            return hits[0]
        if f['mentions_elastics'] and not _cancelled(ctx.n, r'эластик|резин|тяг'):
            ctx.warn('эластики упомянуты, но вариант не найден в классификаторе')
        return None

    if kind == 'adjust':
        stems = {1: 'перв', 2: 'втор', 3: 'трет'}
        for order in f['wire_adjustments']:
            hit = _first(ch, lambda t: stems[order] in t)
            if hit:
                return hit
        if re.search(r'юстир|изгиб', ctx.n):
            ctx.warn('юстировка: вид изгиба не распознан — допишите вручную')
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
            if f['mentions_visit']:
                default = next((c for c, k in numbered if k == 4), numbered[0][0])
                ctx.warn(f'явка: срок не распознан, выбрано «{default.text}» — проверьте')
                return default
            ctx.default('явка 4 нед')
            w = 4
        exact = next((c for c, k in numbered if k == w), None)
        if exact:
            return exact
        nearest = min(numbered, key=lambda ck: abs(ck[1] - w))[0]
        ctx.warn(f'явка через {w} нед: такого варианта нет, выбрано «{nearest.text}»')
        return nearest

    # Группа, для которой правила нет (врач добавил новую)
    return _select_new_group(group, ctx)


# ---------- пункты, которые врач добавил сам ----------
def _stems(text: str) -> list[str]:
    return [word_stem(w) for w in re.findall(r'[а-яa-z]{4,}', norm(text))]


def _own_stems(item: Item, wb: Workbook, exclude: list[Item]) -> list[str]:
    """Основы слов, которые есть только у этого пункта: «цепочк» у «Эластическая
    цепочка без шага» (а «эластическ» есть и у «эластических лигатур»)."""
    others = [norm(o.text) for o in wb.items if o is not item and o not in exclude]
    own = [st for st in _stems(item.text) if not any(stem_in(st, t) for t in others)]
    return list(dict.fromkeys(own))


def _mention(stems: list[str], n: str) -> int | None:
    """Позиция первого слова записи с такой основой (не отменённого)."""
    pos = [m.start() for st in stems
           for m in re.finditer(r'(?<![а-яa-z])' + re.escape(st), n)
           if not _cancelled(n, re.escape(st))]
    return min(pos) if pos else None


def _phrase(n: str, start: int) -> str:
    end = min([p for p in (n.find(c, start) for c in ',.;') if p != -1] or [len(n)])
    return n[start:end]


def _single_mentioned(item: Item, ctx: _Ctx) -> bool:
    if item.words and _mention(item.words, ctx.n) is not None:
        return True
    stems = _own_stems(item, ctx.wb, []) if ctx.wb else []
    if stems:
        return _mention(stems, ctx.n) is not None
    all_stems = _stems(item.text)
    return bool(all_stems) and all(stem_in(st, ctx.n) for st in all_stems)


def _select_new_group(group: Item, ctx: _Ctx) -> list[Item] | Item | None:
    """Группа без правила: только если о ней написано (её слова или слова её
    вариантов), вариант — из той же фразы записи."""
    ch, wb = group.children, ctx.wb
    if wb is None:
        return _best_by_words(ch, ctx.n)
    family = [group] + ch
    stems = _own_stems(group, wb, family) + list(group.words)
    for c in ch:
        stems += [st for st in _own_stems(c, wb, family) if st not in stems]
    start = _mention(stems, ctx.n)
    if start is None:
        return None
    phrase = _phrase(ctx.n, start)
    title = group.text.strip()

    arch_of = {c.id: _arch_of(c) or ('both' if 'обе' in norm(c.text) else None) for c in ch}
    if ch and all(arch_of.values()):            # варианты — челюсти
        a = arches_in(phrase)
        if a is None:
            ctx.warn(f'«{title}»: челюсть не указана — допишите вручную')
            return []
        exact = [c for c in ch if arch_of[c.id] == a]
        if exact:
            return exact[0]
        if a == 'both':
            return [c for c in ch if arch_of[c.id] in ('upper', 'lower')]
        ctx.warn(f'«{title}»: челюсть не найдена в классификаторе — допишите вручную')
        return []

    nums = set(re.findall(r'\d+', phrase))
    scored = []
    for c in ch:
        s = sum(stem_in(st, phrase) for st in _stems(c.text))
        s += sum(2 for d in re.findall(r'\d+', c.text) if d in nums)
        scored.append((s, c))
    best = max((s for s, _ in scored), default=0)
    top = [c for s, c in scored if s == best]
    if ch and (best == 0 or len(top) > 1):
        ctx.warn(f'«{title}»: вариант не распознан — допишите вручную')
        return []
    return top[0] if ch else []


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
    # Новые жалобы ищем только в том, что написано после «жалобы…»,
    # иначе «брекет-система удовлетворительная» дала бы «на отклеивание брекета»
    said = ctx.f['complaint_text']
    if said:
        hit = _best_by_words([c for c in ch if c is not default], said)
        if hit:
            return hit
        ctx.warn(f'жалоба не распознана: «{said}» — выберите вручную')
        return default
    ctx.default('жалоб нет')
    return default


def _cancelled(n: str, stem_rx: str) -> bool:
    """Назначение отменено: «перепел отменен», «без эластиков», «сняли резинки»."""
    for m in re.finditer(stem_rx, n):
        start = max(0, max(n.rfind(c, 0, m.start()) for c in ',.;') + 1)
        ends = [p for p in (n.find(c, m.end()) for c in ',.;') if p != -1]
        part = n[start:min(ends) if ends else len(n)]
        if re.search(r'отмен|\bсня[лт]|\bбез\b|\bне\s+(?:носит|назнач)', part):
            return True
    return False


def _orphan_applies(item: Item, ctx: _Ctx) -> bool:
    t, st = norm(item.text), ctx.f['system_type']
    if 'фиксаци' in t and 'лигатур' in t:
        return st == 'ligature'
    if 'клипс' in t:
        return st == 'self_ligating'
    return _best_by_words([item], ctx.n) is not None


def build_protocol(wb: Workbook, raw: str) -> Protocol:
    ctx = _Ctx(raw, wb)
    if ctx.f['system_type'] is None:
        ctx.warn('тип системы не распознан (лигатурная / самолигирующая)')
    cl = ctx.f['classes']
    if cl['molar'] is None and cl['canine'] is None and \
            re.search(r'класс\w*\s*(?:[1-3]|i{1,3})\b|(?:[1-3]|i{1,3})\s*класс', ctx.n):
        ctx.warn('класс: не указано, по молярам или по клыкам — допишите вручную')
    if ctx.f['wire_no_arch']:
        ctx.default('дуга на обеих челюстях (челюсть не указана)')
    when = _effective_when(wb)
    singles = {it.id: (when[it.id] == 'always' or _single_mentioned(it, ctx))
               for s in wb.sections for it in s.children
               if not it.children and not it.orphan}
    ctx.mentioned_singles = [wb.by_id[i] for i, ok in singles.items()
                             if ok and when[i] != 'always']
    lines: list[tuple[str, str]] = []
    for section in wb.sections:
        out: list[tuple[str, str]] = []
        if norm(section.text).startswith('жалоб'):
            ctx.current = section.id
            sel = _select_complaint(section, ctx)
            ctx.current = None
            if sel:
                out.append((sel.id, sel.text))
        else:
            for item in section.children:
                if item.children:
                    sel = _select_or_default(item, ctx)
                    if sel is not None:     # [] — группа упомянута, вариант не выбран
                        out.append((item.id, item.text))
                        for c in (sel if isinstance(sel, list) else [sel]):
                            out.append((c.id, c.text))
                elif item.orphan:
                    if _orphan_applies(item, ctx):
                        out.append((item.id, item.text))
                elif singles.get(item.id):
                    out.append((item.id, item.text))
        if out:
            lines += [(section.id, section.text)] + out
    if ctx.f['wire_hint'] and not ctx.f['wires']:
        ctx.warn('дуга: упоминание не распознано — проверьте вручную')
    return Protocol(lines, ctx.warnings, ctx.defaults, render_rows(wb, lines, ctx.flags))


def _select_or_default(group: Item, ctx: _Ctx):
    """Выбор правилом; если врач не написал (правило ничего не выбрало или
    подставило своё «по умолчанию») — вариант по умолчанию из пресета."""
    n_def, n_warn = len(ctx.defaults), len(ctx.warnings)
    ctx.current = group.id
    try:
        sel = _select(group, ctx)
    finally:
        ctx.current = None
    if sel and rule_kind(group) == 'wire' and ctx.f['wire_no_arch']:
        ctx.flag(group.id, 'челюсть не указана — дуга на обеих')
    if sel and rule_kind(group) is None:
        ctx.flag(group.id, 'выбрано по словам записи — проверьте')
    target = group.default and next((c for c in group.children if c.id == group.default), None)
    if not target or len(ctx.warnings) > n_warn:
        return sel
    if sel is None or len(ctx.defaults) > n_def:
        del ctx.defaults[n_def:]
        ctx.default(f'{group.text.strip()} {target.text.strip()}')
        return target
    return sel


def _key(line: tuple[str, str]) -> tuple[str, str]:
    return line[0], ' '.join(line[1].split())


def check_references(wb: Workbook) -> list[CaseResult]:
    """Сверка по пунктам (кодам и их порядку), не по тексту. Строка эталона без
    кода (своя строка врача) не проверяется; строка с кодом группы и своим
    текстом — «формулировка врача»: подходит любой вариант этой группы."""
    results = []
    for case in wb.references:
        got = [c for c, _ in build_protocol(wb, case.raw).lines]
        exp, own, free = [], 0, set()
        for code, text in case.lines:
            if not code:
                own += 1
                continue
            it = wb.by_id.get(code)
            if it is not None and it.children and ' '.join(text.split()) != ' '.join(it.text.split()):
                own += 1
                free.add(code)
            exp.append(code)
        if free:     # варианты групп с формулировкой врача не сравниваются
            got = [c for c in got if not (c in wb.by_id and wb.by_id[c].parent in free
                                          and wb.by_id[c].level == 3)]
        text_of = lambda c: (c, wb.by_id[c].text if c in wb.by_id else '')  # noqa: E731
        results.append(CaseResult(
            case.case_id, got == exp,
            missing=[text_of(c) for c in exp if c not in got],
            extra=[text_of(c) for c in got if c not in exp],
            own_lines=own))
    return results

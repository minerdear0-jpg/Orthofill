"""Сборка протокола: правила привязаны к ТЕКСТУ пунктов классификатора,
поэтому врач может перенумеровать пункты и добавлять варианты без правки кода."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .logic import Facts, evaluate
from .methods import METHOD_LABELS
from .parse import arches_in, clause, extract_facts, parse_wire_from_label
from .render import Row, render_rows
from .text import norm, stem_in, word_stem
from .workbook import DictEntry, Item, ReferenceCase, Workbook

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
    dictionary_hits: list[str] = field(default_factory=list)   # сработавшие слова врача

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


def _guess_when(it: Item, refs: list[tuple[set[str], set[str]]]) -> str:
    """«Всегда» — из идеальных результатов пресета (эталоны, колонки E–F): пункт есть
    в результате больше чем в половине примеров, где запись о нём не говорит. Если
    пункт попал в результат из-за слов записи примера — это «может попасть», не
    «всегда» (заказчик 22.10). Без эталонов — всегда."""
    if not refs:
        return 'always'
    free = [codes for codes, said in refs if it.id not in said]
    if not free:
        return 'mentioned'
    used = sum(it.id in codes for codes in free)
    return 'always' if used * 2 > len(free) else 'mentioned'


_EVIDENCE: dict = {}       # доводы эталонов — на набор (эталоны + пункты + словарь)


def _ref_evidence(wb: Workbook) -> list[tuple[set[str], set[str]]]:
    """(коды идеального результата, коды, сказанные в записи примера) — по эталонам.
    Пресет перезагружается часто (новый объект) — кэш по содержимому, не по объекту."""
    key = (tuple((r.raw, tuple(c for c, _ in r.lines)) for r in wb.references if r.lines),
           tuple((it.id, it.text, tuple(it.words)) for it in wb.items),
           tuple((e.word, e.code) for e in wb.dictionary))
    if key in _EVIDENCE:
        return _EVIDENCE[key]
    out = []
    for r in wb.references:
        if not r.lines:
            continue
        codes = {c for c, _ in r.lines}
        try:
            said = _Said(_Ctx(r.raw, wb))
            said_codes = {it.id for it in wb.items if not it.children and it.id in said}
        except Exception:
            said_codes = set()
        out.append((codes, said_codes))
    if len(_EVIDENCE) > 64:
        _EVIDENCE.clear()
    _EVIDENCE[key] = out
    return out


def star_default(group: Item) -> list[Item]:
    """Варианты группы по умолчанию в пресете со «*»: отмеченные звёздочкой (группа «ИЛИ» —
    первый), звёздочка у самой группы — её первый вариант."""
    marked = [c for c in group.children if c.star]
    if not marked and group.star and group.children:
        marked = group.children[:1]
    return marked if group.combine == 'and' else marked[:1]


def _effective_when(wb: Workbook) -> dict[str, str]:
    """«Когда в протоколе» для отдельных пунктов: заданное или угаданное заново
    по текущим эталонам (угаданное не хранится — меняется с эталонами)."""
    if wb.star_mode:            # «*» в ID_CLASS — только отмеченное, без угадывания
        out = {it.id: 'always' if it.star else (it.when if it.when in ('always', 'condition')
                                                 else 'mentioned')
               for it in wb.items if not it.children and it.level == 2 and not it.orphan}
    else:
        refs = _ref_evidence(wb)
        out = {it.id: it.when or _guess_when(it, refs) for it in wb.items
               if not it.children and it.level == 2 and not it.orphan}
    for it in wb.items:             # пункт-сирота: по угаданному условию или по упоминанию
        if it.orphan:
            out[it.id] = it.when or ('condition' if guess_condition(it, wb) else 'mentioned')
    return out


def guess_condition(item: Item, wb: Workbook) -> dict | None:
    """Условие, угаданное по тексту пункта-сироты (было зашито в коде):
    фиксация лигатурами — при лигатурной системе, клипсы — при самолигирующей."""
    if not item.orphan:
        return None
    t = norm(item.text)
    if 'фиксаци' in t and 'лигатур' in t:
        pick = lambda v: 'лигатур' in v and 'самолигир' not in v     # noqa: E731
    elif 'клипс' in t:
        pick = lambda v: 'самолигир' in v                             # noqa: E731
    else:
        return None
    group = next((g for g in wb.items if g.children and rule_kind(g) == 'system'), None)
    variant = group and _first(group.children, pick)
    return {'all': [{'field': group.id, 'is': variant.id}]} if variant else None


def effective_condition(item: Item, wb: Workbook) -> dict | None:
    return item.condition or guess_condition(item, wb)


def guess_settings(wb: Workbook) -> None:
    """Записать угаданные свойства в пункты как явные (для редактора и экспорта
    «как сейчас работает»). Разбор их не требует: build_protocol угадывает сам.
    Заданное явно не трогается."""
    refs = _ref_evidence(wb)
    for it in wb.items:
        if it.children:
            if it.method is None:
                it.method = _guess_kind(it) or 'words'
        elif it.level == 2 and not it.orphan and it.when is None:
            it.when = _guess_when(it, refs)
        elif it.orphan and it.when is None:
            cond = guess_condition(it, wb)
            if cond and it.condition is None:
                it.condition = cond
            it.when = 'condition' if cond else 'mentioned'


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
        self.raw = raw
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
        # словарь врача: группа → выбранный словом вариант; отдельные пункты по слову
        self.forced: dict[str, Item] = {}
        self.forced_singles: set[str] = set()
        self.dictionary_hits: list[str] = []
        # группа → (выбранные варианты, выбрано по записи?) — факты для условий
        self.picked: dict[str, tuple[list[Item], bool]] = {}
        self.unclear: set[str] = set()      # группа упомянута, но не распознана
        self.details: dict[str, str] = {}   # код → уточнение словами врача («22 брекет»)
        self.tokens: list[DictEntry] = []   # привязанные подсказкой слова этой записи

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


def _elastic_named(c: Item, n: str) -> bool:
    """Вариант эластиков назван в записи своим названием («перепел») и не отменён."""
    words = [w for w in re.findall(r'[а-яa-z]+', norm(c.text)) if len(w) >= 3]
    return bool(words) and all(stem_in(word_stem(w), n) for w in words) \
        and not _cancelled(n, word_stem(words[0]))


# указание на зубы/брекеты: «22 брекет», «на 13 зубе», «с 13 по 23», «11, 21»
_TEETH = r'(?:(?:на|с)\s+)?\d{2}(?:\s*(?:,|и|-|–|по)\s*\d{2})*(?:\s+(?:брекет\w*|зуб\w*))?'


def _adjust_detail(raw: str) -> str:
    """Уточнение юстировки — только указание на зубы сразу после порядка изгиба,
    ровно как написано («изгиб первого 22 Брекет» → «22 Брекет»). Больше ничего не
    переносится: программа не пишет того, чего врач не сказал."""
    m = re.search(r'(?:изгиб|юстир)[^.;,]*?(?<![а-яё])(?:перв\w*|втор\w*|трет\w*|[123])'
                  r'(?:\s+порядк\w*)?', raw, re.I)
    if not m:
        return ''
    d = re.match(r'\s*:?\s*(' + _TEETH + r')(?=\s|[.,;]|$)', raw[m.end():], re.I)
    return d.group(1).strip() if d else ''


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
        hits = [c for c in ch if _elastic_named(c, ctx.n)]
        if len(hits) > 1:
            return _several(group, hits, ctx, 'эластики')
        if hits:
            return hits[0]
        if f['mentions_elastics'] and not _cancelled(ctx.n, r'эластик|резин|тяг'):
            ctx.warn('эластики упомянуты, но вариант не найден в классификаторе')
        return None

    if kind == 'adjust':
        stems = {1: 'перв', 2: 'втор', 3: 'трет'}
        hits = []
        for order in f['wire_adjustments']:
            hit = _first(ch, lambda t: stems[order] in t)
            if hit and hit not in hits:
                hits.append(hit)
        if len(hits) > 1:
            return _several(group, hits, ctx, 'юстировка')
        if hits:
            detail = _adjust_detail(ctx.raw)
            if detail:
                ctx.details[hits[0].id] = detail
                ctx.flag(group.id, 'уточнение перенесено из записи — проверьте')
            return hits[0]
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
    if ch and best == 0:
        ctx.warn(f'«{title}»: вариант не распознан — допишите вручную')
        return []
    if group.combine == 'and':
        hits = [c for s, c in scored if s > 0]
        hits = _distinct(hits, phrase) if len(hits) > 1 else hits
    elif len(top) > 1:
        hits = _distinct(top, phrase)
    else:
        return top[0] if ch else []
    if not hits:            # совпало только общее («тяга к минивинту» без сегмента)
        ctx.warn(f'«{title}»: вариант не распознан — допишите вручную')
        return []
    if len(hits) == 1:
        return hits[0]
    return _several(group, hits, ctx, f'«{title}»')


def _distinct(cands: list[Item], phrase: str) -> list[Item]:
    """Варианты, у которых в записи совпало своё — слово или число, которого
    нет у остальных кандидатов («ирригатор» / «ершик», а не общее «минивинт»)."""
    def marks(c: Item) -> set[str]:
        return set(_stems(c.text)) | set(re.findall(r'\d+', c.text))
    nums = set(re.findall(r'\d+', phrase))
    out = []
    for c in cands:
        others = set.intersection(*(marks(o) for o in cands if o is not c))
        own = marks(c) - others
        if any(m in nums if m.isdigit() else stem_in(m, phrase) for m in own):
            out.append(c)
    return out


def _several(group: Item, hits: list[Item], ctx: _Ctx, topic: str) -> list[Item]:
    """Упомянуто несколько вариантов: И — все; ИЛИ — все с «проверьте»
    (программа не выбирает за врача)."""
    if group.combine != 'and':
        names = ', '.join(f'«{c.text.strip()}»' for c in hits)
        ctx.warn(f'{topic}: несколько вариантов ({names}) — проверьте')
    return hits


def _select_complaint(section: Item, ctx: _Ctx) -> Item | None:
    ch, n = section.children, ctx.n
    taught = next((c for c in ch if c.id in ctx.forced_singles), None)
    if taught is not None:              # слово врача — раньше правил
        return taught
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
    if ctx.wb is not None and ctx.wb.star_mode:     # «*»: жалоба по умолчанию — только отмеченная
        default = next((c for c in ch if c.star), None)
    else:
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
    if default is not None:
        ctx.default('жалоб нет')
    return default


def _negated_at(n: str, start: int, end: int) -> bool:
    """Фраза записи вокруг [start, end) отменяет назначение («без …», «… отменён»)."""
    left = max(0, max(n.rfind(c, 0, start) for c in ',.;') + 1)
    ends = [p for p in (n.find(c, end) for c in ',.;') if p != -1]
    part = n[left:min(ends) if ends else len(n)]
    return re.search(r'отмен|\bсня[лт]|\bбез\b|\bне\s+(?:носит|назнач)', part) is not None


def _cancelled(n: str, stem_rx: str) -> bool:
    """Назначение отменено: «перепел отменен», «без эластиков», «сняли резинки»."""
    return any(_negated_at(n, m.start(), m.end()) for m in re.finditer(stem_rx, n))


_SEP = r'\s*[xх×*/\-]\s*'


def _phrase_rx(phrase: str) -> str:
    """Слова врача → шаблон. Короткие слова (до 4 букв) и числа — только целиком
    («гиг» не срабатывает внутри «гигиена», «явка 6» — внутри «явка 60»);
    длинные — по основе с коротким окончанием («квакозябры»); сечение «18х25» —
    с любым знаком и пробелами («18 * 25»)."""
    parts = []
    for w in norm(phrase).split():
        if re.search(r'\d', w):
            nums = [x for x in re.split(r'[xх×*/\-]', w) if x]
            parts.append(_SEP.join(re.escape(x) for x in nums) + r'(?![0-9])')
        elif len(w) <= 4:
            parts.append(re.escape(w) + r'(?![а-яa-z0-9])')
        else:
            parts.append(re.escape(word_stem(w)) + r'[а-яa-z]{0,4}(?![а-яa-z0-9])')
    return r'(?<![а-яa-z0-9])' + r'[\s,.;:]+'.join(parts)


def _dictionary_item(wb: Workbook, e, by_text: dict[str, list[Item]]) -> Item | None:
    """Пункт слова: по коду, если текст тот же; иначе по тексту, только если такой
    текст в пресете один («на верхней челюсти.» есть у нескольких групп)."""
    text = ' '.join(e.item_text.split())
    it = wb.by_id.get(e.code) if e.code else None
    if it is not None and ' '.join(it.text.split()) == text:
        return it
    same = by_text.get(text, [])
    return same[0] if len(same) == 1 else None


def _apply_dictionary(wb: Workbook, ctx: _Ctx) -> None:
    """Слова врача — раньше правил: вариант своей группы или отдельный пункт.
    Несколько слов на одну группу — берётся первое по записи."""
    by_text: dict[str, list[Item]] = {}
    for it in wb.items:
        by_text.setdefault(' '.join(it.text.split()), []).append(it)
    hits = []
    tokens = {id(e) for e in ctx.tokens}
    for e in ctx.tokens + list(wb.dictionary):       # токен записи — раньше словаря
        m = next((m for m in re.finditer(_phrase_rx(e.word), ctx.n)
                  if not _negated_at(ctx.n, m.start(), m.end())), None)
        if m is None:
            continue
        it = _dictionary_item(wb, e, by_text)
        if it is None:
            ctx.warn(f'слово «{e.word}» больше не находит пункт')
            continue
        hits.append((m.start(), e.word, it, m.end(), id(e) in tokens))
    for start, word, it, end, is_token in sorted(hits, key=lambda h: (h[0], not h[4])):
        if not is_token:                 # счётчик «сработало» — только у словаря
            ctx.dictionary_hits.append(word)
        group = wb.by_id.get(it.parent) if it.level == 3 and not it.orphan else None
        if group is None:
            ctx.forced_singles.add(it.id)
        elif rule_kind(group) == 'elastics' and any(
                c is not it and _elastic_named(c, re.sub(_phrase_rx(word),
                                                         lambda m: ' ' * len(m.group()), ctx.n))
                for c in group.children):
            # «тяги перепел»: вариант, названный другим словом, главнее выученного
            # («лиса» = «Медведь» — то же слово: выученное главнее)
            continue
        elif group.id in ctx.forced and ctx.forced[group.id] is it:
            continue                    # то же слово и токеном, и в словаре — не спор
        elif group.id in ctx.forced:
            ctx.warn(f'«{group.text.strip()}»: несколько слов врача — взято первое по записи')
        else:
            ctx.forced[group.id] = it


def _shown(item: Item, when: str, said: _Said, facts: Facts, ctx: _Ctx) -> bool:
    """Выводится ли отдельный пункт: «всегда» / «если упомянут» / «по условию»;
    условие выводит строку только при «да». Слово врача — сказано: строка есть,
    а если условие против — «проверьте» (противоречие показать, не решать)."""
    cond = effective_condition(item, ctx.wb)
    ok = evaluate(cond, facts) is True
    if item.id in ctx.forced_singles:
        if cond is not None and not ok:
            ctx.flag(item.id, 'по условию этой строки быть не должно — проверьте')
        return True
    if when == 'always':
        return ok
    if when == 'mentioned':
        return item.id in said and ok
    return cond is not None and ok


def _check_pairs(wb: Workbook, lines: list[tuple[str, str]], ctx: _Ctx) -> None:
    """Пары «не вместе»: обе строки в протоколе — обеим «проверьте»."""
    have = {c for c, _ in lines}
    for a, b in wb.not_together:
        if a in have and b in have:
            ta, tb = (' '.join(wb.by_id[c].text.split())[:50] for c in (a, b))
            msg = f'«{ta}» и «{tb}» не бывают вместе — проверьте'
            ctx.warn(msg)
            ctx.flag(a, msg)
            ctx.flag(b, msg)


def build_protocol(wb: Workbook, raw: str, tokens: list[tuple[str, str]] | None = None) -> Protocol:
    """tokens — слова записи, привязанные к пунктам принятой подсказкой (слово,
    код): разбираются как слова врача, но только для этой записи."""
    ctx = _Ctx(raw, wb)
    ctx.tokens = [DictEntry(w, wb.by_id[c].text, c) for w, c in (tokens or ()) if c in wb.by_id]
    for w, c in tokens or ():
        if c not in wb.by_id:
            ctx.warn(f'слово «{w}» больше не находит пункт')
    if ctx.f['system_type'] is None:
        ctx.warn('тип системы не распознан (лигатурная / самолигирующая)')
    cl = ctx.f['classes']
    if cl['molar'] is None and cl['canine'] is None and \
            re.search(r'класс\w*\s*(?:[1-3]|i{1,3})\b|(?:[1-3]|i{1,3})\s*класс', ctx.n):
        ctx.warn('класс: не указано, по молярам или по клыкам — допишите вручную')
    if ctx.f['wire_no_arch']:
        ctx.default('дуга на обеих челюстях (челюсть не указана)')
    when = _effective_when(wb)
    _apply_dictionary(wb, ctx)
    said = _Said(ctx)
    ctx.mentioned_singles = [it for s in wb.sections for it in s.children
                             if not it.children and not it.orphan and when[it.id] != 'always'
                             and it.id in said]
    # проход 1: все группы (факты для условий не зависят от порядка разделов)
    complaint = {s.id for s in wb.sections if norm(s.text).startswith('жалоб')}
    chosen: dict[str, object] = {}
    for s in wb.sections:           # порядок разделов — как раньше (строка «по умолчанию»)
        if s.id in complaint:
            ctx.current = s.id
            chosen[s.id] = _select_complaint(s, ctx)
            ctx.current = None
            continue
        for item in s.children:
            if item.children:
                chosen[item.id] = _select_or_default(item, ctx)
    if ctx.f['wire_hint'] and not ctx.f['wires']:    # дуга упомянута, но не распознана
        ctx.unclear |= {g.id for g in wb.items if g.children and rule_kind(g) == 'wire'
                        and g.id not in ctx.picked}
    facts = _facts(ctx, said)
    # проход 2: строки по разделам
    lines: list[tuple[str, str]] = []
    for section in wb.sections:
        out: list[tuple[str, str]] = []
        if section.id in complaint:
            sel = chosen[section.id]
            if sel:
                out.append((sel.id, sel.text))
        else:
            for item in section.children:
                if item.children:
                    sel = chosen[item.id]
                    if sel is not None:     # [] — группа упомянута, вариант не выбран
                        out.append((item.id, item.text))
                        for c in (sel if isinstance(sel, list) else [sel]):
                            detail = ctx.details.get(c.id)
                            text = c.text.rstrip().rstrip('.') + ' ' + detail if detail else c.text
                            out.append((c.id, text))
                elif _shown(item, when[item.id], said, facts, ctx):
                    out.append((item.id, item.text))
        if out:
            lines += [(section.id, section.text)] + out
    _check_pairs(wb, lines, ctx)
    if ctx.f['wire_hint'] and not ctx.f['wires']:
        ctx.warn('дуга: упоминание не распознано — проверьте вручную')
    return Protocol(lines, ctx.warnings, ctx.defaults, render_rows(wb, lines, ctx.flags),
                    ctx.dictionary_hits)


def _select_or_default(group: Item, ctx: _Ctx):
    """Выбор правилом; если врач не написал (правило ничего не выбрало или
    подставило своё «по умолчанию») — вариант по умолчанию из пресета."""
    if group.id in ctx.forced:          # слово врача — без правила и без «проверьте»
        ctx.picked[group.id] = ([ctx.forced[group.id]], True)
        return ctx.forced[group.id]
    sel = _select_rule_or_default(group, ctx)
    return sel


def _select_rule_or_default(group: Item, ctx: _Ctx):
    n_def, n_warn = len(ctx.defaults), len(ctx.warnings)
    n_flag = len(ctx.flags.get(group.id, []))
    ctx.current = group.id
    try:
        sel = _select(group, ctx)
    finally:
        ctx.current = None
    # факт для условий — только выбор по записи: правило ничего не подставило
    # (умолчание, «ближайший» вариант, материал/челюсть по умолчанию) и ни в чём
    # не усомнилось (предупреждение, «проверьте»)
    record = (len(ctx.defaults) == n_def and len(ctx.warnings) == n_warn
              and len(ctx.flags.get(group.id, [])) == n_flag
              and not (rule_kind(group) == 'wire' and ctx.f['wire_no_arch']))
    if sel is None and len(ctx.warnings) > n_warn:
        ctx.unclear.add(group.id)
    if sel and rule_kind(group) == 'wire' and ctx.f['wire_no_arch']:
        ctx.flag(group.id, 'челюсть не указана — дуга на обеих')
    if sel and rule_kind(group) is None:
        ctx.flag(group.id, 'выбрано по словам записи — проверьте')
    if ctx.wb is not None and ctx.wb.star_mode:
        # «*»: само в отчёт — только отмеченный вариант; правила-умолчания выключены
        if sel and record:
            _pick(ctx, group, sel, record)
            return sel
        del ctx.defaults[n_def:]
        marked = star_default(group)
        if not marked:
            if sel is not None and not record and len(ctx.warnings) == n_warn:
                ctx.flags.pop(group.id, None)
            return None
        ctx.default(f'{group.text.strip()} {", ".join(c.text.strip() for c in marked)}')
        _pick(ctx, group, marked, False)
        return marked if group.combine == 'and' else marked[0]
    target = group.default and next((c for c in group.children if c.id == group.default), None)
    if not target or len(ctx.warnings) > n_warn:
        _pick(ctx, group, sel, record)
        return sel
    if sel is None or len(ctx.defaults) > n_def:
        del ctx.defaults[n_def:]
        ctx.default(f'{group.text.strip()} {target.text.strip()}')
        _pick(ctx, group, [target], False)
        return target
    _pick(ctx, group, sel, record)
    return sel


def _pick(ctx: _Ctx, group: Item, sel, record: bool) -> None:
    if sel is not None:
        ctx.picked[group.id] = (sel if isinstance(sel, list) else [sel], record)
        if sel == []:
            ctx.picked[group.id] = ([], record)


class _Said:
    """Упомянут ли в записи пункт (его слова или слово врача) или группа (выбор
    по записи). Считается по запросу и запоминается: проверка слов — самое
    дорогое в разборе, а пунктам «всегда» она не нужна."""

    def __init__(self, ctx: _Ctx):
        self.ctx, self._memo = ctx, {}

    def get(self, code: str) -> bool | None:
        """Да / нет / неизвестно. Группа: выбор по записи или «упомянута без
        варианта» — да; правило что-то подставило или не распознало — неизвестно;
        правило ничего не нашло — нет. Пункта нет в пресете — неизвестно."""
        if code not in self._memo:
            ctx, it = self.ctx, self.ctx.wb.by_id.get(code)
            if code in ctx.picked:
                sel, record = ctx.picked[code]
                self._memo[code] = True if (record or sel == []) else None
            elif code in ctx.unclear or it is None:
                self._memo[code] = None
            elif it.children:
                # не выбрана, но названа словами заголовка («смена дуги на верхней» без
                # размера) — неизвестно; ошибка здесь безопасна: «неизвестно» не выводит
                stems = _stems(it.text)
                hits = sum(stem_in(st, ctx.n) for st in stems)
                named = (stems and hits >= min(2, len(stems))) or \
                    (it.words and _mention(it.words, ctx.n) is not None)
                self._memo[code] = None if named else False
            else:
                self._memo[code] = it.id in ctx.forced_singles or (
                    _best_by_words([it], ctx.n) is not None if it.orphan
                    else _single_mentioned(it, ctx))
        return self._memo[code]

    def __contains__(self, code: str) -> bool:
        return self.get(code) is True


def _facts(ctx: _Ctx, said: _Said) -> Facts:
    known = {g: {c.id for c in sel} for g, (sel, rec) in ctx.picked.items() if rec and sel}
    return Facts(known, said)


def _key(line: tuple[str, str]) -> tuple[str, str]:
    return line[0], ' '.join(line[1].split())


def protocol_for(wb: Workbook, raw: str) -> Protocol:
    """Протокол записи любого вида: строки-пути оболочки (0.5) — из путей,
    иначе — разбор записи."""
    from .shell import SEP
    if SEP.strip() in raw:
        from .shellproto import shell_protocol
        return shell_protocol(wb, raw)
    return build_protocol(wb, raw)


def check_references(wb: Workbook, protocols: list[Protocol] | None = None) -> list[CaseResult]:
    """Сверка по пунктам (кодам и их порядку), не по тексту. Строка эталона без
    кода (своя строка врача) не проверяется; строка с кодом группы и своим
    текстом — «формулировка врача»: подходит любой вариант этой группы."""
    results = []
    for k, case in enumerate(wb.references):
        p = protocols[k] if protocols is not None else protocol_for(wb, case.raw)
        got = [c for c, _ in p.lines]
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
        ref_text = {c: t for c, t in case.lines if c}

        def text_of(c: str) -> tuple[str, str]:
            # пункта нет в пресете (удалён) — текст из строки эталона
            return c, wb.by_id[c].text if c in wb.by_id else ref_text.get(c, '')
        results.append(CaseResult(
            case.case_id, got == exp,
            missing=[text_of(c) for c in exp if c not in got],
            extra=[text_of(c) for c in got if c not in exp],
            own_lines=own))
    return results

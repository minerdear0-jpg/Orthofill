"""Разбор краткой записи врача в факты. Чего нет в записи — None:
умолчания подставляет engine и сообщает о них врачу."""
import re

from .text import norm


def parse_system_type(n):
    if 'самолигир' in n:
        return 'self_ligating'
    if 'лигатур' in n:
        return 'ligature'
    return None

def parse_stage(n):
    if 'детализ' in n:
        return 'detail'
    if 'начальн' in n or 'нивелир' in n:
        return 'initial'
    if 'рабоч' in n:
        return 'working'
    return None

def clause(n, pattern, stops='.;'):
    """Фрагмент raw от совпадения pattern до ближайшего знака из stops."""
    m = re.search(pattern, n)
    if not m:
        return ''
    # знак внутри числа («0.014», «0,018») — не конец фрагмента
    stop = re.compile('[' + re.escape(stops) + r'](?!\d)')
    s = stop.search(n, m.end())
    return n[m.start():s.start() if s else len(n)]

# Упоминание челюсти: верх/верхняя/сверху/в/ч/вч, низ/нижняя/снизу/н/ч/нч, обе/обеих/обоих
ARCH_RE = re.compile(
    r'(?P<both>\bоб(?:е|еих|оих)\b)'
    r'|(?P<upper>\bс?верх\w*|\bв\s*/\s*ч\b|\bвч\b)'
    r'|(?P<lower>\bс?ни[зж]\w*|\bн\s*/\s*ч\b|\bнч\b)')

def arch_marks(text):
    """[(позиция начала, позиция конца, 'upper'|'lower'|'both'), ...]"""
    return [(m.start(), m.end(), m.lastgroup) for m in ARCH_RE.finditer(text)]

def arches_in(fragment):
    found = {a for _, _, a in arch_marks(fragment)}
    if 'both' in found or {'upper', 'lower'} <= found:
        return 'both'
    return found.pop() if found else None

_CLASS_NUM = r'([1-3]|i{1,3})(?![\w])'

def _class_val(v):
    return {'i': 1, 'ii': 2, 'iii': 3}.get(v) or int(v)

def parse_classes(n):
    """Класс моляров и клыков. Число относится к слову, рядом с которым стоит:
    «по молярам 1», «моляры - II», «1 класс по клыкам»."""
    result = {'molar': None, 'canine': None}
    keys = {'моляр': 'molar', 'клык': 'canine'}
    # слово → число («по молярам 1 и клыкам»: 1 — только моляры)
    for m in re.finditer(r'(моляр|клык)\w*\s*[-:]?\s*(?:по\s+)?' + _CLASS_NUM, n):
        k = keys[m.group(1)]
        if result[k] is None:
            result[k] = _class_val(m.group(2))
    # число → слово («1 класс по молярам»)
    for m in re.finditer(r'(?<![\w.,])' + _CLASS_NUM +
                         r'\s*(?:класс\w*\s*)?(?:по\s+)?(моляр|клык)', n):
        k = keys[m.group(2)]
        if result[k] is None:
            result[k] = _class_val(m.group(1))
    return result

# ---------- ДУГИ ----------
# Число размера: 0.016 / 0,016 / .016 / 016 / 16  → «16»
_NUM = r'(?:0?[.,])?0?(\d{2})(?!\d)'
# Разделитель сечения: x (лат.), х (кир.), *, -, /, «на», точка, запятая, пробел
_SIZE2 = re.compile(r'(?<![\d.,])' + _NUM +
                    r'\s*(?:x|х|\*|-|/|на|[.,]|\s)\s*' + _NUM)
_SIZE1 = re.compile(r'(?<![\d.,])' + _NUM)

# Порядок важен: CuNiTi проверяем раньше NiTi («кунити» содержит «нити»)
_MATERIALS = [
    ('CuNiTi', r'c[uy]\s*-?\s*ni\s*-?\s*ti|ку\s*-?\s*ни\s*-?\s*ти|медн\w*|купрум'),
    ('TMA',    r'\btma\b|\bтма\b|бета\s*-?\s*титан|\bbeta\b|β|молибд'),
    ('SS',     r'\bss\b|\bсс\b|стал\w*|\bsteel\b|нерж\w*'),
    ('NiTi',   r'(?<![a-z])ni\s*-?\s*ti|(?<![а-я])ни\s*-?\s*ти|никел\w*'),
]

def detect_material(text):
    for name, rx in _MATERIALS:
        if re.search(rx, text):
            return name
    return None

def detect_size(text):
    """Первое правдоподобное сечение: круглое 12–21 или прямоугольное
    (12–21)×(22–28): глубина у ортодонтических дуг .022/.025/.028."""
    for m in _SIZE2.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if 12 <= a <= 21 and 22 <= b <= 28:
            return (m.group(1), m.group(2))
    for m in _SIZE1.finditer(text):
        if 12 <= int(m.group(1)) <= 21:
            return (m.group(1), None)
    return None

# Пункт записи про другое действие — не часть фразы о дуге
_WIRE_STOP = (r'лигатур|подвяз|эластик|явк|изгиб|юстир|гигиен|слизист|эрози|брекет|'
              r'отклеи|выход|перелом|динамик|класс|моляр|клык|этап|зуб|переклей|'
              r'пружин|недел')
# Слово про другое действие — отдельный «пункт», обрывающий фразу о дуге
# (работает и в записи без запятых: «лигатурная дуга верх 16х25 нити явка 4 нед»)
_SPLIT = re.compile(r'[;\n]|[.,](?!\d)|(\S*(?:' + _WIRE_STOP + r')\S*)')
_NEGATION = re.compile(r'без\s+(?:замен|смен|изменен)|не\s+мен|\bостав|прежн')

def _strong_wire(item):
    """Дуга без слова «дуга»: размер + материал или челюсть + сечение 16х25."""
    size, mat = detect_size(item), detect_material(item)
    return bool(size and mat) or bool(size and size[1] and arch_marks(item))

def _wire_items(n):
    """Текст про дуги: непрерывная цепочка пунктов, где есть «дуг», размер,
    материал или челюсть. Слова про лигатуры, эластики, явку и т.п. цепочку
    обрывают. Цепочка засчитывается, если в ней есть «дуг» или явная дуга."""
    items = [p.strip() for p in _SPLIT.split(n) if p is not None]
    runs, cur, ok = [], [], False
    for it in items + ['']:
        wireish = bool(it) and not re.search(_WIRE_STOP, it) and (
            'дуг' in it or detect_size(it) or detect_material(it) or arch_marks(it))
        if wireish:
            cur.append(it)
            ok |= 'дуг' in it or _strong_wire(it)
        else:
            if cur and ok:
                runs.append(', '.join(cur))
            cur, ok = [], False
    return runs

def wire_hint(n):
    """В записи есть явный признак дуги (материал или сечение 16х25)."""
    if _NEGATION.search(n):        # «оставили 14 нити» — дугу не меняли
        return False
    size = detect_size(n)
    return detect_material(n) is not None or bool(size and size[1])

def _spec(text):
    if _NEGATION.search(text):
        return 'skip'
    size, mat = detect_size(text), detect_material(text)
    return (size, mat) if (size or mat) else None

def parse_wire_from_raw(n):
    """{'upper'|'lower': ((ширина, глубина|None) | None, материал | None)}

    Текст режем по упоминаниям челюстей. Пример: «замена дуги верх 16х25 нити,
    низ 14 нити» → [префикс «замена дуги»] [верх: 16х25 нити] [низ: 14 нити].
    Если размер стоит ДО челюсти («16 нити верх, 14 низ»), сдвигаем на один."""
    result = {}
    for region in _wire_items(n):
        marks = arch_marks(region)
        bounds = [m[0] for m in marks] + [len(region)]
        prefix = _spec(region[:bounds[0]])
        after = [_spec(region[m[1]:bounds[i + 1]]) for i, m in enumerate(marks)]

        if not marks:
            if prefix and prefix != 'skip':
                result['upper'] = result['lower'] = prefix
            continue

        # «16 нити верх, 14 низ»: размер перед челюстью, после последней — пусто
        if prefix and prefix != 'skip' and after[-1] is None:
            specs = [prefix] + after[:-1]
        else:
            specs = after
        # Челюсть без своего размера берёт соседний: «верх и низ 16х25 нити»
        for i, s in enumerate(specs):
            if s is None:
                nxt = next((x for x in specs[i + 1:] if x not in (None, 'skip')), None)
                prv = next((x for x in reversed(specs[:i]) if x not in (None, 'skip')),
                           prefix if prefix != 'skip' else None)
                specs[i] = nxt or prv
        for (_, _, arch), s in zip(marks, specs):
            if s in (None, 'skip'):
                continue
            for a in (('upper', 'lower') if arch == 'both' else (arch,)):
                result[a] = s

    # Материал назван один раз на всё: «верх 16x25, низ 14, нити»
    mats = {m for _, m in result.values() if m}
    if len(mats) == 1:
        mat = mats.pop()
        result = {a: (s, m or mat) for a, (s, m) in result.items()}
    return result

def parse_wire_from_label(label):
    n = norm(label)
    arch = 'upper' if 'верхн' in n else 'lower' if 'нижн' in n else None
    return arch, detect_size(n), detect_material(n)


def parse_weeks(n):
    """Срок явки — из фразы про явку («явка через 4 нед»), а не первое
    «N нед» в записи («перепел на 2 недели» — не явка). Месяцы → ×4."""
    frag = clause(n, r'явк|через', stops='.;,')
    text = frag if frag else n
    m = re.search(r'(\d+)\s*(?:-?х\s*)?нед', text)
    if m:
        return int(m.group(1))
    m = re.search(r'(\d+)\s*(?:-?х\s*)?мес', text)
    return int(m.group(1)) * 4 if m else None

_BAD = r'неудовлетвор|не\s*удовл|неуд\b|плох'
_GOOD = r'удовлетвор|удовл|хорош|норм'

def _good_or_bad(n, topic):
    """'unsatisfactory' / 'satisfactory'; 'unknown' — тема есть, значение не понято;
    None — тема не упомянута."""
    frag = clause(n, topic, stops='.;,')
    if not frag:
        return None
    if re.search(_BAD, frag):
        return 'unsatisfactory'
    if re.search(_GOOD, frag):
        return 'satisfactory'
    return 'unknown'

def parse_hygiene(n):
    return _good_or_bad(n, r'гигиен')

def parse_bracket_state(n):
    return _good_or_bad(n, r'брекет\w*[\s-]*систем|состояни\w*\s+брекет')

def parse_mucosa(n):
    if re.search(r'без\s+эрози|эрози\w*\s+нет|нет\s+эрози', n):
        return 'normal'
    if 'эрози' in n:
        return 'erosion'
    if re.search(r'слизист\w*[^.;,]*(норм|без\s+(?:видим|патолог|изменен))', n):
        return 'normal'
    if 'слизист' in n:
        return 'unknown'
    return None

def parse_dynamics(n):
    if re.search(r'без\s+(?:\w+\s+)?(?:динамик|существен)|нет\s+динамик', n):
        return 'no_dynamics'
    if re.search(r'динамик\w*[^.;,]*(план|положит|есть)|по\s+плану', n):
        return 'plan'
    return None

def parse_ligature_change(n, st):
    if re.search(r'(смен|замен)\w*\s+[^.;]*лигатур|лигатур\w*\s+(смен|замен)', n):
        return True
    return st == 'ligature'

def parse_ligature_arches(n):
    """Челюсть — только во фрагменте про лигатуры (не «дуга на верху»)."""
    return arches_in(clause(n, r'лигатур(?!н)', stops='.;,'))

def parse_binding_arches(n):
    return arches_in(clause(n, r'подвяз', stops='.;,'))

def parse_wire_adjustments(n):
    out = []
    for order, stem in ((1, 'перв'), (2, 'втор'), (3, 'трет')):
        if re.search(rf'изгиб\w*\s+{stem}|{stem}\w*\s+порядк', n):
            out.append(order)
    return out

def extract_facts(raw: str) -> dict:
    n = norm(raw)
    st = parse_system_type(n)
    return {
        'raw_norm': n,
        'system_type': st,
        'stage': parse_stage(n),
        'classes': parse_classes(n),
        'wires': parse_wire_from_raw(n),
        'weeks': parse_weeks(n),
        'hygiene': parse_hygiene(n),
        'mucosa': parse_mucosa(n),
        'bracket_state': parse_bracket_state(n),
        'dynamics': parse_dynamics(n),
        'ligature_change': parse_ligature_change(n, st),
        'ligature_arches': parse_ligature_arches(n),
        'binding': 'подвяз' in n,
        'binding_arches': parse_binding_arches(n),
        'wire_adjustments': parse_wire_adjustments(n),
        'mentions_elastics': re.search(r'эластик|резин|тяг', n) is not None,
        'mentions_visit': 'явк' in n,
        'complaint_text': _complaint_text(n),
        'classes_sided': re.search(r'(?:моляр|клык)[^.;]*?(?:справа|слева)|'
                                   r'(?:справа|слева)[^.;]*?(?:моляр|клык)', n) is not None,
        'wire_hint': wire_hint(n),
    }

def _complaint_text(n):
    """Что врач написал после «жалобы» (без «жалоб нет/не предъявляет»)."""
    frag = clause(n, r'жалоб\w*', stops='.;,')
    frag = re.sub(r'^жалоб\w*\s*:?\s*', '', frag).strip()
    if not frag or re.search(r'^(нет|не\s+пред|отсутств)', frag):
        return ''
    return frag

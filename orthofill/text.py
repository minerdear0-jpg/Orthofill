"""Нормализация текста: записи врача и пунктов классификатора."""
import re

# Слово, набранное в двух раскладках («СuNiTi», «NiТi», «нижнeй»), приводим
# к той раскладке, букв которой в нём больше.
_TO_LAT = str.maketrans('АВСЕНКМОРТХУИаеорсхутнкмиі',
                        'ABCENKMOPTXUIaeopcxutnkmii')
_TO_CYR = str.maketrans('ABCEHKMOPTXYaeopcxykmth',
                        'АВСЕНКМОРТХУаеорсхукмтн')
_WORD = re.compile(r'[A-Za-zА-Яа-яЁёІі]+')


def _fix_mixed_word(m: re.Match) -> str:
    w = m.group(0)
    cyr = len(re.findall(r'[а-яёА-ЯЁіІ]', w))
    lat = len(re.findall(r'[a-zA-Z]', w))
    if not cyr or not lat:
        return w
    return w.translate(_TO_LAT) if lat >= cyr else w.translate(_TO_CYR)


def norm(t: str | None) -> str:
    """Нижний регистр, одна раскладка в слове, ё→е, ×→x, тире→дефис,
    <br> и переводы строк → пробел, без лишних пробелов."""
    if t is None:
        return ''
    s = re.sub(r'<br\s*/?>', ' ', str(t), flags=re.I)
    s = _WORD.sub(_fix_mixed_word, s)
    s = s.lower().replace('ё', 'е').replace('×', 'x')
    s = s.replace('–', '-').replace('—', '-')
    return re.sub(r'\s+', ' ', s).strip()


def word_stem(word: str) -> str:
    """Основа для поиска названия варианта в записи («Перепел» → «перепе»,
    «Лиса» → «лис»): короткое слово без последней буквы, длинное — без двух."""
    w = norm(word)
    cut = 1 if len(w) <= 4 else 2
    return w[:max(3, len(w) - cut)]


def stem_in(stem: str, n: str) -> bool:
    """Есть ли в нормализованном тексте n слово, начинающееся с stem."""
    return bool(stem) and re.search(r'(?<![а-яa-z])' + re.escape(stem), n) is not None

"""0.5 beta 7: чем варианты одной группы отличаются друг от друга (без Tk).

Тексты вариантов часто начинаются одинаково («Слизистая оболочка губ, щёк… влажная,
без…» / «…влажная, в области…») — в карусели их не различить. Здесь — подпись по
отличающейся части и куски текста, которых нет у соседа (для подсветки в просмотре)."""
import difflib
import re

_WORD = re.compile(r'\S+')


def _norm(text: str) -> str:
    return ' '.join(text.split())


def distinct_labels(texts: list[str], min_common: int = 20) -> list[str]:
    """«…хвост» по словам, если у всех вариантов общее начало не короче min_common
    символов; иначе тексты как есть (пробелы схлопнуты)."""
    norm = [_norm(t) for t in texts]
    if len(norm) < 2:
        return norm
    words = [t.split(' ') for t in norm]
    k = 0
    while all(len(w) > k for w in words) and len({w[k] for w in words}) == 1:
        k += 1
    common = len(' '.join(words[0][:k])) + (1 if k else 0)
    if common < min_common or any(len(w) == k for w in words):
        return norm
    return ['…' + t[common:] for t in norm]


def diff_spans(text: str, other: str) -> list[tuple[int, int]]:
    """Куски text (начало, конец), которых нет в other, — по словам; соседние слова
    сливаются в один кусок."""
    mine = [(m.start(), m.end(), m.group()) for m in _WORD.finditer(text)]
    theirs = _WORD.findall(other)
    sm = difflib.SequenceMatcher(a=[w for *_, w in mine], b=theirs, autojunk=False)
    same = set()
    for blk in sm.get_matching_blocks():
        same.update(range(blk.a, blk.a + blk.size))
    spans: list[tuple[int, int]] = []
    for i, (s, e, _) in enumerate(mine):
        if i in same:
            continue
        if spans and i - 1 not in same and i > 0:
            spans[-1] = (spans[-1][0], e)
        else:
            spans.append((s, e))
    return spans

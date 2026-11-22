"""Запасной вариант русского названия: практическая транскрипция латиницы кириллицей.

Нужна только для тайтлов, у которых в TMDB нет русского названия (или тайтл там не найден):
так в каталоге не остаётся названий латиницей. Настоящее русское название из TMDB всегда
имеет приоритет. Отключить запасной вариант: enrich.TRANSLITERATE_FALLBACK = False.
"""
import re

LATIN = re.compile("[A-Za-z]")
CYRILLIC = re.compile("[А-Яа-яЁё]")

_DIGRAPHS = {"shch": "щ", "sch": "ск", "tch": "ч", "sh": "ш", "ch": "ч", "zh": "ж", "kh": "х",
             "ph": "ф", "th": "т", "ck": "к", "qu": "кв", "ee": "и", "oo": "у", "ts": "ц",
             "yu": "ю", "ya": "я", "yo": "ё", "ey": "ей", "ay": "ай", "oy": "ой"}
_SINGLE = dict(zip("abdfhijklmnoprstuvwxyz",
                   ["а", "б", "д", "ф", "х", "и", "дж", "к", "л", "м", "н", "о", "п", "р", "с",
                    "т", "у", "в", "в", "кс", "й", "з"]))
_VOWELS = set("aeiouy")


def has_latin_only_name(text: str) -> bool:
    """Есть ли в названии латиница и нет кириллицы (то есть его стоит заменить)."""
    return bool(LATIN.search(text)) and not CYRILLIC.search(text)


_WORDS = {"the": "зе", "of": "оф", "on": "он", "to": "ту", "and": "энд", "in": "ин", "a": "э", "for": "фор",
          "my": "май", "you": "ю", "me": "ми", "is": "из", "at": "эт", "no": "ноу", "it": "ит",
          "your": "ёр", "with": "виз", "from": "фром", "love": "лав"}


def _word(word: str) -> str:
    """Транскрипция одного слова латиницей."""
    low = word.lower()
    if low in _WORDS:
        out = _WORDS[low]
        return out.capitalize() if word[0].isupper() else out
    if len(low) > 3 and low.endswith("e") and low[-2] not in _VOWELS:     # немая конечная «e»: Code, Move
        low, word = low[:-1], word[:-1]
    out, i = [], 0
    while i < len(low):
        ch = low[i]
        for size in (4, 3, 2):                              # сначала самые длинные сочетания
            chunk = low[i:i + size]
            if len(chunk) == size and chunk in _DIGRAPHS:
                piece, step = _DIGRAPHS[chunk], size
                break
        else:
            step, prev, nxt = 1, (low[i - 1] if i else ""), low[i + 1:i + 2]
            if ch == "e":
                piece = "э" if not prev or prev in _VOWELS else "е"
            elif ch == "c":
                piece = "с" if nxt in ("e", "i", "y") else "к"
            elif ch == "g":
                piece = "дж" if nxt in ("e", "i") and i + 2 < len(low) else "г"
            else:
                piece = _SINGLE.get(ch, "к")
        out.append(piece.capitalize() if word[i].isupper() else piece)
        i += step
    return "".join(out)


def transliterate(text: str) -> str:
    """Латиница → кириллица, остальные символы (цифры, знаки, иероглифы) остаются как есть."""
    return re.sub("[A-Za-z]+", lambda m: _word(m.group()), text)

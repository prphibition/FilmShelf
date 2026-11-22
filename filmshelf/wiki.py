"""Википедия как бесплатный источник без ключа: русское название, описание и постер тайтла.

Как это работает (для одного тайтла, 2–3 запроса):
1. В английской (для латинских названий) или русской (для кириллических) Википедии ищется статья
   «название + год + film/TV series»; подходит статья, чьё название (без пояснения в скобках)
   совпадает с названием тайтла, а год в скобках – с годом выхода (±1).
2. Русское название берётся из межъязыковой ссылки статьи, постер – её главное изображение
   (обычно это постер из карточки фильма).
3. Краткое описание – первые предложения русской статьи.
Тексты Википедии распространяются по лицензии CC BY-SA, изображения – по условиям их страниц.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional, Sequence

from .database import normalize
from .services import ServiceError

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
USER_AGENT = "FilmShelf/1.0 (personal desktop movie catalog; educational project)"
CYRILLIC = re.compile("[А-Яа-яЁё]")
_PAREN = re.compile(r"\s*\(([^)]*)\)\s*$")
_FILMISH = re.compile(r"film|series|tv|anime|drama|miniseries|фильм|сериал|аниме|мультфильм|дорама", re.I)
_YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
SUMMARY_LIMIT = 700


class WikiError(ServiceError):
    """Нет связи с Википедией или она не отвечает."""


@dataclass
class WikiResult:
    page_id: int
    ru_name: str = ""            # русское название (пусто, если у статьи нет русской версии)
    summary: str = ""            # начало русской статьи
    image: Optional[bytes] = None


def _get(url: str, timeout: int = 20) -> Optional[bytes]:
    """GET с повторами; 404 даёт None, сетевой сбой – WikiError."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code == 429 or 500 <= exc.code < 600:      # лимит или сбой сервера – ждём и повторяем
                time.sleep(float(exc.headers.get("Retry-After", 1 + attempt)) if exc.code == 429 else 1 + attempt)
            else:
                raise WikiError(f"Ошибка Википедии: HTTP {exc.code}.")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            if attempt == 2:
                raise WikiError(f"Нет связи с Википедией: {exc}")
            time.sleep(1 + attempt)
    raise WikiError("Википедия не отвечает.")


def _api(api: str, lang: str, params: dict) -> list:
    """Запрос к API MediaWiki; возвращает список страниц ответа (formatversion=2)."""
    url = api.format(lang=lang) + "?" + urllib.parse.urlencode({"action": "query", "format": "json",
                                                                 "formatversion": "2", "redirects": "1", **params})
    raw = _get(url)
    try:
        return (json.loads(raw).get("query") or {}).get("pages") or [] if raw else []
    except ValueError:
        return []


def strip_parenthetical(title: str) -> str:
    """«Parasite (2019 film)» → «Parasite»."""
    return _PAREN.sub("", title).strip()


def _score(page: dict, year: int) -> Optional[int]:
    """Насколько статья подходит; None – не подходит (другой год, не фильм, страница неоднозначности)."""
    if (page.get("pageprops") or {}).get("disambiguation") is not None:
        return None
    paren = _PAREN.search(page.get("title", ""))
    inner = paren.group(1) if paren else ""
    years = [int(y) for y in _YEAR.findall(inner)]
    if years and all(abs(y - year) > 1 for y in years):
        return None
    if paren and not years and not _FILMISH.search(inner):    # «(band)», «(novel)» и т. п.
        return None
    return (3 if years else 0) + (1 if _FILMISH.search(inner) else 0)


def _find(api: str, lang: str, query: str, year: int, kind: str, names: set) -> Optional[dict]:
    series = kind in ("series", "drama")
    suffix = {("en", False): "film", ("en", True): "TV series", ("ru", False): "фильм", ("ru", True): "сериал"}[(lang, series)]
    pages = _api(api, lang, {
        "generator": "search", "gsrsearch": f"{query} {year} {suffix}", "gsrlimit": "6", "gsrnamespace": "0",
        "prop": "langlinks|pageimages|pageprops", "lllang": "ru", "lllimit": "20", "ppprop": "disambiguation",
        "piprop": "thumbnail", "pithumbsize": "500", "pilimit": "20"})
    best, best_key = None, None
    for page in pages:
        if normalize(strip_parenthetical(page.get("title", ""))) not in names:
            continue
        score = _score(page, year)
        if score is None:
            continue
        key = (-score, page.get("index", 99))
        if best_key is None or key < best_key:
            best, best_key = page, key
    return best


def _summary(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) > SUMMARY_LIMIT:
        cut = text[:SUMMARY_LIMIT]
        text = cut[:cut.rfind(". ") + 1] if ". " in cut else cut.rstrip() + "…"
    return text


def lookup(queries: Sequence[str], year: int, kind: str, api: str = WIKI_API,
           want_text: bool = True, want_image: bool = True) -> Optional[WikiResult]:
    """Ищет тайтл в Википедии по вариантам названия (латиница – в английской, кириллица – в русской)."""
    names = {normalize(q) for q in queries}
    page, lang = None, "en"
    for query in queries:
        lang = "ru" if CYRILLIC.search(query) else "en"
        page = _find(api, lang, query, year, kind, names)
        if page:
            break
    if not page:
        return None
    ru_title = page["title"] if lang == "ru" else next(
        (link.get("title", "") for link in page.get("langlinks") or [] if link.get("lang") == "ru"), "")
    result = WikiResult(page_id=int(page.get("pageid", 0)), ru_name=strip_parenthetical(ru_title))
    image_url = (page.get("thumbnail") or {}).get("source", "")
    if ru_title and (want_text or (want_image and not image_url)):
        for ru_page in _api(api, "ru", {"titles": ru_title, "prop": "extracts|pageimages", "exintro": "1",
                                        "explaintext": "1", "exsentences": "3", "piprop": "thumbnail",
                                        "pithumbsize": "500"}):
            result.summary = _summary(ru_page.get("extract", "")) if want_text else ""
            image_url = image_url or (ru_page.get("thumbnail") or {}).get("source", "")
    if want_image and image_url:
        result.image = _get(image_url)
    return result

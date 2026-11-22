"""Сборка большого каталога фильмов и сериалов из открытых наборов данных на GitHub.

Источники (скачиваются через raw.githubusercontent.com):
  1. prust/wikipedia-movie-data      – около 36 000 фильмов из Википедии (название, год, жанры, описание);
  2. MadoDoctor/EDA-Project-Netflix  – netflix_titles.csv: фильмы и сериалы со страной и описанием;
  3. izzulroslan/korean-drama-dataset-eda – 350 корейских дорам (число серий, рейтинг, жанры).

Результат – сжатый файл filmshelf/data/catalog.json.gz, который приложение импортирует при первом
запуске. Названия и описания остаются на английском (как в источниках); страны и жанры переведены.
Запуск из корня проекта:  python tools/build_catalog.py
"""
import csv
import gzip
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from filmshelf.database import normalize  # noqa: E402
from filmshelf.seed_data import TITLES, ALT_NAMES  # noqa: E402

RAW = "https://raw.githubusercontent.com/"
SOURCES = {
    "wiki": RAW + "prust/wikipedia-movie-data/master/movies.json",
    "netflix": RAW + "MadoDoctor/EDA-Project-Netflix/main/netflix_titles.csv",
    "kdrama": RAW + "izzulroslan/korean-drama-dataset-eda/main/kdrama_DATASET.csv",
}
OUT = ROOT / "filmshelf" / "data" / "catalog.json.gz"

COUNTRIES = {
    "United States": "США", "India": "Индия", "United Kingdom": "Великобритания", "Canada": "Канада",
    "France": "Франция", "Japan": "Япония", "Spain": "Испания", "South Korea": "Южная Корея",
    "Germany": "Германия", "Mexico": "Мексика", "Australia": "Австралия", "China": "Китай",
    "Hong Kong": "Гонконг", "Turkey": "Турция", "Egypt": "Египет", "Brazil": "Бразилия",
    "Italy": "Италия", "Philippines": "Филиппины", "Thailand": "Таиланд", "Indonesia": "Индонезия",
    "Argentina": "Аргентина", "Taiwan": "Тайвань", "Nigeria": "Нигерия", "South Africa": "ЮАР",
    "Russia": "Россия", "Poland": "Польша", "Sweden": "Швеция", "Denmark": "Дания",
    "Netherlands": "Нидерланды", "Belgium": "Бельгия", "Ireland": "Ирландия", "Norway": "Норвегия",
    "Israel": "Израиль", "Lebanon": "Ливан", "Colombia": "Колумбия", "Chile": "Чили",
    "Singapore": "Сингапур", "New Zealand": "Новая Зеландия", "Pakistan": "Пакистан",
    "United Arab Emirates": "ОАЭ", "Saudi Arabia": "Саудовская Аравия", "Malaysia": "Малайзия",
    "Czech Republic": "Чехия", "Romania": "Румыния", "Iceland": "Исландия", "Finland": "Финляндия",
    "Austria": "Австрия", "Switzerland": "Швейцария", "Greece": "Греция", "Hungary": "Венгрия",
    "Ukraine": "Украина", "Peru": "Перу", "Vietnam": "Вьетнам", "Bangladesh": "Бангладеш",
    "Kenya": "Кения", "Jordan": "Иордания", "Qatar": "Катар", "Luxembourg": "Люксембург",
    "Cambodia": "Камбоджа", "Uruguay": "Уругвай", "Venezuela": "Венесуэла", "Serbia": "Сербия",
    "Bulgaria": "Болгария", "Croatia": "Хорватия", "Morocco": "Марокко", "Ghana": "Гана",
}
NATIONALITIES = {
    "British": "Великобритания", "Canadian": "Канада", "French": "Франция", "Australian": "Австралия",
    "Indian": "Индия", "Italian": "Италия", "Japanese": "Япония", "Irish": "Ирландия",
    "German": "Германия", "Mexican": "Мексика", "Spanish": "Испания", "Swedish": "Швеция",
    "Danish": "Дания", "Chinese": "Китай", "Russian": "Россия", "Soviet": "СССР",
}
GENRES = {
    "drama": "Драма", "dramas": "Драма", "comedy": "Комедия", "comedies": "Комедия", "silent": "Немое кино",
    "western": "Вестерн", "romance": "Романтика", "romantic": "Романтика", "crime": "Криминал",
    "action": "Боевик", "thriller": "Триллер", "thrillers": "Триллер", "musical": "Мюзикл",
    "adventure": "Приключения", "horror": "Ужасы", "war": "Военный", "science fiction": "Фантастика",
    "sci-fi": "Фантастика", "mystery": "Детектив", "noir": "Нуар", "short": "Короткометражка",
    "animated": "Анимация", "animation": "Анимация", "fantasy": "Фэнтези", "biography": "Биография",
    "historical": "Исторический", "history": "Исторический", "documentary": "Документальный",
    "documentaries": "Документальный", "sports": "Спорт", "sport": "Спорт", "family": "Семейный",
    "independent": "Независимое кино", "supernatural": "Мистика", "life": "Повседневность",
    "medical": "Медицина", "youth": "Молодёжный", "business": "Бизнес", "law": "Юриспруденция",
    "political": "Политика", "melodrama": "Мелодрама", "music": "Музыка", "psychological": "Психологический",
    "school": "Школа", "food": "Еда", "military": "Военный", "friendship": "Дружба",
}
NETFLIX_GENRES = {
    "Dramas": ["Драма"], "TV Dramas": ["Драма"], "Comedies": ["Комедия"], "TV Comedies": ["Комедия"],
    "Action & Adventure": ["Боевик", "Приключения"], "TV Action & Adventure": ["Боевик", "Приключения"],
    "Children & Family Movies": ["Семейный"], "Kids' TV": ["Детский"], "Documentaries": ["Документальный"],
    "Docuseries": ["Документальный"], "Independent Movies": ["Независимое кино"],
    "Romantic Movies": ["Романтика"], "Romantic TV Shows": ["Романтика"], "Thrillers": ["Триллер"],
    "TV Thrillers": ["Триллер"], "Horror Movies": ["Ужасы"], "TV Horror": ["Ужасы"],
    "Sci-Fi & Fantasy": ["Фантастика", "Фэнтези"], "TV Sci-Fi & Fantasy": ["Фантастика", "Фэнтези"],
    "Stand-Up Comedy": ["Стендап"], "Stand-Up Comedy & Talk Shows": ["Стендап"],
    "Music & Musicals": ["Мюзикл"], "Anime Features": ["Аниме"], "Anime Series": ["Аниме"],
    "Crime TV Shows": ["Криминал"], "Reality TV": ["Реалити"], "TV Mysteries": ["Детектив"],
    "Teen TV Shows": ["Подростковый"], "Classic Movies": ["Классика"], "Cult Movies": ["Культовое кино"],
    "Sports Movies": ["Спорт"], "Science & Nature TV": ["Наука и природа"], "TV Action & Adventure ": ["Боевик"],
    "Classic & Cult TV": ["Классика"], "Horror": ["Ужасы"],
}
ASIAN = {"South Korea", "China", "Taiwan", "Thailand", "Japan", "Hong Kong"}


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:
        return resp.read()


def shorten(text: str, limit: int = 420) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > limit // 2 else cut.rsplit(" ", 1)[0] + "…")


def genres_ru(names, table=GENRES):
    out = []
    for name in names:
        value = table.get(name.strip().lower(), None) if table is GENRES else None
        if value is None and table is GENRES:
            value = name.strip().capitalize()
        for item in ([value] if isinstance(value, str) else value or []):
            if item and item not in out:
                out.append(item)
    return out or ["Другое"]


def from_wiki(raw: bytes):
    pat = re.compile(r"\b(?:is|was) an? (?:\d{4} |upcoming |unreleased )?([A-Z][a-z]+)(?:-[A-Z][a-z]+)*")
    for m in json.loads(raw):
        title, year = (m.get("title") or "").strip(), m.get("year")
        if not title or not isinstance(year, int) or not 1888 <= year <= 2030:
            continue
        found = pat.search(m.get("extract") or "")
        country = NATIONALITIES.get(found.group(1), "США") if found else "США"
        yield [title, "", "", "movie", year, country, 1, 100,
               shorten(m.get("extract") or ""), genres_ru(m.get("genres") or [])]


def from_netflix(raw: bytes):
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        title, year = (r["title"] or "").strip(), (r["release_year"] or "").strip()
        if not title or not year.isdigit():
            continue
        first = (r["country"].split(",")[0].strip() if r["country"] else "")
        country = COUNTRIES.get(first, first or "Не указана")
        listed = [x.strip() for x in r["listed_in"].split(",")]
        anime = any(x.startswith("Anime") for x in listed)
        genres = []
        for x in listed:
            for g in NETFLIX_GENRES.get(x, []):
                if g not in genres:
                    genres.append(g)
        tv = r["type"] == "TV Show"
        if anime:
            kind = "anime"
        elif tv and (first in ASIAN):
            kind = "drama"
        else:
            kind = "series" if tv else "movie"
        dur = r["duration"].split()
        number = int(dur[0]) if dur and dur[0].isdigit() else 0
        if tv:
            episodes, duration = max(1, number) * 10, 45          # оценка: 10 серий в сезоне по 45 минут
        else:
            episodes, duration = 1, number if number else 100
        yield [title, "", "", kind, int(year), country, episodes, duration,
               shorten(r["description"]), genres or ["Другое"]]


def from_kdrama(raw: bytes):
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8"))):
        title, year = (r["Title"] or "").strip(), (r["Year of release"] or "").strip()
        if not title or not year.isdigit():
            continue
        eps = r["Number of Episodes"].strip()
        yield [title, "", "", "drama", int(year), "Южная Корея", int(eps) if eps.isdigit() else 16, 65,
               shorten(r["Description"]), genres_ru(r["Genre"].split(","))]


def main() -> None:
    # названия демонстрационных тайтлов (с другими названиями): такие записи пропускаем
    demo_names = {normalize(n) for item, alt in zip(TITLES, ALT_NAMES)
                  for n in [item[0], item[1]] + alt.split(",") if n.strip()}
    seen, records = set(), []
    for key, reader in (("kdrama", from_kdrama), ("netflix", from_netflix), ("wiki", from_wiki)):
        print("загрузка", key, "…")
        added = 0
        for rec in reader(fetch(SOURCES[key])):
            signature = (normalize(rec[0]), rec[4])            # название + год: дубликаты между источниками
            if signature in seen or signature[0] in demo_names:
                continue
            seen.add(signature)
            records.append(rec)
            added += 1
        print("  добавлено:", added)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(records, fh, ensure_ascii=False, separators=(",", ":"))
    print("всего записей:", len(records), "размер файла, МБ:", round(OUT.stat().st_size / 1e6, 1))


if __name__ == "__main__":
    main()

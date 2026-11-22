"""Импорт большого каталога из сжатого файла filmshelf/data/catalog.json.gz в базу данных."""
import gzip
import json
import sqlite3
from pathlib import Path
from typing import Optional, Union

from .database import build_search_text

CATALOG_FILE = Path(__file__).parent / "data" / "catalog.json.gz"
BIG_CATALOG_THRESHOLD = 1000       # если тайтлов меньше, каталог считается не загруженным


def catalog_needed(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM titles").fetchone()[0] < BIG_CATALOG_THRESHOLD


def import_catalog(conn: sqlite3.Connection, path: Union[str, Path, None] = None) -> int:
    """Добавляет записи каталога одной транзакцией и возвращает их число (0, если файла нет).

    Формат записи: [название, оригинальное название, другие названия, тип, год, страна,
    число серий, длительность, описание, [жанры]].
    """
    path = Path(path or CATALOG_FILE)
    if not path.is_file():
        return 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        records = json.load(fh)
    genre_ids = {name: gid for gid, name in conn.execute("SELECT id, name FROM genres")}
    with conn:
        for rec in records:
            for genre in rec[9]:
                if genre not in genre_ids:
                    genre_ids[genre] = conn.execute("INSERT INTO genres (name) VALUES (?)", (genre,)).lastrowid
        first_id = (conn.execute("SELECT MAX(id) FROM titles").fetchone()[0] or 0) + 1
        rows, links = [], []
        for offset, (name, original, alt, kind, year, country, episodes, duration,
                     description, genres) in enumerate(records):
            title_id = first_id + offset
            hay, names_hay, key = build_search_text(name, original, alt, country, year, kind,
                                                    description, " ".join(genres))
            rows.append((title_id, name, original, alt, kind, year, country, max(1, episodes),
                         max(1, duration), description, hay, names_hay, key))
            links.extend((title_id, genre_ids[g]) for g in genres)
        conn.executemany(
            "INSERT INTO titles (id, name, original_name, alt_names, kind, year, country, episodes, "
            "duration, description, hay, names_hay, name_key) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        conn.executemany("INSERT OR IGNORE INTO title_genres (title_id, genre_id) VALUES (?, ?)", links)
    return len(rows)

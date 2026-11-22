"""Подключение к SQLite и создание схемы базы данных."""
import re
import sqlite3
from pathlib import Path
from typing import Union

from .config import KINDS

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    email         TEXT NOT NULL UNIQUE,
    salt          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS titles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    original_name TEXT NOT NULL DEFAULT '',
    alt_names     TEXT NOT NULL DEFAULT '',
    kind          TEXT NOT NULL CHECK (kind IN ('movie', 'series', 'drama', 'anime')),
    year          INTEGER NOT NULL CHECK (year BETWEEN 1888 AND 2100),
    country       TEXT NOT NULL,
    episodes      INTEGER NOT NULL DEFAULT 1 CHECK (episodes >= 1),
    duration      INTEGER NOT NULL DEFAULT 90 CHECK (duration >= 1),
    description   TEXT NOT NULL DEFAULT '',
    poster        TEXT NOT NULL DEFAULT '',
    votes         INTEGER NOT NULL DEFAULT 0,
    score_sum     INTEGER NOT NULL DEFAULT 0,
    name_key      TEXT NOT NULL DEFAULT '',
    names_hay     TEXT NOT NULL DEFAULT '',
    hay           TEXT NOT NULL DEFAULT '',
    enriched      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS genres (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS title_genres (
    title_id INTEGER NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    genre_id INTEGER NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
    PRIMARY KEY (title_id, genre_id)
);

CREATE TABLE IF NOT EXISTS list_entries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    title_id   INTEGER NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    status     TEXT NOT NULL CHECK (status IN
               ('watching', 'completed', 'plan', 'on_hold', 'dropped')),
    score      INTEGER CHECK (score IS NULL OR score BETWEEN 1 AND 10),
    progress   INTEGER NOT NULL DEFAULT 0 CHECK (progress >= 0),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (user_id, title_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    title_id   INTEGER NOT NULL REFERENCES titles(id) ON DELETE CASCADE,
    text       TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (user_id, title_id)
);

CREATE INDEX IF NOT EXISTS idx_titles_year     ON titles(year);
CREATE INDEX IF NOT EXISTS idx_titles_name_key ON titles(name_key);
CREATE INDEX IF NOT EXISTS idx_titles_country  ON titles(country);

-- Число оценок и их сумма хранятся в таблице titles и обновляются триггерами,
-- поэтому рейтинг не нужно вычислять агрегатным запросом по всей таблице оценок.
CREATE TRIGGER IF NOT EXISTS trg_entries_insert AFTER INSERT ON list_entries
WHEN NEW.score IS NOT NULL
BEGIN
    UPDATE titles SET votes = votes + 1, score_sum = score_sum + NEW.score WHERE id = NEW.title_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_entries_delete AFTER DELETE ON list_entries
WHEN OLD.score IS NOT NULL
BEGIN
    UPDATE titles SET votes = votes - 1, score_sum = score_sum - OLD.score WHERE id = OLD.title_id;
END;
CREATE TRIGGER IF NOT EXISTS trg_entries_update AFTER UPDATE ON list_entries
BEGIN
    UPDATE titles SET votes = votes - 1, score_sum = score_sum - OLD.score
        WHERE id = OLD.title_id AND OLD.score IS NOT NULL;
    UPDATE titles SET votes = votes + 1, score_sum = score_sum + NEW.score
        WHERE id = NEW.title_id AND NEW.score IS NOT NULL;
END;
CREATE INDEX IF NOT EXISTS idx_entries_user  ON list_entries(user_id, status);
CREATE INDEX IF NOT EXISTS idx_entries_title ON list_entries(title_id);
CREATE INDEX IF NOT EXISTS idx_reviews_title ON reviews(title_id);
"""


_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normalize(text) -> str:
    """Приводит строку к виду для поиска: нижний регистр, «ё» → «е», без знаков препинания."""
    text = str(text if text is not None else "").casefold().replace("ё", "е")
    return " ".join(_PUNCTUATION.sub(" ", text).split())


def build_search_text(name, original_name, alt_names, country, year, kind,
                      description, genres) -> tuple:
    """Возвращает (hay, names_hay, name_key) – нормализованные тексты для поиска и сортировки."""
    names = f"{name} {original_name} {alt_names}"
    hay = normalize(" ".join([names, country, str(year), KINDS.get(kind, ""), description, genres]))
    return hay, normalize(names), str(name).casefold()


def _casefold(value):
    """SQL-функция регистронезависимого сравнения (в т. ч. для кириллицы)."""
    return value.casefold() if isinstance(value, str) else value


def connect(path: Union[str, Path]) -> sqlite3.Connection:
    """Открывает соединение, включает внешние ключи и регистрирует casefold()."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("casefold", 1, _casefold, deterministic=True)
    conn.create_function("norm", 1, normalize, deterministic=True)
    conn.create_function("kind_ru", 1, lambda kind: KINDS.get(kind, ""), deterministic=True)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Создаёт таблицы, индексы и триггеры; при необходимости мигрирует базу прежней версии."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(titles)")}
    if columns:                                    # база уже существует – добавляем недостающие столбцы
        for name, ddl in (("poster", "TEXT NOT NULL DEFAULT ''"), ("alt_names", "TEXT NOT NULL DEFAULT ''"),
                          ("votes", "INTEGER NOT NULL DEFAULT 0"), ("score_sum", "INTEGER NOT NULL DEFAULT 0"),
                          ("name_key", "TEXT NOT NULL DEFAULT ''"), ("names_hay", "TEXT NOT NULL DEFAULT ''"),
                          ("hay", "TEXT NOT NULL DEFAULT ''"), ("enriched", "INTEGER NOT NULL DEFAULT 0")):
            if name not in columns:
                conn.execute(f"ALTER TABLE titles ADD COLUMN {name} {ddl}")
    conn.executescript(SCHEMA)
    if columns and "votes" not in columns:         # пересчёт счётчиков оценок для старой базы
        conn.execute("UPDATE titles SET "
                     "votes = (SELECT COUNT(score) FROM list_entries e WHERE e.title_id = titles.id), "
                     "score_sum = (SELECT COALESCE(SUM(score), 0) FROM list_entries e WHERE e.title_id = titles.id)")
    rebuild_search_text(conn)
    conn.commit()


def rebuild_search_text(conn: sqlite3.Connection) -> None:
    """Заполняет поисковые столбцы у тайтлов, где они ещё пусты."""
    rows = conn.execute(
        "SELECT t.id, t.name, t.original_name, t.alt_names, t.country, t.year, t.kind, t.description, "
        "(SELECT GROUP_CONCAT(g.name, ' ') FROM title_genres tg JOIN genres g ON g.id = tg.genre_id "
        " WHERE tg.title_id = t.id) AS genres FROM titles t WHERE t.hay = ''").fetchall()
    for r in rows:
        hay, names_hay, key = build_search_text(r["name"], r["original_name"], r["alt_names"], r["country"],
                                                r["year"], r["kind"], r["description"], r["genres"] or "")
        conn.execute("UPDATE titles SET hay = ?, names_hay = ?, name_key = ? WHERE id = ?",
                     (hay, names_hay, key, r["id"]))

"""Слой доступа к данным: все SQL-запросы приложения."""
import sqlite3
from typing import Optional

from .database import build_search_text, normalize
from .models import ListEntry, Review, SearchFilters, Title

# Параметр сглаживания взвешенного рейтинга: вес «априорного» среднего в голосах
PRIOR_WEIGHT = 3

# Допустимые способы сортировки каталога (белый список защищает от SQL-инъекций).
# «По рейтингу» – взвешенная оценка (байесовское сглаживание); тайтлы без оценок идут в конце.
SORT_CLAUSES = {
    "rating": "(votes = 0), ((score_sum + %d * ?) * 1.0 / (votes + %d)) DESC, name_key" % (PRIOR_WEIGHT, PRIOR_WEIGHT),
    "year": "year DESC, name_key",
    "name": "name_key",
}

_GENRES_COLUMN = """(SELECT GROUP_CONCAT(name, ', ') FROM
           (SELECT g.name FROM title_genres tg
            JOIN genres g ON g.id = tg.genre_id
            WHERE tg.title_id = t.id ORDER BY g.name)) AS genres"""

_ENTRY_SELECT = """
SELECT e.*, t.name AS title_name, t.kind, t.episodes, t.duration
FROM list_entries e JOIN titles t ON t.id = e.title_id
"""


def _to_title(row: sqlite3.Row) -> Title:
    votes = row["votes"]
    return Title(
        id=row["id"], name=row["name"], original_name=row["original_name"],
        kind=row["kind"], year=row["year"], country=row["country"],
        episodes=row["episodes"], duration=row["duration"],
        description=row["description"], poster=row["poster"], alt_names=row["alt_names"],
        genres=row["genres"].split(", ") if row["genres"] else [],
        avg_score=round(row["score_sum"] / votes, 2) if votes else None,
        votes=votes,
    )


def _to_entry(row: sqlite3.Row) -> ListEntry:
    return ListEntry(
        id=row["id"], user_id=row["user_id"], title_id=row["title_id"],
        title_name=row["title_name"], kind=row["kind"], status=row["status"],
        score=row["score"], progress=row["progress"], episodes=row["episodes"],
        duration=row["duration"], updated_at=row["updated_at"],
    )


class UserRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(self, username: str, email: str, salt: str,
            password_hash: str, role: str = "user") -> int:
        cur = self.conn.execute(
            "INSERT INTO users (username, email, salt, password_hash, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, email, salt, password_hash, role),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_by_username(self, username: str) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM users WHERE casefold(username) = casefold(?)",
            (username,),
        ).fetchone()

    def email_exists(self, email: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM users WHERE casefold(email) = casefold(?)", (email,)
        ).fetchone() is not None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


class TitleRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # --- условия отбора ---
    @staticmethod
    def _where(f: SearchFilters) -> tuple:
        where, params = [], []
        tokens = normalize(f.query).split()
        for token in tokens:                         # каждое слово запроса должно где-то встретиться
            where.append("instr(t.hay, ?) > 0")
            params.append(token)
        if f.kind:
            where.append("t.kind = ?")
            params.append(f.kind)
        if f.genre:
            where.append(
                "EXISTS (SELECT 1 FROM title_genres tg JOIN genres g "
                "ON g.id = tg.genre_id WHERE tg.title_id = t.id AND g.name = ?)")
            params.append(f.genre)
        if f.country:
            where.append("t.country = ?")
            params.append(f.country)
        if f.year_from is not None:
            where.append("t.year >= ?")
            params.append(f.year_from)
        if f.year_to is not None:
            where.append("t.year <= ?")
            params.append(f.year_to)
        if f.min_score is not None:
            where.append("t.votes > 0 AND t.score_sum * 1.0 / t.votes >= ?")
            params.append(f.min_score)
        return (" WHERE " + " AND ".join(where) if where else ""), params, tokens

    def global_mean(self) -> float:
        """Средняя оценка по всей системе – «априорное» значение для взвешенного рейтинга."""
        row = self.conn.execute("SELECT SUM(score_sum) * 1.0 / NULLIF(SUM(votes), 0) FROM titles").fetchone()
        return row[0] if row[0] is not None else 7.5

    def count_matching(self, f: SearchFilters) -> int:
        where, params, _ = self._where(f)
        return self.conn.execute("SELECT COUNT(*) FROM titles t" + where, params).fetchone()[0]

    def search(self, f: SearchFilters, limit: Optional[int] = None, offset: int = 0) -> list[Title]:
        """Возвращает тайтлы по фильтрам; limit/offset задают страницу результатов."""
        where, params, tokens = self._where(f)
        order = SORT_CLAUSES.get(f.sort, SORT_CLAUSES["rating"])
        order_params = [self.global_mean()] if "?" in order else []
        if tokens:                                   # тайтлы, в названии которых есть вся фраза, – выше
            order = "(instr(t.names_hay, ?) = 0), " + order
            order_params = [" ".join(tokens)] + order_params
        page = f" LIMIT {int(limit)} OFFSET {int(offset)}" if limit is not None else ""
        inner = "SELECT * FROM titles t" + where + " ORDER BY " + order + page
        # жанры подтягиваются уже только для строк страницы; порядок повторяется во внешнем запросе
        sql = f"SELECT t.*, {_GENRES_COLUMN} FROM ({inner}) t ORDER BY " + order
        return [_to_title(r) for r in self.conn.execute(sql, params + order_params + order_params)]

    def get(self, title_id: int) -> Optional[Title]:
        row = self.conn.execute(
            f"SELECT t.*, {_GENRES_COLUMN} FROM titles t WHERE t.id = ?", (title_id,)).fetchone()
        return _to_title(row) if row else None

    # --- изменение каталога ---
    def _search_columns(self, data: dict, genres: list) -> tuple:
        return build_search_text(data["name"], data["original_name"], data["alt_names"], data["country"],
                                 data["year"], data["kind"], data["description"], " ".join(genres))

    def add(self, data: dict, genres: list[str]) -> int:
        hay, names_hay, key = self._search_columns(data, genres)
        cur = self.conn.execute(
            "INSERT INTO titles (name, original_name, alt_names, kind, year, country, "
            "episodes, duration, description, poster, hay, names_hay, name_key) VALUES "
            "(:name, :original_name, :alt_names, :kind, :year, :country, :episodes, "
            ":duration, :description, :poster, :hay, :names_hay, :name_key)",
            {**data, "hay": hay, "names_hay": names_hay, "name_key": key})
        self._set_genres(cur.lastrowid, genres)
        self.conn.commit()
        return cur.lastrowid

    def update(self, title_id: int, data: dict, genres: list[str]) -> None:
        hay, names_hay, key = self._search_columns(data, genres)
        self.conn.execute(
            "UPDATE titles SET name=:name, original_name=:original_name, alt_names=:alt_names, "
            "kind=:kind, year=:year, country=:country, episodes=:episodes, "
            "duration=:duration, description=:description, poster=:poster, "
            "hay=:hay, names_hay=:names_hay, name_key=:name_key WHERE id=:id",
            {**data, "id": title_id, "hay": hay, "names_hay": names_hay, "name_key": key})
        self._set_genres(title_id, genres)
        self.conn.commit()

    def delete(self, title_id: int) -> None:
        self.conn.execute("DELETE FROM titles WHERE id = ?", (title_id,))
        self.conn.commit()

    def _set_genres(self, title_id: int, genres: list[str]) -> None:
        self.conn.execute("DELETE FROM title_genres WHERE title_id = ?", (title_id,))
        for name in genres:
            self.conn.execute("INSERT OR IGNORE INTO genres (name) VALUES (?)", (name,))
            self.conn.execute(
                "INSERT OR IGNORE INTO title_genres (title_id, genre_id) "
                "SELECT ?, id FROM genres WHERE name = ?", (title_id, name))

    def genres(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT g.name FROM genres g JOIN title_genres tg "
            "ON tg.genre_id = g.id ORDER BY g.name")
        return [r[0] for r in rows]

    def countries(self) -> list[str]:
        rows = self.conn.execute("SELECT DISTINCT country FROM titles ORDER BY country")
        return [r[0] for r in rows]

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM titles").fetchone()[0]


class ListRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, user_id: int, title_id: int, status: str,
               score: Optional[int], progress: int) -> None:
        self.conn.execute(
            "INSERT INTO list_entries (user_id, title_id, status, score, progress) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, title_id) DO UPDATE SET "
            "status = excluded.status, score = excluded.score, "
            "progress = excluded.progress, "
            "updated_at = datetime('now', 'localtime')",
            (user_id, title_id, status, score, progress))
        self.conn.commit()

    def get(self, user_id: int, title_id: int) -> Optional[ListEntry]:
        row = self.conn.execute(
            _ENTRY_SELECT + " WHERE e.user_id = ? AND e.title_id = ?",
            (user_id, title_id)).fetchone()
        return _to_entry(row) if row else None

    def for_user(self, user_id: int, status: Optional[str] = None) -> list[ListEntry]:
        sql = _ENTRY_SELECT + " WHERE e.user_id = ?"
        params: list = [user_id]
        if status:
            sql += " AND e.status = ?"
            params.append(status)
        sql += " ORDER BY e.updated_at DESC, e.id DESC"
        return [_to_entry(r) for r in self.conn.execute(sql, params)]

    def delete(self, user_id: int, title_id: int) -> None:
        self.conn.execute(
            "DELETE FROM list_entries WHERE user_id = ? AND title_id = ?",
            (user_id, title_id))
        self.conn.commit()

    def top_genre(self, user_id: int) -> Optional[str]:
        row = self.conn.execute(
            "SELECT g.name, COUNT(*) AS c FROM list_entries e "
            "JOIN title_genres tg ON tg.title_id = e.title_id "
            "JOIN genres g ON g.id = tg.genre_id "
            "WHERE e.user_id = ? AND e.status = 'completed' "
            "GROUP BY g.id ORDER BY c DESC, g.name LIMIT 1", (user_id,)).fetchone()
        return row["name"] if row else None


class ReviewRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert(self, user_id: int, title_id: int, text: str) -> None:
        self.conn.execute(
            "INSERT INTO reviews (user_id, title_id, text) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, title_id) DO UPDATE SET text = excluded.text, "
            "created_at = datetime('now', 'localtime')", (user_id, title_id, text))
        self.conn.commit()

    def for_title(self, title_id: int) -> list[Review]:
        rows = self.conn.execute(
            "SELECT r.*, u.username FROM reviews r JOIN users u ON u.id = r.user_id "
            "WHERE r.title_id = ? ORDER BY r.created_at DESC, r.id DESC", (title_id,))
        return [Review(r["id"], r["user_id"], r["username"], r["title_id"],
                       r["text"], r["created_at"]) for r in rows]

    def get(self, review_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()

    def delete(self, review_id: int) -> None:
        self.conn.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        self.conn.commit()

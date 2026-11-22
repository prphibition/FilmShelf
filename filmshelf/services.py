"""Слой бизнес-логики: правила, проверки данных и сценарии использования."""
import csv
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, Union

from .config import (KINDS, REVIEW_MAX_LEN, REVIEW_MIN_LEN, SCORE_MAX,
                     SCORE_MIN, STATUSES)
from .models import ListEntry, Review, SearchFilters, Title, User, UserStats
from .repository import (ListRepository, ReviewRepository, TitleRepository,
                         UserRepository)
from .security import hash_password, verify_password

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ServiceError(Exception):
    """Базовое исключение бизнес-логики; сообщение показывается пользователю."""


class ValidationError(ServiceError):
    """Некорректные входные данные."""


class AuthError(ServiceError):
    """Ошибка аутентификации или нехватка прав."""


class NotFoundError(ServiceError):
    """Запрошенный объект не найден."""


def _to_user(row: sqlite3.Row) -> User:
    return User(row["id"], row["username"], row["email"], row["role"], row["created_at"])


class AuthService:
    def __init__(self, conn: sqlite3.Connection):
        self.users = UserRepository(conn)

    def register(self, username: str, email: str, password: str,
                 role: str = "user") -> User:
        username, email = username.strip(), email.strip()
        if not USERNAME_RE.match(username):
            raise ValidationError(
                "Логин: 3–20 символов, только латиница, цифры и «_».")
        if not EMAIL_RE.match(email):
            raise ValidationError("Введите корректный адрес электронной почты.")
        if (len(password) < 6 or not re.search(r"[A-Za-z]", password)
                or not re.search(r"\d", password)):
            raise ValidationError(
                "Пароль: не короче 6 символов, должен содержать букву и цифру.")
        if self.users.get_by_username(username):
            raise ValidationError("Пользователь с таким логином уже существует.")
        if self.users.email_exists(email):
            raise ValidationError("Этот адрес электронной почты уже используется.")
        salt, digest = hash_password(password)
        self.users.add(username, email, salt, digest, role)
        return _to_user(self.users.get_by_username(username))

    def login(self, username: str, password: str) -> User:
        row = self.users.get_by_username(username.strip())
        # Одинаковое сообщение для обоих случаев не раскрывает, какой логин существует
        if row is None or not verify_password(password, row["salt"], row["password_hash"]):
            raise AuthError("Неверный логин или пароль.")
        return _to_user(row)


class CatalogService:
    def __init__(self, conn: sqlite3.Connection):
        self.titles = TitleRepository(conn)

    def search(self, filters: SearchFilters, limit: Optional[int] = None,
               offset: int = 0) -> list[Title]:
        return self.titles.search(filters, limit, offset)

    def count(self, filters: SearchFilters) -> int:
        """Число тайтлов, подходящих под фильтры (для постраничного вывода)."""
        return self.titles.count_matching(filters)

    def get(self, title_id: int) -> Title:
        title = self.titles.get(title_id)
        if title is None:
            raise NotFoundError("Тайтл не найден.")
        return title

    def genres(self) -> list[str]:
        return self.titles.genres()

    def countries(self) -> list[str]:
        return self.titles.countries()

    def create(self, actor: User, data: dict, genres: list[str]) -> int:
        self._require_admin(actor)
        clean, genres = self._validate(data, genres)
        return self.titles.add(clean, genres)

    def update(self, actor: User, title_id: int, data: dict, genres: list[str]) -> None:
        self._require_admin(actor)
        self.get(title_id)
        clean, genres = self._validate(data, genres)
        self.titles.update(title_id, clean, genres)

    def delete(self, actor: User, title_id: int) -> None:
        self._require_admin(actor)
        self.get(title_id)
        self.titles.delete(title_id)

    @staticmethod
    def _require_admin(actor: User) -> None:
        if not actor.is_admin:
            raise AuthError("Недостаточно прав: действие доступно администратору.")

    @staticmethod
    def _validate(data: dict, genres: list[str]) -> tuple[dict, list[str]]:
        clean = {
            "name": str(data.get("name", "")).strip(),
            "original_name": str(data.get("original_name", "")).strip(),
            "alt_names": ", ".join(p.strip() for p in str(data.get("alt_names", "")).split(",") if p.strip()),
            "kind": data.get("kind"),
            "country": str(data.get("country", "")).strip(),
            "description": str(data.get("description", "")).strip(),
            # только имя файла: путь к каталогу постеров определяется приложением
            "poster": os.path.basename(str(data.get("poster", "")).strip()),
        }
        if not clean["name"]:
            raise ValidationError("Укажите название.")
        if clean["kind"] not in KINDS:
            raise ValidationError("Выберите тип тайтла.")
        if not clean["country"]:
            raise ValidationError("Укажите страну производства.")
        try:
            clean["year"] = int(data.get("year"))
            clean["episodes"] = int(data.get("episodes", 1))
            clean["duration"] = int(data.get("duration", 90))
        except (TypeError, ValueError):
            raise ValidationError("Год, число серий и длительность должны быть числами.")
        if not 1888 <= clean["year"] <= date.today().year + 5:
            raise ValidationError("Год выпуска вне допустимого диапазона.")
        if clean["kind"] == "movie":
            clean["episodes"] = 1
        if clean["episodes"] < 1 or clean["duration"] < 1:
            raise ValidationError("Число серий и длительность должны быть положительными.")
        genres = sorted({g.strip() for g in genres if g.strip()})
        if not genres:
            raise ValidationError("Укажите хотя бы один жанр.")
        return clean, genres


class ListService:
    def __init__(self, conn: sqlite3.Connection):
        self.titles = TitleRepository(conn)
        self.entries = ListRepository(conn)

    def set_entry(self, user: User, title_id: int, status: str,
                  score: Optional[int], progress: int = 0) -> ListEntry:
        if status not in STATUSES:
            raise ValidationError("Недопустимый статус.")
        title = self.titles.get(title_id)
        if title is None:
            raise NotFoundError("Тайтл не найден.")
        if score is not None:
            if status == "plan":
                raise ValidationError("Нельзя оценить тайтл со статусом «Запланировано».")
            if not SCORE_MIN <= score <= SCORE_MAX:
                raise ValidationError(f"Оценка должна быть от {SCORE_MIN} до {SCORE_MAX}.")
        if status == "completed":
            progress = title.episodes
        elif status == "plan":
            progress = 0
        elif not 0 <= progress <= title.episodes:
            raise ValidationError(f"Прогресс должен быть от 0 до {title.episodes}.")
        self.entries.upsert(user.id, title_id, status, score, progress)
        return self.entries.get(user.id, title_id)

    def get_entry(self, user: User, title_id: int) -> Optional[ListEntry]:
        return self.entries.get(user.id, title_id)

    def entries_of(self, user: User, status: Optional[str] = None) -> list[ListEntry]:
        return self.entries.for_user(user.id, status)

    def remove(self, user: User, title_id: int) -> None:
        self.entries.delete(user.id, title_id)

    def export_csv(self, user: User, path: Union[str, Path]) -> int:
        entries = self.entries.for_user(user.id)
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["Название", "Тип", "Статус", "Оценка", "Прогресс", "Обновлено"])
            for e in entries:
                writer.writerow([e.title_name, KINDS[e.kind], STATUSES[e.status],
                                 e.score if e.score is not None else "",
                                 f"{e.progress}/{e.episodes}", e.updated_at])
        return len(entries)


class ReviewService:
    def __init__(self, conn: sqlite3.Connection):
        self.titles = TitleRepository(conn)
        self.reviews = ReviewRepository(conn)

    def save(self, user: User, title_id: int, text: str) -> None:
        text = text.strip()
        if self.titles.get(title_id) is None:
            raise NotFoundError("Тайтл не найден.")
        if not REVIEW_MIN_LEN <= len(text) <= REVIEW_MAX_LEN:
            raise ValidationError(
                f"Длина отзыва: от {REVIEW_MIN_LEN} до {REVIEW_MAX_LEN} символов.")
        self.reviews.upsert(user.id, title_id, text)

    def for_title(self, title_id: int) -> list[Review]:
        return self.reviews.for_title(title_id)

    def delete(self, user: User, review_id: int) -> None:
        row = self.reviews.get(review_id)
        if row is None:
            raise NotFoundError("Отзыв не найден.")
        if row["user_id"] != user.id and not user.is_admin:
            raise AuthError("Можно удалять только собственные отзывы.")
        self.reviews.delete(review_id)


class StatsService:
    def __init__(self, conn: sqlite3.Connection):
        self.entries = ListRepository(conn)

    def for_user(self, user: User) -> UserStats:
        entries = self.entries.for_user(user.id)
        counts = {key: 0 for key in STATUSES}
        for e in entries:
            counts[e.status] += 1
        scores = [e.score for e in entries if e.score is not None]
        mean = round(sum(scores) / len(scores), 2) if scores else None
        minutes = sum(e.progress * e.duration for e in entries)
        return UserStats(counts, len(entries), mean, minutes,
                         self.entries.top_genre(user.id))


@dataclass
class Services:
    """Контейнер сервисов, создаваемых поверх одного соединения с БД."""
    auth: AuthService
    catalog: CatalogService
    lists: ListService
    reviews: ReviewService
    stats: StatsService

    @classmethod
    def create(cls, conn: sqlite3.Connection) -> "Services":
        return cls(AuthService(conn), CatalogService(conn), ListService(conn),
                   ReviewService(conn), StatsService(conn))

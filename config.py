"""Конфигурация и справочные константы приложения."""
from pathlib import Path

APP_NAME = "FilmShelf"
DB_DIR = Path.home() / ".filmshelf"
DB_PATH = DB_DIR / "filmshelf.db"

# Статусы записи в личном списке пользователя
STATUSES = {
    "watching": "Смотрю",
    "completed": "Просмотрено",
    "plan": "Запланировано",
    "on_hold": "Отложено",
    "dropped": "Брошено",
}

# Типы тайтлов в каталоге
KINDS = {
    "movie": "Фильм",
    "series": "Сериал",
    "drama": "Дорама",
    "anime": "Аниме",
}

SCORE_MIN, SCORE_MAX = 1, 10
PBKDF2_ITERATIONS = 600_000
REVIEW_MIN_LEN, REVIEW_MAX_LEN = 10, 2000

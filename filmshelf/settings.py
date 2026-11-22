"""Пользовательские настройки (файл settings.json в папке данных приложения)."""
import json
import os

from .config import DB_DIR

SETTINGS_FILE = DB_DIR / "settings.json"


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(values: dict) -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    data = {**load_settings(), **values}
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def tmdb_key() -> str:
    """Ключ TMDB: переменная окружения TMDB_API_KEY или сохранённое значение."""
    return os.environ.get("TMDB_API_KEY", "").strip() or str(load_settings().get("tmdb_key", "")).strip()


def auto_localize() -> bool:
    """Подгружать ли русские названия и постеры автоматически (по умолчанию – да, если есть ключ)."""
    return bool(load_settings().get("auto_localize", True))

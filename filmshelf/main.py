"""Точка входа: подготовка базы данных и запуск графического интерфейса."""
import sys

from .catalog_import import catalog_needed, import_catalog
from .config import DB_DIR, DB_PATH
from .database import connect, init_db
from .seed_data import ensure_demo_posters, is_empty, seed_demo_data
from .services import Services
from .ui.app import App


def main() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect(DB_PATH)
    init_db(conn)
    if is_empty(conn):
        seed_demo_data(conn)
    else:
        ensure_demo_posters(conn)
    if "--no-catalog" not in sys.argv and catalog_needed(conn):
        print("Первый запуск: импорт каталога фильмов и сериалов, подождите несколько секунд…")
        print("Добавлено тайтлов:", import_catalog(conn))
    App(Services.create(conn), DB_PATH).mainloop()


if __name__ == "__main__":
    main()

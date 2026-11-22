"""Снимки экрана для курсовой (рисунки 9–12): каталог с постерами, поиск, карточка, окно загрузки.

Запуск из корня проекта:   python tools/make_screenshots.py

Что делает: загружает русские названия и постеры для первой страницы каталога (Википедия, а при
наличии ключа TMDB_API_KEY – ещё и TMDB), открывает приложение, входит как demo и сохраняет четыре
снимка в папку screenshots/. Нужны интернет, Pillow и обычный экран (Windows, macOS или Linux с X11;
Wayland не поддерживается). Пока идёт съёмка, не трогайте мышь и не закрывайте окна поверх приложения.
Ключ TMDB на снимках не показывается: поле в окне загрузки очищается (сохранённый ключ не меняется).
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.platform == "win32":                      # чтобы координаты окна совпадали с пикселями экрана
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

from filmshelf import enrich, posters                                   # noqa: E402
from filmshelf.catalog_import import catalog_needed, import_catalog    # noqa: E402
from filmshelf.config import DB_DIR, DB_PATH                           # noqa: E402
from filmshelf.database import connect, init_db                        # noqa: E402
from filmshelf.models import SearchFilters                             # noqa: E402
from filmshelf.seed_data import ensure_demo_posters, is_empty, seed_demo_data  # noqa: E402
from filmshelf.services import Services                                # noqa: E402
from filmshelf.settings import tmdb_key                                # noqa: E402
from filmshelf.ui.app import App                                       # noqa: E402
from filmshelf.ui.title_window import TitleWindow                      # noqa: E402
from filmshelf.ui.tmdb_window import TmdbWindow                        # noqa: E402

OUT = Path("screenshots")


def prepare_database():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect(DB_PATH)
    init_db(conn)
    if is_empty(conn):
        seed_demo_data(conn)
    else:
        ensure_demo_posters(conn)
    if catalog_needed(conn):
        print("Импорт каталога, подождите несколько секунд…")
        import_catalog(conn)
    return conn


def localize_first_page(conn) -> None:
    """Русские названия и постеры для тайтлов, которые видны на первой странице каталога."""
    services = Services.create(conn)
    ids = [t.id for t in services.catalog.search(SearchFilters(), 100, 0)]
    todo = enrich.pending_ids(conn, None, ids)
    if not todo:
        print("Первая страница уже обработана.")
        return
    print(f"Загружаю русские названия и постеры для {len(todo)} тайтлов (1–2 минуты)…")
    progress = enrich.Progress()
    enrich.enrich(DB_PATH, todo, tmdb_key(), progress, workers=4, with_posters=True)
    print(f"Готово: обработано {progress.done}, переименовано {progress.renamed}, постеров {progress.posters}."
          + (f" Сообщение: {progress.message}" if progress.message else ""))


def pump(widget, seconds: float = 1.0) -> None:
    end = time.time() + seconds
    while time.time() < end:
        widget.update()
        time.sleep(0.05)


def grab(widget, name: str) -> None:
    from PIL import ImageGrab
    try:
        widget.attributes("-topmost", True)
    except Exception:
        pass
    widget.lift()
    widget.focus_force()
    pump(widget, 1.2)
    x, y, w, h = widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height()
    path = OUT / name
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
    print("Сохранено:", path)


def main() -> None:
    if posters.Image is None:
        sys.exit("Нужна библиотека Pillow: python -m pip install Pillow")
    OUT.mkdir(exist_ok=True)
    conn = prepare_database()
    localize_first_page(conn)

    app = App(Services.create(conn), DB_PATH)
    app.localizer = None                                   # фоновая автозагрузка на время съёмки не нужна
    app.geometry("1120x720+40+40")
    frame = app.root_frame.winfo_children()[0]
    frame.username.set("demo")
    frame.password.set("demo1234")
    frame.on_submit()
    pump(app, 1.5)
    cat = app.catalog_tab

    grab(app, "ris09_katalog.png")                         # рисунок 9: каталог с миниатюрами постеров

    cat.query.set("игра в кальмара")                      # рисунок 10: поиск по русскому названию
    cat.search()
    pump(app, 1.0)
    grab(app, "ris10_poisk.png")

    cat.query.set("паразиты")                              # рисунок 11: карточка тайтла
    cat.search()
    pump(app, 1.0)
    rows = cat.tree.get_children()
    if rows:
        card = TitleWindow(app, int(rows[0]))
        grab(card, "ris11_kartochka.png")
        card.destroy()

    cat.query.set("")                                      # рисунок 12: окно загрузки (ключ не показываем)
    cat.search()
    pump(app, 1.0)
    window = TmdbWindow(app, [int(i) for i in cat.tree.get_children()])
    window.key.set("")
    grab(window, "ris12_okno_zagruzki.png")
    window.destroy()

    app.destroy()
    print("Готово. Вставьте снимки из папки screenshots/ в курсовую на места рисунков 9–12.")


if __name__ == "__main__":
    main()

"""Русские названия, описания и оригинальные постеры для тайтлов каталога из TMDB и Википедии.

Нужен интернет; ключ TMDB необязателен (без него работает только Википедия), бесплатный ключ TMDB (themoviedb.org → профиль → API) и Pillow для постеров.
  Windows (cmd):  set TMDB_API_KEY=ключ        python tools\\enrich_from_tmdb.py --limit 2000
  macOS / Linux:  export TMDB_API_KEY=ключ     python3 tools/enrich_from_tmdb.py --limit 2000
Параметры: --limit N (сколько тайтлов, по умолчанию все ещё не обработанные), --workers N (потоков, 6),
--no-posters (только названия и описания). Прервать можно в любой момент (Ctrl+C): прогресс сохраняется.
Данные и изображения принадлежат TMDB (This product uses the TMDB API but is not endorsed by TMDB).
"""
import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from filmshelf.config import DB_PATH  # noqa: E402
from filmshelf.database import connect  # noqa: E402
from filmshelf.enrich import Progress, enrich, pending_ids  # noqa: E402
from filmshelf.settings import tmdb_key  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--no-posters", action="store_true")
    args = parser.parse_args()
    key = tmdb_key()
    if not key:
        print("Ключ TMDB не задан (переменная окружения TMDB_API_KEY) – используется только Википедия.")
    if not DB_PATH.exists():
        print("База данных не найдена: сначала один раз запустите приложение.")
        return 1
    conn = connect(DB_PATH)
    ids = pending_ids(conn, args.limit)
    conn.close()
    print(f"К обработке: {len(ids)} тайтлов. Прервать: Ctrl+C.")
    progress, stop = Progress(), threading.Event()
    worker = threading.Thread(target=enrich, args=(DB_PATH, ids, key, progress, stop, args.workers, not args.no_posters))
    worker.start()
    try:
        while worker.is_alive():
            time.sleep(2)
            print(f"\r{progress.done}/{progress.total}  русских названий: {progress.renamed}  "
                  f"постеров: {progress.posters}  ошибок: {progress.errors}", end="", flush=True)
    except KeyboardInterrupt:
        stop.set()
        worker.join()
    print(f"\n{progress.message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

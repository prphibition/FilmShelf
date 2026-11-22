"""Загрузка настоящих постеров демонстрационных тайтлов из TMDB (нужны интернет и Pillow).

1. Зарегистрируйтесь на https://www.themoviedb.org и в настройках профиля (раздел API)
   бесплатно получите ключ.
2. Задайте ключ в переменной окружения и запустите скрипт из корня проекта:
      Windows (cmd):   set TMDB_API_KEY=ваш_ключ        затем   python tools\\fetch_posters.py
      Windows (PS):    $env:TMDB_API_KEY="ваш_ключ"      затем   python tools/fetch_posters.py
      macOS / Linux:   export TMDB_API_KEY=ваш_ключ      затем   python3 tools/fetch_posters.py
3. Постеры сохраняются в filmshelf/posters/pNN.png и заменяют стилизованные.
   Если для тайтла ничего не найдено, остаётся запасная иллюстрация.

Данные и изображения принадлежат TMDB (This product uses the TMDB API but is not
endorsed or certified by TMDB).
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
OUT = ROOT / "filmshelf" / "posters"
SIZE = (400, 600)


def api_get(path: str, params: dict, key: str) -> dict:
    """GET-запрос к API TMDB; поддерживаются ключ v3 и токен v4 (начинается с «eyJ»)."""
    params, headers = dict(params), {"Accept": "application/json"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    else:
        params["api_key"] = key
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as resp:
        return json.load(resp)


def result_year(item: dict):
    date = item.get("release_date") or item.get("first_air_date") or ""
    return int(date[:4]) if date[:4].isdigit() else None


def pick(results: list, year: int):
    """Выбирает результат поиска с постером, предпочитая совпадение года (±1)."""
    candidates = [r for r in results
                  if r.get("poster_path") and r.get("media_type", "movie") in ("movie", "tv")]
    for item in candidates:
        found = result_year(item)
        if found is not None and abs(found - year) <= 1:
            return item
    return candidates[0] if candidates else None


def find_poster_path(queries: list, year: int, key: str):
    for query in queries:
        for language in ("ru-RU", "en-US"):
            data = api_get("/search/multi", {"query": query, "language": language}, key)
            item = pick(data.get("results", []), year)
            if item:
                return item["poster_path"]
    return None


def download_png(poster_path: str, target: Path) -> None:
    from PIL import Image, ImageOps          # импорт здесь, чтобы pick() работал без Pillow
    with urllib.request.urlopen(IMAGE_BASE + poster_path, timeout=30) as resp:
        data = resp.read()
    with Image.open(io.BytesIO(data)) as img:
        ImageOps.fit(img.convert("RGB"), SIZE).save(target, "PNG", optimize=True)


def main() -> int:
    key = os.environ.get("TMDB_API_KEY", "").strip()
    if not key:
        print("Не задана переменная окружения TMDB_API_KEY (см. описание в начале файла).")
        return 1
    from filmshelf.seed_data import TITLES
    OUT.mkdir(parents=True, exist_ok=True)
    done = 0
    for number, (name, original, _kind, year, *_rest) in enumerate(TITLES, start=1):
        queries = [name] + ([original] if original and original != name else [])
        try:
            path = find_poster_path(queries, year, key)
            if path:
                download_png(path, OUT / f"p{number:02d}.png")
                done += 1
                print(f"[{number:02d}] {name}: постер загружен")
            else:
                print(f"[{number:02d}] {name}: не найден, оставлена иллюстрация")
        except urllib.error.HTTPError as exc:
            print(f"[{number:02d}] {name}: ошибка HTTP {exc.code}")
            if exc.code in (401, 403):
                print("Проверьте ключ TMDB_API_KEY.")
                return 1
        except (urllib.error.URLError, OSError) as exc:
            print(f"[{number:02d}] {name}: сеть/файл: {exc}")
        time.sleep(0.3)                      # не превышаем лимиты запросов
    print(f"Готово: загружено постеров {done} из {len(TITLES)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

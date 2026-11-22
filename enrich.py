"""Обогащение каталога данными TMDB: русские названия и описания, оригинальные постеры.

Источники: TMDB (нужен бесплатный ключ; основной) и Википедия (ключ не нужен; работает сама, если
ключа нет, а при его наличии добирает недостающее: русское название, описание, постер).

Для каждого тайтла выполняется один поисковый запрос к API TMDB (язык ru-RU); если найден
подходящий результат, название и описание заменяются русскими (прежнее название остаётся в
«оригинальном» и находится поиском), а постер скачивается и сохраняется в папку постеров.
Запросы идут в нескольких потоках, запись в базу – в одном.

Класс AutoEnricher делает то же самое автоматически в фоне: сначала для тайтлов, показанных в
результатах поиска, затем (по желанию) для всего остального каталога.
"""
import queue
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

from . import posters, wiki
from .database import connect, normalize
from .repository import TitleRepository
from .services import ServiceError
from .translit import has_latin_only_name, transliterate

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
CYRILLIC = re.compile("[А-Яа-яЁё]")
# Если у тайтла нет русского названия в TMDB (или он там не найден), название записывается
# кириллицей по транскрипции, чтобы в каталоге не оставалось латиницы.
TRANSLITERATE_FALLBACK = True


class TmdbError(ServiceError):
    """Ошибка обращения к TMDB (сеть, сервер)."""


class TmdbAuthError(TmdbError):
    """Неверный ключ TMDB."""


@dataclass
class Progress:
    """Состояние обработки; читается интерфейсом из другого потока."""
    total: int = 0
    done: int = 0
    renamed: int = 0
    posters: int = 0
    errors: int = 0
    finished: bool = False
    message: str = ""


def _request(url: str, key: str, timeout: int = 20) -> Optional[bytes]:
    """GET-запрос с ключом (v3 – параметр api_key, v4 – токен Bearer) и повторами при сбоях."""
    headers = {"Accept": "application/json"}
    if key.startswith("eyJ"):
        headers["Authorization"] = "Bearer " + key
    else:
        url += ("&" if "?" in url else "?") + "api_key=" + urllib.parse.quote(key)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise TmdbAuthError(f"Ключ TMDB не принят (HTTP {exc.code}).")
            if exc.code == 404:
                return None
            if exc.code == 429:                           # превышен лимит запросов – ждём и повторяем
                time.sleep(float(exc.headers.get("Retry-After", "2")) + 0.5)
            elif 500 <= exc.code < 600:
                time.sleep(1 + attempt)
            else:
                raise TmdbError(f"Ошибка TMDB: HTTP {exc.code}.")
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            if attempt == 3:
                raise TmdbError(f"Нет связи с TMDB: {exc}")
            time.sleep(1 + attempt)
    raise TmdbError("TMDB не отвечает.")


def result_year(item: dict) -> Optional[int]:
    date = item.get("release_date") or item.get("first_air_date") or ""
    return int(date[:4]) if date[:4].isdigit() else None


def pick(results: Sequence[dict], year: int, queries: Sequence[str]) -> Optional[dict]:
    """Выбирает результат поиска: год совпадает (±1) либо совпадает название.

    Из подходящих результатов предпочитается тот, у которого есть постер."""
    wanted = {normalize(q) for q in queries}
    fitting = []
    for item in results:
        found = result_year(item)
        names = {normalize(item.get(k) or "") for k in ("original_title", "original_name", "title", "name")}
        if (found is not None and abs(found - year) <= 1) or (wanted & names):
            fitting.append(item)
    return next((i for i in fitting if i.get("poster_path")), fitting[0] if fitting else None)


def _queries(title) -> list:
    """Варианты запроса: латинские названия предпочтительнее русского."""
    parts = [title.original_name] + [a.strip() for a in title.alt_names.split(",")] + [title.name]
    seen, out = set(), []
    for part in sorted((p for p in parts if p.strip()), key=lambda p: bool(CYRILLIC.search(p))):
        if normalize(part) not in seen:
            seen.add(normalize(part))
            out.append(part)
    return out[:2]


def find_match(title, key: str, api_base: str = API_BASE) -> Optional[dict]:
    """Ищет тайтл в TMDB; если у найденного нет постера, пробует остальные варианты запроса."""
    kind = "movie" if title.episodes == 1 and title.kind in ("movie", "anime") else "tv"
    year_param = "year" if kind == "movie" else "first_air_date_year"
    queries = _queries(title)
    first = None
    for query in queries:
        for with_year in (True, False):
            params = {"query": query, "language": "ru-RU", "include_adult": "false"}
            if with_year:
                params[year_param] = title.year
            raw = _request(f"{api_base}/search/{kind}?{urllib.parse.urlencode(params)}", key)
            item = pick(json.loads(raw).get("results", []), title.year, queries) if raw else None
            if item and item.get("poster_path"):
                return item
            first = first or item
    return first


def enrich(db_path: Union[str, Path], ids: Sequence[int], key: str, progress: Progress,
           stop: Optional[threading.Event] = None, workers: int = 6, with_posters: bool = True,
           api_base: str = API_BASE, image_base: str = IMAGE_BASE,
           user_dir: Union[str, Path, None] = None, on_title=None,
           use_wiki: bool = True, wiki_api: str = wiki.WIKI_API) -> Progress:
    """Обрабатывает тайтлы с указанными id; вызывается в отдельном потоке (своё соединение с БД).

    on_title(id) вызывается после записи каждого тайтла (из потока обработки)."""
    stop = stop or threading.Event()
    if not key and not use_wiki:
        progress.message, progress.finished = "Нужен ключ TMDB.", True
        return progress
    conn = connect(db_path)
    repo = TitleRepository(conn)
    progress.total, progress.finished = len(ids), False
    consecutive_errors = 0

    def fetch(title):
        match, image = None, None
        if key:                                                # основной источник – TMDB
            match = find_match(title, key, api_base)
            if match and with_posters and match.get("poster_path"):
                image = _request(image_base + match["poster_path"], key)
        if use_wiki:                                           # Википедия добирает недостающее
            need_name = not (match and CYRILLIC.search(match.get("title") or match.get("name") or ""))
            need_text = not (match and CYRILLIC.search(match.get("overview") or ""))
            need_image = with_posters and image is None
            if need_name or need_text or need_image:
                found = wiki.lookup(_queries(title), title.year, title.kind, wiki_api,
                                    want_text=need_text, want_image=need_image)
                if found:
                    match, image = _merge_wiki(match, image, found, need_name, need_text)
        return title, match, image

    try:
        with ThreadPoolExecutor(workers) as pool:
            for start in range(0, len(ids), workers * 2):
                if stop.is_set():
                    progress.message = "Остановлено пользователем."
                    break
                batch = [t for t in (repo.get(i) for i in ids[start:start + workers * 2]) if t]
                futures = [pool.submit(fetch, t) for t in batch]
                for title, future in zip(batch, futures):
                    try:
                        _, match, image = future.result()
                    except TmdbAuthError as exc:
                        progress.message = str(exc)
                        return progress
                    except (TmdbError, wiki.WikiError) as exc:
                        progress.errors += 1
                        consecutive_errors += 1
                        progress.done += 1
                        if consecutive_errors >= 20:
                            progress.message = f"Остановлено после серии ошибок: {exc}"
                            return progress
                        continue
                    consecutive_errors = 0
                    _apply(conn, repo, title, match, image, progress, user_dir)
                    progress.done += 1
                    if on_title:
                        on_title(title.id)
        if not progress.message:
            progress.message = "Готово."
    finally:
        progress.finished = True
        conn.close()
    return progress


def _merge_wiki(match, image, found, need_name: bool, need_text: bool):
    """Дополняет результат TMDB (или создаёт новый) данными из Википедии; возвращает (match, image)."""
    match = dict(match or {})
    match.setdefault("id", found.page_id)
    if need_name and found.ru_name:
        match["title"] = found.ru_name
    if need_text and found.summary:
        match["overview"] = found.summary
    if image is None and found.image:
        image, match["poster_name"] = found.image, f"wiki{found.page_id}.png"
    return match, image


def _apply(conn, repo, title, match, image, progress, user_dir) -> None:
    """Записывает результат: русские название и описание, постер; помечает тайтл обработанным.

    Без совпадения в TMDB (или без русского названия там) название записывается кириллицей по
    транскрипции, если включён TRANSLITERATE_FALLBACK; прежнее название остаётся «оригинальным»."""
    ru_name = (match.get("title") or match.get("name") or "") if match else ""
    overview = ((match.get("overview") or "").strip()) if match else ""
    new_name = ru_name if CYRILLIC.search(ru_name) else title.name
    if TRANSLITERATE_FALLBACK and has_latin_only_name(new_name):
        new_name = transliterate(new_name)
    poster_name = title.poster
    if match and image:
        try:
            poster_name = posters.import_poster_bytes(
                image, match.get("poster_name") or f"tmdb{match['id']}.png", user_dir)
            progress.posters += 1
        except (ServiceError, OSError) as exc:             # битое изображение не должно ронять обработку
            progress.message = str(exc)
    data = {"name": new_name,
            "original_name": title.original_name or (title.name if new_name != title.name else ""),
            "alt_names": title.alt_names, "kind": title.kind, "year": title.year,
            "country": title.country, "episodes": title.episodes, "duration": title.duration,
            "description": overview if CYRILLIC.search(overview) else title.description,
            "poster": poster_name}
    if new_name != title.name:
        progress.renamed += 1
    if match or new_name != title.name:
        repo.update(title.id, data, title.genres)
    conn.execute("UPDATE titles SET enriched = 1 WHERE id = ?", (title.id,))
    conn.commit()


def pending_ids(conn, limit: Optional[int] = None, only: Optional[Sequence[int]] = None) -> list:
    """id тайтлов, ещё не обработанных TMDB (по убыванию числа оценок, затем по id)."""
    sql = "SELECT id FROM titles WHERE enriched = 0"
    params: list = []
    if only is not None:
        if not only:
            return []
        sql += " AND id IN (%s)" % ",".join("?" * len(only))
        params += list(only)
    sql += " ORDER BY votes DESC, id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return [r[0] for r in conn.execute(sql, params)]


class AutoEnricher:
    """Фоновая автоматическая локализация: русские названия и оригинальные постеры из TMDB.

    request(ids) ставит в начало очереди тайтлы, показанные пользователю (предыдущий пакет
    прерывается); когда очередь пуста и crawl=True, обрабатывается остальной каталог. Обновлённые
    id попадают в updated – интерфейс забирает их через take_updated() и перерисовывает строки.
    """

    BACKOFF = 30            # пауза после серии сетевых ошибок, секунд
    CRAWL_BATCH = 120

    def __init__(self, db_path, get_key, user_dir=None, api_base=API_BASE, image_base=IMAGE_BASE,
                 workers: int = 6, crawl: bool = True, use_wiki: bool = True,
                 wiki_api: str = wiki.WIKI_API):
        self.db_path, self.get_key, self.user_dir = db_path, get_key, user_dir
        self.use_wiki, self.wiki_api = use_wiki, wiki_api
        self.api_base, self.image_base, self.workers = api_base, image_base, workers
        self.crawl = crawl
        self.enabled = True
        self.message = ""                 # последнее сообщение об ошибке (для строки состояния)
        self.busy = False
        self.processed = 0                # сколько тайтлов обработано за сеанс
        self._updated: queue.SimpleQueue = queue.SimpleQueue()
        self._cv = threading.Condition()
        self._wanted: Optional[list] = None
        self._stop = threading.Event()
        self._closed = False
        self._paused = False
        self._bad_key = ""                # ключ, который TMDB уже отклонил
        self._thread: Optional[threading.Thread] = None

    # --- управление из интерфейса ---
    def request(self, ids: Sequence[int]) -> None:
        """Тайтлы, которые нужно локализовать в первую очередь (обычно – текущая страница)."""
        with self._cv:
            self._wanted = list(ids)
            self._stop.set()
            self._ensure_thread()
            self._cv.notify_all()

    def wake(self) -> None:
        """Проверить условия заново (включили автозагрузку, ввели ключ и т. п.)."""
        with self._cv:
            self._ensure_thread()
            self._cv.notify_all()

    def pause(self) -> None:
        with self._cv:
            self._paused = True
            self._stop.set()

    def resume(self) -> None:
        with self._cv:
            self._paused = False
            self._cv.notify_all()

    def close(self) -> None:
        with self._cv:
            self._closed = True
            self._stop.set()
            self._cv.notify_all()

    def take_updated(self) -> list:
        ids = []
        while True:
            try:
                ids.append(self._updated.get_nowait())
            except queue.Empty:
                return ids

    @property
    def needs_key(self) -> bool:
        """Нет (рабочего) ключа TMDB; тогда используется только Википедия, если она включена."""
        return not self._key()

    def _key(self) -> str:
        key = self.get_key()
        return "" if key == self._bad_key else key

    # --- рабочий поток ---
    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, daemon=True, name="tmdb-auto")
            self._thread.start()

    def _next_batch(self):
        """Ждёт работу и возвращает (id, событие остановки); None – пора завершаться."""
        with self._cv:
            while True:
                if self._closed:
                    return None
                if self._paused or not self.enabled or (self.needs_key and not self.use_wiki) or posters.Image is None:
                    self._cv.wait(1.0)
                    continue
                self._stop = threading.Event()
                if self._wanted is not None:
                    ids, self._wanted = self._wanted, None
                    return ("page", ids), self._stop
                if self.crawl:
                    return ("crawl", None), self._stop
                self._cv.wait(1.0)

    def _run(self) -> None:
        while True:
            batch = self._next_batch()
            if batch is None:
                return
            (mode, ids), stop = batch
            key = self._key()
            conn = connect(self.db_path)
            try:
                ids = pending_ids(conn, None if mode == "page" else self.CRAWL_BATCH, ids)
            finally:
                conn.close()
            if not ids:
                if mode == "crawl":                          # весь каталог обработан – ждём новых запросов
                    with self._cv:
                        self.busy = False
                        while self._wanted is None and not self._closed:
                            self._cv.wait(2.0)
                continue
            progress = Progress()
            self.busy = True
            try:
                enrich(self.db_path, ids, key, progress, stop, self.workers, True, self.api_base,
                       self.image_base, self.user_dir, on_title=self._updated.put,
                       use_wiki=self.use_wiki, wiki_api=self.wiki_api)
            except Exception as exc:                          # поток не должен умирать из-за случайной ошибки
                progress.message = f"Ошибка: {exc}"
            self.busy = False
            self.processed += progress.done
            if "Ключ TMDB не принят" in progress.message:
                self._bad_key = key                          # дальше – только Википедия (если включена)
                self.message = progress.message
                if mode == "page":                           # эти тайтлы – снова в начало очереди
                    with self._cv:
                        self._wanted = self._wanted if self._wanted is not None else ids
            elif progress.message.startswith(("Остановлено после", "Ошибка")):
                self.message = progress.message
                with self._cv:                                # нет сети – не долбим сервер
                    self._cv.wait(self.BACKOFF)
            elif not (self._bad_key and self.get_key() == self._bad_key):
                self.message = ""                             # (отклонённый ключ остаётся в сообщении)

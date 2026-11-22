"""Тесты обогащения каталога данными TMDB на локальном имитаторе API (без интернета)."""
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from filmshelf import enrich, posters
from filmshelf.database import connect, init_db
from filmshelf.models import SearchFilters
from filmshelf.repository import TitleRepository
from filmshelf.services import Services

try:
    from PIL import Image
except ImportError:                                   # pragma: no cover
    Image = None

MOVIES = {"parasite": {"id": 496243, "title": "Паразиты", "original_title": "기생충",
                       "overview": "Обитатели полуподвала становятся прислугой в богатом доме.",
                       "poster_path": "/parasite.jpg", "release_date": "2019-05-30"}}
SHOWS = {"squid game": {"id": 93405, "name": "Игра в кальмара", "original_name": "오징어 게임",
                        "overview": "Сотни людей, погрязших в долгах, играют в детские игры.",
                        "poster_path": "/squid.jpg", "first_air_date": "2021-09-17"}}


def jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (500, 750), (120, 60, 200)).save(buf, "JPEG")
    return buf.getvalue()


class FakeTmdb(BaseHTTPRequestHandler):
    requests_seen = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        FakeTmdb.requests_seen.append(url.path)
        if query.get("api_key") != ["testkey"]:
            self.send_response(401)
            self.end_headers()
            return
        if url.path.startswith("/t/p/w500/"):
            body, ctype = jpeg_bytes(), "image/jpeg"
        else:
            table = MOVIES if url.path.endswith("/search/movie") else SHOWS
            found = table.get(query["query"][0].casefold())
            body, ctype = json.dumps({"results": [found] if found else []}).encode(), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)


WIKI_PAGES = {   # поисковый запрос → ответ имитатора Википедии
    "nothing like it 1999 film": {"pageid": 77, "title": "Nothing Like It (1999 film)", "index": 1,
                                  "langlinks": [{"lang": "ru", "title": "Ничего подобного (фильм, 1999)"}],
                                  "thumbnail": {"source": "IMG/nothing.jpg"}},
    "parasite 2019 film": {"pageid": 5, "title": "Parasite (2019 film)", "index": 1,
                           "langlinks": [{"lang": "ru", "title": "Паразиты (фильм)"}]},     # без постера
}
WIKI_RU = {"Ничего подобного (фильм, 1999)": "Ничего подобного — вымышленный фильм. Он снят в 1999 году. Третье предложение.",
           "Паразиты (фильм)": "Паразиты — южнокорейский фильм."}


class FakeWiki(BaseHTTPRequestHandler):
    """Имитатор MediaWiki API: /en/api и /ru/api, изображения – /img/*."""
    requests_seen = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        FakeWiki.requests_seen.append(url.path)
        if url.path.startswith("/img/"):
            body, ctype = jpeg_bytes(), "image/jpeg"
        else:
            pages = []
            if "generator" in query:
                page = WIKI_PAGES.get(query["gsrsearch"][0].casefold())
                if page:
                    host = self.headers["Host"]
                    page = json.loads(json.dumps(page).replace("IMG/", f"http://{host}/img/"))
                    pages = [page]
            elif url.path.startswith("/ru/"):
                title = query["titles"][0]
                if title in WIKI_RU:
                    pages = [{"title": title, "extract": WIKI_RU[title]}]
            body, ctype = json.dumps({"query": {"pages": pages}}).encode(), "application/json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)


@unittest.skipIf(Image is None, "нужна библиотека Pillow")
class TmdbCase(unittest.TestCase):
    """Общая фикстура: имитатор TMDB и база с тремя тайтлами на английском."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeTmdb)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        port = cls.server.server_address[1]
        cls.api, cls.images = f"http://127.0.0.1:{port}/3", f"http://127.0.0.1:{port}/t/p/w500"
        cls.wiki_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeWiki)
        threading.Thread(target=cls.wiki_server.serve_forever, daemon=True).start()
        cls.wiki_api = f"http://127.0.0.1:{cls.wiki_server.server_address[1]}/{{lang}}/api"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.wiki_server.shutdown()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "t.db"
        conn = connect(self.db)
        init_db(conn)
        repo = TitleRepository(conn)
        base = {"original_name": "", "alt_names": "", "country": "США", "episodes": 1, "duration": 100,
                "description": "English text.", "poster": ""}
        self.movie = repo.add(dict(base, name="Parasite", kind="movie", year=2019), ["Драма"])
        self.show = repo.add(dict(base, name="Squid Game", kind="drama", year=2021, episodes=9), ["Триллер"])
        self.unknown = repo.add(dict(base, name="Nothing Like It", kind="movie", year=1999), ["Драма"])
        conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def add_title(self, name, year, kind="movie"):
        conn = connect(self.db)
        tid = TitleRepository(conn).add({"name": name, "original_name": "", "alt_names": "", "kind": kind,
                                         "year": year, "country": "США", "episodes": 1, "duration": 100,
                                         "description": "English text.", "poster": ""}, ["Драма"])
        conn.close()
        return tid

    def title(self, tid):
        conn = connect(self.db)
        try:
            return Services.create(conn).catalog.get(tid)
        finally:
            conn.close()


@unittest.skipIf(Image is None, "нужна библиотека Pillow")
class EnrichTests(TmdbCase):
    def run_enrich(self, ids, key="testkey", **kw):
        progress = enrich.Progress()
        kw.setdefault("wiki_api", self.wiki_api)
        enrich.enrich(self.db, ids, key, progress, workers=2, api_base=self.api, image_base=self.images,
                      user_dir=Path(self.tmp.name) / "posters", **kw)
        return progress

    def test_titles_get_russian_names_descriptions_and_posters(self):
        progress = self.run_enrich([self.movie, self.show, self.unknown])
        self.assertEqual((progress.done, progress.renamed, progress.posters), (3, 3, 3))
        conn = connect(self.db)
        services = Services.create(conn)
        movie = services.catalog.get(self.movie)
        self.assertEqual((movie.name, movie.original_name), ("Паразиты", "Parasite"))
        self.assertIn("полуподвала", movie.description)
        self.assertTrue((Path(self.tmp.name) / "posters" / movie.poster).is_file())
        self.assertEqual(services.catalog.get(self.show).name, "Игра в кальмара")
        unknown = services.catalog.get(self.unknown)           # не найден в TMDB – берётся из Википедии
        self.assertEqual((unknown.name, unknown.original_name), ("Ничего подобного", "Nothing Like It"))
        self.assertIn("вымышленный", unknown.description)
        self.assertTrue((Path(self.tmp.name) / "posters" / "wiki77.png").is_file())
        self.assertEqual(unknown.poster, "wiki77.png")
        self.assertEqual([t.id for t in services.catalog.search(SearchFilters(query="nothing like it"))], [self.unknown])
        conn.close()

    def test_fallback_can_be_disabled(self):
        rare = self.add_title("Rebel Moon", 2023)               # нет ни в TMDB, ни в Википедии
        enrich.TRANSLITERATE_FALLBACK = False
        try:
            self.run_enrich([rare])
        finally:
            enrich.TRANSLITERATE_FALLBACK = True
        self.assertEqual(self.title(rare).name, "Rebel Moon")

    def test_title_found_nowhere_gets_transliterated_name(self):
        rare = self.add_title("Rebel Moon", 2023)
        self.run_enrich([rare])
        self.assertEqual((self.title(rare).name, self.title(rare).original_name), ("Ребел Мун", "Rebel Moon"))

    def test_wikipedia_only_mode_without_tmdb_key(self):
        progress = self.run_enrich([self.movie, self.unknown], key="")
        self.assertEqual((progress.done, progress.renamed, progress.posters), (2, 2, 1))
        movie, unknown = self.title(self.movie), self.title(self.unknown)
        self.assertEqual((movie.name, movie.original_name), ("Паразиты", "Parasite"))
        self.assertIn("южнокорейский", movie.description)
        self.assertEqual(movie.poster, "")                      # у статьи нет изображения
        self.assertEqual((unknown.name, unknown.poster), ("Ничего подобного", "wiki77.png"))

    def test_wikipedia_is_not_asked_when_tmdb_has_everything(self):
        FakeWiki.requests_seen.clear()
        self.run_enrich([self.movie])
        self.assertEqual(FakeWiki.requests_seen, [])

    def test_wikipedia_fills_gaps_left_by_tmdb(self):
        # TMDB знает фильм, но у него нет постера: изображение берётся из Википедии, название – из TMDB
        MOVIES["nothing like it"] = {"id": 9, "title": "Ничего подобного!", "overview": "Описание из TMDB.",
                                     "poster_path": None, "release_date": "1999-01-01"}
        try:
            self.run_enrich([self.unknown])
        finally:
            del MOVIES["nothing like it"]
        title = self.title(self.unknown)
        self.assertEqual((title.name, title.description, title.poster), ("Ничего подобного!", "Описание из TMDB.", "wiki77.png"))

    def test_wikipedia_article_of_another_year_is_rejected(self):
        other = self.add_title("Nothing Like It", 2010)         # в Википедии только версия 1999 года
        self.run_enrich([other], key="")
        self.assertEqual(self.title(other).name, "Нотинг Лик Ит")

    def test_old_english_name_and_russian_name_are_both_searchable(self):
        self.run_enrich([self.movie])
        conn = connect(self.db)
        services = Services.create(conn)
        for query in ("parasite", "паразиты"):
            self.assertEqual([t.id for t in services.catalog.search(SearchFilters(query=query))], [self.movie])
        conn.close()

    def test_processed_titles_are_not_requested_again(self):
        self.run_enrich([self.movie, self.unknown])
        conn = connect(self.db)
        self.assertEqual(enrich.pending_ids(conn), [self.show])
        conn.close()

    def test_wrong_key_stops_without_changes(self):
        progress = self.run_enrich([self.movie], key="bad")
        self.assertIn("не принят", progress.message)
        conn = connect(self.db)
        self.assertEqual(Services.create(conn).catalog.get(self.movie).name, "Parasite")
        conn.close()

    def test_without_posters_only_text_is_updated(self):
        progress = self.run_enrich([self.movie], with_posters=False)
        self.assertEqual((progress.renamed, progress.posters), (1, 0))

    def test_pick_requires_matching_year_or_title(self):
        item = {"title": "Другое", "original_title": "Other", "release_date": "1950-01-01", "poster_path": "/x"}
        self.assertIsNone(enrich.pick([item], 2019, ["Parasite"]))
        self.assertEqual(enrich.pick([dict(item, release_date="2018-05-01")], 2019, ["Parasite"])["title"], "Другое")

    def test_pick_prefers_result_with_poster(self):
        bare = {"id": 1, "title": "Без постера", "release_date": "2019-01-01", "poster_path": None}
        good = {"id": 2, "title": "С постером", "release_date": "2019-02-01", "poster_path": "/p.jpg"}
        self.assertEqual(enrich.pick([bare, good], 2019, ["x"])["id"], 2)
        self.assertEqual(enrich.pick([bare], 2019, ["x"])["id"], 1)

    def test_corrupt_image_does_not_break_processing(self):
        conn = connect(self.db)
        repo = TitleRepository(conn)
        title = repo.get(self.movie)
        progress = enrich.Progress()
        match = {"id": 7, "title": "Паразиты", "overview": "", "poster_path": "/x"}
        enrich._apply(conn, repo, title, match, b"not an image", progress, Path(self.tmp.name) / "posters")
        self.assertEqual(repo.get(self.movie).name, "Паразиты")
        self.assertEqual(repo.get(self.movie).poster, "")
        conn.close()


class TranslitTests(unittest.TestCase):
    def test_latin_names_become_cyrillic(self):
        from filmshelf.translit import has_latin_only_name, transliterate
        self.assertEqual(transliterate("Sherlock Holmes"), "Шерлок Холмес")
        self.assertEqual(transliterate("Eden 2"), "Эден 2")
        self.assertEqual(transliterate("Rebel Moon"), "Ребел Мун")
        self.assertTrue(has_latin_only_name("Goblin"))
        self.assertFalse(has_latin_only_name("Гоблин"))
        self.assertFalse(has_latin_only_name("Leon: Леон"))
        self.assertFalse(has_latin_only_name("1917"))


@unittest.skipIf(Image is None, "нужна библиотека Pillow")
class AutoEnricherTests(TmdbCase):
    """Фоновый загрузчик: поиск показал тайтлы – они получают русские названия и постеры сами."""

    def make(self, key="testkey", **kw):
        auto = enrich.AutoEnricher(self.db, lambda: key, user_dir=Path(self.tmp.name) / "posters",
                                   api_base=self.api, image_base=self.images, workers=2,
                                   wiki_api=self.wiki_api, **kw)
        self.addCleanup(auto.close)
        return auto

    @staticmethod
    def wait_for(condition, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if condition():
                return True
            time.sleep(0.05)
        return False

    def collect(self, auto, count):
        got = []
        self.wait_for(lambda: got.extend(auto.take_updated()) or len(got) >= count)
        return got

    def test_requested_titles_are_localized_and_reported(self):
        auto = self.make(crawl=False)
        auto.request([self.movie, self.show])
        self.assertEqual(sorted(self.collect(auto, 2)), sorted([self.movie, self.show]))
        conn = connect(self.db)
        services = Services.create(conn)
        movie = services.catalog.get(self.movie)
        self.assertEqual(movie.name, "Паразиты")
        self.assertTrue((Path(self.tmp.name) / "posters" / movie.poster).is_file())
        self.assertEqual(services.catalog.get(self.unknown).name, "Nothing Like It")   # не запрашивали – не тронут
        conn.close()

    def test_crawl_finishes_the_rest_of_the_catalog(self):
        auto = self.make(crawl=True)
        auto.wake()
        self.assertTrue(self.wait_for(lambda: enrich.pending_ids(connect(self.db)) == []))
        conn = connect(self.db)
        self.assertEqual(Services.create(conn).catalog.get(self.unknown).name, "Ничего подобного")
        conn.close()

    def test_works_through_wikipedia_without_key(self):
        auto = self.make(key="", crawl=False)
        auto.request([self.unknown])
        self.assertEqual(self.collect(auto, 1), [self.unknown])
        self.assertTrue(auto.needs_key)
        self.assertEqual(self.title(self.unknown).name, "Ничего подобного")

    def test_nothing_happens_without_any_source_or_when_disabled(self):
        auto = self.make(key="", crawl=True, use_wiki=False)
        auto.request([self.movie])
        time.sleep(0.5)
        self.assertEqual(auto.take_updated(), [])
        auto = self.make(crawl=True)
        auto.enabled = False
        auto.request([self.movie])
        time.sleep(0.5)
        self.assertEqual(auto.take_updated(), [])

    def test_rejected_key_falls_back_to_wikipedia(self):
        auto = self.make(key="bad", crawl=False)
        auto.request([self.movie])
        self.assertEqual(self.collect(auto, 1), [self.movie])    # тайтл всё равно обработан – через Википедию
        self.assertIn("не принят", auto.message)                 # а пользователь видит, что ключ плохой
        self.assertTrue(auto.needs_key)
        self.assertEqual(self.title(self.movie).name, "Паразиты")

    def test_newer_request_replaces_older_one(self):
        auto = self.make(crawl=False)
        auto.pause()
        auto.request([self.movie])
        auto.request([self.show])              # пока пауза – действует последний запрос
        auto.resume()
        self.assertEqual(self.collect(auto, 1), [self.show])


if __name__ == "__main__":
    unittest.main(verbosity=2)

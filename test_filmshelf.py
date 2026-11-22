"""Модульные тесты бизнес-логики и слоя данных FilmShelf."""
import csv
import gzip
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from filmshelf import posters
from filmshelf.catalog_import import import_catalog
from filmshelf.database import connect, init_db
from filmshelf.models import SearchFilters
from filmshelf.security import hash_password, verify_password
from filmshelf.seed_data import TITLES
from tools import fetch_posters
from filmshelf.services import (AuthError, NotFoundError, Services,
                                ValidationError)


def make_services():
    conn = connect(":memory:")
    init_db(conn)
    return conn, Services.create(conn)


MOVIE = {"name": "Начало", "original_name": "Inception", "kind": "movie",
         "year": 2010, "country": "США", "episodes": 1, "duration": 148,
         "description": "Фантастический триллер."}
SERIES = {"name": "Шерлок", "original_name": "Sherlock", "kind": "series",
          "year": 2010, "country": "Великобритания", "episodes": 13,
          "duration": 90, "description": "Детектив."}


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.conn, self.s = make_services()
        self.admin = self.s.auth.register("admin", "admin@example.com", "admin123", "admin")
        self.user = self.s.auth.register("anna_k", "anna@example.com", "secret12")
        self.movie = self.s.catalog.create(self.admin, MOVIE, ["Фантастика", "Триллер"])
        self.series = self.s.catalog.create(self.admin, SERIES, ["Детектив", "Драма"])


class SecurityTests(unittest.TestCase):
    def test_hash_verifies_correct_password(self):
        salt, digest = hash_password("secret12")
        self.assertTrue(verify_password("secret12", salt, digest))
        self.assertFalse(verify_password("secret13", salt, digest))

    def test_same_password_gives_different_hashes(self):
        self.assertNotEqual(hash_password("secret12")[1], hash_password("secret12")[1])


class AuthTests(BaseCase):
    def test_register_and_login(self):
        user = self.s.auth.login("ANNA_K", "secret12")
        self.assertEqual(user.username, "anna_k")
        self.assertFalse(user.is_admin)

    def test_duplicate_username_rejected(self):
        with self.assertRaises(ValidationError):
            self.s.auth.register("Anna_K", "other@example.com", "secret12")

    def test_duplicate_email_rejected(self):
        with self.assertRaises(ValidationError):
            self.s.auth.register("other", "anna@example.com", "secret12")

    def test_invalid_email_rejected(self):
        with self.assertRaises(ValidationError):
            self.s.auth.register("newuser", "not-an-email", "secret12")

    def test_weak_password_rejected(self):
        for bad in ("abc12", "abcdefgh", "12345678"):
            with self.assertRaises(ValidationError):
                self.s.auth.register("newuser", "n@example.com", bad)

    def test_wrong_password_rejected(self):
        with self.assertRaises(AuthError):
            self.s.auth.login("anna_k", "wrong123")

    def test_password_not_stored_in_plain_text(self):
        row = self.conn.execute("SELECT * FROM users WHERE username='anna_k'").fetchone()
        self.assertNotIn("secret12", tuple(row))


class CatalogTests(BaseCase):
    def test_search_cyrillic_case_insensitive(self):
        found = self.s.catalog.search(SearchFilters(query="шерЛОК"))
        self.assertEqual([t.name for t in found], ["Шерлок"])

    def test_search_by_original_name(self):
        found = self.s.catalog.search(SearchFilters(query="incep"))
        self.assertEqual(found[0].id, self.movie)

    def test_filter_by_genre_kind_and_year(self):
        self.assertEqual(len(self.s.catalog.search(SearchFilters(genre="Драма"))), 1)
        self.assertEqual(len(self.s.catalog.search(SearchFilters(kind="movie"))), 1)
        self.assertEqual(len(self.s.catalog.search(SearchFilters(year_from=2011))), 0)

    def test_non_admin_cannot_create(self):
        with self.assertRaises(AuthError):
            self.s.catalog.create(self.user, MOVIE, ["Драма"])

    def test_admin_update_and_delete(self):
        changed = dict(MOVIE, name="Начало (2010)")
        self.s.catalog.update(self.admin, self.movie, changed, ["Фантастика"])
        self.assertEqual(self.s.catalog.get(self.movie).name, "Начало (2010)")
        self.s.catalog.delete(self.admin, self.movie)
        with self.assertRaises(NotFoundError):
            self.s.catalog.get(self.movie)

    def test_title_validation(self):
        with self.assertRaises(ValidationError):
            self.s.catalog.create(self.admin, dict(MOVIE, year=1500), ["Драма"])
        with self.assertRaises(ValidationError):
            self.s.catalog.create(self.admin, dict(MOVIE, name=" "), ["Драма"])
        with self.assertRaises(ValidationError):
            self.s.catalog.create(self.admin, MOVIE, [])

    def test_search_by_alternative_english_name(self):
        self.s.catalog.create(self.admin, dict(SERIES, name="Игра в кальмара", original_name="Ojingeo Geim",
                                               alt_names="Squid Game", year=2021), ["Триллер"])
        found = self.s.catalog.search(SearchFilters(query="squid GAME"))
        self.assertEqual([t.name for t in found], ["Игра в кальмара"])

    def test_search_matches_country_genre_year_and_kind_words(self):
        for query in ("сша", "фантастика", "2010 фильм", "США триллер 2010"):
            names = [t.name for t in self.s.catalog.search(SearchFilters(query=query))]
            self.assertIn("Начало", names, query)

    def test_search_requires_every_word_to_match(self):
        self.assertEqual(self.s.catalog.search(SearchFilters(query="фантастика детектив")), [])

    def test_search_ignores_punctuation_and_yo(self):
        self.s.catalog.create(self.admin, dict(MOVIE, name="Крёстный отец", original_name="The Godfather",
                                               year=1972), ["Драма"])
        found = self.s.catalog.search(SearchFilters(query="крестный,  отец!"))
        self.assertEqual([t.name for t in found], ["Крёстный отец"])

    def test_title_matches_are_listed_before_description_matches(self):
        self.s.catalog.create(self.admin, dict(MOVIE, name="Берег", original_name="Shore", year=2001,
                                               description="Фильм про море и ветер."), ["Драма"])
        self.s.catalog.create(self.admin, dict(MOVIE, name="Море", original_name="Sea", year=2002), ["Драма"])
        names = [t.name for t in self.s.catalog.search(SearchFilters(query="море"))]
        self.assertEqual(names, ["Море", "Берег"])

    def test_poster_name_saved_without_directories(self):
        tid = self.s.catalog.create(self.admin, dict(MOVIE, poster="../../etc/cover.png"), ["Драма"])
        self.assertEqual(self.s.catalog.get(tid).poster, "cover.png")

    def test_movie_always_has_one_episode(self):
        tid = self.s.catalog.create(self.admin, dict(MOVIE, episodes=5), ["Драма"])
        self.assertEqual(self.s.catalog.get(tid).episodes, 1)


class PosterTests(unittest.TestCase):
    PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00"
           b"\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7"
           b"\x00\x00\x00\x00IEND\xaeB`\x82")

    def test_missing_poster_and_path_traversal(self):
        self.assertIsNone(posters.poster_path("net-takogo.png"))
        self.assertIsNone(posters.poster_path("../../etc/passwd"))

    def test_bundled_posters_exist_for_all_demo_titles(self):
        for number in range(1, len(TITLES) + 1):
            self.assertIsNotNone(posters.poster_path(f"p{number:02d}.png"), number)

    def test_tmdb_result_choice_prefers_matching_year_and_poster(self):
        results = [{"media_type": "person", "poster_path": "/a.jpg"},
                   {"media_type": "movie", "poster_path": None, "release_date": "2019-05-30"},
                   {"media_type": "movie", "poster_path": "/old.jpg", "release_date": "1990-01-01"},
                   {"media_type": "tv", "poster_path": "/ok.jpg", "first_air_date": "2019-12-14"}]
        self.assertEqual(fetch_posters.pick(results, 2019)["poster_path"], "/ok.jpg")
        self.assertIsNone(fetch_posters.pick([{"media_type": "movie", "poster_path": None}], 2000))

    def test_import_poster_copies_file_to_user_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "cover.png"
            source.write_bytes(self.PNG)
            name = posters.import_poster(source, Path(tmp) / "posters")
            self.assertTrue(name.endswith(".png"))
            self.assertIsNotNone(posters.poster_path(name, Path(tmp) / "posters"))


class ListTests(BaseCase):
    def test_average_score_and_votes(self):
        other = self.s.auth.register("boris", "b@example.com", "secret12")
        self.s.lists.set_entry(self.user, self.movie, "completed", 9)
        self.s.lists.set_entry(other, self.movie, "completed", 8)
        title = self.s.catalog.get(self.movie)
        self.assertEqual((title.avg_score, title.votes), (8.5, 2))

    def test_sort_by_rating_puts_unrated_last(self):
        self.s.lists.set_entry(self.user, self.series, "completed", 10)
        ranked = self.s.catalog.search(SearchFilters(sort="rating"))
        self.assertEqual([t.id for t in ranked], [self.series, self.movie])

    def test_completed_sets_progress_to_all_episodes(self):
        entry = self.s.lists.set_entry(self.user, self.series, "completed", 8, 3)
        self.assertEqual(entry.progress, 13)

    def test_progress_out_of_range_rejected(self):
        with self.assertRaises(ValidationError):
            self.s.lists.set_entry(self.user, self.series, "watching", None, 14)

    def test_invalid_score_rejected(self):
        for bad in (0, 11):
            with self.assertRaises(ValidationError):
                self.s.lists.set_entry(self.user, self.movie, "completed", bad)

    def test_plan_cannot_have_score(self):
        with self.assertRaises(ValidationError):
            self.s.lists.set_entry(self.user, self.movie, "plan", 7)

    def test_repeated_set_updates_single_entry(self):
        self.s.lists.set_entry(self.user, self.series, "watching", None, 2)
        self.s.lists.set_entry(self.user, self.series, "watching", 7, 5)
        entries = self.s.lists.entries_of(self.user)
        self.assertEqual((len(entries), entries[0].progress, entries[0].score), (1, 5, 7))

    def test_deleting_title_removes_entries(self):
        self.s.lists.set_entry(self.user, self.movie, "completed", 9)
        self.s.catalog.delete(self.admin, self.movie)
        self.assertEqual(self.s.lists.entries_of(self.user), [])

    def test_export_csv(self):
        self.s.lists.set_entry(self.user, self.movie, "completed", 9)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "list.csv"
            self.assertEqual(self.s.lists.export_csv(self.user, path), 1)
            with open(path, encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh, delimiter=";"))
        self.assertEqual(rows[1][:4], ["Начало", "Фильм", "Просмотрено", "9"])


class ReviewAndStatsTests(BaseCase):
    def test_review_length_validation(self):
        with self.assertRaises(ValidationError):
            self.s.reviews.save(self.user, self.movie, "коротко")

    def test_one_review_per_user_is_updated(self):
        self.s.reviews.save(self.user, self.movie, "Первый вариант отзыва.")
        self.s.reviews.save(self.user, self.movie, "Второй вариант отзыва.")
        reviews = self.s.reviews.for_title(self.movie)
        self.assertEqual([r.text for r in reviews], ["Второй вариант отзыва."])

    def test_only_author_or_admin_can_delete_review(self):
        other = self.s.auth.register("boris", "b@example.com", "secret12")
        self.s.reviews.save(self.user, self.movie, "Отзыв пользователя Анны.")
        rid = self.s.reviews.for_title(self.movie)[0].id
        with self.assertRaises(AuthError):
            self.s.reviews.delete(other, rid)
        self.s.reviews.delete(self.admin, rid)
        self.assertEqual(self.s.reviews.for_title(self.movie), [])

    def test_user_statistics(self):
        self.s.lists.set_entry(self.user, self.movie, "completed", 9)
        self.s.lists.set_entry(self.user, self.series, "watching", 7, 4)
        st = self.s.stats.for_user(self.user)
        self.assertEqual(st.total, 2)
        self.assertEqual(st.counts["completed"], 1)
        self.assertEqual(st.mean_score, 8.0)
        self.assertEqual(st.minutes_watched, 148 + 4 * 90)
        self.assertIn(st.top_genre, ("Фантастика", "Триллер"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class CatalogScaleTests(BaseCase):
    def _catalog_file(self, tmp, count=250):
        records = [[f"Movie {i}", "", "", "movie", 1990 + i % 30, "США", 1, 100 + i % 20,
                    f"Story number {i} about the sea.", ["Драма", "Комедия"] if i % 2 else ["Боевик"]]
                   for i in range(count)]
        path = Path(tmp) / "catalog.json.gz"
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(records, fh)
        return path

    def test_import_adds_titles_genres_and_search_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            added = import_catalog(self.conn, self._catalog_file(tmp))
        self.assertEqual(added, 250)
        self.assertEqual(self.s.catalog.count(SearchFilters(query="movie 249")), 1)
        self.assertEqual(self.s.catalog.count(SearchFilters(genre="Боевик")), 125)

    def test_import_without_file_does_nothing(self):
        self.assertEqual(import_catalog(self.conn, "net-takogo-faila.json.gz"), 0)

    def test_paging_returns_disjoint_pages_and_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            import_catalog(self.conn, self._catalog_file(tmp))
        f = SearchFilters(query="movie", sort="name")
        first, second = self.s.catalog.search(f, 100, 0), self.s.catalog.search(f, 100, 100)
        self.assertEqual((len(first), len(second), self.s.catalog.count(f)), (100, 100, 250))
        self.assertFalse({t.id for t in first} & {t.id for t in second})

    def test_rating_counters_follow_changes_of_list_entries(self):
        self.s.lists.set_entry(self.user, self.movie, "completed", 6)
        self.s.lists.set_entry(self.user, self.movie, "completed", 10)
        self.assertEqual((self.s.catalog.get(self.movie).avg_score, self.s.catalog.get(self.movie).votes), (10.0, 1))
        self.s.lists.set_entry(self.user, self.movie, "dropped", None)
        self.assertEqual(self.s.catalog.get(self.movie).votes, 0)
        self.s.lists.set_entry(self.user, self.movie, "completed", 8)
        self.s.lists.remove(self.user, self.movie)
        self.assertEqual((self.s.catalog.get(self.movie).avg_score, self.s.catalog.get(self.movie).votes), (None, 0))

    def test_migration_of_old_database_fills_new_columns(self):
        old = sqlite3.connect(":memory:")
        old.row_factory = sqlite3.Row
        old.executescript("""
            CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, email TEXT, salt TEXT, password_hash TEXT,
                               role TEXT DEFAULT 'user', created_at TEXT DEFAULT '');
            CREATE TABLE titles(id INTEGER PRIMARY KEY, name TEXT, original_name TEXT DEFAULT '', kind TEXT,
                year INTEGER, country TEXT, episodes INTEGER DEFAULT 1, duration INTEGER DEFAULT 90,
                description TEXT DEFAULT '');
            CREATE TABLE genres(id INTEGER PRIMARY KEY, name TEXT UNIQUE);
            CREATE TABLE title_genres(title_id INTEGER, genre_id INTEGER, PRIMARY KEY(title_id, genre_id));
            CREATE TABLE list_entries(id INTEGER PRIMARY KEY, user_id INTEGER, title_id INTEGER, status TEXT,
                score INTEGER, progress INTEGER DEFAULT 0, updated_at TEXT DEFAULT '', UNIQUE(user_id, title_id));
            CREATE TABLE reviews(id INTEGER PRIMARY KEY, user_id INTEGER, title_id INTEGER, text TEXT,
                created_at TEXT DEFAULT '', UNIQUE(user_id, title_id));
            INSERT INTO titles(id, name, kind, year, country) VALUES (1, 'Паразиты', 'movie', 2019, 'Южная Корея');
            INSERT INTO genres VALUES (1, 'Драма'); INSERT INTO title_genres VALUES (1, 1);
            INSERT INTO list_entries(user_id, title_id, status, score) VALUES (1, 1, 'completed', 9);""")
        from filmshelf.database import _casefold, normalize
        old.create_function("casefold", 1, _casefold)
        old.create_function("norm", 1, normalize)
        init_db(old)
        row = old.execute("SELECT votes, score_sum, hay FROM titles").fetchone()
        self.assertEqual((row["votes"], row["score_sum"]), (1, 9))
        self.assertIn("драма", row["hay"])

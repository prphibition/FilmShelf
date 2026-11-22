"""Сценарное тестирование интерфейса (запуск в виртуальном дисплее)."""
import sys
import time
import unittest

from filmshelf.database import connect, init_db
from filmshelf.seed_data import seed_demo_data
from filmshelf.services import Services
from filmshelf.ui.app import App
from filmshelf.ui.title_editor import TitleEditor
from filmshelf.ui.title_window import TitleWindow


class UiScenarios(unittest.TestCase):
    def setUp(self):
        conn = connect(":memory:")
        init_db(conn)
        seed_demo_data(conn)
        self.app = App(Services.create(conn))

    def tearDown(self):
        self.app.destroy()

    def login(self, name, password):
        frame = self.app.root_frame.winfo_children()[0]
        frame.username.set(name)
        frame.password.set(password)
        frame.on_submit()
        return frame

    def test_01_wrong_password_shows_error(self):
        frame = self.login("demo", "wrong999")
        self.assertIn("Неверный", frame.error.cget("text"))
        self.assertIsNone(self.app.user)

    def test_02_register_password_mismatch(self):
        frame = self.app.root_frame.winfo_children()[0]
        frame.toggle_mode()
        frame.username.set("tester"); frame.email.set("t@example.com")
        frame.password.set("abc12345"); frame.confirm.set("abc12346")
        frame.on_submit()
        self.assertIn("не совпадают", frame.error.cget("text"))

    def test_03_login_opens_catalog_with_all_titles(self):
        self.login("demo", "demo1234")
        self.assertEqual(len(self.app.catalog_tab.tree.get_children()), 29)

    def test_04_filter_by_genre_and_kind(self):
        self.login("demo", "demo1234")
        cat = self.app.catalog_tab
        cat.kind.set("Аниме"); cat.genre.set("Фэнтези"); cat.search()
        self.assertEqual(len(cat.tree.get_children()), 5)

    def test_05_title_card_saves_entry(self):
        self.login("demo", "demo1234")
        cat = self.app.catalog_tab
        cat.query.set("Паразиты"); cat.search()
        tid = int(cat.tree.get_children()[0])
        win = TitleWindow(self.app, tid)
        win.status.set("Брошено"); win.score.set("4"); win.save_entry()
        entry = self.app.services.lists.get_entry(self.app.user, tid)
        self.assertEqual((entry.status, entry.score), ("dropped", 4))
        win.destroy()

    def test_06_invalid_progress_blocked(self):
        self.login("demo", "demo1234")
        tid = self.app.services.catalog.search(
            __import__("filmshelf.models", fromlist=["SearchFilters"]).SearchFilters(query="Шерлок"))[0].id
        win = TitleWindow(self.app, tid)
        win.status.set("Смотрю"); win.progress.set("99")
        from tkinter import messagebox
        shown = []
        messagebox.showerror = lambda *a, **k: shown.append(a)
        win.save_entry()
        self.assertEqual(len(shown), 1)
        self.assertEqual(self.app.services.lists.get_entry(self.app.user, tid).status, "plan")
        win.destroy()

    def test_07_my_list_filter_by_status(self):
        self.login("demo", "demo1234")
        lst = self.app.list_tab
        lst.current.set("watching"); lst.reload()
        self.assertEqual(len(lst.tree.get_children()), 3)

    def test_08_profile_statistics(self):
        self.login("demo", "demo1234")
        text = self.app.profile_tab.summary.cget("text")
        self.assertIn("Тайтлов в списке: 12", text)

    def test_09_admin_controls_only_for_admin(self):
        self.login("demo", "demo1234")
        def labels(w):
            out = [w.cget("text")] if "text" in w.keys() else []
            for c in w.winfo_children():
                out += labels(c)
            return out
        self.assertNotIn("Добавить тайтл", labels(self.app.catalog_tab))
        self.app.show_login(); self.login("admin", "admin123")
        self.assertIn("Добавить тайтл", labels(self.app.catalog_tab))

    def test_10_admin_creates_title_via_editor(self):
        self.login("admin", "admin123")
        ed = TitleEditor(self.app, None)
        ed.vars["name"].set("Тестовый фильм"); ed.vars["year"].set("2024")
        ed.vars["country"].set("Россия"); ed.vars["genres"].set("Драма, Комедия")
        ed.save()
        self.app.catalog_tab.query.set("Тестовый"); self.app.catalog_tab.search()
        self.assertEqual(len(self.app.catalog_tab.tree.get_children()), 1)

    def test_11_poster_shown_in_card_and_catalog_preview(self):
        self.login("demo", "demo1234")
        cat = self.app.catalog_tab
        cat.query.set("Паразиты"); cat.search()
        self.app.update()               # обработка события выбора строки
        self.assertTrue(cat.poster_view.has_image)
        win = TitleWindow(self.app, int(cat.tree.get_children()[0]))
        self.assertTrue(win.poster_view.has_image)
        win.destroy()

    def test_12_live_search_by_english_name_and_empty_result_message(self):
        self.login("demo", "demo1234")
        cat = self.app.catalog_tab
        cat.query_entry.insert(0, "squid game")      # без нажатия Enter: поиск по мере ввода
        time.sleep(0.4)
        self.app.update()
        self.assertEqual([cat.tree.item(i)["values"][0] for i in cat.tree.get_children()],
                         ["Игра в кальмара"])
        cat.query.set("zzzz")
        time.sleep(0.4)
        self.app.update()
        self.assertEqual(len(cat.tree.get_children()), 0)
        self.assertIn("Ничего не найдено", cat.status.cget("text"))

    def test_13_cover_is_drawn_for_title_without_poster_and_catalog_is_paged(self):
        from filmshelf.catalog_import import import_catalog
        self.app.services.catalog.titles.conn.execute("UPDATE titles SET poster = '' WHERE id = 1")
        import gzip, json, tempfile, pathlib
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "c.json.gz"
            with gzip.open(path, "wt", encoding="utf-8") as fh:
                json.dump([[f"Movie {i}", "", "", "movie", 2000, "США", 1, 100, "Text", ["Драма"]]
                           for i in range(250)], fh)
            import_catalog(self.app.services.catalog.titles.conn, path)
        self.login("demo", "demo1234")
        cat = self.app.catalog_tab
        self.assertEqual(len(cat.tree.get_children()), 100)          # страница из 100 строк
        self.assertIn("Стр. 1 из 3", cat.page_label.cget("text"))
        cat.turn_page(1)
        self.assertIn("Стр. 2 из 3", cat.page_label.cget("text"))
        cat.query.set("movie 249"); cat.search()
        self.app.update()
        self.assertFalse(cat.poster_view.has_image)                  # у импортированного тайтла нет файла
        self.assertGreater(len(cat.poster_view.find_all()), 10)      # обложка нарисована на холсте

    def test_14_tmdb_window_localizes_titles_on_page(self):
        import tempfile, threading
        from http.server import ThreadingHTTPServer
        from pathlib import Path
        from tests.test_enrich import FakeTmdb
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeTmdb)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.db"
            conn = connect(path); init_db(conn)
            services = Services.create(conn)
            services.catalog.titles.add({"name": "Parasite", "original_name": "", "alt_names": "", "kind": "movie",
                                         "year": 2019, "country": "США", "episodes": 1, "duration": 100,
                                         "description": "English.", "poster": ""}, ["Драма"])
            admin = services.auth.register("admin", "admin@example.com", "admin123", "admin")
            self.app.destroy()
            self.app = App(services, path)
            self.login("admin", "admin123")
            from filmshelf.ui.tmdb_window import TmdbWindow
            win = TmdbWindow(self.app, [int(i) for i in self.app.catalog_tab.tree.get_children()],
                             on_done=self.app.catalog_tab._after_edit,
                             api_base=f"http://127.0.0.1:{port}/3", image_base=f"http://127.0.0.1:{port}/t/p/w500")
            win.key.set("testkey")
            win.with_posters.set(False)
            win.start()
            for _ in range(60):
                self.app.update(); time.sleep(0.1)
                if win.thread and not win.thread.is_alive():
                    break
            time.sleep(0.5)                   # окно опрашивает поток раз в 300 мс и затем обновляет каталог
            self.app.update()
            self.assertEqual(win.progress.renamed, 1)
            self.assertEqual(self.app.catalog_tab.tree.item(self.app.catalog_tab.tree.get_children()[0])["values"][0], "Паразиты")
            win.destroy()
            conn.close()
        server.shutdown()

    def test_15_results_have_thumbnails_and_get_russian_names_and_posters_automatically(self):
        import tempfile, threading
        from http.server import ThreadingHTTPServer
        from pathlib import Path
        from filmshelf import posters
        from tests.test_enrich import FakeTmdb
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeTmdb)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        old_dir = posters.USER_DIR
        with tempfile.TemporaryDirectory() as tmp:
            posters.USER_DIR = Path(tmp) / "posters"
            try:
                path = Path(tmp) / "app.db"
                conn = connect(path); init_db(conn)
                services = Services.create(conn)
                services.catalog.titles.add({"name": "Parasite", "original_name": "", "alt_names": "", "kind": "movie",
                                             "year": 2019, "country": "США", "episodes": 1, "duration": 100,
                                             "description": "English.", "poster": ""}, ["Драма"])
                services.auth.register("admin", "admin@example.com", "admin123", "admin")
                self.app.destroy()
                self.app = App(services, path)
                loc = self.app.localizer                      # ключ и адреса – от имитатора TMDB
                loc.get_key = lambda: "testkey"
                loc.api_base = f"http://127.0.0.1:{port}/3"
                loc.image_base = f"http://127.0.0.1:{port}/t/p/w500"
                self.login("admin", "admin123")
                cat = self.app.catalog_tab
                row = cat.tree.get_children()[0]
                self.assertTrue(cat.tree.item(row, "image"))             # в результатах поиска есть миниатюра
                for _ in range(100):
                    self.app.update(); time.sleep(0.1)
                    if cat.tree.item(row)["values"][0] == "Паразиты":
                        break
                self.assertEqual(cat.tree.item(row)["values"][0], "Паразиты")
                self.assertTrue(cat.poster_view.has_image)               # настоящий постер вместо нарисованной обложки
                cat.query.set("parasite"); cat.search()                  # прежнее название тоже находится
                self.assertEqual(len(cat.tree.get_children()), 1)
            finally:
                self.app.localizer.close()
                posters.USER_DIR = old_dir
                conn.close()
        server.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2)

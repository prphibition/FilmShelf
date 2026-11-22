"""Главное окно приложения: переключение между экранами."""
import tkinter as tk
from tkinter import ttk

from ..config import APP_NAME
from ..enrich import AutoEnricher
from ..services import Services
from ..settings import tmdb_key
from .catalog import CatalogFrame
from .login import LoginFrame
from .my_list import MyListFrame
from .profile import ProfileFrame
from .theme import apply_theme


class App(tk.Tk):
    def __init__(self, services: Services, db_path=None):
        super().__init__()
        self.services = services
        self.db_path = db_path          # путь к файлу БД (нужен окну TMDB; для базы в памяти – None)
        self.user = None
        # фоновая загрузка русских названий и постеров из TMDB (для базы в памяти не нужна)
        self.localizer = AutoEnricher(db_path, tmdb_key) if db_path else None
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.title(f"{APP_NAME} — каталог фильмов и сериалов")
        self.geometry("1120x720")
        self.minsize(960, 640)
        apply_theme(self)
        self.root_frame = ttk.Frame(self)
        self.root_frame.pack(fill="both", expand=True)
        self.show_login()

    def close(self) -> None:
        if self.localizer is not None:
            self.localizer.close()
        self.destroy()

    def _clear(self) -> None:
        for child in self.root_frame.winfo_children():
            child.destroy()

    def show_login(self) -> None:
        self.user = None
        self._clear()
        LoginFrame(self.root_frame, self).pack(fill="both", expand=True)

    def on_login(self, user) -> None:
        self.user = user
        self._clear()
        header = ttk.Frame(self.root_frame, padding=(12, 8))
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, style="Title.TLabel",
                  font=("TkDefaultFont", 16, "bold")).pack(side="left")
        ttk.Button(header, text="Выйти", command=self.show_login).pack(side="right")
        role = " (администратор)" if user.is_admin else ""
        ttk.Label(header, text=f"{user.username}{role}").pack(side="right", padx=12)

        self.tabs = ttk.Notebook(self.root_frame)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.catalog_tab = CatalogFrame(self.tabs, self)
        self.list_tab = MyListFrame(self.tabs, self)
        self.profile_tab = ProfileFrame(self.tabs, self)
        self.tabs.add(self.catalog_tab, text="  Каталог  ")
        self.tabs.add(self.list_tab, text="  Мой список  ")
        self.tabs.add(self.profile_tab, text="  Профиль  ")
        self.tabs.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _on_tab_changed(self, _event) -> None:
        current = self.tabs.nametowidget(self.tabs.select())
        if hasattr(current, "reload"):
            current.reload()
        elif hasattr(current, "search"):
            current.search()

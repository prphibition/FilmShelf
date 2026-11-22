"""Окно «Русские названия и постеры»: обогащение каталога данными TMDB в фоновом потоке."""
import threading
import tkinter as tk
from tkinter import ttk

from .. import enrich, posters, wiki
from ..settings import save_settings, tmdb_key
from .theme import BG


class TmdbWindow(tk.Toplevel):
    def __init__(self, app, page_ids, on_done=None, api_base=enrich.API_BASE, image_base=enrich.IMAGE_BASE,
                 wiki_api=wiki.WIKI_API):
        super().__init__(app)
        self.app, self.page_ids, self.on_done = app, list(page_ids), on_done
        self.api_base, self.image_base, self.wiki_api = api_base, image_base, wiki_api
        self.configure(background=BG)
        self.title("Русские названия и постеры (TMDB)")
        self.resizable(False, False)
        self.conn = app.services.catalog.titles.conn
        self.localizer = getattr(app, "localizer", None)
        if self.localizer is not None:               # пока окно открыто, фоновая автозагрузка не мешает
            self.localizer.pause()
        self.thread, self.progress, self.stop = None, enrich.Progress(), threading.Event()

        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, wraplength=460, justify="left", text=(
            "Приложение найдёт тайтлы в TMDB и Википедии, заменит названия и описания русскими и скачает "
            "оригинальные постеры. Википедия работает без ключа; бесплатный ключ TMDB (themoviedb.org → "
            "профиль → Настройки → API) даёт больше постеров и названий. Ключ сохраняется: после этого "
            "тайтлы в результатах поиска подгружаются сами, а остальной каталог — в фоне.")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="Ключ TMDB (необязательно)").grid(row=1, column=0, sticky="w", pady=(12, 2))
        self.key = tk.StringVar(value=tmdb_key())
        ttk.Entry(body, textvariable=self.key, width=52).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="Что обработать").grid(row=3, column=0, sticky="w", pady=(10, 2))
        pending = len(enrich.pending_ids(self.conn))
        self.scopes = {f"Тайтлы на текущей странице ({len(self.page_ids)})": ("page", None),
                       "Первые 1000 необработанных": ("top", 1000),
                       f"Все необработанные ({pending})": ("all", None)}
        self.scope = tk.StringVar(value=next(iter(self.scopes)))
        ttk.Combobox(body, textvariable=self.scope, values=list(self.scopes), state="readonly",
                     width=50).grid(row=4, column=0, columnspan=2, sticky="w")
        self.with_posters = tk.BooleanVar(value=posters.Image is not None)
        check = ttk.Checkbutton(body, text="Скачивать постеры (нужна библиотека Pillow)", variable=self.with_posters)
        check.grid(row=5, column=0, columnspan=2, sticky="w", pady=(10, 0))
        if posters.Image is None:
            check.state(["disabled"])
        self.bar = ttk.Progressbar(body, length=460, mode="determinate")
        self.bar.grid(row=6, column=0, columnspan=2, pady=(14, 4))
        self.label = ttk.Label(body, style="Muted.TLabel", wraplength=460, text="Готово к запуску.")
        self.label.grid(row=7, column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(12, 0))
        self.start_btn = ttk.Button(buttons, text="Начать", style="Accent.TButton", command=self.start)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(buttons, text="Остановить", command=self.stop.set, state="disabled")
        self.stop_btn.pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.close)

    def start(self) -> None:
        key = self.key.get().strip()
        save_settings({"tmdb_key": key})                  # пустой ключ – работаем только с Википедией
        mode, limit = self.scopes[self.scope.get()]
        ids = enrich.pending_ids(self.conn, limit, self.page_ids if mode == "page" else None)
        if not ids:
            self.label.config(text="Нечего обрабатывать: все выбранные тайтлы уже проверены.", style="Muted.TLabel")
            return
        self.progress, self.stop = enrich.Progress(), threading.Event()
        self.stop_btn.config(command=self.stop.set)
        self.thread = threading.Thread(
            target=enrich.enrich, daemon=True,
            args=(self.app.db_path, ids, key, self.progress, self.stop, 6, self.with_posters.get(),
                  self.api_base, self.image_base), kwargs={"wiki_api": self.wiki_api})
        self.thread.start()
        self.start_btn.state(["disabled"])
        self.stop_btn.state(["!disabled"])
        self.label.config(style="Muted.TLabel")
        self._poll()

    def _poll(self) -> None:
        p = self.progress
        self.bar.config(maximum=max(1, p.total), value=p.done)
        self.label.config(text=f"Обработано {p.done} из {p.total} · русских названий: {p.renamed} · "
                               f"постеров: {p.posters} · ошибок: {p.errors}  {p.message}")
        if self.thread is not None and self.thread.is_alive():
            self.after(300, self._poll)
            return
        self.start_btn.state(["!disabled"])
        self.stop_btn.state(["disabled"])
        if p.message and "Ключ" in p.message:
            self.label.config(style="Error.TLabel")
        if self.on_done:
            self.on_done()

    def close(self) -> None:
        self.stop.set()
        if self.localizer is not None:
            self.localizer.resume()
            self.localizer.wake()
        self.destroy()

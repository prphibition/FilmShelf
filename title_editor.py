"""Окно добавления и редактирования тайтла (только для администратора)."""
import tkinter as tk
from tkinter import filedialog, ttk

from .. import posters
from ..config import KINDS
from ..services import ServiceError
from .theme import BG


class TitleEditor(tk.Toplevel):
    def __init__(self, app, title_id, on_saved=None):
        super().__init__(app)
        self.app, self.title_id, self.on_saved = app, title_id, on_saved
        self.catalog = app.services.catalog
        self.configure(background=BG)
        self.title("Редактирование тайтла" if title_id else "Новый тайтл")
        self.resizable(False, False)
        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)
        self.vars = {k: tk.StringVar() for k in (
            "name", "original_name", "alt_names", "kind", "year", "country", "episodes",
            "duration", "genres", "poster")}
        self.vars["kind"].set(KINDS["movie"])
        self.vars["episodes"].set("1")
        self.vars["duration"].set("90")

        fields = (("Название", "name", "entry"), ("Оригинальное название", "original_name", "entry"),
                  ("Другие названия (через запятую)", "alt_names", "entry"),
                  ("Тип", "kind", "combo"), ("Год выпуска", "year", "spin"),
                  ("Страна", "country", "entry"), ("Серий", "episodes", "spin"),
                  ("Длительность серии, мин", "duration", "spin"),
                  ("Жанры (через запятую)", "genres", "entry"))
        for r, (label, key, kind) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 12))
            if kind == "combo":
                widget = ttk.Combobox(body, textvariable=self.vars[key], state="readonly",
                                      values=list(KINDS.values()), width=30)
            elif kind == "spin":
                widget = ttk.Spinbox(body, textvariable=self.vars[key], from_=1, to=2100, width=12)
            else:
                widget = ttk.Entry(body, textvariable=self.vars[key], width=44)
            widget.grid(row=r, column=1, sticky="w", pady=3)
        row = len(fields)
        ttk.Label(body, text="Постер").grid(row=row, column=0, sticky="w", pady=3)
        box = ttk.Frame(body)
        box.grid(row=row, column=1, sticky="w", pady=3)
        ttk.Entry(box, textvariable=self.vars["poster"], width=30, state="readonly").pack(side="left")
        ttk.Button(box, text="Выбрать файл…", command=self.choose_poster).pack(side="left", padx=6)
        ttk.Label(body, text="Описание").grid(row=row + 1, column=0, sticky="nw", pady=3)
        self.description = tk.Text(body, width=44, height=5, wrap="word", font="TkDefaultFont")
        self.description.grid(row=row + 1, column=1, pady=3)
        self.error = ttk.Label(body, style="Error.TLabel", wraplength=380)
        self.error.grid(row=row + 2, column=0, columnspan=2, sticky="w")
        bar = ttk.Frame(body)
        bar.grid(row=row + 3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(bar, text="Сохранить", command=self.save, style="Accent.TButton").pack(side="left", padx=6)
        ttk.Button(bar, text="Отмена", command=self.destroy).pack(side="left")
        if title_id:
            self._load(title_id)

    def _load(self, title_id: int) -> None:
        t = self.catalog.get(title_id)
        for key, value in (("name", t.name), ("original_name", t.original_name), ("alt_names", t.alt_names),
                           ("kind", KINDS[t.kind]), ("year", t.year), ("country", t.country),
                           ("episodes", t.episodes), ("duration", t.duration),
                           ("genres", ", ".join(t.genres)), ("poster", t.poster)):
            self.vars[key].set(str(value))
        self.description.insert("1.0", t.description)

    def choose_poster(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="Постер тайтла",
            filetypes=[("Изображения", "*.png *.gif *.jpg *.jpeg *.webp *.bmp"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            self.vars["poster"].set(posters.import_poster(path))
        except ServiceError as exc:
            self.error.config(text=str(exc))

    def save(self) -> None:
        kind = next((k for k, v in KINDS.items() if v == self.vars["kind"].get()), None)
        data = {k: v.get() for k, v in self.vars.items() if k not in ("genres", "kind")}
        data.update(kind=kind, description=self.description.get("1.0", "end"))
        genres = self.vars["genres"].get().split(",")
        try:
            if self.title_id:
                self.catalog.update(self.app.user, self.title_id, data, genres)
            else:
                self.catalog.create(self.app.user, data, genres)
        except ServiceError as exc:
            self.error.config(text=str(exc))
            return
        if self.on_saved:
            self.on_saved()
        self.destroy()

"""Вкладка «Каталог»: поиск, фильтры и сортировка тайтлов."""
import tkinter as tk
import zlib
from tkinter import messagebox, ttk

from .. import posters
from ..config import KINDS
from ..database import normalize
from ..models import SearchFilters
from ..services import ServiceError
from ..settings import auto_localize, save_settings
from .common import fill_tree, make_tree, parse_number, selected_id
from .poster_view import PosterView
from .title_editor import TitleEditor
from .title_window import TitleWindow
from .tmdb_window import TmdbWindow

ANY = "Любой"
PAGE_SIZE = 100
POLL_MS = 600                      # как часто забирать из фонового загрузчика обновлённые тайтлы
THUMB_CACHE_LIMIT = 400
SORTS = {"По рейтингу": "rating", "По году выхода": "year", "По названию": "name"}
COLUMNS = (("name", "Название", 230), ("kind", "Тип", 75), ("year", "Год", 55, "center"),
           ("country", "Страна", 110), ("genres", "Жанры", 210),
           ("score", "Рейтинг", 70, "center"), ("votes", "Оценок", 65, "center"))


class CatalogFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self.catalog = app.services.catalog
        self.localizer = getattr(app, "localizer", None)     # фоновая загрузка названий и постеров
        self._thumbs, self._placeholders = {}, {}           # кэш миниатюр (ссылки нужны, пока строки на экране)
        self._poll_job = None
        self._build_filters()
        self._build_preview()
        self.tree = make_tree(self, COLUMNS, height=5, thumbs=True)
        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_preview())
        self._build_buttons()
        self.status = ttk.Label(self, style="Muted.TLabel")
        self.status.pack(anchor="w", pady=(6, 0))
        self._build_localizer_bar()
        self.bind("<Destroy>", self._on_destroy)
        self.reload_options()
        self.search()
        self._poll_localizer()

    def _build_filters(self) -> None:
        box = ttk.LabelFrame(self, text="Поиск и фильтры", padding=8)
        box.pack(fill="x", pady=(0, 8))
        self.query = tk.StringVar()
        self.kind = tk.StringVar(value=ANY)
        self.genre = tk.StringVar(value=ANY)
        self.country = tk.StringVar(value=ANY)
        self.year_from = tk.StringVar()
        self.year_to = tk.StringVar()
        self.min_score = tk.StringVar()
        self.sort = tk.StringVar(value="По рейтингу")

        ttk.Label(box, text="Поиск: название, страна, жанр, год…").grid(row=0, column=0, sticky="w")
        entry = ttk.Entry(box, textvariable=self.query, width=34)
        entry.grid(row=1, column=0, padx=(0, 10), sticky="w")
        entry.bind("<Return>", lambda e: self.search())
        entry.bind("<Escape>", lambda e: self.query.set(""))
        self.query_entry = entry
        self._pending = None
        self.query.trace_add("write", lambda *_: self._schedule_search())
        self.kind_box = self._combo(box, "Тип", self.kind, 1, [ANY, *KINDS.values()])
        self.genre_box = self._combo(box, "Жанр", self.genre, 2, [ANY])
        self.country_box = self._combo(box, "Страна", self.country, 3, [ANY])
        self._combo(box, "Сортировка", self.sort, 4, list(SORTS))
        self._spin(box, "Год от", self.year_from, 0, 1888, 2100, 1, row=2)
        self._spin(box, "Год до", self.year_to, 1, 1888, 2100, 1, row=2)
        self._spin(box, "Рейтинг от", self.min_score, 2, 1, 10, 0.5, row=2)
        buttons = ttk.Frame(box)
        buttons.grid(row=3, column=3, columnspan=2, sticky="e", pady=(0, 0))
        ttk.Button(buttons, text="Найти", command=self.search, style="Accent.TButton").pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Сбросить", command=self.reset).pack(side="left")

    @staticmethod
    def _combo(box, label, var, col, values):
        ttk.Label(box, text=label).grid(row=0, column=col, sticky="w")
        combo = ttk.Combobox(box, textvariable=var, values=values, state="readonly", width=16)
        combo.grid(row=1, column=col, padx=(0, 10), sticky="w")
        return combo

    @staticmethod
    def _spin(box, label, var, col, lo, hi, step, row=0):
        ttk.Label(box, text=label).grid(row=row, column=col, sticky="w", pady=(6, 0))
        ttk.Spinbox(box, textvariable=var, from_=lo, to=hi, increment=step,
                    width=9).grid(row=row + 1, column=col, padx=(0, 10), sticky="w")

    def _build_preview(self) -> None:
        """Панель справа от таблицы: постер и краткие сведения о выбранном тайтле."""
        self.preview = ttk.Frame(self, style="Card.TFrame", padding=10, width=190)
        self.preview.pack(side="right", fill="y", padx=(8, 0))
        self.preview.pack_propagate(False)
        self.poster_view = PosterView(self.preview, 150)
        self.poster_view.pack(pady=(0, 8))
        self.preview_name = ttk.Label(self.preview, style="Card.TLabel", wraplength=165,
                                      font=("TkDefaultFont", 11, "bold"), justify="center")
        self.preview_name.pack()
        self.preview_info = ttk.Label(self.preview, style="CardMuted.TLabel", wraplength=165,
                                      justify="center")
        self.preview_info.pack(pady=(4, 0))

    def show_preview(self) -> None:
        title_id = selected_id(self.tree)
        if title_id is None:
            return
        self._show_title(self.catalog.get(title_id))

    def _show_title(self, title) -> None:
        self.poster_view.show(title)
        score = f"{title.avg_score:.1f}" if title.avg_score is not None else "—"
        original = (f"\nОригинал: {title.original_name}"
                    if title.original_name and normalize(title.original_name) != normalize(title.name) else "")
        self.preview_name.config(text=title.name)
        self.preview_info.config(text=f"{KINDS[title.kind]} · {title.year}{original}\nРейтинг: {score}\n"
                                      f"{', '.join(title.genres)}")

    def _build_buttons(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="Открыть карточку", command=self.open_selected,
                   style="Accent.TButton").pack(side="left")
        if self.app.db_path:                         # ключ TMDB и ручной запуск нужны любому пользователю
            ttk.Button(bar, text="Русские названия и постеры…",
                       command=self.open_tmdb).pack(side="left", padx=(6, 0))
        pager = ttk.Frame(bar)
        pager.pack(side="right")
        self.prev_btn = ttk.Button(pager, text="◀ Назад", command=lambda: self.turn_page(-1))
        self.prev_btn.pack(side="left")
        self.page_label = ttk.Label(pager, style="Muted.TLabel", text="Стр. 1 из 1")
        self.page_label.pack(side="left", padx=10)
        self.next_btn = ttk.Button(pager, text="Вперёд ▶", command=lambda: self.turn_page(1))
        self.next_btn.pack(side="left")
        if self.app.user.is_admin:
            ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
            ttk.Button(bar, text="Добавить тайтл", command=self.add_title).pack(side="left")
            ttk.Button(bar, text="Изменить", command=self.edit_title).pack(side="left", padx=6)
            ttk.Button(bar, text="Удалить", command=self.delete_title).pack(side="left")

    def reload_options(self) -> None:
        self.genre_box["values"] = [ANY, *self.catalog.genres()]
        self.country_box["values"] = [ANY, *self.catalog.countries()]

    def _collect_filters(self) -> SearchFilters:
        kind_key = next((k for k, v in KINDS.items() if v == self.kind.get()), None)
        return SearchFilters(
            query=self.query.get().strip(), kind=kind_key,
            genre=None if self.genre.get() == ANY else self.genre.get(),
            country=None if self.country.get() == ANY else self.country.get(),
            year_from=parse_number(self.year_from.get(), int),
            year_to=parse_number(self.year_to.get(), int),
            min_score=parse_number(self.min_score.get(), float),
            sort=SORTS[self.sort.get()])

    def _schedule_search(self) -> None:
        """Поиск по мере ввода: запрос выполняется через 250 мс после последнего нажатия клавиши."""
        if self._pending is not None:
            self.after_cancel(self._pending)
        self._pending = self.after(250, self.search)

    def search(self) -> None:
        if self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None
        try:
            filters = self._collect_filters()
        except ValueError:
            messagebox.showwarning("Фильтры", "Год и рейтинг должны быть числами.")
            return
        self.filters = filters
        self.offset = 0
        self._load()

    def turn_page(self, step: int) -> None:
        self.offset = max(0, self.offset + step * PAGE_SIZE)
        self._load()

    def _load(self) -> None:
        """Загружает текущую страницу результатов по сохранённым фильтрам."""
        total = self.catalog.count(self.filters)
        self.offset = min(self.offset, max(0, (total - 1) // PAGE_SIZE * PAGE_SIZE))
        titles = self.catalog.search(self.filters, PAGE_SIZE, self.offset)
        rows = [(t.id, self._row_values(t), self._thumb(t)) for t in titles]
        self._prune_thumbs(titles)
        fill_tree(self.tree, rows)
        pages = max(1, -(-total // PAGE_SIZE))
        self.page_label.config(text=f"Стр. {self.offset // PAGE_SIZE + 1} из {pages}")
        self.prev_btn.state(["!disabled"] if self.offset > 0 else ["disabled"])
        self.next_btn.state(["!disabled"] if self.offset + PAGE_SIZE < total else ["disabled"])
        count = f"{total:,}".replace(",", " ")
        if rows:
            self.tree.selection_set(str(rows[0][0]))
            self.status.config(text=f"Найдено тайтлов: {count} · показаны {self.offset + 1}–{self.offset + len(rows)}")
        else:
            self.poster_view.clear("Ничего\nне найдено")
            self.preview_name.config(text="")
            self.preview_info.config(text="")
            self.status.config(text="Ничего не найдено. Попробуйте другое слово или сбросьте фильтры.")
        if self.localizer is not None:               # показанным тайтлам – русские названия и постеры в первую очередь
            self.localizer.request([t.id for t in titles])

    # --- строки таблицы и миниатюры постеров ---
    @staticmethod
    def _row_values(t) -> tuple:
        return (t.name, KINDS[t.kind], t.year, t.country, ", ".join(t.genres),
                f"{t.avg_score:.1f}" if t.avg_score is not None else "—", t.votes)

    def _thumb(self, title) -> tk.PhotoImage:
        """Миниатюра постера; пока настоящего нет – цветная заглушка (позже строка обновится сама)."""
        if title.poster:
            photo = self._thumbs.get(title.poster)
            if photo is None:
                photo = posters.load_photo(title.poster, posters.THUMB_WIDTH)
                if photo is not None:
                    self._thumbs[title.poster] = photo
            if photo is not None:
                return photo
        bucket = zlib.crc32(title.name.encode("utf-8")) % 12
        if bucket not in self._placeholders:
            self._placeholders[bucket] = posters.placeholder_thumb(f"ph{bucket}")
        return self._placeholders[bucket]

    def _prune_thumbs(self, titles) -> None:
        if len(self._thumbs) > THUMB_CACHE_LIMIT:
            keep = {t.poster for t in titles}
            self._thumbs = {name: img for name, img in self._thumbs.items() if name in keep}

    # --- фоновая загрузка русских названий и постеров ---
    def _build_localizer_bar(self) -> None:
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(2, 0))
        self.loc_status = ttk.Label(bar, style="Muted.TLabel")
        self.loc_status.pack(side="left")
        if self.localizer is not None:
            self.auto_var = tk.BooleanVar(value=auto_localize())
            self.localizer.enabled = self.auto_var.get()
            ttk.Checkbutton(bar, text="Подгружать русские названия и постеры автоматически",
                            variable=self.auto_var, command=self._toggle_auto).pack(side="right")

    def _toggle_auto(self) -> None:
        save_settings({"auto_localize": bool(self.auto_var.get())})
        self.localizer.enabled = bool(self.auto_var.get())
        self.localizer.wake()
        self._update_loc_status()

    def _update_loc_status(self) -> None:
        loc = self.localizer
        if loc is None:
            text = ""
        elif posters.Image is None:
            text = "Для настоящих постеров установите Pillow: python -m pip install Pillow"
        elif not loc.enabled:
            text = "Автозагрузка названий и постеров выключена."
        elif loc.needs_key and not loc.use_wiki:
            text = loc.message or ("Для русских названий и постеров нужен бесплатный ключ TMDB — "
                                   "кнопка «Русские названия и постеры…».")
        elif loc.message:
            text = loc.message
        else:
            source = "Википедии" if loc.needs_key else "TMDB и Википедии"
            hint = ("" if not loc.needs_key else
                    " · с ключом TMDB постеров и названий будет больше (кнопка «Русские названия и постеры…»)")
            text = (f"Загружаю русские названия и постеры из {source}… обработано: {loc.processed}{hint}"
                    if loc.busy else f"Русские названия и постеры из {source}: обработано {loc.processed}{hint}")
        self.loc_status.config(text=text)

    def _poll_localizer(self) -> None:
        """Забирает у фонового загрузчика обновлённые тайтлы и перерисовывает их строки."""
        self._poll_job = None
        if self.localizer is not None:
            updated = self.localizer.take_updated()
            if updated:
                self._refresh_rows(updated)
            self._update_loc_status()
        self._poll_job = self.after(POLL_MS, self._poll_localizer)

    def _refresh_rows(self, ids) -> None:
        """Обновляет на месте название и миниатюру уже показанных строк (выбор и страница не сбрасываются)."""
        shown, selected = set(self.tree.get_children()), selected_id(self.tree)
        for title_id in ids:
            if str(title_id) not in shown:
                continue
            try:
                title = self.catalog.get(title_id)
            except ServiceError:                     # тайтл успели удалить
                continue
            self.tree.item(str(title_id), values=self._row_values(title), image=self._thumb(title))
            if title_id == selected:
                self._show_title(title)

    def _on_destroy(self, event) -> None:
        if event.widget is self:
            for job in (self._poll_job, self._pending):
                if job is not None:
                    self.after_cancel(job)
            self._poll_job = self._pending = None

    def reset(self) -> None:
        for var in (self.query, self.year_from, self.year_to, self.min_score):
            var.set("")
        for var in (self.kind, self.genre, self.country):
            var.set(ANY)
        self.sort.set("По рейтингу")
        self.search()

    def open_selected(self) -> None:
        title_id = selected_id(self.tree)
        if title_id is None:
            messagebox.showinfo("Каталог", "Выберите тайтл в списке.")
            return
        TitleWindow(self.app, title_id, on_change=self._load)

    def open_tmdb(self) -> None:
        TmdbWindow(self.app, [int(i) for i in self.tree.get_children()], on_done=self._after_edit)

    def add_title(self) -> None:
        TitleEditor(self.app, None, on_saved=self._after_edit)

    def edit_title(self) -> None:
        title_id = selected_id(self.tree)
        if title_id is None:
            messagebox.showinfo("Каталог", "Выберите тайтл для редактирования.")
            return
        TitleEditor(self.app, title_id, on_saved=self._after_edit)

    def delete_title(self) -> None:
        title_id = selected_id(self.tree)
        if title_id is None:
            return
        if messagebox.askyesno("Удаление", "Удалить тайтл вместе с оценками и отзывами?"):
            try:
                self.catalog.delete(self.app.user, title_id)
            except ServiceError as exc:
                messagebox.showerror("Ошибка", str(exc))
            self._after_edit()

    def _after_edit(self) -> None:
        self.reload_options()
        self.search()

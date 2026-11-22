"""Карточка тайтла: описание, рейтинг, личная оценка и отзывы."""
import tkinter as tk
from tkinter import messagebox, ttk

from ..config import KINDS, SCORE_MAX, SCORE_MIN, STATUSES
from ..services import ServiceError
from .poster_view import PosterView
from .theme import ACCENT_HI, BG, MUTED

NO_SCORE = "—"


class TitleWindow(tk.Toplevel):
    def __init__(self, app, title_id: int, on_change=None):
        super().__init__(app)
        self.app, self.title_id, self.on_change = app, title_id, on_change
        self.services = app.services
        self.title_obj = self.services.catalog.get(title_id)
        self.configure(background=BG)
        self.title(self.title_obj.name)
        self.geometry("860x800")
        self.minsize(780, 700)
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        self._build_header(body)
        self._build_list_box(body)
        self._build_reviews(body)
        self.refresh()

    def _build_header(self, body) -> None:
        t = self.title_obj
        top = ttk.Frame(body)
        top.pack(fill="x")
        self.poster_view = PosterView(top, 200)
        self.poster_view.show(t)
        self.poster_view.pack(side="left", anchor="n", padx=(0, 14))
        info_box = ttk.Frame(top)
        info_box.pack(side="left", fill="both", expand=True)
        body = info_box
        ttk.Label(body, text=t.name, font=("TkDefaultFont", 18, "bold"),
                  style="Title.TLabel", wraplength=560).pack(anchor="w")
        if t.original_name and t.original_name != t.name:
            ttk.Label(body, text=t.original_name, style="Muted.TLabel").pack(anchor="w")
        if t.alt_names:
            ttk.Label(body, text="Также: " + t.alt_names, style="Muted.TLabel",
                      wraplength=560).pack(anchor="w")
        episodes = "" if t.kind == "movie" else f" · {t.episodes} эп."
        info = (f"{KINDS[t.kind]} · {t.year} · {t.country}{episodes} · "
                f"{t.duration} мин. · {', '.join(t.genres)}")
        ttk.Label(body, text=info, wraplength=560).pack(anchor="w", pady=(6, 2))
        self.rating = ttk.Label(body, font=("TkDefaultFont", 12, "bold"), foreground=ACCENT_HI)
        self.rating.pack(anchor="w")
        text = tk.Text(body, height=9, wrap="word", font="TkDefaultFont", padx=8, pady=6)
        text.insert("1.0", t.description or "Описание отсутствует.")
        text.config(state="disabled")
        text.pack(fill="x", pady=8)

    def _build_list_box(self, body) -> None:
        box = ttk.LabelFrame(body, text="Мой список", padding=8)
        box.pack(fill="x")
        self.status = tk.StringVar()
        self.score = tk.StringVar(value=NO_SCORE)
        self.progress = tk.StringVar(value="0")
        ttk.Label(box, text="Статус").grid(row=0, column=0, sticky="w")
        ttk.Combobox(box, textvariable=self.status, values=list(STATUSES.values()),
                     state="readonly", width=16).grid(row=1, column=0, padx=(0, 10))
        ttk.Label(box, text="Оценка").grid(row=0, column=1, sticky="w")
        ttk.Combobox(box, textvariable=self.score, state="readonly", width=6,
                     values=[NO_SCORE, *range(SCORE_MIN, SCORE_MAX + 1)]
                     ).grid(row=1, column=1, padx=(0, 10))
        ttk.Label(box, text=f"Просмотрено серий (из {self.title_obj.episodes})").grid(
            row=0, column=2, sticky="w")
        ttk.Spinbox(box, textvariable=self.progress, from_=0, to=self.title_obj.episodes,
                    width=6).grid(row=1, column=2, padx=(0, 14), sticky="w")
        ttk.Button(box, text="Сохранить", command=self.save_entry,
                   style="Accent.TButton").grid(row=1, column=3)
        ttk.Button(box, text="Убрать из списка", command=self.remove_entry).grid(
            row=1, column=4, padx=6)

    def _build_reviews(self, body) -> None:
        box = ttk.LabelFrame(body, text="Отзывы", padding=8)
        box.pack(fill="both", expand=True, pady=(10, 0))
        frame = ttk.Frame(box)
        frame.pack(fill="both", expand=True)
        self.reviews = tk.Text(frame, height=8, wrap="word", state="disabled",
                               font="TkDefaultFont", padx=8, pady=6)
        scroll = ttk.Scrollbar(frame, command=self.reviews.yview)
        self.reviews.configure(yscrollcommand=scroll.set)
        self.reviews.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.reviews.tag_configure("author", font=("TkDefaultFont", 10, "bold"),
                                   foreground=ACCENT_HI)
        self.reviews.tag_configure("date", foreground=MUTED)
        ttk.Label(box, text="Ваш отзыв").pack(anchor="w", pady=(8, 0))
        self.review_text = tk.Text(box, height=3, wrap="word", font="TkDefaultFont",
                                  padx=8, pady=6)
        self.review_text.pack(fill="x")
        bar = ttk.Frame(box)
        bar.pack(fill="x", pady=(6, 0))
        ttk.Button(bar, text="Опубликовать отзыв", command=self.save_review,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(bar, text="Удалить мой отзыв", command=self.delete_review).pack(
            side="left", padx=6)

    def refresh(self) -> None:
        t = self.services.catalog.get(self.title_id)
        self.rating.config(text=(
            f"Рейтинг {t.avg_score:.2f} из 10 · оценок: {t.votes}"
            if t.avg_score is not None else "Рейтинг: оценок пока нет"))
        entry = self.services.lists.get_entry(self.app.user, self.title_id)
        if entry:
            self.status.set(STATUSES[entry.status])
            self.score.set(str(entry.score) if entry.score else NO_SCORE)
            self.progress.set(str(entry.progress))
        else:
            self.status.set(STATUSES["plan"])
        self._show_reviews()

    def _show_reviews(self) -> None:
        self.reviews.config(state="normal")
        self.reviews.delete("1.0", "end")
        items = self.services.reviews.for_title(self.title_id)
        if not items:
            self.reviews.insert("end", "Отзывов пока нет — станьте первым.")
        for r in items:
            self.reviews.insert("end", r.username, "author")
            self.reviews.insert("end", f"  {r.created_at}\n", "date")
            self.reviews.insert("end", r.text + "\n\n")
        self.reviews.config(state="disabled")

    def _status_key(self) -> str:
        return next(k for k, v in STATUSES.items() if v == self.status.get())

    def save_entry(self) -> None:
        score = None if self.score.get() == NO_SCORE else int(self.score.get())
        try:
            self.services.lists.set_entry(self.app.user, self.title_id, self._status_key(),
                                          score, int(self.progress.get() or 0))
        except (ServiceError, ValueError) as exc:
            messagebox.showerror("Мой список", str(exc), parent=self)
            return
        self._changed()

    def remove_entry(self) -> None:
        self.services.lists.remove(self.app.user, self.title_id)
        self.score.set(NO_SCORE)
        self.progress.set("0")
        self._changed()

    def save_review(self) -> None:
        try:
            self.services.reviews.save(self.app.user, self.title_id,
                                       self.review_text.get("1.0", "end"))
        except ServiceError as exc:
            messagebox.showerror("Отзыв", str(exc), parent=self)
            return
        self.review_text.delete("1.0", "end")
        self._show_reviews()

    def delete_review(self) -> None:
        own = [r for r in self.services.reviews.for_title(self.title_id)
               if r.user_id == self.app.user.id]
        if own:
            self.services.reviews.delete(self.app.user, own[0].id)
            self._show_reviews()

    def _changed(self) -> None:
        self.refresh()
        if self.on_change:
            self.on_change()

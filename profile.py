"""Вкладка «Профиль»: данные аккаунта и статистика просмотров."""
import tkinter as tk
from tkinter import ttk

from ..config import STATUSES
from .theme import ACCENT_HI, BAR_COLORS, BORDER, MUTED, SURFACE, TEXT


class ProfileFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=16)
        self.app = app
        user = app.user
        role = "администратор" if user.is_admin else "пользователь"
        ttk.Label(self, text=user.username, style="Title.TLabel",
                  font=("TkDefaultFont", 20, "bold")).pack(anchor="w")
        ttk.Label(self, text=f"{user.email} · {role} · на сайте с {user.created_at[:10]}",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 14))
        self.summary = ttk.Label(self, justify="left", font=("TkDefaultFont", 11))
        self.summary.pack(anchor="w")
        ttk.Label(self, text="Распределение списка по статусам",
                  font=("TkDefaultFont", 11, "bold")).pack(anchor="w", pady=(16, 4))
        self.canvas = tk.Canvas(self, width=620, height=240, background=SURFACE,
                                highlightthickness=1, highlightbackground=BORDER)
        self.canvas.pack(anchor="w")
        self.reload()

    def reload(self) -> None:
        stats = self.app.services.stats.for_user(self.app.user)
        hours, minutes = divmod(stats.minutes_watched, 60)
        mean = f"{stats.mean_score:.2f}" if stats.mean_score is not None else "—"
        self.summary.config(text=(
            f"Тайтлов в списке: {stats.total}\n"
            f"Средняя оценка: {mean}\n"
            f"Время просмотра: {hours} ч {minutes} мин\n"
            f"Любимый жанр (по просмотренному): {stats.top_genre or '—'}"))
        self._draw(stats.counts)

    def _draw(self, counts: dict) -> None:
        c = self.canvas
        c.delete("all")
        top = max(max(counts.values()), 1)
        slot, base, area = 110, 200, 160
        for i, (key, label) in enumerate(STATUSES.items()):
            x0 = 30 + i * slot
            h = counts[key] / top * area
            c.create_rectangle(x0, base - h, x0 + 70, base, fill=BAR_COLORS[key], outline="")
            c.create_text(x0 + 35, base - h - 10, text=str(counts[key]), fill=ACCENT_HI)
            c.create_text(x0 + 35, base + 16, text=label, fill=TEXT)

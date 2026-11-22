"""Вкладка «Мой список»: просмотр и управление личным списком."""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..config import KINDS, STATUSES
from ..services import ServiceError
from .common import fill_tree, make_tree, selected_id
from .title_window import TitleWindow

COLUMNS = (("name", "Название", 300), ("kind", "Тип", 80), ("status", "Статус", 110),
           ("score", "Оценка", 70, "center"), ("progress", "Прогресс", 100, "center"),
           ("updated", "Обновлено", 140, "center"))


class MyListFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=8)
        self.app = app
        self.lists = app.services.lists
        self.current = tk.StringVar(value="all")
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(0, 8))
        self.buttons = {}
        for key, label in (("all", "Все"), *STATUSES.items()):
            btn = ttk.Radiobutton(bar, text=label, value=key, variable=self.current,
                                  style="Toolbutton", command=self.reload)
            btn.pack(side="left", padx=(0, 4))
            self.buttons[key] = (btn, label)
        self.tree = make_tree(self, COLUMNS, height=10)
        self.tree.bind("<Double-1>", lambda e: self.open_selected())
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Открыть карточку", command=self.open_selected).pack(side="left")
        ttk.Button(actions, text="Удалить из списка", command=self.remove_selected).pack(
            side="left", padx=6)
        ttk.Button(actions, text="Экспорт в CSV", command=self.export).pack(side="right")
        self.reload()

    def reload(self) -> None:
        everything = self.lists.entries_of(self.app.user)
        for key, (btn, label) in self.buttons.items():
            n = len(everything) if key == "all" else sum(e.status == key for e in everything)
            btn.config(text=f"{label} ({n})")
        key = self.current.get()
        shown = everything if key == "all" else [e for e in everything if e.status == key]
        fill_tree(self.tree, [(e.title_id, (
            e.title_name, KINDS[e.kind], STATUSES[e.status],
            e.score if e.score is not None else "—",
            f"{e.progress} / {e.episodes}", e.updated_at)) for e in shown])

    def open_selected(self) -> None:
        title_id = selected_id(self.tree)
        if title_id is not None:
            TitleWindow(self.app, title_id, on_change=self.reload)

    def remove_selected(self) -> None:
        title_id = selected_id(self.tree)
        if title_id is not None and messagebox.askyesno("Мой список", "Убрать тайтл из списка?"):
            self.lists.remove(self.app.user, title_id)
            self.reload()

    def export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV-файл", "*.csv")],
            initialfile="my_list.csv")
        if not path:
            return
        try:
            count = self.lists.export_csv(self.app.user, path)
        except (ServiceError, OSError) as exc:
            messagebox.showerror("Экспорт", str(exc))
            return
        messagebox.showinfo("Экспорт", f"Записей сохранено: {count}")

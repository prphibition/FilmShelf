"""Общие вспомогательные функции для окон интерфейса."""
import tkinter as tk
from tkinter import ttk
from typing import Optional, Sequence

from .theme import STRIPE


def make_tree(parent: tk.Misc, columns: Sequence[tuple], height: int = 15,
              thumbs: bool = False) -> ttk.Treeview:
    """Создаёт таблицу с вертикальной прокруткой.

    columns — последовательность (id, заголовок, ширина[, выравнивание]).
    thumbs — добавить слева колонку миниатюр постеров (строки становятся выше).
    """
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], height=height, selectmode="browse",
                        show="tree headings" if thumbs else "headings",
                        style="Posters.Treeview" if thumbs else "Treeview")
    if thumbs:
        tree.heading("#0", text="")
        tree.column("#0", width=56, minwidth=56, stretch=False, anchor="center")
    for col in columns:
        tree.heading(col[0], text=col[1])
        tree.column(col[0], width=col[2], anchor=col[3] if len(col) > 3 else "w")
    scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    tree.tag_configure("odd", background=STRIPE)
    return tree


def parse_number(text: str, cast=int) -> Optional[float]:
    """Преобразует строку поля ввода в число; пустая строка даёт None."""
    text = text.strip().replace(",", ".")
    if not text:
        return None
    return cast(text)


def fill_tree(tree: ttk.Treeview, rows: Sequence[tuple]) -> None:
    """Перезаполняет таблицу; каждая строка — (iid, значения[, изображение])."""
    tree.delete(*tree.get_children())
    for i, row in enumerate(rows):
        iid, values = row[0], row[1]
        tree.insert("", "end", iid=str(iid), values=values, image=row[2] if len(row) > 2 else "",
                    tags=("odd",) if i % 2 else ())


def selected_id(tree: ttk.Treeview) -> Optional[int]:
    sel = tree.selection()
    return int(sel[0]) if sel else None

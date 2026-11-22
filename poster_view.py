"""Виджет постера: настоящее изображение или нарисованная заглушка для тайтлов без постера."""
import colorsys
import tkinter as tk
import zlib

from .. import posters
from ..config import KINDS
from ..models import Title
from .theme import ACCENT, ACCENT_HI, BG, BORDER, MUTED


def _hex(h: float, s: float, v: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


class PosterView(tk.Canvas):
    """Холст пропорций 2:3. Для тайтла без файла постера рисуется обложка: градиент,
    тип, название, год и страна – цвет задаётся названием, поэтому он стабилен."""

    def __init__(self, parent, width: int):
        self.w, self.h = width, round(width * 1.5)
        super().__init__(parent, width=self.w, height=self.h, background=BG,
                         highlightthickness=1, highlightbackground=BORDER)
        self._photo = None
        self.has_image = False
        self.clear()

    def clear(self, text: str = "Выберите тайтл\nв списке") -> None:
        self.delete("all")
        self._photo, self.has_image = None, False
        self.create_text(self.w / 2, self.h / 2, text=text, fill=MUTED, justify="center")

    def show(self, title: Title) -> None:
        self.delete("all")
        self._photo = posters.load_photo(title.poster, self.w) if title.poster else None
        self.has_image = self._photo is not None
        if self._photo is not None:
            self.create_image(self.w / 2, self.h / 2, image=self._photo)
        else:
            self._draw_cover(title)

    def _draw_cover(self, title: Title) -> None:
        hue = (zlib.crc32(title.name.encode("utf-8")) % 360) / 360.0 * 0.28 + 0.62     # фиолетово-пурпурная гамма
        bands = 36
        for i in range(bands):
            t = i / (bands - 1)
            self.create_rectangle(0, i * self.h / bands, self.w, (i + 1) * self.h / bands + 1,
                                  fill=_hex(hue + 0.05 * t, 0.62 + 0.25 * t, 0.62 - 0.52 * t), outline="")
        scale = self.w / 200
        pad = round(14 * scale)
        self.create_rectangle(2, 2, self.w - 2, self.h - 2, outline=ACCENT_HI, width=1)
        badge = KINDS.get(title.kind, "").upper()
        text_id = self.create_text(pad + 8 * scale, pad + 8 * scale, text=badge, anchor="w",
                                   fill="white", font=("TkDefaultFont", max(7, round(8 * scale)), "bold"))
        x0, y0, x1, y1 = self.bbox(text_id)
        box = self.create_rectangle(x0 - 7, y0 - 3, x1 + 7, y1 + 3, fill=ACCENT, outline="")
        self.tag_lower(box, text_id)
        length = len(title.name)
        size = max(8, round(17 * scale * (1.0 if length <= 20 else 0.8 if length <= 38 else 0.62)))
        self.create_rectangle(pad, self.h * 0.60, pad + 34 * scale, self.h * 0.60 + 3, fill=ACCENT_HI, outline="")
        self.create_text(pad, self.h * 0.64, text=title.name.upper(), anchor="nw", fill="white",
                         width=self.w - 2 * pad, font=("TkDefaultFont", size, "bold"))
        self.create_text(pad, self.h - pad - 20 * scale, text=f"{title.year} · {title.country}",
                         anchor="w", fill="#e3d9fa", font=("TkDefaultFont", max(7, round(9 * scale))))
        self.create_text(pad, self.h - pad, text="FILMSHELF", anchor="w", fill=ACCENT_HI,
                         font=("TkDefaultFont", max(6, round(7 * scale)), "bold"))

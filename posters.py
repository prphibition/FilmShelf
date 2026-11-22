"""Постеры тайтлов: поиск файла, импорт пользовательского изображения, загрузка в Tk."""
import colorsys
import shutil
import tkinter as tk
import uuid
import zlib
from fractions import Fraction
from pathlib import Path
from typing import Optional, Union

from .config import DB_DIR
from .services import ValidationError

try:                                   # Pillow необязателен: он добавляет JPEG и качественное масштабирование
    from PIL import Image, ImageOps, ImageTk
except ImportError:                    # pragma: no cover
    Image = ImageOps = ImageTk = None

BUNDLED_DIR = Path(__file__).parent / "posters"   # постеры демонстрационных данных
USER_DIR = DB_DIR / "posters"                     # постеры, добавленные администратором
POSTER_SIZE = (400, 600)
THUMB_WIDTH = 40                                  # миниатюра в списке результатов (40×60)


def poster_path(name: str, user_dir: Union[str, Path, None] = None) -> Optional[Path]:
    """Ищет файл постера по имени сначала в каталоге пользователя, затем в поставке."""
    name = Path(name or "").name            # защита от выхода за пределы каталога
    if not name:
        return None
    for base in (user_dir or USER_DIR, BUNDLED_DIR):
        candidate = Path(base) / name
        if candidate.is_file():
            return candidate
    return None


def import_poster(source: Union[str, Path], user_dir: Union[str, Path, None] = None) -> str:
    """Копирует выбранное изображение в каталог постеров и возвращает имя файла."""
    source, target_dir = Path(source), Path(user_dir or USER_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    if Image is not None:
        name = uuid.uuid4().hex + ".png"
        try:
            with Image.open(source) as img:
                ImageOps.fit(img.convert("RGB"), POSTER_SIZE).save(target_dir / name, "PNG")
        except OSError:
            raise ValidationError("Не удалось открыть изображение.")
        return name
    if source.suffix.lower() not in (".png", ".gif"):
        raise ValidationError("Выберите PNG или GIF либо установите Pillow (pip install Pillow).")
    name = uuid.uuid4().hex + source.suffix.lower()
    shutil.copyfile(source, target_dir / name)
    return name


def import_poster_bytes(data: bytes, name: str, user_dir: Union[str, Path, None] = None) -> str:
    """Сохраняет скачанное изображение (обычно JPEG) как PNG 400×600; нужна библиотека Pillow."""
    if Image is None:
        raise ValidationError("Для загрузки постеров установите Pillow (pip install Pillow).")
    import io
    target_dir = Path(user_dir or USER_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(data)) as img:
        ImageOps.fit(img.convert("RGB"), POSTER_SIZE).save(target_dir / name, "PNG")
    return name


def load_photo(name: str, width: int) -> Optional[tk.PhotoImage]:
    """Возвращает изображение постера заданной ширины или None, если файла нет."""
    path = poster_path(name)
    if path is None:
        return None
    try:
        if Image is not None:
            with Image.open(path) as img:
                height = round(img.height * width / img.width)
                return ImageTk.PhotoImage(img.convert("RGB").resize((width, height), Image.LANCZOS))
        photo = tk.PhotoImage(file=str(path))
        ratio = Fraction(width, photo.width()).limit_denominator(8)
        if ratio.numerator > 1:
            photo = photo.zoom(ratio.numerator)
        if ratio.denominator > 1:
            photo = photo.subsample(ratio.denominator)
        return photo
    except (tk.TclError, OSError):
        return None


def placeholder_thumb(seed: str, width: int = THUMB_WIDTH) -> tk.PhotoImage:
    """Временная миниатюра-градиент (цвет зависит от названия), пока настоящий постер не загружен."""
    height = round(width * 1.5)
    img = tk.PhotoImage(width=width, height=height)
    hue = (zlib.crc32(seed.encode("utf-8")) % 360) / 360.0 * 0.28 + 0.62
    bands = 6
    for i in range(bands):
        r, g, b = colorsys.hsv_to_rgb(hue % 1.0, 0.55 + 0.2 * i / bands, 0.62 - 0.4 * i / bands)
        img.put("#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255)),
                to=(0, i * height // bands, width, (i + 1) * height // bands))
    return img

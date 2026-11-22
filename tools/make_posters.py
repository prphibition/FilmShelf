"""Генерация красивых запасных постеров для демонстрационных тайтлов (нужен Pillow).

Если настоящие постеры не загружены (см. tools/fetch_posters.py), приложение показывает
эти стилизованные обложки: градиент, свечение, мотив по типу произведения и крупное название.
"""
import colorsys
import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from filmshelf.config import KINDS  # noqa: E402
from filmshelf.seed_data import TITLES  # noqa: E402

W, H = 400, 600
OUT = Path(__file__).resolve().parents[1] / "filmshelf" / "posters"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def hsv(h, s, v, a=None):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v)))
    c = (int(r * 255), int(g * 255), int(b * 255))
    return c + (a,) if a is not None else c


def lerp(c1, c2, t):
    return tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3))


def gradient(top, bottom, tilt):
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            t = min(1, max(0, (y + (x - W / 2) * tilt) / H))
            px[x, y] = lerp(top, bottom, t)
    return img


def glow(img, shapes, blur):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for box, color in shapes:
        d.ellipse(box, fill=color)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def motif(img, kind, hue, rng):
    """Крупный графический мотив в верхней части постера."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    light = hsv(hue + 0.02, 0.35, 1.0)
    if kind == "movie":                         # катушка плёнки
        cx, cy = rng.randint(230, 330), rng.randint(110, 170)
        for r, a in ((150, 30), (112, 40), (74, 55)):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=light + (a + 40,), width=5)
        for k in range(6):
            ang = k * math.pi / 3
            x, y = cx + 74 * math.cos(ang) * 0.62, cy + 74 * math.sin(ang) * 0.62
            d.ellipse([x - 16, y - 16, x + 16, y + 16], fill=light + (70,))
    elif kind == "series":                      # экран телевизора со световыми полосами
        x0, y0 = rng.randint(70, 120), rng.randint(70, 110)
        d.rounded_rectangle([x0, y0, x0 + 230, y0 + 150], 18, outline=light + (110,), width=5)
        for k in range(7):
            d.line([x0 + 14, y0 + 20 + k * 18, x0 + 216, y0 + 20 + k * 18], fill=light + (38,), width=3)
        d.polygon([(x0 + 95, y0 + 45), (x0 + 95, y0 + 105), (x0 + 150, y0 + 75)], fill=light + (120,))
    elif kind == "drama":                       # луна и лепестки
        cx, cy = rng.randint(220, 300), rng.randint(130, 180)
        d.ellipse([cx - 90, cy - 90, cx + 90, cy + 90], fill=light + (70,))
        d.ellipse([cx - 70, cy - 100, cx + 110, cy + 80], fill=(0, 0, 0, 0))
        for _ in range(16):
            px_, py_ = rng.randint(20, W - 20), rng.randint(40, 340)
            s = rng.randint(6, 16)
            d.ellipse([px_, py_, px_ + s * 1.6, py_ + s], fill=hsv(hue + 0.1, 0.4, 1.0, rng.randint(50, 130)))
    else:                                       # аниме: солнце, лучи и горы
        cx, cy = W // 2, 190
        for k in range(24):
            ang = k * math.pi / 12
            d.polygon([(cx, cy), (cx + 420 * math.cos(ang - .05), cy + 420 * math.sin(ang - .05)),
                       (cx + 420 * math.cos(ang + .05), cy + 420 * math.sin(ang + .05))], fill=light + (22,))
        d.ellipse([cx - 80, cy - 80, cx + 80, cy + 80], fill=hsv(hue + 0.04, 0.3, 1.0, 120))
        for base, col in ((330, 60), (370, 90)):
            pts = [(0, H)]
            x = 0
            while x <= W + 60:
                pts.append((x, base - rng.randint(20, 90)))
                x += rng.randint(50, 90)
            pts += [(W, H)]
            d.polygon(pts, fill=hsv(hue, 0.7, 0.18, col + 100))
    return Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(0.6)))


def vignette(img):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse([-W * .25, -H * .1, W * 1.25, H * 1.1], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(90))
    dark = Image.new("RGBA", img.size, (6, 3, 12, 255))
    inv = Image.eval(mask, lambda v: 255 - v)
    dark.putalpha(inv.point(lambda v: int(v * 0.85)))
    return Image.alpha_composite(img, dark)


def wrap(draw, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if draw.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line]


def make(index, name, kind, year, country):
    rng = random.Random(index * 7919 + 13)
    hue = rng.choice([0.73, 0.77, 0.81, 0.85, 0.69, 0.89, 0.64])
    img = gradient(hsv(hue, 0.62, 0.62), hsv(hue + 0.05, 0.9, 0.10), rng.uniform(-.25, .25))
    img = glow(img, [([rng.randint(-80, 200), rng.randint(-60, 120), rng.randint(220, 480), rng.randint(220, 380)],
                      hsv(hue + rng.uniform(-.06, .08), .55, 1.0, 120)) for _ in range(3)], 55)
    img = motif(img, kind, hue, rng)
    img = vignette(img)
    # затемнение низа под текстом
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(H // 2, H):
        sd.line([(0, y), (W, y)], fill=(5, 2, 12, int(235 * ((y - H / 2) / (H / 2)) ** 1.4)))
    img = Image.alpha_composite(img, shade)
    d = ImageDraw.Draw(img)
    accent = hsv(hue + 0.04, 0.55, 1.0)
    # бейдж типа
    badge, bf = KINDS[kind].upper(), ImageFont.truetype(BOLD, 15)
    bw = d.textlength(badge, font=bf) + 28
    d.rounded_rectangle([26, 28, 26 + bw, 58], 15, fill=(139, 92, 246, 235))
    d.text((40, 34), badge, font=bf, fill="white")
    # название
    title = name.upper()
    size = 50
    while size > 22:
        font = ImageFont.truetype(BOLD, size)
        lines = wrap(d, title, font, W - 70)
        if len(lines) <= 4 and all(d.textlength(l, font=font) <= W - 70 for l in lines):
            break
        size -= 2
    block = len(lines) * (size + 8)
    y = 470 - block
    d.rectangle([35, y - 20, 95, y - 16], fill=accent)
    for line in lines:
        d.text((37, y + 3), line, font=font, fill=(0, 0, 0, 160))
        d.text((35, y), line, font=font, fill=(250, 246, 255))
        y += size + 8
    small = ImageFont.truetype(REG, 17)
    d.text((35, 505), f"{year}  ·  {country}", font=small, fill=(225, 214, 250))
    d.text((35, 545), "FILMSHELF", font=ImageFont.truetype(BOLD, 13), fill=accent)
    # рамка
    d.rectangle([10, 10, W - 11, H - 11], outline=accent + (90,), width=2)
    return img.convert("RGB")


# Номера тайтлов, для которых в проект уже положены настоящие постеры
# (датасет laxmimerit/Movies-Poster_Dataset на GitHub): иллюстрации их не перезаписывают.
REAL_POSTERS = {15, 16, 17, 19, 20, 21, 28}

if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, _orig, kind, year, country, *_rest) in enumerate(TITLES, start=1):
        if i in REAL_POSTERS:
            continue
        make(i, name, kind, year, country).save(OUT / f"p{i:02d}.png", optimize=True)
    print("постеров создано:", len(TITLES) - len(REAL_POSTERS), "(настоящие не тронуты:", len(REAL_POSTERS), ")")

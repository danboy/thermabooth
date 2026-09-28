"""Photo filters and photobooth layout compositing (Pillow + numpy)."""

import io
import textwrap
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

FILTERS = ["none", "bw", "noir", "sepia", "vivid", "warm", "cool", "vintage"]
LAYOUTS = ["grid", "strip"]
FRAMES = {
    "white": ((255, 255, 255), (60, 60, 60)),
    "black": ((20, 20, 20), (240, 240, 240)),
    "cream": ((250, 244, 228), (90, 60, 40)),
    "pink": ((255, 214, 224), (140, 30, 80)),
    "sky": ((208, 230, 250), (20, 60, 110)),
}

# Thermal printer paper: 58mm at 203dpi = 384 dots wide. Height is whatever the roll needs.
PRINT_WIDTH = 384

_FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "LiberationSans-Bold.ttf",
]


def _font(size: int) -> ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _tone(img: Image.Image, matrix) -> Image.Image:
    arr = np.asarray(img, dtype=np.float32)
    out = arr @ np.array(matrix, dtype=np.float32).T
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _vignette(img: Image.Image, strength: float = 0.45) -> Image.Image:
    w, h = img.size
    y, x = np.ogrid[:h, :w]
    d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2)
    mask = 1 - strength * np.clip(d - 0.4, 0, 1) ** 1.5
    arr = np.asarray(img, dtype=np.float32) * mask[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def apply_filter(img: Image.Image, name: str) -> Image.Image:
    img = img.convert("RGB")
    if name == "bw":
        return ImageOps.grayscale(img).convert("RGB")
    if name == "noir":
        g = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=2)
        return ImageEnhance.Contrast(g.convert("RGB")).enhance(1.35)
    if name == "sepia":
        return _tone(img, [[0.393, 0.769, 0.189], [0.349, 0.686, 0.168], [0.272, 0.534, 0.131]])
    if name == "vivid":
        img = ImageEnhance.Color(img).enhance(1.6)
        return ImageEnhance.Contrast(img).enhance(1.15)
    if name == "warm":
        return _tone(img, [[1.08, 0, 0], [0, 1.0, 0], [0, 0, 0.88]])
    if name == "cool":
        return _tone(img, [[0.9, 0, 0], [0, 1.0, 0], [0, 0, 1.12]])
    if name == "vintage":
        img = ImageEnhance.Color(img).enhance(0.75)
        img = _tone(img, [[1.0, 0.05, 0], [0, 0.95, 0.05], [0.05, 0.1, 0.8]])
        img = ImageEnhance.Contrast(img).enhance(0.9)
        return _vignette(img)
    return img


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.4))


def _caption(draw: ImageDraw.ImageDraw, box, text: str, fill, date_fill) -> None:
    x0, y0, x1, y1 = box
    date = datetime.now().strftime("%b %d, %Y")
    text = text.strip()
    height = y1 - y0
    if text:
        size = int(height * 0.34)
        font = _font(size)
        while size > 18:
            font = _font(size)
            lines = textwrap.wrap(text, width=max(8, int((x1 - x0) / (size * 0.62)))) or [text]
            if len(lines) * size * 1.15 <= height * 0.7:
                break
            size -= 4
        block = "\n".join(lines)
        draw.multiline_text(((x0 + x1) / 2, y0 + height * 0.38), block, font=font, fill=fill, anchor="mm", align="center")
        draw.text(((x0 + x1) / 2, y1 - height * 0.12), date, font=_font(int(height * 0.14)), fill=date_fill, anchor="mm")
    else:
        draw.text(((x0 + x1) / 2, (y0 + y1) / 2), date, font=_font(int(height * 0.2)), fill=date_fill, anchor="mm")


def compose(photos: list[Image.Image], filter_name: str, layout: str, frame: str, caption: str) -> Image.Image:
    """Build the final shareable image from the raw photos."""
    bg, ink = FRAMES.get(frame, FRAMES["white"])
    shots = [apply_filter(p, filter_name) for p in photos]
    n = len(shots)

    if layout == "strip":
        w, margin, gap, cap_h = 600, 30, 20, 170
        sw = w - 2 * margin
        sh = sw * 3 // 4
        h = margin + n * sh + (n - 1) * gap + margin + cap_h
        canvas = Image.new("RGB", (w, h), bg)
        for i, s in enumerate(shots):
            canvas.paste(_cover(s, (sw, sh)), (margin, margin + i * (sh + gap)))
        _caption(ImageDraw.Draw(canvas), (margin, h - cap_h, w - margin, h - 10), caption, ink, ink)
        return canvas

    # 2x2 grid, 3:4 print proportions
    w, h, margin, gap, cap_h = 1200, 1600, 60, 40, 260
    cols = 2
    rows = (n + cols - 1) // cols
    sw = (w - 2 * margin - gap) // cols
    sh = (h - 2 * margin - cap_h - (rows - 1) * gap) // rows
    canvas = Image.new("RGB", (w, h), bg)
    for i, s in enumerate(shots):
        r, c = divmod(i, cols)
        canvas.paste(_cover(s, (sw, sh)), (margin + c * (sw + gap), margin + r * (sh + gap)))
    _caption(ImageDraw.Draw(canvas), (margin, h - margin - cap_h, w - margin, h - margin), caption, ink, ink)
    return canvas


def for_print(final: Image.Image) -> Image.Image:
    """Scale the composed image to the printer's paper width, roll length grows to fit."""
    w, h = final.size
    new_h = max(1, round(h * PRINT_WIDTH / w))
    return final.resize((PRINT_WIDTH, new_h), Image.LANCZOS)


def to_jpeg(img: Image.Image, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def thumbnail(img: Image.Image, filter_name: str, size=(240, 180)) -> bytes:
    return to_jpeg(apply_filter(_cover(img, size), filter_name), 80)

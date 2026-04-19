import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TILE_W = 512
TILE_H = 512
LABEL_H = 40
COLS = 3
ROWS = 2
PAD = 10
BG = (255, 255, 255)
BORDER = (40, 40, 40)
LABEL_BG = (230, 230, 230)

ORDER = ("iso", "top", "north", "south", "east", "west")
LABELS = {
    "iso": "ISO (primary)",
    "top": "TOP",
    "north": "NORTH",
    "south": "SOUTH",
    "east": "EAST",
    "west": "WEST",
}


def _font():
    try:
        return ImageFont.load_default(size=28)
    except TypeError:
        return ImageFont.load_default()


def _flatten(img: Image.Image) -> Image.Image:
    if img.mode != "RGBA":
        return img.convert("RGB")
    bg = Image.new("RGB", img.size, BG)
    bg.paste(img, (0, 0), img)
    return bg


def build_composite(view_paths: dict[str, Path]) -> Image.Image:
    total_tile_h = LABEL_H + TILE_H
    W = COLS * TILE_W + (COLS + 1) * PAD
    H = ROWS * total_tile_h + (ROWS + 1) * PAD
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    font = _font()

    for i, view in enumerate(ORDER):
        r, c = divmod(i, COLS)
        x0 = PAD + c * (TILE_W + PAD)
        y0 = PAD + r * (total_tile_h + PAD)

        draw.rectangle([x0, y0, x0 + TILE_W, y0 + LABEL_H], fill=LABEL_BG)
        draw.text((x0 + 10, y0 + 6), LABELS[view], fill=(20, 20, 20), font=font)

        img_y0 = y0 + LABEL_H
        draw.rectangle([x0, img_y0, x0 + TILE_W, img_y0 + TILE_H], outline=BORDER, width=2)

        img = _flatten(Image.open(view_paths[view]))
        iw, ih = img.size
        scale = min(TILE_W / iw, TILE_H / ih)
        nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
        resized = img.resize((nw, nh), Image.LANCZOS)
        ox = x0 + (TILE_W - nw) // 2
        oy = img_y0 + (TILE_H - nh) // 2
        canvas.paste(resized, (ox, oy))

    return canvas


def composite_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

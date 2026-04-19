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
        resized = img.resize((nw, nh), Image.NEAREST)
        ox = x0 + (TILE_W - nw) // 2
        oy = img_y0 + (TILE_H - nh) // 2
        canvas.paste(resized, (ox, oy))

    return canvas


def composite_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _view_paths(schematic_dir: Path) -> dict[str, Path] | None:
    paths = {v: schematic_dir / f"{v}.png" for v in ORDER}
    if any(not p.is_file() for p in paths.values()):
        return None
    return paths


def _cli() -> int:
    import argparse
    import logging

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    log = logging.getLogger("composite")

    p = argparse.ArgumentParser(description="Render composite grid PNGs for a directory of schematic subdirs.")
    p.add_argument("--input", type=Path, default=Path("./nbt-out"), help="Directory of <id>/ schematic subdirs (default: ./nbt-out).")
    p.add_argument("--output", type=Path, required=True, help="Directory to write <id>.png composites into.")
    p.add_argument("--limit", type=int, default=None, help="Stop after this many composites.")
    p.add_argument("--force", action="store_true", help="Overwrite existing composites (default: skip).")
    args = p.parse_args()

    if not args.input.is_dir():
        log.error("Input directory does not exist: %s", args.input)
        return 2
    args.output.mkdir(parents=True, exist_ok=True)

    subdirs = sorted(s for s in args.input.iterdir() if s.is_dir())
    written = skipped = missing = 0
    for sub in subdirs:
        if args.limit is not None and written >= args.limit:
            break
        out_path = args.output / f"{sub.name}.png"
        if out_path.exists() and not args.force:
            skipped += 1
            continue
        paths = _view_paths(sub)
        if paths is None:
            log.warning("%s: missing one or more views, skipping", sub.name)
            missing += 1
            continue
        build_composite(paths).save(out_path)
        written += 1
        if written % 25 == 0:
            log.info("wrote %d composites (last: %s)", written, sub.name)

    log.info("done. wrote=%d skipped=%d missing=%d", written, skipped, missing)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

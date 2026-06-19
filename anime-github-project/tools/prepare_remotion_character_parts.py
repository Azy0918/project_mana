from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
CHAR_DIR = ROOT / "remotion-anime" / "public" / "assets" / "13th-register" / "characters"
PART_DIR = ROOT / "remotion-anime" / "public" / "assets" / "13th-register" / "character_parts"


# Normalized head ellipses on each source canvas: left, top, right, bottom.
HEAD_BOXES: dict[str, tuple[float, float, float, float]] = {
    "タクミ_tsukkomi.png": (0.40, 0.08, 0.58, 0.38),
    "タクミ_surprised.png": (0.40, 0.08, 0.58, 0.38),
    "ミナ_neutral.png": (0.40, 0.07, 0.60, 0.39),
    "ミナ_cold.png": (0.40, 0.07, 0.60, 0.39),
    "未来の会社員_tired.png": (0.39, 0.07, 0.61, 0.40),
    "未来の会社員_anxious.png": (0.39, 0.07, 0.61, 0.40),
    "常連のおじいさん_neutral.png": (0.40, 0.07, 0.60, 0.39),
}


def make_ellipse_mask(size: tuple[int, int], box: tuple[float, float, float, float], blur: int) -> Image.Image:
    width, height = size
    left, top, right, bottom = box
    px_box = (left * width, top * height, right * width, bottom * height)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(px_box, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(blur))


def prepare_parts() -> None:
    PART_DIR.mkdir(parents=True, exist_ok=True)
    for name, box in HEAD_BOXES.items():
        src = CHAR_DIR / name
        if not src.exists():
            continue
        image = Image.open(src).convert("RGBA")
        alpha = image.getchannel("A")
        head_mask = make_ellipse_mask(image.size, box, blur=max(10, image.size[0] // 90))
        head_mask = Image.composite(head_mask, Image.new("L", image.size, 0), alpha)

        head = Image.new("RGBA", image.size, (0, 0, 0, 0))
        head.paste(image, (0, 0), head_mask)

        body = image.copy()
        body_alpha = Image.composite(Image.new("L", image.size, 0), alpha, head_mask)
        body.putalpha(body_alpha)

        stem = src.stem
        head.save(PART_DIR / f"{stem}_head.png")
        body.save(PART_DIR / f"{stem}_body.png")
    print(f"wrote parts to {PART_DIR}")


if __name__ == "__main__":
    prepare_parts()

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    files = sorted(Path("13th-register-kamishibai/assets/scenes").glob("scene_*.jpg"))[:8]
    thumb_w, thumb_h = 188, 334
    label_h = 28
    sheet = Image.new("RGB", (thumb_w * 4, (thumb_h + label_h) * 2), (8, 12, 18))
    draw = ImageDraw.Draw(sheet)

    for index, path in enumerate(files):
        image = Image.open(path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h))
        x = (index % 4) * thumb_w + (thumb_w - image.width) // 2
        y = (index // 4) * (thumb_h + label_h)
        sheet.paste(image, (x, y))
        draw.text(((index % 4) * thumb_w + 6, y + thumb_h + 5), path.stem, fill=(220, 240, 255))

    out = Path("outputs/scene_contact_sheet.jpg")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    print(out)


if __name__ == "__main__":
    main()

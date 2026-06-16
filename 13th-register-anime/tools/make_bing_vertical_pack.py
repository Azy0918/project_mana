from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "tools" / "pv_image_assets_new"
OUT_DIR = ROOT / "bing_video_creator"
WIDTH = 1080
HEIGHT = 1920


@dataclass(frozen=True)
class BingShot:
    slug: str
    title: str
    source_image: str
    prompt: str


SHOTS: tuple[BingShot, ...] = (
    BingShot(
        slug="01_midnight_store",
        title="Midnight Convenience Store",
        source_image="pv_cut_01_exterior_store.png",
        prompt=(
            "Vertical 9:16 anime PV shot, midnight Japanese convenience store exterior, "
            "rainy blue neon, quiet street, slow cinematic push-in, subtle reflections, "
            "mysterious sci-fi mood, no text, no subtitles, 5 seconds."
        ),
    ),
    BingShot(
        slug="02_takumi_reacts",
        title="Takumi Reacts",
        source_image="pv_cut_07_takumi_closeup.png",
        prompt=(
            "Vertical 9:16 anime close-up of Takumi, a young male convenience store clerk, "
            "holding a scanner and reacting with a sharp tsukkomi expression, slight head motion, "
            "natural blink, subtle mouth movement, neon register glow on his face, no text, no subtitles, 5 seconds."
        ),
    ),
    BingShot(
        slug="03_mina_operates",
        title="Mina Operates The Register",
        source_image="pv_cut_08_mina_button.png",
        prompt=(
            "Vertical 9:16 anime shot of Mina, calm expressionless female clerk, operating a futuristic register terminal, "
            "small hand motion, restrained blinking, cool blue light, quiet cyber convenience store atmosphere, "
            "no text, no subtitles, 5 seconds."
        ),
    ),
    BingShot(
        slug="04_future_salaryman",
        title="Future Salaryman Arrives",
        source_image="pv_cut_04_future_salaryman.png",
        prompt=(
            "Vertical 9:16 anime shot of a tired middle-aged salaryman from the future standing in a midnight convenience store, "
            "holding a glowing shopping bag, exhausted expression, slow breathing, slight camera drift, "
            "melancholic sci-fi mood, no text, no subtitles, 5 seconds."
        ),
    ),
    BingShot(
        slug="05_register_glitch",
        title="The 13th Register Glitches",
        source_image="pv_cut_06_register_vanish.png",
        prompt=(
            "Vertical 9:16 anime sci-fi shot of the Thirteenth Register, a futuristic self-checkout machine, "
            "glowing cyan screen, warning light pulses, subtle glitch effect, scanning lines, ominous blue reflections, "
            "no text, no subtitles, 5 seconds."
        ),
    ),
)


def cover_resize(image: Image.Image, width: int, height: int) -> Image.Image:
    src_w, src_h = image.size
    scale = max(width / src_w, height / src_h)
    resized = image.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def contain_resize(image: Image.Image, width: int, height: int) -> Image.Image:
    src_w, src_h = image.size
    scale = min(width / src_w, height / src_h)
    return image.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)


def make_vertical_reference(source_path: Path, out_path: Path, title: str) -> None:
    source = Image.open(source_path).convert("RGB")
    background = cover_resize(source, WIDTH, HEIGHT).filter(ImageFilter.GaussianBlur(26))
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (5, 8, 16, 92))
    canvas = Image.alpha_composite(background.convert("RGBA"), overlay)

    foreground = contain_resize(source, WIDTH - 96, 980)
    x = (WIDTH - foreground.width) // 2
    y = 390
    shadow = Image.new("RGBA", foreground.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (0, 0, foreground.width - 1, foreground.height - 1),
        radius=26,
        fill=(0, 0, 0, 160),
    )
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(24)), (x, y + 20))
    canvas.alpha_composite(foreground.convert("RGBA"), (x, y))

    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, WIDTH, 180), fill=(3, 6, 12, 120))
    draw.text((54, 70), title, fill=(235, 245, 255, 255))
    draw.text((54, HEIGHT - 126), "Bing Video Creator reference frame / 9:16", fill=(190, 210, 226, 230))
    canvas.convert("RGB").save(out_path, quality=94)


def write_prompt_files(shots: tuple[BingShot, ...]) -> None:
    lines = [
        "# Bing Video Creator Vertical Prompt Pack",
        "",
        "Use these prompts one by one in Bing Video Creator. Current public reports describe Bing Video Creator as a free, short, vertical 9:16 text-to-video tool, so the prompts are written as 5-second vertical clips.",
        "",
        "Common instruction: anime PV style, no text, no subtitles, no logos.",
        "",
    ]
    txt_lines: list[str] = []
    for index, shot in enumerate(shots, 1):
        lines.extend(
            [
                f"## {index}. {shot.title}",
                "",
                f"Reference image: `vertical_refs/{shot.slug}.jpg`",
                "",
                "```text",
                shot.prompt,
                "```",
                "",
            ]
        )
        txt_lines.append(f"{index}. {shot.title}\n{shot.prompt}\n")

    (OUT_DIR / "bing_vertical_prompts.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT_DIR / "bing_vertical_prompts.txt").write_text("\n\n".join(txt_lines), encoding="utf-8")


def main() -> int:
    refs_dir = OUT_DIR / "vertical_refs"
    refs_dir.mkdir(parents=True, exist_ok=True)

    for shot in SHOTS:
        source_path = SOURCE_DIR / shot.source_image
        if not source_path.exists():
            raise FileNotFoundError(source_path)
        make_vertical_reference(source_path, refs_dir / f"{shot.slug}.jpg", shot.title)

    write_prompt_files(SHOTS)
    print(textwrap.dedent(
        f"""
        Wrote Bing Video Creator pack:
        - {OUT_DIR / "bing_vertical_prompts.md"}
        - {OUT_DIR / "bing_vertical_prompts.txt"}
        - {refs_dir}
        """
    ).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

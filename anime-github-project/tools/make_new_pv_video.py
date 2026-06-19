from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from puppet_motion_engine import (
    MotionContext,
    PuppetMotionEngine,
    build_audio_level_track,
    create_default_engine,
    create_engine_from_json,
)


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "pv_image_assets_new"
AUDIO_PATH = ROOT / "output_aivis_pv_narration_nise" / "13th_register_pv_narration_nise_60s.wav"
OUTPUT_DIR = ROOT / "output_video"
WORK_DIR = ROOT / "_pv_frames_new"

WIDTH = 1280
HEIGHT = 720
FPS = 30


@dataclass(frozen=True)
class Scene:
    image: str
    seconds: float
    start_zoom: float
    end_zoom: float
    pan_x: float
    pan_y: float
    label: str = ""
    label_at: str = "none"
    sequence: tuple[str, ...] = ()
    sequence_hold: tuple[float, ...] = ()


SCENES: list[Scene] = [
    Scene("pv_key_visual_textless_v1.png", 4.0, 1.00, 1.07, -0.04, 0.00),
    Scene("pv_cut_01_exterior_store.png", 4.2, 1.03, 1.10, 0.05, -0.02, "午前二時三分", "lower"),
    Scene("pv_cut_16_empty_aisle.png", 2.4, 1.02, 1.08, 0.04, 0.00),
    Scene("pv_cut_10_clock_217.png", 3.5, 1.04, 1.13, -0.04, 0.00),
    Scene("pv_cut_02_register_closeup.png", 4.0, 1.02, 1.14, 0.00, 0.04, "夜だけ開くレジ", "lower"),
    Scene("pv_cut_15_hand_scan.png", 2.4, 1.02, 1.10, -0.05, 0.02),
    Scene("pv_cut_07_takumi_closeup.png", 3.6, 1.04, 1.12, -0.05, 0.00),
    Scene("pv_cut_08_mina_button.png", 3.6, 1.04, 1.12, 0.04, 0.01),
    Scene("pv_cut_03_takumi_mina_register.png", 4.2, 1.04, 1.12, -0.05, 0.01),
    Scene("pv_cut_04_future_salaryman.png", 4.1, 1.02, 1.10, 0.04, 0.00, "未来からの返品", "lower"),
    Scene("pv_cut_09_future_onigiri_closeup.png", 3.6, 1.03, 1.16, 0.00, 0.02),
    Scene("pv_cut_17_alert_screen.png", 2.2, 1.02, 1.10, -0.03, 0.00),
    Scene("pv_cut_11_register_warning.png", 3.5, 1.03, 1.11, -0.03, 0.00),
    Scene("pv_cut_12_microwave_glow.png", 4.0, 1.03, 1.12, -0.04, 0.02),
    Scene("pv_cut_05_future_vision.png", 4.8, 1.03, 1.16, 0.00, -0.03),
    Scene("pv_cut_13_refund_coins.png", 4.0, 1.03, 1.11, 0.03, 0.01),
    Scene("pv_cut_18_receipt_props.png", 2.4, 1.02, 1.10, 0.04, 0.00),
    Scene("pv_cut_06_register_vanish.png", 4.0, 1.04, 1.12, -0.04, 0.02, "なかったことにはしない", "lower"),
    Scene("pv_cut_14_final_empty_store.png", 3.0, 1.03, 1.06, 0.02, 0.00),
    Scene("pv_key_visual_textless_v1.png", 4.8, 1.08, 1.00, 0.04, 0.00, "第十三レジ", "center"),
]


def get_audio_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\meiryob.ttc"),
        Path(r"C:\Windows\Fonts\meiryo.ttc"),
        Path(r"C:\Windows\Fonts\YuGothB.ttc"),
        Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


FONT_TITLE = load_font(92)
FONT_LOWER = load_font(42)


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def cover_image(source: Image.Image, zoom: float, pan_x: float, pan_y: float) -> Image.Image:
    src_w, src_h = source.size
    base_scale = max(WIDTH / src_w, HEIGHT / src_h) * zoom
    new_w = int(src_w * base_scale)
    new_h = int(src_h * base_scale)
    resized = source.resize((new_w, new_h), Image.Resampling.LANCZOS)

    max_x = max(new_w - WIDTH, 0)
    max_y = max(new_h - HEIGHT, 0)
    center_x = max_x / 2
    center_y = max_y / 2
    crop_x = int(center_x + pan_x * max_x / 2)
    crop_y = int(center_y + pan_y * max_y / 2)
    crop_x = max(0, min(crop_x, max_x))
    crop_y = max(0, min(crop_y, max_y))
    return resized.crop((crop_x, crop_y, crop_x + WIDTH, crop_y + HEIGHT))


def select_sequence_image(
    loaded: dict[str, Image.Image],
    scene: Scene,
    local_t: float,
) -> Image.Image:
    if not scene.sequence:
        return loaded[scene.image]

    if scene.sequence_hold and len(scene.sequence_hold) == len(scene.sequence):
        total = sum(scene.sequence_hold)
        threshold = (local_t % 1.0) * total
        cursor = 0.0
        for image_name, hold in zip(scene.sequence, scene.sequence_hold, strict=True):
            cursor += hold
            if threshold <= cursor:
                return loaded[image_name]
        return loaded[scene.sequence[-1]]

    index = min(int(local_t * len(scene.sequence)), len(scene.sequence) - 1)
    return loaded[scene.sequence[index]]


def add_vignette(frame: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    steps = 80
    for i in range(steps):
        alpha = int((i / steps) ** 2 * 130)
        draw.rectangle(
            (i * -10, i * -6, WIDTH - i * -10, HEIGHT - i * -6),
            outline=(0, 0, 0, alpha),
            width=8,
        )
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def add_letterbox(frame: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(frame)
    bar_h = 42
    draw.rectangle((0, 0, WIDTH, bar_h), fill=(4, 6, 10))
    draw.rectangle((0, HEIGHT - bar_h, WIDTH, HEIGHT), fill=(4, 6, 10))
    return frame


def add_scanlines(frame: Image.Image, alpha: int = 24) -> Image.Image:
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(0, HEIGHT, 4):
        draw.line((0, y, WIDTH, y), fill=(0, 18, 26, alpha), width=1)
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def draw_text_with_glow(
    frame: Image.Image,
    text: str,
    font: ImageFont.ImageFont,
    xy: tuple[int, int],
    anchor: str,
    fill: tuple[int, int, int, int],
) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for radius, alpha in [(10, 70), (5, 110), (2, 150)]:
        glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        gdraw.text(xy, text, font=font, anchor=anchor, fill=(0, 210, 255, alpha))
        glow = glow.filter(ImageFilter.GaussianBlur(radius))
        layer = Image.alpha_composite(layer, glow)
    draw = ImageDraw.Draw(layer)
    draw.text(xy, text, font=font, anchor=anchor, fill=fill)
    return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")


def add_title_logo(frame: Image.Image, text: str, local_t: float, opacity: int) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    center = (WIDTH // 2, HEIGHT // 2 - 4)

    bbox = draw.textbbox(center, text, font=FONT_TITLE, anchor="mm", stroke_width=2)
    pad_x = 42
    line_y_top = bbox[1] - 28
    line_y_bottom = bbox[3] + 28
    line_x1 = bbox[0] - pad_x
    line_x2 = bbox[2] + pad_x

    line_alpha = int(opacity * 0.78)
    glow_alpha = int(opacity * 0.32)
    for blur_radius, alpha_scale in [(16, 0.42), (7, 0.58)]:
        glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(glow)
        gdraw.text(
            center,
            text,
            font=FONT_TITLE,
            anchor="mm",
            fill=(0, 220, 255, int(opacity * alpha_scale)),
            stroke_width=3,
            stroke_fill=(0, 180, 255, int(opacity * alpha_scale)),
        )
        gdraw.line((line_x1, line_y_top, line_x2, line_y_top), fill=(0, 220, 255, glow_alpha), width=3)
        gdraw.line((line_x1, line_y_bottom, line_x2, line_y_bottom), fill=(0, 220, 255, glow_alpha), width=3)
        layer = Image.alpha_composite(layer, glow.filter(ImageFilter.GaussianBlur(blur_radius)))

    draw = ImageDraw.Draw(layer)
    draw.line((line_x1, line_y_top, line_x2, line_y_top), fill=(190, 245, 255, line_alpha), width=2)
    draw.line((line_x1, line_y_bottom, line_x2, line_y_bottom), fill=(190, 245, 255, line_alpha), width=2)
    draw.line((line_x1 + 18, line_y_top + 8, line_x1 + 82, line_y_top + 8), fill=(0, 220, 255, line_alpha), width=2)
    draw.line((line_x2 - 82, line_y_bottom - 8, line_x2 - 18, line_y_bottom - 8), fill=(0, 220, 255, line_alpha), width=2)

    jitter = int(math.sin(local_t * math.pi * 18) * 3)
    if 0.18 < local_t < 0.24 or 0.72 < local_t < 0.78:
        draw.text(
            (center[0] + jitter, center[1] - 3),
            text,
            font=FONT_TITLE,
            anchor="mm",
            fill=(0, 220, 255, int(opacity * 0.36)),
            stroke_width=2,
            stroke_fill=(0, 70, 100, int(opacity * 0.28)),
        )

    draw.text(
        center,
        text,
        font=FONT_TITLE,
        anchor="mm",
        fill=(248, 253, 255, opacity),
        stroke_width=3,
        stroke_fill=(0, 22, 34, int(opacity * 0.92)),
    )
    return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")


def add_label(
    frame: Image.Image,
    scene: Scene,
    local_t: float,
    textless: bool,
    only_final_title: bool,
) -> Image.Image:
    if textless or not scene.label or scene.label_at == "none":
        return frame
    if only_final_title and scene.label_at != "center":
        return frame
    appear = min(local_t / 0.18, 1.0)
    disappear = min((1.0 - local_t) / 0.18, 1.0)
    opacity = int(255 * max(0.0, min(appear, disappear)))
    if opacity <= 0:
        return frame

    if scene.label_at == "center":
        dim = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, int(95 * opacity / 255)))
        frame = Image.alpha_composite(frame.convert("RGBA"), dim).convert("RGB")
        return add_title_logo(frame, scene.label, local_t, opacity)

    return draw_text_with_glow(
        frame,
        scene.label,
        FONT_LOWER,
        (WIDTH // 2, HEIGHT - 94),
        "mm",
        (235, 245, 255, opacity),
    )


def add_transition_flash(frame: Image.Image, scene_frame: int, scene_frames: int) -> Image.Image:
    edge = min(scene_frame, scene_frames - scene_frame - 1)
    if edge >= 8:
        return frame
    strength = (8 - edge) / 8
    overlay = Image.new("RGB", (WIDTH, HEIGHT), (90, 220, 255))
    return Image.blend(frame, overlay, 0.16 * strength)


def add_pulse(frame: Image.Image, global_frame: int) -> Image.Image:
    pulse = 1.0 + math.sin(global_frame * 0.09) * 0.025
    color = ImageEnhance.Color(frame).enhance(1.03)
    return ImageEnhance.Contrast(color).enhance(pulse)


def add_rain(frame: Image.Image, global_frame: int, strength: int = 42) -> Image.Image:
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    offset = (global_frame * 19) % 180
    for i in range(strength):
        x = (i * 83 + global_frame * 9) % (WIDTH + 160) - 80
        y = (i * 47 + offset) % (HEIGHT + 180) - 90
        length = 28 + (i % 4) * 8
        alpha = 26 + (i % 3) * 12
        draw.line((x, y, x - 12, y + length), fill=(160, 220, 255, alpha), width=1)
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def add_cyan_flicker(frame: Image.Image, global_frame: int, strength: float = 0.08) -> Image.Image:
    flicker = (math.sin(global_frame * 0.47) + math.sin(global_frame * 0.11)) * 0.5
    alpha = int(max(0, flicker) * 255 * strength)
    if alpha <= 0:
        return frame
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 210, 255, alpha))
    return Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")


def add_hand_scan_animation(frame: Image.Image, global_frame: int, local_t: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    sweep = 0.18 + (local_t * 0.92 % 0.74)
    x = int(WIDTH * sweep)
    y1 = int(HEIGHT * 0.27)
    y2 = int(HEIGHT * 0.76)
    for width, alpha in [(28, 28), (14, 55), (4, 150)]:
        draw.line((x - 170, y1, x + 40, y2), fill=(80, 230, 255, alpha), width=width)
    for i in range(5):
        offset = i * 48 + int(math.sin(global_frame * 0.18 + i) * 12)
        draw.line(
            (x - 210 + offset, y1 + 70, x - 150 + offset, y2 - 60),
            fill=(130, 245, 255, 42),
            width=1,
        )
    glow = layer.filter(ImageFilter.GaussianBlur(7))
    return Image.alpha_composite(Image.alpha_composite(frame.convert("RGBA"), glow), layer).convert("RGB")


def add_alert_screen_animation(frame: Image.Image, global_frame: int, local_t: float) -> Image.Image:
    pulse = 0.5 + 0.5 * math.sin(global_frame * 0.42)
    alpha = int(34 + pulse * 62)
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cx, cy = WIDTH // 2, HEIGHT // 2
    size = int(196 + pulse * 34)
    points = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    draw.polygon(points, outline=(255, 42, 32, alpha))
    draw.polygon(
        [(cx, cy - size - 22), (cx + size + 22, cy), (cx, cy + size + 22), (cx - size - 22, cy)],
        outline=(255, 70, 45, int(alpha * 0.42)),
    )
    for i in range(9):
        y = int(HEIGHT * 0.22 + i * 42 + math.sin(global_frame * 0.2 + i) * 5)
        draw.line((int(WIDTH * 0.22), y, int(WIDTH * 0.80), y), fill=(255, 50, 40, 20 + i * 2), width=1)
    if int(global_frame / 4) % 6 == 0:
        band_y = int(HEIGHT * (0.18 + local_t * 0.62))
        draw.rectangle((0, band_y, WIDTH, band_y + 10), fill=(255, 80, 70, 38))
    return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")


def add_receipt_print_animation(frame: Image.Image, global_frame: int, local_t: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    progress = min(1.0, local_t * 1.2)
    reveal_y = int(HEIGHT * (0.25 + progress * 0.47))
    draw.rectangle((int(WIDTH * 0.30), reveal_y - 8, int(WIDTH * 0.56), reveal_y + 10), fill=(150, 245, 255, 62))
    for i in range(10):
        y = reveal_y - i * 24 + int(math.sin(global_frame * 0.1 + i) * 2)
        if int(HEIGHT * 0.24) < y < int(HEIGHT * 0.73):
            x1 = int(WIDTH * (0.34 + (i % 3) * 0.018))
            x2 = int(WIDTH * (0.50 - (i % 4) * 0.012))
            draw.line((x1, y, x2, y), fill=(35, 95, 110, 76), width=2)
    glow = layer.filter(ImageFilter.GaussianBlur(3))
    return Image.alpha_composite(Image.alpha_composite(frame.convert("RGBA"), glow), layer).convert("RGB")


def add_empty_aisle_animation(frame: Image.Image, global_frame: int) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    flicker = 0.5 + 0.5 * math.sin(global_frame * 0.23) * math.sin(global_frame * 0.047)
    draw.rectangle((0, 42, WIDTH, 145), fill=(190, 240, 255, int(18 + flicker * 22)))
    if global_frame % 97 < 6:
        draw.rectangle((0, 42, WIDTH, HEIGHT - 42), fill=(0, 190, 255, 24))
    return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")


def add_advanced_animation(frame: Image.Image, scene: Scene, global_frame: int, local_t: float) -> Image.Image:
    if scene.image == "pv_cut_15_hand_scan.png":
        return add_hand_scan_animation(frame, global_frame, local_t)
    if scene.image == "pv_cut_17_alert_screen.png":
        return add_alert_screen_animation(frame, global_frame, local_t)
    if scene.image == "pv_cut_18_receipt_props.png":
        return add_receipt_print_animation(frame, global_frame, local_t)
    if scene.image == "pv_cut_16_empty_aisle.png":
        return add_empty_aisle_animation(frame, global_frame)
    return frame


def soft_rect_mask(size: tuple[int, int], radius: int, feather: int, opacity: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    inset = max(0, feather)
    draw.rounded_rectangle(
        (inset, inset, size[0] - inset - 1, size[1] - inset - 1),
        radius=radius,
        fill=opacity,
    )
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    return mask


def overlay_puppet_patch(
    frame: Image.Image,
    box: tuple[int, int, int, int],
    dx: float,
    dy: float,
    angle: float = 0.0,
    scale: float = 1.0,
    opacity: int = 150,
    feather: int = 18,
    radius: int = 32,
) -> Image.Image:
    x1, y1, x2, y2 = box
    x1 = max(0, min(x1, WIDTH - 1))
    y1 = max(0, min(y1, HEIGHT - 1))
    x2 = max(x1 + 1, min(x2, WIDTH))
    y2 = max(y1 + 1, min(y2, HEIGHT))

    patch = frame.crop((x1, y1, x2, y2)).convert("RGBA")
    mask = soft_rect_mask(patch.size, radius, feather, opacity)
    patch.putalpha(mask)

    if abs(scale - 1.0) > 0.001:
        new_size = (
            max(1, int(round(patch.width * scale))),
            max(1, int(round(patch.height * scale))),
        )
        patch = patch.resize(new_size, Image.Resampling.BICUBIC)

    if abs(angle) > 0.01:
        patch = patch.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)

    center_x = (x1 + x2) / 2 + dx
    center_y = (y1 + y2) / 2 + dy
    paste_x = int(round(center_x - patch.width / 2))
    paste_y = int(round(center_y - patch.height / 2))
    base = frame.convert("RGBA")
    base.alpha_composite(patch, (paste_x, paste_y))
    return base.convert("RGB")


def add_puppet_animation(
    frame: Image.Image,
    scene: Scene,
    global_frame: int,
    local_t: float,
    puppet_engine: PuppetMotionEngine,
) -> Image.Image:
    return puppet_engine.apply(frame, scene.image, MotionContext(local_t=local_t, global_frame=global_frame))


def add_takumi_stable_blink(frame: Image.Image, scene: Scene, local_t: float) -> Image.Image:
    if scene.image != "pv_cut_07_takumi_closeup.png":
        return frame

    blink_windows = ((0.50, 0.045), (0.78, 0.035))
    strength = 0.0
    for center, half_width in blink_windows:
        distance = abs(local_t - center)
        if distance <= half_width:
            strength = max(strength, 1.0 - distance / half_width)

    if strength <= 0.0:
        return frame

    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cover_alpha = int(46 * strength)
    line_alpha = int(150 * strength)
    shadow_alpha = int(42 * strength)

    # Draw only eyelids over the already transformed original frame.
    draw.rounded_rectangle((421, 197, 495, 222), radius=11, fill=(190, 128, 100, cover_alpha))
    draw.rounded_rectangle((532, 173, 606, 199), radius=11, fill=(190, 128, 100, cover_alpha))
    draw.line([(427, 210), (459, 216), (490, 209)], fill=(28, 18, 18, line_alpha), width=3, joint="curve")
    draw.line([(538, 187), (569, 193), (600, 185)], fill=(28, 18, 18, line_alpha), width=3, joint="curve")
    draw.line([(430, 213), (459, 218), (487, 213)], fill=(255, 220, 190, shadow_alpha), width=1, joint="curve")
    draw.line([(541, 190), (568, 195), (597, 190)], fill=(255, 220, 190, shadow_alpha), width=1, joint="curve")
    return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")


def draw_glow_line(
    layer: Image.Image,
    points: list[tuple[int, int]] | tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    width: int,
) -> None:
    draw = ImageDraw.Draw(layer)
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    for glow_width, alpha_scale in [(width + 8, 0.28), (width + 4, 0.46)]:
        glow_fill = (fill[0], fill[1], fill[2], int(fill[3] * alpha_scale))
        gdraw.line(points, fill=glow_fill, width=glow_width, joint="curve")
    layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(5)))
    draw.line(points, fill=fill, width=width, joint="curve")


def register_screen_rect(scene: Scene) -> tuple[int, int, int, int] | None:
    if scene.image == "pv_cut_02_register_closeup.png":
        return (500, 108, 792, 405)
    if scene.image == "pv_key_visual_textless_v1.png":
        return (548, 182, 684, 338)
    return None


def add_register_face_expression(
    frame: Image.Image,
    scene: Scene,
    global_frame: int,
    local_t: float,
) -> Image.Image:
    rect = register_screen_rect(scene)
    if rect is None:
        return frame

    x1, y1, x2, y2 = rect
    w = x2 - x1
    h = y2 - y1
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    breath = 0.72 + 0.28 * math.sin(global_frame * 0.15)
    alpha = int(178 + 52 * breath)
    color = (75, 235, 255, alpha)
    talk = math.sin(global_frame * 0.38) > 0.16

    # A very light screen wash makes the changed expression read as intentional.
    draw.rounded_rectangle(
        (x1 + int(w * 0.08), y1 + int(h * 0.12), x2 - int(w * 0.08), y2 - int(h * 0.12)),
        radius=max(6, int(w * 0.03)),
        fill=(0, 18, 26, 10),
    )

    line_w = max(2, int(w * 0.015))

    mouth_y = y1 + int(h * 0.66)
    mouth_w = max(18, int(w * 0.105))
    if scene.image == "pv_cut_02_register_closeup.png" and talk:
        mouth_h = max(5, int(h * 0.035))
        mouth_points = [
            (x1 + w // 2 - mouth_w, mouth_y),
            (x1 + w // 2 - mouth_w // 3, mouth_y + mouth_h),
            (x1 + w // 2 + mouth_w // 3, mouth_y + mouth_h),
            (x1 + w // 2 + mouth_w, mouth_y),
        ]
        draw_glow_line(layer, mouth_points, color, line_w)
    else:
        draw_glow_line(layer, (x1 + w // 2 - mouth_w, mouth_y, x1 + w // 2 + mouth_w, mouth_y), color, line_w)

    if 0.70 < local_t < 0.92:
        scan_y = y1 + int(h * ((local_t - 0.70) / 0.22))
        draw.line((x1 + int(w * 0.14), scan_y, x2 - int(w * 0.14), scan_y), fill=(130, 250, 255, 74), width=1)

    return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")


def add_alarm_shake(frame: Image.Image, global_frame: int, scene: Scene) -> Image.Image:
    if "warning" not in scene.image and "vanish" not in scene.image:
        return frame
    dx = int(math.sin(global_frame * 1.7) * 3)
    dy = int(math.sin(global_frame * 2.3) * 2)
    shifted = Image.new("RGB", (WIDTH, HEIGHT), (4, 6, 10))
    shifted.paste(frame, (dx, dy))
    return shifted.crop((0, 0, WIDTH, HEIGHT))


def add_scene_motion_effects(
    frame: Image.Image,
    scene: Scene,
    global_frame: int,
    local_t: float,
    register_face: bool,
    advanced_animation: bool,
    takumi_stable_blink: bool,
    puppet_animation: bool,
    vtuber_motion: bool,
    audio_level: float,
    puppet_engine: PuppetMotionEngine,
) -> Image.Image:
    if any(key in scene.image for key in ["key_visual", "exterior", "future_salaryman"]):
        frame = add_rain(frame, global_frame)
    if any(key in scene.image for key in ["register", "warning", "microwave", "vanish"]):
        frame = add_cyan_flicker(frame, global_frame)
    if register_face:
        frame = add_register_face_expression(frame, scene, global_frame, local_t)
    if advanced_animation:
        frame = add_advanced_animation(frame, scene, global_frame, local_t)
    if puppet_animation:
        frame = add_puppet_animation(frame, scene, global_frame, local_t, puppet_engine)
    if takumi_stable_blink:
        frame = add_takumi_stable_blink(frame, scene, local_t)
    if vtuber_motion:
        frame = puppet_engine.apply_vtuber_micro_motion(
            frame,
            scene.image,
            MotionContext(local_t=local_t, global_frame=global_frame, audio_level=audio_level),
        )
    frame = add_alarm_shake(frame, global_frame, scene)
    return frame


def render_frames(
    textless: bool,
    only_final_title: bool,
    motion_effects: bool,
    register_face: bool,
    advanced_animation: bool,
    takumi_stable_blink: bool,
    puppet_animation: bool,
    vtuber_motion: bool,
    puppet_engine: PuppetMotionEngine,
) -> int:
    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    audio_duration = get_audio_duration(AUDIO_PATH)
    target_frames = int(round(audio_duration * FPS))
    audio_levels = build_audio_level_track(AUDIO_PATH, FPS, target_frames)

    scene_total = sum(scene.seconds for scene in SCENES)
    scale = audio_duration / scene_total
    adjusted = [max(1, int(round(scene.seconds * scale * FPS))) for scene in SCENES]
    delta = target_frames - sum(adjusted)
    adjusted[-1] += delta

    image_names = {scene.image for scene in SCENES}
    for scene in SCENES:
        image_names.update(scene.sequence)
    loaded = {image_name: Image.open(ASSET_DIR / image_name).convert("RGB") for image_name in image_names}

    frame_index = 0
    for scene, scene_frames in zip(SCENES, adjusted, strict=True):
        for scene_frame in range(scene_frames):
            local_t = scene_frame / max(scene_frames - 1, 1)
            e = ease(local_t)
            zoom = scene.start_zoom + (scene.end_zoom - scene.start_zoom) * e
            pan_x = scene.pan_x * (e * 2 - 1)
            pan_y = scene.pan_y * (e * 2 - 1)

            source = select_sequence_image(loaded, scene, local_t)
            frame = cover_image(source, zoom, pan_x, pan_y)
            frame = add_pulse(frame, frame_index)
            if motion_effects:
                frame = add_scene_motion_effects(
                    frame,
                    scene,
                    frame_index,
                    local_t,
                    register_face,
                    advanced_animation,
                    takumi_stable_blink,
                    puppet_animation,
                    vtuber_motion,
                    audio_levels.at_frame(frame_index),
                    puppet_engine,
                )
            frame = add_vignette(frame)
            frame = add_scanlines(frame)
            frame = add_transition_flash(frame, scene_frame, scene_frames)
            frame = add_letterbox(frame)
            frame = add_label(frame, scene, local_t, textless, only_final_title)
            frame.save(WORK_DIR / f"frame_{frame_index:05d}.jpg", quality=91, optimize=False)
            frame_index += 1

    return frame_index


def encode_video(output_name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / output_name
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-framerate",
            str(FPS),
            "-i",
            str(WORK_DIR / "frame_%05d.jpg"),
            "-i",
            str(AUDIO_PATH),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(out_path),
        ],
        check=True,
    )
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="第十三レジPVを新規画像素材から生成します。")
    parser.add_argument(
        "--output-name",
        default="13th_register_pv_nise_new_images.mp4",
        help="出力MP4ファイル名",
    )
    parser.add_argument(
        "--textless",
        action="store_true",
        help="PV見出し文字を消し、映像重視版として出力します。",
    )
    parser.add_argument(
        "--only-final-title",
        action="store_true",
        help="途中のPV見出し文字を消し、最後の中央タイトルだけ表示します。",
    )
    parser.add_argument(
        "--motion-effects",
        action="store_true",
        help="雨、レジ発光、警告揺れなどの疑似アニメ効果を追加します。",
    )
    parser.add_argument(
        "--register-face",
        action="store_true",
        help="第十三レジの画面に口変化・スキャン線の表情差分を重ねます。",
    )
    parser.add_argument(
        "--advanced-animation",
        action="store_true",
        help="手元スキャン、警告画面、レシート、無人店内に追加のカット内アニメ効果を入れます。",
    )
    parser.add_argument(
        "--takumi-stable-blink",
        action="store_true",
        help="タクミの元絵を固定したまま、まぶただけを重ねる安定まばたきを追加します。",
    )
    parser.add_argument(
        "--puppet-animation",
        action="store_true",
        help="人物カットにLive2D/After Effects風の微細なパーツ分解アニメを追加します。",
    )
    parser.add_argument(
        "--vtuber-motion",
        action="store_true",
        help="人物の目パチ、口パク風の口形、顔ハイライトを追加してVtuber風の自然な微動を重ねます。",
    )
    parser.add_argument(
        "--rig-json",
        default="",
        help="Puppet/VtuberリグJSONを指定します。未指定ならデフォルトリグを使います。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not AUDIO_PATH.exists():
        raise FileNotFoundError(f"audio not found: {AUDIO_PATH}")
    required_images = {scene.image for scene in SCENES}
    for scene in SCENES:
        required_images.update(scene.sequence)
    missing = [image_name for image_name in sorted(required_images) if not (ASSET_DIR / image_name).exists()]
    if missing:
        raise FileNotFoundError(f"missing image assets: {missing}")

    puppet_engine = (
        create_engine_from_json(WIDTH, HEIGHT, Path(args.rig_json))
        if args.rig_json
        else create_default_engine(WIDTH, HEIGHT)
    )

    frame_count = render_frames(
        textless=args.textless,
        only_final_title=args.only_final_title,
        motion_effects=args.motion_effects,
        register_face=args.register_face,
        advanced_animation=args.advanced_animation,
        takumi_stable_blink=args.takumi_stable_blink,
        puppet_animation=args.puppet_animation,
        vtuber_motion=args.vtuber_motion,
        puppet_engine=puppet_engine,
    )
    video_path = encode_video(args.output_name)
    print(f"frames={frame_count}")
    print(f"video={video_path.resolve()}")
    print(f"size={video_path.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

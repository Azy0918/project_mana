from __future__ import annotations

from array import array
from dataclasses import dataclass
import json
import math
from pathlib import Path
import wave

from PIL import Image, ImageDraw, ImageFilter


@dataclass(frozen=True)
class MotionValue:
    base: float = 0.0
    sway: float = 0.0
    secondary: float = 0.0
    positive_secondary: float = 0.0

    def at(self, local_t: float) -> float:
        sway = math.sin(local_t * math.tau)
        secondary = math.sin(local_t * math.tau * 1.7 + 0.8)
        return self.base + self.sway * sway + self.secondary * secondary + self.positive_secondary * max(0.0, secondary)


@dataclass(frozen=True)
class PuppetPatch:
    name: str
    box: tuple[int, int, int, int]
    dx: MotionValue
    dy: MotionValue
    angle: MotionValue = MotionValue()
    scale: MotionValue = MotionValue(base=1.0)
    opacity: int = 120
    feather: int = 28
    radius: int = 64
    motion_scale: float = 1.0


@dataclass(frozen=True)
class SceneRig:
    image_name: str
    patches: tuple[PuppetPatch, ...]


@dataclass(frozen=True)
class FaceRig:
    image_name: str
    left_eye: tuple[int, int, int, int]
    right_eye: tuple[int, int, int, int]
    mouth: tuple[int, int, int, int]
    color: tuple[int, int, int]
    blink_times: tuple[float, ...] = (0.24, 0.68)
    talk_start: float = 0.12
    talk_end: float = 0.88
    mouth_strength: float = 1.0
    highlight_box: tuple[int, int, int, int] | None = None
    gaze_strength: float = 1.0
    breath_strength: float = 1.0
    eye_light_strength: float = 1.0


@dataclass(frozen=True)
class MotionContext:
    local_t: float
    global_frame: int = 0
    audio_level: float = 0.0


@dataclass(frozen=True)
class AudioLevelTrack:
    fps: int
    levels: tuple[float, ...]

    def at_frame(self, frame_index: int) -> float:
        if not self.levels:
            return 0.0
        index = max(0, min(frame_index, len(self.levels) - 1))
        return self.levels[index]


def build_audio_level_track(path: Path, fps: int, target_frames: int) -> AudioLevelTrack:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if sample_width != 2:
        return AudioLevelTrack(fps=fps, levels=tuple(0.0 for _ in range(target_frames)))

    samples = array("h")
    samples.frombytes(raw)
    if channels > 1:
        mono = array("h")
        for index in range(0, len(samples), channels):
            mono.append(int(sum(samples[index : index + channels]) / channels))
        samples = mono

    samples_per_frame = max(1, int(rate / fps))
    rms_values: list[float] = []
    for frame_index in range(target_frames):
        start = frame_index * samples_per_frame
        end = min(start + samples_per_frame, len(samples))
        if start >= len(samples) or end <= start:
            rms_values.append(0.0)
            continue
        window = samples[start:end]
        square_sum = sum(float(sample) * float(sample) for sample in window)
        rms_values.append(math.sqrt(square_sum / len(window)))

    nonzero = sorted(value for value in rms_values if value > 0)
    if not nonzero:
        return AudioLevelTrack(fps=fps, levels=tuple(0.0 for _ in range(target_frames)))

    reference = max(nonzero[min(len(nonzero) - 1, int(len(nonzero) * 0.90))], 1.0)
    raw_levels = [min(1.0, (value / reference) ** 0.75) for value in rms_values]

    smoothed: list[float] = []
    prev = 0.0
    for level in raw_levels:
        prev = prev * 0.58 + level * 0.42
        smoothed.append(prev)
    return AudioLevelTrack(fps=fps, levels=tuple(smoothed))


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


class PuppetMotionEngine:
    def __init__(
        self,
        width: int,
        height: int,
        rigs: tuple[SceneRig, ...],
        face_rigs: dict[str, FaceRig] | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.rigs = {rig.image_name: rig for rig in rigs}
        self.face_rigs = face_rigs if face_rigs is not None else FACE_RIGS

    def apply(self, frame: Image.Image, image_name: str, context: MotionContext | float) -> Image.Image:
        if isinstance(context, (int, float)):
            context = MotionContext(local_t=float(context))
        rig = self.rigs.get(image_name)
        if rig is None:
            return frame

        output = frame
        for patch in rig.patches:
            output = self._overlay_patch(output, patch, context.local_t)
        return output

    def apply_vtuber_micro_motion(
        self,
        frame: Image.Image,
        image_name: str,
        context: MotionContext | float,
        global_frame: int | None = None,
        audio_level: float | None = None,
    ) -> Image.Image:
        if isinstance(context, (int, float)):
            context = MotionContext(
                local_t=float(context),
                global_frame=global_frame or 0,
                audio_level=audio_level or 0.0,
            )
        rig = self.face_rigs.get(image_name)
        if rig is None:
            return frame

        layer = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)

        blink = self._blink_strength(context.local_t, rig)
        self._draw_eye_life(draw, rig.left_eye, blink, rig, context.local_t, context.global_frame, -1)
        self._draw_eye_life(draw, rig.right_eye, blink, rig, context.local_t, context.global_frame, 1)
        if blink > 0:
            self._draw_blink(draw, rig.left_eye, blink, rig.color)
            self._draw_blink(draw, rig.right_eye, blink, rig.color)

        talking = rig.talk_start <= context.local_t <= rig.talk_end
        mouth_open = 0.0
        if talking:
            phrase = math.sin(context.global_frame * 0.58) * 0.55 + math.sin(context.global_frame * 0.23 + 0.7) * 0.35
            audio_mouth = max(0.0, min(context.audio_level, 1.0))
            mouth_open = max(audio_mouth, max(0.0, phrase) * 0.42) * rig.mouth_strength
        self._draw_mouth(draw, rig.mouth, mouth_open, rig.color)

        if rig.highlight_box is not None:
            self._draw_breath_light(layer, rig, context.local_t, context.global_frame)
            self._draw_face_highlight(layer, rig, context.local_t, context.global_frame)

        return Image.alpha_composite(frame.convert("RGBA"), layer).convert("RGB")

    def render_frame(self, frame: Image.Image, image_name: str, context: MotionContext) -> Image.Image:
        output = self.apply(frame, image_name, context)
        return self.apply_vtuber_micro_motion(output, image_name, context)

    def describe(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        image_names = sorted(set(self.rigs) | set(self.face_rigs))
        for image_name in image_names:
            scene_rig = self.rigs.get(image_name)
            face_rig = self.face_rigs.get(image_name)
            rows.append(
                {
                    "image_name": image_name,
                    "patches": [patch.name for patch in scene_rig.patches] if scene_rig else [],
                    "motion_scales": [patch.motion_scale for patch in scene_rig.patches] if scene_rig else [],
                    "face": face_rig is not None,
                    "blink_times": face_rig.blink_times if face_rig else (),
                    "mouth": face_rig.mouth if face_rig else None,
                }
            )
        return rows

    def _overlay_patch(self, frame: Image.Image, patch_def: PuppetPatch, local_t: float) -> Image.Image:
        x1, y1, x2, y2 = patch_def.box
        x1 = max(0, min(x1, self.width - 1))
        y1 = max(0, min(y1, self.height - 1))
        x2 = max(x1 + 1, min(x2, self.width))
        y2 = max(y1 + 1, min(y2, self.height))

        patch = frame.crop((x1, y1, x2, y2)).convert("RGBA")
        patch.putalpha(soft_rect_mask(patch.size, patch_def.radius, patch_def.feather, patch_def.opacity))

        motion_scale = max(0.0, patch_def.motion_scale)

        scale = 1.0 + (patch_def.scale.at(local_t) - 1.0) * motion_scale
        if abs(scale - 1.0) > 0.001:
            patch = patch.resize(
                (max(1, int(round(patch.width * scale))), max(1, int(round(patch.height * scale)))),
                Image.Resampling.BICUBIC,
            )

        angle = patch_def.angle.at(local_t) * motion_scale
        if abs(angle) > 0.01:
            patch = patch.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)

        center_x = (x1 + x2) / 2 + patch_def.dx.at(local_t) * motion_scale
        center_y = (y1 + y2) / 2 + patch_def.dy.at(local_t) * motion_scale
        paste_x = int(round(center_x - patch.width / 2))
        paste_y = int(round(center_y - patch.height / 2))

        base = frame.convert("RGBA")
        base.alpha_composite(patch, (paste_x, paste_y))
        return base.convert("RGB")

    @staticmethod
    def _blink_strength(local_t: float, rig: FaceRig) -> float:
        strength = 0.0
        for center in rig.blink_times:
            half_width = 0.035
            distance = abs(local_t - center)
            if distance <= half_width:
                strength = max(strength, 1.0 - distance / half_width)
        return strength

    @staticmethod
    def _draw_blink(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], strength: float, color: tuple[int, int, int]) -> None:
        x1, y1, x2, y2 = box
        alpha = int(86 * strength)
        line_alpha = int(170 * strength)
        fill = (max(0, color[0] - 34), max(0, color[1] - 38), max(0, color[2] - 42), alpha)
        draw.rounded_rectangle((x1, y1, x2, y2), radius=max(4, (y2 - y1) // 2), fill=fill)
        mid_y = int((y1 + y2) / 2)
        draw.line((x1 + 5, mid_y, (x1 + x2) // 2, mid_y + 3, x2 - 5, mid_y), fill=(24, 18, 18, line_alpha), width=3, joint="curve")

    @staticmethod
    def _draw_eye_life(
        draw: ImageDraw.ImageDraw,
        box: tuple[int, int, int, int],
        blink: float,
        rig: FaceRig,
        local_t: float,
        global_frame: int,
        side: int,
    ) -> None:
        if rig.eye_light_strength <= 0:
            return
        x1, y1, x2, y2 = box
        width = x2 - x1
        height = y2 - y1
        visible = max(0.0, 1.0 - blink)
        gaze_x = math.sin(local_t * math.tau * 0.7 + global_frame * 0.012) * 2.0 * rig.gaze_strength
        gaze_y = math.sin(local_t * math.tau * 0.9 + side * 0.6) * 1.0 * rig.gaze_strength
        shine_alpha = int(92 * visible * rig.eye_light_strength)
        shade_alpha = int(34 * visible * rig.eye_light_strength)
        if shine_alpha <= 0:
            return
        cx = int((x1 + x2) / 2 + gaze_x)
        cy = int((y1 + y2) / 2 + gaze_y)
        draw.ellipse(
            (
                cx - max(3, width // 14),
                cy - max(2, height // 7),
                cx + max(3, width // 14),
                cy + max(2, height // 7),
            ),
            fill=(32, 60, 70, shade_alpha),
        )
        draw.ellipse(
            (
                x1 + width * 0.18 + gaze_x,
                y1 + height * 0.12 + gaze_y,
                x1 + width * 0.34 + gaze_x,
                y1 + height * 0.34 + gaze_y,
            ),
            fill=(245, 252, 255, shine_alpha),
        )
        draw.ellipse(
            (
                x1 + width * 0.55 + gaze_x,
                y1 + height * 0.52 + gaze_y,
                x1 + width * 0.65 + gaze_x,
                y1 + height * 0.68 + gaze_y,
            ),
            fill=(180, 236, 255, int(shine_alpha * 0.55)),
        )

    @staticmethod
    def _draw_mouth(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], open_amount: float, color: tuple[int, int, int]) -> None:
        x1, y1, x2, y2 = box
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        width = x2 - x1
        raw_height = y2 - y1
        amount = max(0.0, min(open_amount, 1.35))
        line_color = (28, 14, 18, 128)
        inner = (28, 12, 16, int(112 + 72 * min(amount, 1.0)))
        lip = (max(40, color[0] - 54), max(30, color[1] - 60), max(30, color[2] - 64), 130)

        if amount < 0.16:
            smile = int(raw_height * 0.12)
            draw.arc((x1 + 3, cy - smile, x2 - 3, cy + smile + 4), start=8, end=172, fill=line_color, width=2)
            return

        if amount < 0.55:
            mouth_w = int(width * (0.64 + amount * 0.22))
            mouth_h = max(3, int(raw_height * (0.22 + amount * 0.34)))
            draw.rounded_rectangle(
                (cx - mouth_w // 2, cy - mouth_h // 2, cx + mouth_w // 2, cy + mouth_h // 2),
                radius=max(2, mouth_h // 2),
                fill=inner,
                outline=lip,
                width=2,
            )
            return

        mouth_w = int(width * min(1.0, 0.72 + amount * 0.12))
        mouth_h = max(4, int(raw_height * min(1.25, 0.46 + amount * 0.52)))
        draw.ellipse(
            (cx - mouth_w // 2, cy - mouth_h // 2, cx + mouth_w // 2, cy + mouth_h // 2),
            fill=inner,
            outline=lip,
            width=2,
        )
        draw.arc(
            (cx - mouth_w // 3, cy - mouth_h // 2, cx + mouth_w // 3, cy + mouth_h // 3),
            start=18,
            end=162,
            fill=(238, 150, 154, int(58 * min(amount, 1.0))),
            width=2,
        )

    def _draw_breath_light(self, layer: Image.Image, rig: FaceRig, local_t: float, global_frame: int) -> None:
        if rig.highlight_box is None or rig.breath_strength <= 0:
            return
        x1, y1, x2, y2 = rig.highlight_box
        breath = (math.sin(local_t * math.tau * 1.15 + global_frame * 0.01) + 1.0) / 2.0
        alpha = int((8 + breath * 14) * rig.breath_strength)
        glow = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        r, g, b = rig.color
        draw.rounded_rectangle(
            (x1 - 18, y1 + 28, x2 + 18, y2 + 36),
            radius=42,
            fill=(min(255, r + 45), min(255, g + 42), min(255, b + 36), alpha),
        )
        layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(18)))

    def _draw_face_highlight(self, layer: Image.Image, rig: FaceRig, local_t: float, global_frame: int) -> None:
        assert rig.highlight_box is not None
        x1, y1, x2, y2 = rig.highlight_box
        sweep = int(math.sin(local_t * math.tau + global_frame * 0.015) * 12)
        glow = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        r, g, b = rig.color
        draw.ellipse(
            (x1 + sweep, y1, x2 + sweep, y2),
            fill=(min(255, r + 35), min(255, g + 34), min(255, b + 28), 22),
        )
        layer.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)))


DEFAULT_RIGS: tuple[SceneRig, ...] = (
    SceneRig(
        "pv_cut_07_takumi_closeup.png",
        (
            PuppetPatch("takumi_face", (315, 58, 690, 382), MotionValue(sway=1.6), MotionValue(secondary=0.9), MotionValue(sway=0.28), MotionValue(base=1.003, secondary=0.002), 118, 28, 70, 0.35),
            PuppetPatch("takumi_hand", (70, 458, 300, 690), MotionValue(secondary=-1.2), MotionValue(sway=2.0), MotionValue(sway=-0.55), MotionValue(base=1.002), 122, 24, 42, 0.55),
        ),
    ),
    SceneRig(
        "pv_cut_08_mina_button.png",
        (
            PuppetPatch("mina_upper", (600, 54, 950, 430), MotionValue(sway=0.8), MotionValue(secondary=0.8), MotionValue(sway=-0.18), MotionValue(base=1.002), 110, 30, 76, 0.25),
            PuppetPatch("mina_hand", (500, 420, 820, 660), MotionValue(secondary=1.2), MotionValue(sway=0.8), MotionValue(secondary=0.24), MotionValue(base=1.002), 92, 24, 46, 0.45),
        ),
    ),
    SceneRig(
        "pv_cut_03_takumi_mina_register.png",
        (
            PuppetPatch("takumi_pair", (180, 86, 520, 650), MotionValue(sway=1.0), MotionValue(secondary=0.9), MotionValue(sway=0.18), MotionValue(base=1.002), 92, 34, 74, 0.25),
            PuppetPatch("mina_pair", (690, 70, 1080, 660), MotionValue(secondary=-0.8), MotionValue(sway=0.7), MotionValue(secondary=-0.15), MotionValue(base=1.0015), 88, 34, 74, 0.25),
        ),
    ),
    SceneRig(
        "pv_cut_04_future_salaryman.png",
        (
            PuppetPatch("salaryman_body", (420, 54, 850, 650), MotionValue(secondary=1.0), MotionValue(sway=1.5), MotionValue(sway=-0.22), MotionValue(base=1.002, positive_secondary=0.002), 118, 34, 82, 0.22),
            PuppetPatch("salaryman_lower", (330, 300, 930, 695), MotionValue(sway=0.6), MotionValue(secondary=1.2), MotionValue(secondary=0.12), MotionValue(base=1.001), 78, 40, 72, 0.12),
        ),
    ),
)


FACE_RIGS: dict[str, FaceRig] = {
    "pv_cut_07_takumi_closeup.png": FaceRig(
        image_name="pv_cut_07_takumi_closeup.png",
        left_eye=(421, 197, 495, 222),
        right_eye=(532, 173, 606, 199),
        mouth=(478, 276, 552, 304),
        color=(190, 128, 100),
        blink_times=(0.22, 0.58, 0.82),
        mouth_strength=1.18,
        highlight_box=(374, 116, 640, 328),
        gaze_strength=1.10,
        breath_strength=0.85,
        eye_light_strength=1.10,
    ),
    "pv_cut_08_mina_button.png": FaceRig(
        image_name="pv_cut_08_mina_button.png",
        left_eye=(415, 176, 470, 198),
        right_eye=(500, 176, 552, 198),
        mouth=(456, 278, 516, 296),
        color=(184, 142, 122),
        blink_times=(0.30, 0.74),
        mouth_strength=0.52,
        highlight_box=(350, 92, 610, 334),
        gaze_strength=0.45,
        breath_strength=0.55,
        eye_light_strength=0.72,
    ),
    "pv_cut_04_future_salaryman.png": FaceRig(
        image_name="pv_cut_04_future_salaryman.png",
        left_eye=(565, 210, 628, 230),
        right_eye=(672, 212, 733, 232),
        mouth=(620, 320, 697, 346),
        color=(155, 112, 96),
        blink_times=(0.36, 0.70),
        mouth_strength=0.82,
        highlight_box=(500, 120, 790, 390),
        gaze_strength=0.35,
        breath_strength=0.72,
        eye_light_strength=0.56,
    ),
}


def motion_value_from_dict(data: dict[str, float] | None, default_base: float = 0.0) -> MotionValue:
    data = data or {}
    return MotionValue(
        base=float(data.get("base", default_base)),
        sway=float(data.get("sway", 0.0)),
        secondary=float(data.get("secondary", 0.0)),
        positive_secondary=float(data.get("positive_secondary", 0.0)),
    )


def motion_value_to_dict(value: MotionValue) -> dict[str, float]:
    return {
        "base": value.base,
        "sway": value.sway,
        "secondary": value.secondary,
        "positive_secondary": value.positive_secondary,
    }


def scene_rig_from_dict(data: dict[str, object]) -> SceneRig:
    patches: list[PuppetPatch] = []
    for item in data.get("patches", []):
        patch = item if isinstance(item, dict) else {}
        patches.append(
            PuppetPatch(
                name=str(patch.get("name", "patch")),
                box=tuple(int(v) for v in patch.get("box", (0, 0, 1, 1))),  # type: ignore[arg-type]
                dx=motion_value_from_dict(patch.get("dx") if isinstance(patch.get("dx"), dict) else None),
                dy=motion_value_from_dict(patch.get("dy") if isinstance(patch.get("dy"), dict) else None),
                angle=motion_value_from_dict(patch.get("angle") if isinstance(patch.get("angle"), dict) else None),
                scale=motion_value_from_dict(patch.get("scale") if isinstance(patch.get("scale"), dict) else None, 1.0),
                opacity=int(patch.get("opacity", 120)),
                feather=int(patch.get("feather", 28)),
                radius=int(patch.get("radius", 64)),
                motion_scale=float(patch.get("motion_scale", 1.0)),
            )
        )
    return SceneRig(image_name=str(data["image_name"]), patches=tuple(patches))


def face_rig_from_dict(data: dict[str, object]) -> FaceRig:
    highlight = data.get("highlight_box")
    return FaceRig(
        image_name=str(data["image_name"]),
        left_eye=tuple(int(v) for v in data["left_eye"]),  # type: ignore[arg-type]
        right_eye=tuple(int(v) for v in data["right_eye"]),  # type: ignore[arg-type]
        mouth=tuple(int(v) for v in data["mouth"]),  # type: ignore[arg-type]
        color=tuple(int(v) for v in data.get("color", (180, 130, 110))),  # type: ignore[arg-type]
        blink_times=tuple(float(v) for v in data.get("blink_times", (0.24, 0.68))),  # type: ignore[arg-type]
        talk_start=float(data.get("talk_start", 0.12)),
        talk_end=float(data.get("talk_end", 0.88)),
        mouth_strength=float(data.get("mouth_strength", 1.0)),
        highlight_box=tuple(int(v) for v in highlight) if highlight else None,  # type: ignore[arg-type]
        gaze_strength=float(data.get("gaze_strength", 1.0)),
        breath_strength=float(data.get("breath_strength", 1.0)),
        eye_light_strength=float(data.get("eye_light_strength", 1.0)),
    )


def scene_rig_to_dict(rig: SceneRig) -> dict[str, object]:
    return {
        "image_name": rig.image_name,
        "patches": [
            {
                "name": patch.name,
                "box": list(patch.box),
                "dx": motion_value_to_dict(patch.dx),
                "dy": motion_value_to_dict(patch.dy),
                "angle": motion_value_to_dict(patch.angle),
                "scale": motion_value_to_dict(patch.scale),
                "opacity": patch.opacity,
                "feather": patch.feather,
                "radius": patch.radius,
                "motion_scale": patch.motion_scale,
            }
            for patch in rig.patches
        ],
    }


def face_rig_to_dict(rig: FaceRig) -> dict[str, object]:
    return {
        "image_name": rig.image_name,
        "left_eye": list(rig.left_eye),
        "right_eye": list(rig.right_eye),
        "mouth": list(rig.mouth),
        "color": list(rig.color),
        "blink_times": list(rig.blink_times),
        "talk_start": rig.talk_start,
        "talk_end": rig.talk_end,
        "mouth_strength": rig.mouth_strength,
        "highlight_box": list(rig.highlight_box) if rig.highlight_box else None,
        "gaze_strength": rig.gaze_strength,
        "breath_strength": rig.breath_strength,
        "eye_light_strength": rig.eye_light_strength,
    }


def export_default_rig_json(path: Path) -> None:
    data = {
        "version": 1,
        "scene_rigs": [scene_rig_to_dict(rig) for rig in DEFAULT_RIGS],
        "face_rigs": [face_rig_to_dict(rig) for rig in FACE_RIGS.values()],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_rig_json(path: Path) -> tuple[tuple[SceneRig, ...], dict[str, FaceRig]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    scene_rigs = tuple(scene_rig_from_dict(item) for item in data.get("scene_rigs", []))
    face_rigs = {
        rig.image_name: rig
        for rig in (face_rig_from_dict(item) for item in data.get("face_rigs", []))
    }
    return scene_rigs, face_rigs


def create_default_engine(width: int, height: int) -> PuppetMotionEngine:
    return PuppetMotionEngine(width=width, height=height, rigs=DEFAULT_RIGS, face_rigs=FACE_RIGS)


def create_engine_from_json(width: int, height: int, path: Path) -> PuppetMotionEngine:
    rigs, face_rigs = load_rig_json(path)
    return PuppetMotionEngine(width=width, height=height, rigs=rigs, face_rigs=face_rigs)

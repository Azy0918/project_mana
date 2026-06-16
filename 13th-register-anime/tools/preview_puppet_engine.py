from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw

from puppet_motion_engine import (
    MotionContext,
    build_audio_level_track,
    create_default_engine,
    create_engine_from_json,
)


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "pv_image_assets_new"
DEFAULT_AUDIO = ROOT / "output_aivis_pv_narration_nise" / "13th_register_pv_narration_nise_60s.wav"
DEFAULT_OUT = ROOT / "output_video" / "puppet_engine_previews"
WIDTH = 1280
HEIGHT = 720
FPS = 30


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Puppet/Vtuber風モーションエンジンの静止画プレビューを作成します。")
    parser.add_argument(
        "--image",
        default="pv_cut_07_takumi_closeup.png",
        help="pv_image_assets_new 内の画像名",
    )
    parser.add_argument(
        "--times",
        default="0.15,0.30,0.50,0.72,0.90",
        help="0.0-1.0 のローカル時刻をカンマ区切りで指定",
    )
    parser.add_argument(
        "--audio",
        default=str(DEFAULT_AUDIO),
        help="口パク用の音声WAV。存在しない場合は無音扱い",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT),
        help="プレビュー画像の出力先",
    )
    parser.add_argument(
        "--rig-json",
        default="",
        help="外部JSONリグを使う場合に指定",
    )
    parser.add_argument(
        "--contact-sheet",
        action="store_true",
        help="指定した時刻のプレビューを1枚の比較画像にもまとめます。",
    )
    parser.add_argument(
        "--animated-gif",
        action="store_true",
        help="短いVtuber風モーション確認GIFも出力します。",
    )
    parser.add_argument(
        "--talk-demo",
        action="store_true",
        help="音声なしでも口パク確認用の仮音量を使います。",
    )
    return parser.parse_args()


def cover_image(source: Image.Image) -> Image.Image:
    src_w, src_h = source.size
    scale = max(WIDTH / src_w, HEIGHT / src_h)
    resized = source.resize((int(src_w * scale), int(src_h * scale)), Image.Resampling.LANCZOS)
    x = max(0, (resized.width - WIDTH) // 2)
    y = max(0, (resized.height - HEIGHT) // 2)
    return resized.crop((x, y, x + WIDTH, y + HEIGHT))


def save_contact_sheet(frames: list[tuple[float, Image.Image]], image_name: str, out_dir: Path) -> Path:
    thumb_w = 320
    thumb_h = 180
    label_h = 28
    padding = 8
    sheet_w = len(frames) * (thumb_w + padding) + padding
    sheet_h = thumb_h + label_h + padding * 2
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 20))
    draw = ImageDraw.Draw(sheet)

    for index, (local_t, frame) in enumerate(frames):
        x = padding + index * (thumb_w + padding)
        thumb = frame.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (x, padding + label_h))
        draw.text((x, padding), f"{Path(image_name).stem}  t={local_t:.2f}", fill=(230, 230, 232))

    out_path = out_dir / f"{Path(image_name).stem}_contact_sheet.jpg"
    sheet.save(out_path, quality=92)
    return out_path


def demo_audio_level(frame_index: int) -> float:
    fast = math.sin(frame_index * 0.72) * 0.5 + 0.5
    slow = math.sin(frame_index * 0.19 + 0.8) * 0.5 + 0.5
    gate = 1.0 if frame_index % 17 < 12 else 0.18
    return max(0.0, min(1.0, (fast * 0.62 + slow * 0.38) * gate))


def save_animated_gif(
    source: Image.Image,
    image_name: str,
    out_dir: Path,
    engine,
    audio_track,
    talk_demo: bool,
) -> Path:
    frame_count = 48
    frames: list[Image.Image] = []
    for index in range(frame_count):
        local_t = index / max(1, frame_count - 1)
        audio_level = demo_audio_level(index) if talk_demo else (audio_track.at_frame(index) if audio_track else 0.0)
        context = MotionContext(local_t=local_t, global_frame=index, audio_level=audio_level)
        rendered = engine.render_frame(source.copy(), image_name, context)
        frames.append(rendered.resize((480, 270), Image.Resampling.LANCZOS))

    out_path = out_dir / f"{Path(image_name).stem}_vtuber_motion.gif"
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=42, loop=0, optimize=True)
    return out_path


def main() -> int:
    args = parse_args()
    image_path = ASSET_DIR / args.image
    if not image_path.exists():
        raise FileNotFoundError(f"image not found: {image_path}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    times = [float(item.strip()) for item in args.times.split(",") if item.strip()]
    max_frame = max(1, int(FPS * 4))
    audio_path = Path(args.audio)
    audio_track = build_audio_level_track(audio_path, FPS, max_frame) if audio_path.exists() else None

    source = cover_image(Image.open(image_path).convert("RGB"))
    engine = create_engine_from_json(WIDTH, HEIGHT, Path(args.rig_json)) if args.rig_json else create_default_engine(WIDTH, HEIGHT)

    rendered_frames: list[tuple[float, Image.Image]] = []
    for index, local_t in enumerate(times):
        frame_index = min(max_frame - 1, max(0, int(local_t * max_frame)))
        context = MotionContext(
            local_t=max(0.0, min(local_t, 1.0)),
            global_frame=frame_index,
            audio_level=audio_track.at_frame(frame_index) if audio_track else 0.0,
        )
        rendered = engine.render_frame(source.copy(), args.image, context)
        rendered_frames.append((local_t, rendered.copy()))
        out_path = out_dir / f"{Path(args.image).stem}_{index:02d}_{local_t:.2f}.jpg"
        rendered.save(out_path, quality=92)
        print(out_path)

    if args.contact_sheet and rendered_frames:
        print(save_contact_sheet(rendered_frames, args.image, out_dir))

    if args.animated_gif:
        print(save_animated_gif(source, args.image, out_dir, engine, audio_track, args.talk_demo))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

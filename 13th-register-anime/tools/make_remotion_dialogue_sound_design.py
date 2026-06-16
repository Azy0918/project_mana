from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from make_pv_sound_design_v2 import (
    ROOT,
    SAMPLE_RATE,
    SOUND_DIR,
    duck_under_voice,
    read_wav_mono,
    write_wav,
)
from make_pv_sound_design_v3 import build_design_v3, mux_video


DEFAULT_VOICE = (
    ROOT
    / "remotion-anime"
    / "public"
    / "assets"
    / "13th-register"
    / "audio"
    / "voice_drama.wav"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remotion会話アニメ版にBGM/効果音を重ねます。",
    )
    parser.add_argument(
        "--video-in",
        default=str(ROOT / "output_video" / "13th_register_remotion_puppet_allcast_v1.mp4"),
        help="音声を差し替える入力MP4",
    )
    parser.add_argument(
        "--voice",
        default=str(DEFAULT_VOICE),
        help="会話音声WAV",
    )
    parser.add_argument(
        "--output-video",
        default=str(ROOT / "output_video" / "13th_register_remotion_puppet_allcast_v1_sound_v3.mp4"),
        help="出力MP4",
    )
    parser.add_argument(
        "--voice-gain",
        type=float,
        default=1.0,
        help="会話音声の音量倍率",
    )
    parser.add_argument(
        "--design-gain",
        type=float,
        default=0.72,
        help="BGM/効果音の音量倍率",
    )
    parser.add_argument(
        "--duration-sec",
        type=float,
        default=60.05,
        help="音声をこの秒数に切り詰めます。0以下なら切り詰めません。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    SOUND_DIR.mkdir(parents=True, exist_ok=True)

    video_in = Path(args.video_in)
    voice_path = Path(args.voice)
    video_out = Path(args.output_video)

    voice, rate = read_wav_mono(voice_path)
    if rate != SAMPLE_RATE:
        raise ValueError(f"expected {SAMPLE_RATE}, got {rate}")
    if args.duration_sec > 0:
        voice = voice[: int(args.duration_sec * SAMPLE_RATE)]

    duration = len(voice) / SAMPLE_RATE
    design = build_design_v3(duration)[: len(voice)]
    design = duck_under_voice(design, voice) * args.design_gain
    mixed = np.clip(voice * args.voice_gain + design, -0.98, 0.98)

    design_path = SOUND_DIR / "13th_register_remotion_sound_design_v3.wav"
    mixed_path = SOUND_DIR / "13th_register_remotion_dialogue_mixed_v3.wav"
    write_wav(design_path, design)
    write_wav(mixed_path, mixed)
    mux_video(video_in, mixed_path, video_out)

    print(f"sound_design={design_path.resolve()} {design_path.stat().st_size}")
    print(f"mixed_audio={mixed_path.resolve()} {mixed_path.stat().st_size}")
    print(f"video={video_out.resolve()} {video_out.stat().st_size}")
    print(f"duration={duration:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

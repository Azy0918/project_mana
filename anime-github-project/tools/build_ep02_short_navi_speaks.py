from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

from build_episode_video import (
    CREAM,
    FONT,
    FPS,
    FX,
    FY,
    FW,
    FH,
    GREEN,
    H,
    KAMI,
    REPO,
    TEXT_X,
    TEXT_Y,
    W,
    ass_time,
    fit_text,
)

FF = imageio_ffmpeg.get_ffmpeg_exe()
MANIFEST = KAMI / "scene_manifest_ep02.json"
SOURCE_AUDIO = KAMI / "assets" / "ep02_full_voice_reading_hiragana.wav"
OUT = REPO / "video" / "ep02_short_navi_speaks.mp4"
AUDIO_OUT = REPO / "outputs" / "shorts" / "ep02_short_navi_speaks_audio.wav"
ASS_OUT = REPO / "ep02_short_navi_speaks_subs.ass"

LINE_IDS = [
    "ep02_v007",  # ナビ hook
    "ep02_v008",
    "ep02_v009",
    "ep02_v010",
    "ep02_v011",
    "ep02_v012",
    "ep02_v019",
    "ep02_v020",
    "ep02_v021",
]
PAUSE = 0.055
END_DUR = 2.75

HOOK = "会社帰り、\\Nバイクのナビがしゃべった。"
NEXT = "このあと\\N午前2時17分——"


def ass_escape(s: str) -> str:
    return (s or "").replace("{", "(").replace("}", ")").replace("\n", "")


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        frames = wf.getnframes()
        audio = np.frombuffer(wf.readframes(frames), dtype=np.int16)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return audio, rate


def write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    audio = np.clip(audio, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(audio.tobytes())


def beep(rate: int) -> np.ndarray:
    dur = 0.22
    t = np.arange(int(rate * dur)) / rate
    tone = np.sin(2 * math.pi * 880 * t) * 0.34 + np.sin(2 * math.pi * 1320 * t) * 0.18
    env = np.sin(np.linspace(0, math.pi, tone.size))
    return (tone * env * 32767).astype(np.int16)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in manifest}
    source, rate = read_wav(SOURCE_AUDIO)
    pause_audio = np.zeros(int(rate * PAUSE), dtype=np.int16)

    segments = []
    audio_parts = []
    cursor = 0.0
    for lid in LINE_IDS:
        row = by_id[lid]
        start = int(float(row["start"]) * rate)
        end = int(float(row["end"]) * rate)
        clip = source[start:end].copy()
        if lid == "ep02_v007":
            b = beep(rate)
            clip[: len(b)] = np.clip(clip[: len(b)].astype(np.int32) + b.astype(np.int32), -32768, 32767)
        audio_parts.append(clip)
        audio_parts.append(pause_audio)
        dur = len(clip) / rate
        segments.append(
            {
                "id": lid,
                "speaker": row["speaker"],
                "dialogue": row["dialogue"],
                "image": KAMI / row["image"],
                "start": cursor,
                "end": cursor + dur,
                "dur": dur,
            }
        )
        cursor += dur + PAUSE

    speech_end = segments[-1]["end"]
    total = speech_end + END_DUR
    audio = np.concatenate(audio_parts + [np.zeros(int(rate * END_DUR), dtype=np.int16)])
    write_wav(AUDIO_OUT, audio, rate)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KB,{FONT},56,{CREAM},&H000000FF,&H00101A26,&H96000000,-1,0,0,0,100,100,0,0,1,3,2,7,40,40,40,1
Style: Title,{FONT},64,{CREAM},&H000000FF,&H64000000,&H96000000,-1,0,0,0,100,100,0,0,1,4,3,5,60,60,0,1
Style: Pop,{FONT},64,{CREAM},&H000000FF,&H00101A26,&H78000000,-1,0,0,0,100,100,0,0,1,4,3,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    def dlg(a: float, b: float, style: str, text: str) -> None:
        events.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{text}")

    def seg(lid: str):
        return next(s for s in segments if s["id"] == lid)

    dlg(0.05, min(5.2, speech_end), "Title", f"{{\\pos({W // 2},280)\\fs68\\c{GREEN}\\b1}}{HOOK}")
    dlg(seg("ep02_v009")["start"], seg("ep02_v009")["start"] + 5.0, "Pop",
        f"{{\\pos({W // 2},305)\\fs58\\c{GREEN}\\b1}}2074年の\\N食品流通管理システム")
    dlg(seg("ep02_v010")["start"], seg("ep02_v011")["end"], "Pop",
        f"{{\\pos({W // 2},305)\\fs62\\c{GREEN}\\b1}}到着予定\\N02:16:50")

    subtitle_overrides = {
        "ep02_v009": [
            (0.00, 0.42, "ナビ", "私は2074年の\\N食品流通管理システムです。"),
            (0.42, 1.00, "ナビ", "欠落した配送記録を回収するため、\\N第十三レジへの接続が必要です。"),
        ],
        "ep02_v012": [
            (0.00, 0.36, "ナレーション", "表示された座標は、\\N汗田が昔開発していた"),
            (0.36, 0.72, "ナレーション", "制御システムに\\Nよく似ていた。"),
            (0.72, 1.00, "ナレーション", "汗田はヘルメットをかぶり、\\N夜の国道へ走り出した。"),
        ],
    }

    def add_sub(start: float, end: float, speaker: str, raw: str) -> None:
        raw = ass_escape(raw).replace("\\\\N", "\\N")
        speaker = ass_escape(speaker)
        fs, sp_fs, body = fit_text(raw, bool(speaker))
        if speaker:
            text = f"{{\\pos({TEXT_X},{TEXT_Y})\\fs{sp_fs}\\c{GREEN}\\b1}}{speaker}{{\\r\\fs{fs}}}\\N{body}"
        else:
            text = f"{{\\pos({TEXT_X},{TEXT_Y})\\fs{fs}}}{body}"
        dlg(start, end, "KB", text)

    for s in segments:
        if s["id"] in subtitle_overrides:
            for a, b, speaker, raw in subtitle_overrides[s["id"]]:
                start = s["start"] + (s["end"] - s["start"]) * a
                end = s["start"] + (s["end"] - s["start"]) * b
                add_sub(start, end, speaker, raw)
        else:
            add_sub(s["start"], s["end"], s["speaker"], s["dialogue"])

    dlg(speech_end, total, "Title", f"{{\\pos({W // 2},760)\\fs86\\b1}}{NEXT}")
    dlg(speech_end, total, "Title", f"{{\\pos({W // 2},1110)\\fs46\\c{GREEN}}}続きは本編へ")
    ASS_OUT.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

    img_segments = [(s["image"], s["dur"] + PAUSE, "line") for s in segments]
    img_segments.append((segments[-1]["image"], END_DUR + 1.0, "end"))
    missing = [str(p) for p, _, _ in img_segments if not p.exists()]
    if missing:
        print("MISSING IMAGES:\n" + "\n".join(missing))
        return 1

    sc_filter = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    cmd = [FF, "-y"]
    for img, dur, _kind in img_segments:
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(img)]
    cmd += ["-i", str(AUDIO_OUT)]

    filters = []
    for i, (_img, _dur, kind) in enumerate(img_segments):
        if kind == "end":
            filters.append(f"[{i}:v]{sc_filter},drawbox=0:0:{W}:{H}:black@0.55:t=fill[v{i}]")
        else:
            filters.append(f"[{i}:v]{sc_filter}[v{i}]")
    filters.append("".join(f"[v{i}]" for i in range(len(img_segments))) + f"concat=n={len(img_segments)}:v=1:a=0[cat]")
    speech_box_enable = f"between(t\\,0\\,{speech_end:.3f})"
    filters.append(
        f"[cat]drawbox=x={FX}:y={FY}:w={FW}:h={FH}:color=0x0E1B2E@0.86:t=fill:enable={speech_box_enable},"
        f"drawbox=x={FX}:y={FY}:w={FW}:h={FH}:color=0xA6C178@0.70:t=3:enable={speech_box_enable},"
        f"subtitles={ASS_OUT.name}[vout]"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", f"{len(img_segments)}:a",
        "-t", f"{total:.3f}",
        "-r", str(FPS),
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        str(OUT),
    ]
    print(f"build ep02 navi short: {len(segments)} lines, total={total:.2f}s -> {OUT}", flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO))
    if proc.returncode == 0:
        print(f"OK {OUT} {OUT.stat().st_size / 1_000_000:.1f} MB", flush=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

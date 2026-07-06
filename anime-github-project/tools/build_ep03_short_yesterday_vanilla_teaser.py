from __future__ import annotations

import json
import math
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
MANIFEST = KAMI / "scene_manifest_ep03.json"
SOURCE_AUDIO = KAMI / "assets" / "ep03_full_voice_reading_hiragana.wav"
OUT = REPO / "video" / "ep03_short_yesterday_vanilla_teaser.mp4"
AUDIO_OUT = REPO / "outputs" / "shorts" / "ep03_short_yesterday_vanilla_teaser_audio.wav"
ASS_OUT = REPO / "ep03_short_yesterday_vanilla_teaser_subs.ass"

PAUSE = 0.035
MONTAGE_DUR = 4.0
END_DUR = 3.2
TITLE = "第3話 昨日に溶けるアイスクリーム"

SEQUENCE = [
    "ep03_v001",
    "ep03_v002",
    "ep03_v003",
    "ep03_v006",
    "ep03_v007",
    "ep03_v005",
    "ep03_v010",
    "ep03_v011",
    "montage_melting",
    "ep03_v017",
    "ep03_v019",
    "ep03_v020",
    "ep03_v027",
    "ep03_v028",
    "ep03_v047",
    "ep03_v048",
    "ep03_v049",
    "ep03_v050",
    "ep03_v036_reg",
]


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


def tone(rate: int, freq: float, dur: float, amp: float = 0.24) -> np.ndarray:
    t = np.arange(int(rate * dur)) / rate
    data = np.sin(2 * math.pi * freq * t)
    env = np.sin(np.linspace(0, math.pi, data.size))
    return (data * env * amp * 32767).astype(np.int16)


def add_at(base: np.ndarray, add: np.ndarray, pos: int) -> None:
    if pos >= len(base):
        return
    end = min(len(base), pos + len(add))
    mixed = base[pos:end].astype(np.int32) + add[: end - pos].astype(np.int32)
    base[pos:end] = np.clip(mixed, -32768, 32767).astype(np.int16)


def ambient(rate: int, dur: float) -> np.ndarray:
    t = np.arange(int(rate * dur)) / rate
    low = np.sin(2 * math.pi * 55 * t) * 0.018
    mid = np.sin(2 * math.pi * 110 * t + 0.7) * 0.012
    pulse = np.sin(2 * math.pi * 0.08 * t) * 0.5 + 0.5
    hum = (low + mid) * (0.65 + 0.35 * pulse)
    return (hum * 32767).astype(np.int16)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in manifest}
    source, rate = read_wav(SOURCE_AUDIO)
    pause_audio = np.zeros(int(rate * PAUSE), dtype=np.int16)

    segments = []
    audio_parts = []
    cursor = 0.0
    for key in SEQUENCE:
        if key == "montage_melting":
            img = KAMI / by_id["ep03_v012"]["image"]
            dur = MONTAGE_DUR
            segments.append(
                {
                    "id": key,
                    "speaker": "",
                    "dialogue": "",
                    "image": img,
                    "start": cursor,
                    "end": cursor + dur,
                    "dur": dur,
                }
            )
            audio_parts.append(np.zeros(int(rate * dur), dtype=np.int16))
            audio_parts.append(pause_audio)
            cursor += dur + PAUSE
            continue

        row = by_id[key]
        start = int(float(row["start"]) * rate)
        end = int(float(row["end"]) * rate)
        clip = source[start:end].copy()
        audio_parts.append(clip)
        audio_parts.append(pause_audio)
        dur = len(clip) / rate
        segments.append(
            {
                "id": key,
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
    audio = np.clip(audio.astype(np.int32) + ambient(rate, len(audio) / rate).astype(np.int32), -32768, 32767).astype(np.int16)

    seg_by_id = {s["id"]: s for s in segments}
    # Freezer tick, register beep, electronic register start.
    for off, freq in [(0.15, 520), (1.55, 580), (2.8, 640)]:
        add_at(audio, tone(rate, freq, 0.16, 0.16), int((seg_by_id["montage_melting"]["start"] + off) * rate))
    add_at(audio, tone(rate, 1040, 0.18, 0.26), int(seg_by_id["ep03_v017"]["start"] * rate))
    add_at(audio, tone(rate, 1320, 0.22, 0.30), int(seg_by_id["ep03_v036_reg"]["start"] * rate))
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

    subtitle_overrides = {
        "ep03_v006": "商品名は、昨日バニラ。",
        "ep03_v007": "溶けると昨日になります。",
        "ep03_v005": "そういう機能じゃないです。",
        "ep03_v027": "これは食品ではない。\\N時間保存媒体だ。",
        "ep03_v036_reg": "第十三レジ。\\Nただいま営業中。",
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

    dlg(0.05, 4.9, "Title", f"{{\\pos({W // 2},255)\\fs74\\c{GREEN}\\b1}}冷凍庫に、\\N昨日が入ってます。")
    dlg(seg_by_id["ep03_v006"]["start"], seg_by_id["ep03_v007"]["end"], "Pop",
        f"{{\\pos({W // 2},300)\\fs72\\c{GREEN}\\b1}}昨日バニラ")
    dlg(seg_by_id["ep03_v006"]["start"] + 3.1, seg_by_id["ep03_v007"]["end"], "Pop",
        f"{{\\pos({W // 2},420)\\fs50}}溶けると昨日になります")

    m = seg_by_id["montage_melting"]
    step = MONTAGE_DUR / 3
    dlg(m["start"], m["start"] + step, "Pop", f"{{\\pos({W // 2},330)\\fs86\\c{GREEN}\\b1}}冷凍庫温度\\N-18")
    dlg(m["start"] + step, m["start"] + step * 2, "Pop", f"{{\\pos({W // 2},330)\\fs86\\c{GREEN}\\b1}}冷凍庫温度\\N-17")
    dlg(m["start"] + step * 2, m["end"], "Pop", f"{{\\pos({W // 2},330)\\fs86\\c{GREEN}\\b1}}冷凍庫温度\\N-16")
    dlg(seg_by_id["ep03_v017"]["start"], seg_by_id["ep03_v020"]["end"], "Pop",
        f"{{\\pos({W // 2},290)\\fs62\\c{GREEN}\\b1}}昨日の売上表示")

    dlg(seg_by_id["ep03_v036_reg"]["start"] - 0.65, seg_by_id["ep03_v036_reg"]["end"], "Title",
        f"{{\\pos({W // 2},300)\\fs96\\c{GREEN}\\b1}}2:17")
    dlg(speech_end, total, "Title", f"{{\\pos({W // 2},620)\\fs72\\b1}}時間は袋分け\\Nできるのか。")
    dlg(speech_end, total, "Title", f"{{\\pos({W // 2},940)\\fs52\\c{GREEN}}}続きは本編で")
    dlg(speech_end, total, "Title", f"{{\\pos({W // 2},1120)\\fs46}}{TITLE}")

    for s in segments:
        if s["id"] == "montage_melting":
            continue
        add_sub(s["start"], s["end"], s["speaker"], subtitle_overrides.get(s["id"], s["dialogue"]))

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
            filters.append(f"[{i}:v]{sc_filter},drawbox=0:0:{W}:{H}:black@0.62:t=fill[v{i}]")
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
    print(f"build ep03 yesterday vanilla teaser: {len(segments)} segments, total={total:.2f}s -> {OUT}", flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO))
    if proc.returncode == 0:
        print(f"OK {OUT} {OUT.stat().st_size / 1_000_000:.1f} MB", flush=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

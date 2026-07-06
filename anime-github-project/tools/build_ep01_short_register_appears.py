# -*- coding: utf-8 -*-
"""第1話ショート: 第十三レジ登場まで。

既存の scene_manifest / 連結音声 / planned画像を使い、会話の間を詰めた
縦型ショートを生成する。
出力: video/ep01_short_register_appears.mp4
"""
from __future__ import annotations

import json
import subprocess
import sys
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_episode_video import ass_time, fit_text, FONT, W, H, FPS, GREEN, FX, FY, FW, FH, TEXT_X, TEXT_Y  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
KAMI = REPO / "13th-register-kamishibai"
FF = imageio_ffmpeg.get_ffmpeg_exe()
RATE = 44100

OUT = REPO / "video" / "ep01_short_register_appears.mp4"
WORK = REPO / "outputs" / "shorts"
AUDIO_OUT = WORK / "ep01_short_register_appears_audio.wav"
ASS_OUT = REPO / "ep01_short_register_appears_subs.ass"
SFX = REPO / "anime-github-project" / "tools" / "sfx_register.wav"

# Full requested section except ep01_v001. The opening narration is omitted to keep the
# short inside the requested 60-75 second range.
LINE_IDS = [f"ep01_v{i:03d}" for i in range(4, 35)]
PAUSE = 0.015
END_DUR = 1.25

HOOK = "このコンビニ、2時17分にレジが増えます。"
APPEAR_TEXT = "本当に増えた。"
ENDCARD = ["続きは本編へ", "第1話 公開中", "深夜二時の第十三レジ"]


def read_wav_pcm(path: Path):
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        frames = w.getnframes()
        pcm = np.frombuffer(w.readframes(frames), dtype=np.int16).copy()
    if channels != 1 or width != 2 or rate != RATE:
        raise SystemExit(f"unsupported wav format: {path} ch={channels} width={width} rate={rate}")
    return pcm


def silence(sec: float) -> np.ndarray:
    return np.zeros(int(round(RATE * sec)), dtype=np.int16)


def slice_pcm(pcm: np.ndarray, start: float, end: float) -> np.ndarray:
    a = max(0, int(round(start * RATE)))
    b = min(len(pcm), int(round(end * RATE)))
    return pcm[a:b].copy()


def mix_at(base: np.ndarray, add: np.ndarray, at_sec: float, volume: float = 0.26) -> np.ndarray:
    pos = int(round(at_sec * RATE))
    if pos >= len(base):
        return base
    n = min(len(add), len(base) - pos)
    mixed = base.astype(np.int32)
    mixed[pos:pos + n] += (add[:n].astype(np.float32) * volume).astype(np.int32)
    return np.clip(mixed, -32768, 32767).astype(np.int16)


def write_wav(path: Path, pcm: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def ass_escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", "")


def main() -> int:
    scenes = {s["id"]: s for s in json.loads((KAMI / "scene_manifest.json").read_text(encoding="utf-8"))}
    source_audio = read_wav_pcm(KAMI / "assets" / "ep01_full_voice_reading_hiragana_mina_mao.wav")

    segments = []
    audio_parts = []
    cursor = 0.0
    sfx_at = None

    for lid in LINE_IDS:
        sc = scenes[lid]
        clip = slice_pcm(source_audio, float(sc["start"]), float(sc["end"]))
        dur = len(clip) / RATE
        img = KAMI / (sc.get("image") or "").split("?")[0]
        if not img.exists():
            raise SystemExit(f"missing image: {img}")
        if lid == "ep01_v028":
            sfx_at = cursor
        segments.append({
            "id": lid,
            "start": cursor,
            "end": cursor + dur,
            "dur": dur,
            "speaker": sc.get("speaker", ""),
            "dialogue": sc.get("dialogue", ""),
            "image": img,
        })
        audio_parts.append(clip)
        cursor += dur
        audio_parts.append(silence(PAUSE))
        cursor += PAUSE

    speech_end = cursor
    audio_parts.append(silence(END_DUR))
    cursor += END_DUR
    total = cursor
    full_audio = np.concatenate(audio_parts)

    if SFX.exists() and sfx_at is not None:
        full_audio = mix_at(full_audio, read_wav_pcm(SFX), sfx_at, volume=0.24)

    write_wav(AUDIO_OUT, full_audio)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KB,{FONT},54,&H00D2E8F1,&H000000FF,&H00101010,&HA0000000,-1,0,0,0,100,100,0,0,1,4,2,7,40,40,40,1
Style: Title,{FONT},64,&H00D2E8F1,&H000000FF,&H00101010,&HA0000000,-1,0,0,0,100,100,0,0,1,5,2,5,50,50,0,1
Style: Pop,{FONT},58,&H00D2E8F1,&H000000FF,&H00101010,&HA0000000,-1,0,0,0,100,100,0,0,1,5,2,5,50,50,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    def dlg(a: float, b: float, style: str, text: str):
        events.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{text}")

    def seg(lid: str):
        return next(s for s in segments if s["id"] == lid)

    dlg(0.05, min(seg("ep01_v007")["end"], total), "Title",
        f"{{\\pos({W // 2},270)\\fs62\\c{GREEN}\\b1}}{HOOK}")
    dlg(seg("ep01_v028")["start"], seg("ep01_v031")["end"] + 0.25, "Pop",
        f"{{\\pos({W // 2},300)\\fs70\\c{GREEN}\\b1}}{APPEAR_TEXT}")

    for ln in segments:
        raw = ass_escape(ln["dialogue"])
        sp = ass_escape((ln["speaker"] or "").strip())
        fs, sp_fs, body = fit_text(raw, bool(sp))
        if sp:
            text = f"{{\\pos({TEXT_X},{TEXT_Y})\\fs{sp_fs}\\c{GREEN}\\b1}}{sp}{{\\r\\fs{fs}}}\\N{body}"
        else:
            text = f"{{\\pos({TEXT_X},{TEXT_Y})\\fs{fs}}}{body}"
        dlg(ln["start"], ln["end"], "KB", text)

    endcard_start = max(0.0, speech_end - 0.95)
    dlg(endcard_start, total, "Title", f"{{\\pos({W // 2},360)\\fs68\\b1}}{ENDCARD[0]}")
    dlg(endcard_start, total, "Title", f"{{\\pos({W // 2},485)\\fs50\\c{GREEN}}}{ENDCARD[1]}")
    dlg(endcard_start, total, "Title", f"{{\\pos({W // 2},590)\\fs46}}{ENDCARD[2]}")
    ASS_OUT.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

    img_segments = [(ln["image"], ln["dur"] + PAUSE, "line") for ln in segments]
    img_segments.append((segments[-1]["image"], END_DUR + 2.0, "end"))

    sc_filter = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    cmd = [FF, "-y"]
    for img, dur, _kind in img_segments:
        cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(img)]
    cmd += ["-i", str(AUDIO_OUT)]

    n = len(img_segments)
    audio_idx = n
    filters = []
    for i, (_img, _dur, kind) in enumerate(img_segments):
        if i == 0:
            filters.append(f"[{i}:v]{sc_filter},drawbox=0:0:{W}:{H}:black@0.18:t=fill[v{i}]")
        elif kind == "end":
            filters.append(f"[{i}:v]{sc_filter},drawbox=0:0:{W}:{H}:black@0.58:t=fill[v{i}]")
        else:
            filters.append(f"[{i}:v]{sc_filter}[v{i}]")
    filters.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cat]")
    speech_box_enable = f"between(t\\,0\\,{speech_end:.3f})"
    filters.append(
        f"[cat]drawbox=x={FX}:y={FY}:w={FW}:h={FH}:color=0x0E1B2E@0.86:t=fill:enable={speech_box_enable},"
        f"drawbox=x={FX}:y={FY}:w={FW}:h={FH}:color=0xA6C178@0.70:t=3:enable={speech_box_enable},"
        f"subtitles={ASS_OUT.name}[vout]"
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", f"{audio_idx}:a",
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
    print(f"build ep01 register short: {len(segments)} lines, total={total:.2f}s -> {OUT}", flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO))
    if proc.returncode == 0:
        print(f"OK {OUT} {OUT.stat().st_size / 1_000_000:.1f} MB", flush=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

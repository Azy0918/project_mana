# -*- coding: utf-8 -*-
"""第1話ショート(縦9:16/1080x1920/30fps/BGMなし)を生成する専用スクリプト。

本編素材は変更せず、scene_manifest のタイムコードで既存フル音声を切り出して
ショート用に再構成する。
出力: video/ep01_short_future_onigiri.mp4
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
PAUSE = 0.08
END_DUR = 2.2
OUT = REPO / "video" / "ep01_short_future_onigiri.mp4"
WORK = REPO / "outputs" / "shorts"
AUDIO_OUT = WORK / "ep01_short_future_onigiri_audio.wav"
ASS_OUT = REPO / "ep01_short_future_onigiri_subs.ass"
SFX = REPO / "anime-github-project" / "tools" / "sfx_register.wav"

LINE_IDS = [
    "ep01_v015",  # エリ: 2時17分、第十三レジ。
    "ep01_v016",  # タクミ: はぁ？
    "ep01_v029",  # 第十三レジ: ただいま営業中
    "ep01_v030",
    "ep01_v031",
    "ep01_v033",
    "ep01_v034",
    "ep01_v038",
    "ep01_v039",
    "ep01_v040",
    "ep01_v041",
    "ep01_v042",
    "ep01_v053",
    "ep01_v054",
    "ep01_v056",
    "ep01_v057",
]

IMAGE_OVERRIDES = {
    # 起動音声の瞬間は「現れた」絵を強めに使う
    "ep01_v029": "assets/scenes/planned/ep01_vc04_register_appears_v4.png",
}

HOOK = "深夜2時17分、レジが増えた。"
ENDCARD = [
    "本編はYouTubeで公開中",
    "深夜二時の第十三レジ 第1話",
    "未来のおにぎり、温めますか",
]


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


def mix_at(base: np.ndarray, add: np.ndarray, at_sec: float, volume: float = 0.34) -> np.ndarray:
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
    register_sfx_at = None

    for lid in LINE_IDS:
        sc = scenes[lid]
        clip = slice_pcm(source_audio, float(sc["start"]), float(sc["end"]))
        dur = len(clip) / RATE
        img_rel = IMAGE_OVERRIDES.get(lid, (sc.get("image") or "").split("?")[0])
        img = KAMI / img_rel
        if not img.exists():
            raise SystemExit(f"missing image: {img}")
        if lid == "ep01_v029":
            register_sfx_at = cursor
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

    if SFX.exists() and register_sfx_at is not None:
        sfx = read_wav_pcm(SFX)
        full_audio = mix_at(full_audio, sfx, register_sfx_at, volume=0.28)

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

    dlg(0.05, min(4.3, total), "Title", f"{{\\pos({W // 2},540)\\fs88\\c{GREEN}\\b1}}{HOOK}")
    dlg(seg("ep01_v040")["start"], seg("ep01_v040")["end"] + 0.2, "Pop",
        f"{{\\pos({W // 2},520)\\fs68\\c{GREEN}\\b1}}返品レシートは50年後")
    dlg(seg("ep01_v053")["start"], seg("ep01_v054")["end"] + 0.2, "Pop",
        f"{{\\pos({W // 2},500)\\fs60\\b1}}完全栄養おにぎり\\N{{\\c{GREEN}}}製造年月日 2074年")
    dlg(seg("ep01_v056")["start"], seg("ep01_v056")["end"] + 0.2, "Pop",
        f"{{\\pos({W // 2},520)\\fs66\\c{GREEN}\\b1}}人類生存率 0.03％低下")
    dlg(seg("ep01_v057")["start"], min(seg("ep01_v057")["end"] + 0.4, speech_end), "Pop",
        f"{{\\pos({W // 2},450)\\fs52\\b1}}僕の時給で扱っていい数字じゃない")

    for ln in segments:
        raw = ass_escape(ln["dialogue"])
        sp = ass_escape((ln["speaker"] or "").strip())
        fs, sp_fs, body = fit_text(raw, bool(sp))
        if sp:
            text = f"{{\\pos({TEXT_X},{TEXT_Y})\\fs{sp_fs}\\c{GREEN}\\b1}}{sp}{{\\r\\fs{fs}}}\\N{body}"
        else:
            text = f"{{\\pos({TEXT_X},{TEXT_Y})\\fs{fs}}}{body}"
        dlg(ln["start"], ln["end"], "KB", text)

    dlg(speech_end, total, "Title", f"{{\\pos({W // 2},780)\\fs76\\b1}}{ENDCARD[0]}")
    dlg(speech_end, total, "Title", f"{{\\pos({W // 2},930)\\fs54\\c{GREEN}}}{ENDCARD[1]}")
    dlg(speech_end, total, "Title", f"{{\\pos({W // 2},1040)\\fs48}}{ENDCARD[2]}")
    ASS_OUT.write_text(header + "\n".join(events) + "\n", encoding="utf-8")

    img_segments = []
    for ln in segments:
        img_segments.append((ln["image"], ln["dur"] + PAUSE, "line"))
    img_segments.append((segments[-1]["image"], END_DUR, "end"))

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
            filters.append(f"[{i}:v]{sc_filter},drawbox=0:0:{W}:{H}:black@0.30:t=fill[v{i}]")
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
    print(f"build ep01 short: {len(segments)} lines, total={total:.2f}s -> {OUT}", flush=True)
    proc = subprocess.run(cmd, cwd=str(REPO))
    if proc.returncode == 0:
        print(f"OK {OUT} {OUT.stat().st_size / 1_000_000:.1f} MB", flush=True)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())

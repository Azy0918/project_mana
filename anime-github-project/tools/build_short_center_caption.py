# -*- coding: utf-8 -*-
"""ショート用センターテキスト版: 各話の出だし約1分を、会話ボックスなしの
中央フローティング字幕(PV風)で書き出すテストビルド。

YouTube Shortsは下部に関連動画リンク等のUIが自動表示され、下部の
会話ボックス字幕と重なって両方読めなくなるため、字幕をセーフゾーン内の
中央(縦位置1180px付近)に文字だけで表示する。

使い方: python build_short_center_caption.py 01 02 03
出力:   video/ep0N_center_caption_1min.mp4
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
from build_episode_video import (  # noqa: E402
    ass_time, wrap_jp, ep_paths, img_path, FONT, W, H, FPS, GREEN, TITLES, SERIES,
)

REPO = Path(__file__).resolve().parents[2]
FF = imageio_ffmpeg.get_ffmpeg_exe()
RATE = 44100
CX = W // 2
CAP_Y = 1180          # 字幕ブロック中心: 画面中央よりやや下、Shorts UI(下部~500px)より上
TARGET_SEC = 60.0     # 出だしの目標尺
MAX_SEC = 66.0        # 行境界で切るときの上限
TAIL = 0.8


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != RATE:
            raise SystemExit(f"unsupported wav: {path}")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).copy()


def write_wav(path: Path, pcm: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def center_fit(raw: str):
    """中央表示用: 折返し幅と行数からフォントを選ぶ(最大4行)。"""
    for fs, wrap in ((58, 15), (52, 17), (46, 19), (40, 22)):
        body = wrap_jp(raw, wrap)
        if body.count("\\N") + 1 <= 4:
            return fs, body
    return 40, wrap_jp(raw, 22)


def build(ep: str) -> int:
    epn = int(ep)
    manifest, audio_path = ep_paths(ep)
    scenes = json.loads(manifest.read_text(encoding="utf-8"))

    # 出だし: 行境界で TARGET_SEC を超えた直後まで(上限 MAX_SEC)
    picked = []
    for s in scenes:
        if float(s["start"]) >= MAX_SEC:
            break
        picked.append(s)
        if float(s["end"]) >= TARGET_SEC:
            break
    content = float(picked[-1]["end"]) + 0.15
    total = content + TAIL

    # 音声: 通し音声の先頭を行境界で切り出し
    pcm = read_wav(audio_path)
    cut = pcm[: int(round(content * RATE))]
    cut = np.concatenate([cut, np.zeros(int(RATE * TAIL), dtype=np.int16)])
    work = REPO / "outputs" / "shorts"
    audio_out = work / f"ep{ep}_center_caption_audio.wav"
    write_wav(audio_out, cut)

    # 画像タイムライン
    cuts: list[list] = []
    prev = None
    for s in picked:
        p = img_path(s["image"])
        if str(p) != prev:
            cuts.append([p, float(s["start"])])
            prev = str(p)
    durs = []
    for i, (_p, st) in enumerate(cuts):
        end = cuts[i + 1][1] if i + 1 < len(cuts) else total
        durs.append(max(0.1, end - st))
    missing = [str(p) for p, _ in cuts if not p.exists()]
    if missing:
        print("MISSING IMAGES:\n  " + "\n  ".join(missing))
        return 1

    # --- .ass: 枠なし。中央寄せ(An5)+太アウトライン+影で背景なしでも読めるように ---
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Center,{FONT},56,&H00F1E8D2,&H000000FF,&H00101A26,&H96000000,-1,0,0,0,100,100,0,0,1,5,3,5,50,50,0,1
Style: Head,{FONT},40,&H00F1E8D2,&H000000FF,&H00101A26,&H96000000,-1,0,0,0,100,100,0,0,1,4,2,5,50,50,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []

    def dlg(a: float, b: float, style: str, text: str):
        ev.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{text}")

    # 冒頭2.5秒だけ上部にタイトル(文字のみ)
    dlg(0.1, 2.5, "Head", f"{{\\pos({CX},320)\\fs38\\c{GREEN}}}{SERIES}")
    dlg(0.1, 2.5, "Head", f"{{\\pos({CX},400)\\fs46\\b1}}第{epn}話「{TITLES.get(epn, '')}」")

    for i, s in enumerate(picked):
        start = float(s["start"])
        end = float(picked[i + 1]["start"]) if i + 1 < len(picked) else content
        if end <= start:
            end = start + 0.8
        raw = (s.get("dialogue") or "").replace("{", "(").replace("}", ")").replace("\n", "")
        if not raw:
            continue
        speaker = (s.get("speaker") or "").strip()
        fs, body = center_fit(raw)
        if speaker:
            text = (f"{{\\pos({CX},{CAP_Y})\\fs{min(38, fs)}\\c{GREEN}\\b1}}{speaker}"
                    f"{{\\r\\fs{fs}\\b1}}\\N{body}")
        else:
            text = f"{{\\pos({CX},{CAP_Y})\\fs{fs}\\b1}}{body}"
        dlg(start, end, "Center", text)

    ass = REPO / f"ep{ep}_center_caption_subs.ass"
    ass.write_text(header + "\n".join(ev) + "\n", encoding="utf-8")

    # --- ffmpeg: 枠のdrawboxなし。字幕の可読性は字幕自体の縁取り+薄い全面スクリムで確保 ---
    SC = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    cmd = [FF, "-y"]
    for (p, _st), d in zip(cuts, durs):
        cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(p)]
    cmd += ["-i", str(audio_out)]
    n = len(cuts)

    v = [f"[{i}:v]{SC}[v{i}]" for i in range(n)]
    v.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cat]")
    v.append(f"[cat]drawbox=0:0:{W}:{H}:black@0.10:t=fill,subtitles={ass.name}[vout]")

    out = REPO / "video" / f"ep{ep}_center_caption_1min.mp4"
    out.parent.mkdir(exist_ok=True)
    cmd += ["-filter_complex", ";".join(v),
            "-map", "[vout]", "-map", f"{n}:a", "-t", f"{total:.3f}",
            "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(out)]
    print(f"EP{ep}: {len(picked)}行 / {n}カット / {total:.1f}s -> {out.name}", flush=True)
    r = subprocess.run(cmd, cwd=str(REPO))
    if r.returncode == 0 and out.exists():
        print(f"OK -> {out} ({out.stat().st_size / 1_000_000:.1f} MB)", flush=True)
    return r.returncode


def main() -> int:
    eps = [e.zfill(2) for e in (sys.argv[1:] or ["01", "02", "03"])]
    for ep in eps:
        rc = build(ep)
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

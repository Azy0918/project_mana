# -*- coding: utf-8 -*-
"""第3話のショート(縦9:16/1080x1920/30fps/BGMなし)を生成する専用スクリプト。
本編 build_episode_video.py を一切変更せず、字幕スタイル/ヘルパーだけ流用する。
- 構成 = shorts/ep03_short_yesterday_vanilla.json (line_ids を本編scene_manifestから抽出)
- 音声 = 既存 AivisSpeech クリップ(anime_clips/ep03_aivis/raw)を連結(BGMなし)
- 冒頭フックテロップ / 末尾エンドカード を付与
使い方: python build_ep03_short.py
出力: outputs/shorts/ep03_short_yesterday_vanilla.mp4
"""
from __future__ import annotations
import sys, json, io, wave, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import imageio_ffmpeg
# 本編パイプラインの字幕仕様・ヘルパーを流用(本編は無改変)
from build_episode_video import (ass_time, fit_text, FONT, W, H, FPS,
                                 GREEN, FX, FY, FW, FH, TEXT_X, TEXT_Y)

FF = imageio_ffmpeg.get_ffmpeg_exe()
REPO = Path(__file__).resolve().parents[2]
KAMI = REPO / "13th-register-kamishibai"
RATE = 44100
CX = W // 2
OUT_NAME = "ep03_short_yesterday_vanilla.mp4"


def silence(sec):
    return b"\x00\x00" * int(RATE * sec)


def main():
    cfg = json.loads((REPO / "shorts" / "ep03_short_yesterday_vanilla.json").read_text(encoding="utf-8"))
    scenes = {s["id"]: s for s in json.loads((REPO / cfg["source_scene"]).read_text(encoding="utf-8"))}
    clip_dir = Path(cfg["clip_dir"])
    hook_dur = float(cfg["hook_dur"]); end_dur = float(cfg["end_dur"]); pause = float(cfg["pause_ms"]) / 1000.0

    # 選択行: 本編scene_manifestから dialogue/image/clip を取得
    lines = []
    for lid in cfg["line_ids"]:
        sc = scenes[lid]
        cp = clip_dir / f"{lid}.wav"
        if not cp.exists():
            raise SystemExit(f"クリップ無し: {cp}")
        with wave.open(str(cp), "rb") as w:
            dur = w.getnframes() / w.getframerate(); pcm = w.readframes(w.getnframes())
        img = (sc.get("image", "") or "").split("?")[0]
        lines.append({"id": lid, "speaker": sc.get("speaker", ""), "dialogue": sc.get("dialogue", ""),
                      "image": KAMI / img, "dur": dur, "pcm": pcm})

    # 音声連結: 冒頭silence(hook) + 各clip+pause + 末尾silence(end)
    full = bytearray(silence(hook_dur))
    cursor = hook_dur
    img_segs = [(lines[0]["image"], hook_dur, "hook")]  # フックは1行目画像を暗転
    for ln in lines:
        ln["start"] = cursor
        full += ln["pcm"]; cursor += ln["dur"]
        ln["end"] = cursor
        full += silence(pause); cursor += pause
        img_segs.append((ln["image"], ln["dur"] + pause, "line"))
    speech_end = cursor
    full += silence(end_dur); cursor += end_dur
    img_segs.append((lines[-1]["image"], end_dur, "end"))
    total = cursor

    # 音声wav書き出し
    (REPO / "outputs" / "shorts").mkdir(parents=True, exist_ok=True)
    audio_path = REPO / "outputs" / "shorts" / "ep03_short_audio.wav"
    with wave.open(str(audio_path), "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(RATE); o.writeframes(bytes(full))

    # 画像欠落チェック
    missing = [str(p) for p, _d, _k in img_segs if not Path(p).exists()]
    if missing:
        raise SystemExit("MISSING IMAGES:\n  " + "\n  ".join(sorted(set(missing))))

    # --- .ass (フックテロップ / 各セリフ字幕 / エンドカード) ---
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KB,{FONT},56,&H00D2E8F1,&H000000FF,&H00101A26,&H96000000,-1,0,0,0,100,100,0,0,1,3,2,7,40,40,40,1
Style: Title,{FONT},64,&H00D2E8F1,&H000000FF,&H64000000,&H96000000,-1,0,0,0,100,100,0,0,1,4,3,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    def dlg(a, b, style, text):
        ev.append(f"Dialogue: 0,{ass_time(a)},{ass_time(b)},{style},,0,0,0,,{text}")

    # フックテロップ(中央やや上・大きめ)。音声開始まで強く出す
    dlg(0.05, hook_dur + 0.35, "Title", f"{{\\pos({CX},640)\\fs96\\c{GREEN}\\b1}}{cfg['hook']}")
    # 各セリフ字幕(本編と同じ下三分の一ボックス+話者名)
    for ln in lines:
        raw = (ln["dialogue"] or "").replace("{", "(").replace("}", ")").replace("\n", "")
        sp = (ln["speaker"] or "").strip()
        fs, sp_fs, body = fit_text(raw, bool(sp))
        pos = f"\\pos({TEXT_X},{TEXT_Y})"
        if sp:
            text = f"{{{pos}\\fs{sp_fs}\\c{GREEN}\\b1}}{sp}{{\\r\\fs{fs}}}\\N{body}"
        else:
            text = f"{{{pos}\\fs{fs}}}{body}"
        dlg(ln["start"], ln["end"], "KB", text)
    # エンドカード(本編誘導・3行中央)
    ec = cfg["endcard"]
    dlg(speech_end, total, "Title", f"{{\\pos({CX},820)\\fs76\\b1}}{ec[0]}")
    dlg(speech_end, total, "Title", f"{{\\pos({CX},960)\\fs56\\c{GREEN}}}{ec[1]}")
    dlg(speech_end, total, "Title", f"{{\\pos({CX},1090)\\fs48}}{ec[2]}")

    ass_path = REPO / "ep03_short_subs.ass"
    ass_path.write_text(header + "\n".join(ev) + "\n", encoding="utf-8")

    # --- ffmpeg (画像タイムライン + 字幕、BGMなし=vox音声のみ) ---
    SC = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    cmd = [FF, "-y"]
    for img, d, _k in img_segs:
        cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(img)]
    cmd += ["-i", str(audio_path)]
    n = len(img_segs); aidx = n
    v = []
    for i, (_img, _d, kind) in enumerate(img_segs):
        if kind in ("hook", "end"):
            v.append(f"[{i}:v]{SC},drawbox=0:0:{W}:{H}:black@0.55:t=fill[v{i}]")
        else:
            v.append(f"[{i}:v]{SC}[v{i}]")
    v.append("".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[cat]")
    en = f"between(t\\,{hook_dur:.3f}\\,{speech_end:.3f})"  # 字幕ボックスは発話区間のみ
    v.append(
        f"[cat]drawbox=x={FX}:y={FY}:w={FW}:h={FH}:color=0x0E1B2E@0.86:t=fill:enable={en},"
        f"drawbox=x={FX}:y={FY}:w={FW}:h={FH}:color=0xA6C178@0.70:t=3:enable={en},"
        f"subtitles={ass_path.name}[vout]"
    )
    out = REPO / "outputs" / "shorts" / OUT_NAME
    cmd += ["-filter_complex", ";".join(v),
            "-map", "[vout]", "-map", f"{aidx}:a", "-t", f"{total:.3f}",
            "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", str(out)]
    print(f"SHORT ep03: lines={len(lines)} total={total:.1f}s (hook {hook_dur}/speech {speech_end-hook_dur:.1f}/end {end_dur}) -> {out.name}", flush=True)
    r = subprocess.run(cmd, cwd=str(REPO))
    if r.returncode == 0 and out.exists():
        print(f"OK -> {out}  ({out.stat().st_size/1_000_000:.1f} MB)", flush=True)
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())

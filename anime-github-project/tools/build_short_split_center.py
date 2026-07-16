# -*- coding: utf-8 -*-
"""本編をショート用に分割し、PV風センターテキスト版(枠なし・中央字幕・Shorts UI回避)で
各セグメントを書き出す。build_short_center_caption.py の全編分割版。

- 各話をカット境界で <=MAX 秒に均等分割(パート数=ceil(総尺/MAX))。
- セグメントごとに: 本編画像(カット境界)＋薄いスクリム、中央フローティング字幕、
  冒頭2.8秒に「第N話○「タイトル」＋パート小見出し」を表示。
- 音声は通し音声[a,z]をffmpegで切り出し。字幕/画像は先頭a秒ぶんオフセット。

使い方: python build_short_split_center.py 01 02 03 04
出力:   video/ep0N_short_KofM.mp4
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_episode_video import (  # noqa: E402
    ass_time, wrap_jp, ep_paths, img_path, FONT, W, H, FPS, GREEN, TITLES, SERIES,
)

REPO = Path(__file__).resolve().parents[2]
FF = imageio_ffmpeg.get_ffmpeg_exe()
CX = W // 2
CAP_Y = 1180          # 字幕ブロック中心: 画面中央よりやや下、Shorts UI(下部)より上
MAX_SEC = 175.0       # 1本の上限(YouTube Shortsは最大180秒)
TAIL = 0.8            # 末尾の余韻(無音)
MARU = "①②③④⑤⑥⑦⑧⑨"

# 各話・各パートの小見出し(ストーリー要約)。続きと分かる「第N話○」は自動付与。
PART_TITLES = {
    1: ["深夜のコンビニに未来の男", "2074年製おにぎりを温める", "世界の危機も業務連絡"],
    2: ["バイクのナビが未来を案内", "返品おにぎりと次の異常地点"],
    3: ["昨日に戻る店内", "時間は袋分けできる"],
    4: ["点滅するホットスナックケース", "味より演出の未来商品"],
}


def cut_boundaries(scenes):
    """画像が切り替わる行の (index, start_sec) 一覧。"""
    res = []
    prev = None
    for i, s in enumerate(scenes):
        im = str(s.get("image", ""))
        if im != prev:
            res.append((i, float(s["start"])))
            prev = im
    return res


def plan_segments(scenes):
    """カット境界で MAX_SEC 以内に均等分割した境界秒 [0, .., total] を返す。"""
    total = float(scenes[-1]["end"])
    nb = cut_boundaries(scenes)
    parts = max(1, math.ceil(total / MAX_SEC))
    target = total / parts
    bounds = [0.0]
    for pi in range(1, parts):
        goal = target * pi
        cand = [(abs(st - goal), st) for _, st in nb
                if st > bounds[-1] + 20 and st < total - 20]
        if cand:
            cand.sort()
            bounds.append(cand[0][1])
    bounds.append(total)
    uniq = [bounds[0]]
    for b in bounds[1:]:
        if b > uniq[-1] + 5:
            uniq.append(b)
    return uniq


def center_fit(raw: str):
    """中央表示用: 折返し幅と行数からフォントを選ぶ(最大4行)。"""
    for fs, wrap in ((58, 15), (52, 17), (46, 19), (40, 22)):
        body = wrap_jp(raw, wrap)
        if body.count("\\N") + 1 <= 4:
            return fs, body
    return 40, wrap_jp(raw, 22)


def build_segment(ep, epn, scenes, a, z, k, n, audio_path):
    """[a,z] のセグメントを 1 本のショートに書き出す。"""
    seg = [s for s in scenes if a <= float(s["start"]) < z]
    if not seg:
        return 0
    content = z - a
    total = content + TAIL
    maru = MARU[k - 1] if k - 1 < len(MARU) else f"({k})"
    sub = PART_TITLES.get(epn, [""] * n)
    part_sub = sub[k - 1] if k - 1 < len(sub) else ""

    # 音声: 通し音声[a,z]を切り出し(44.1k mono)
    work = REPO / "outputs" / "shorts"
    work.mkdir(parents=True, exist_ok=True)
    audio_out = work / f"ep{ep}_short_{k}of{n}_audio.wav"
    subprocess.run([FF, "-y", "-ss", f"{a:.3f}", "-i", str(audio_path),
                    "-t", f"{content:.3f}", "-ar", "44100", "-ac", "1",
                    "-c:a", "pcm_s16le", str(audio_out)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 画像タイムライン(セグメント先頭a秒ぶんオフセット)
    cuts = []
    prev = None
    for s in seg:
        p = img_path(s["image"])
        if str(p) != prev:
            cuts.append([p, float(s["start"]) - a])
            prev = str(p)
    durs = []
    for i, (_p, st) in enumerate(cuts):
        end = cuts[i + 1][1] if i + 1 < len(cuts) else total
        durs.append(max(0.1, end - st))
    missing = [str(p) for p, _ in cuts if not p.exists()]
    if missing:
        print("MISSING IMAGES:\n  " + "\n  ".join(missing))
        return 1

    # --- .ass: 枠なし・中央寄せ(An5)・太アウトライン+影 ---
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

    def dlg(t0, t1, style, text):
        ev.append(f"Dialogue: 0,{ass_time(t0)},{ass_time(t1)},{style},,0,0,0,,{text}")

    # 冒頭2.8秒: シリーズ名 / 第N話○ / タイトル / パート小見出し
    dlg(0.1, 2.8, "Head", f"{{\\pos({CX},300)\\fs34\\c{GREEN}}}{SERIES}")
    dlg(0.1, 2.8, "Head", f"{{\\pos({CX},378)\\fs50\\b1}}第{epn}話{maru}")
    dlg(0.1, 2.8, "Head", f"{{\\pos({CX},452)\\fs36}}「{TITLES.get(epn, '')}」")
    if part_sub:
        dlg(0.1, 2.8, "Head", f"{{\\pos({CX},520)\\fs32\\c{GREEN}}}{part_sub}")

    # 常時: 右上に第N話○(続き明示・小さめ)
    dlg(2.8, total, "Head", f"{{\\pos({W-120},110)\\fs34\\c{GREEN}\\b1}}第{epn}話{maru}")

    for i, s in enumerate(seg):
        start = float(s["start"]) - a
        end = (float(seg[i + 1]["start"]) - a) if i + 1 < len(seg) else content
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

    ass = REPO / f"ep{ep}_short_{k}of{n}_subs.ass"
    ass.write_text(header + "\n".join(ev) + "\n", encoding="utf-8")

    # --- ffmpeg: 枠なし。字幕縁取り+薄い全面スクリムで可読性確保 ---
    SC = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    cmd = [FF, "-y"]
    for (p, _st), d in zip(cuts, durs):
        cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(p)]
    cmd += ["-i", str(audio_out)]
    nn = len(cuts)
    v = [f"[{i}:v]{SC}[v{i}]" for i in range(nn)]
    v.append("".join(f"[v{i}]" for i in range(nn)) + f"concat=n={nn}:v=1:a=0[cat]")
    v.append(f"[cat]drawbox=0:0:{W}:{H}:black@0.10:t=fill,subtitles={ass.name}[vout]")

    out = REPO / "video" / f"ep{ep}_short_{k}of{n}.mp4"
    out.parent.mkdir(exist_ok=True)
    cmd += ["-filter_complex", ";".join(v),
            "-map", "[vout]", "-map", f"{nn}:a", "-t", f"{total:.3f}",
            "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(out)]
    print(f"EP{ep} {k}/{n}: {len(seg)}行 / {nn}カット / {total:.1f}s -> {out.name}", flush=True)
    r = subprocess.run(cmd, cwd=str(REPO))
    if r.returncode == 0 and out.exists():
        print(f"  OK {out.stat().st_size / 1_000_000:.1f} MB", flush=True)
    return r.returncode


def build(ep: str) -> int:
    epn = int(ep)
    manifest, audio_path = ep_paths(ep)
    scenes = json.loads(manifest.read_text(encoding="utf-8"))
    bounds = plan_segments(scenes)
    n = len(bounds) - 1
    for k in range(1, n + 1):
        rc = build_segment(ep, epn, scenes, bounds[k - 1], bounds[k], k, n, audio_path)
        if rc:
            return rc
    return 0


def main() -> int:
    eps = [e.zfill(2) for e in (sys.argv[1:] or ["01", "02", "03", "04"])]
    for ep in eps:
        rc = build(ep)
        if rc:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

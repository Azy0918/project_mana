from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

REPO = Path(__file__).resolve().parents[2]
FF = imageio_ffmpeg.get_ffmpeg_exe()
KAMI = REPO / "13th-register-kamishibai"
W, H, FPS = 1080, 1920, 30
FONT = "Yu Gothic"
WRAP = 16
BGM_VOL = 0.09
TITLE_DUR = 3.0     # opening title card seconds
END_DUR = 4.0       # end card seconds
CX = W // 2
# visual-novel dialogue frame (lower third, drawn during the episode body)
FX, FY, FW, FH = 40, 1440, 1000, 330
TEXT_X, TEXT_Y = FX + 55, FY + 40
# persistent top badge box: 第N話 + episode title
BADGE_X, BADGE_Y, BADGE_H = 30, 30, 72

SERIES = "深夜二時の第十三レジ"
TITLES = {
    1: "未来のおにぎり、温めますか", 2: "ナビが未来を案内しました", 3: "昨日に溶けるアイスクリーム",
    4: "未来レシートは先に謝る", 5: "昭和の伝票、まだ未処理です", 6: "賞味期限が生まれる前のパン",
    7: "宇宙宅配便、店留めです", 8: "月面店、発注しすぎました", 9: "銀河ポイントカードはお持ちですか",
    10: "あの会社員、返品済みです", 11: "第十二レジと第十四レジ", 12: "午前二時十七分、通常営業です",
}
CYAN = "&H00FFE553&"


def ep_paths(ep: str):
    if ep == "01":
        return (KAMI / "scene_manifest.json",
                KAMI / "assets" / "ep01_full_voice_reading_hiragana_mina_mao.wav")
    return (KAMI / f"scene_manifest_ep{ep}.json",
            KAMI / "assets" / f"ep{ep}_full_voice_reading_hiragana.wav")


def probe_duration(path: Path) -> float:
    p = subprocess.run([FF, "-hide_banner", "-i", str(path)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    err = (p.stderr or b"").decode("utf-8", "ignore")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err)
    if not m:
        raise SystemExit(f"could not probe duration of {path}")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cc = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cc:02d}"


def wrap_jp(text: str, n: int = WRAP) -> str:
    lines, cur = [], ""
    for ch in text:
        cur += ch
        if (ch in "、。！？" and len(cur) >= 8) or len(cur) >= n:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    if len(lines) >= 2 and len(lines[-1]) <= 2 and len(lines[-2]) + len(lines[-1]) <= n + 1:
        last = lines.pop()
        lines[-1] += last
    return "\\N".join(lines)


def img_path(image_field: str) -> Path:
    return KAMI / image_field.split("?")[0]


def main() -> int:
    ep = (sys.argv[1] if len(sys.argv) > 1 else "01").zfill(2)
    epn = int(ep)
    title = TITLES.get(epn, "")
    manifest, audio = ep_paths(ep)
    (REPO / "video").mkdir(exist_ok=True)
    out = REPO / "video" / f"ep{ep}_youtube_vertical_1080x1920.mp4"
    ass = REPO / f"ep{ep}_subs.ass"

    scenes = json.loads(manifest.read_text(encoding="utf-8"))
    content = probe_duration(audio)
    total = TITLE_DUR + content + END_DUR
    es = TITLE_DUR + content
    badge_w = min(W - 60, 56 + len(f"第{epn}話　{title}") * 35)

    # image timeline (one segment per cut)
    cuts: list[list] = []
    prev = None
    for s in scenes:
        p = img_path(s["image"])
        if str(p) != prev:
            cuts.append([p, float(s["start"])])
            prev = str(p)
    durs = []
    for i, (_p, st) in enumerate(cuts):
        end = cuts[i + 1][1] if i + 1 < len(cuts) else content
        durs.append(max(0.1, end - st))
    missing = [str(p) for p, _ in cuts if not p.exists()]
    if missing:
        print("MISSING IMAGES:\n  " + "\n  ".join(missing))
        return 1
    first_img, last_img = cuts[0][0], cuts[-1][0]

    # --- .ass: floating title card, boxed top badge, dialogue, end card ---
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KB,{FONT},56,&H00FFFFFF,&H000000FF,&H00101A26,&H96000000,-1,0,0,0,100,100,0,0,1,3,2,7,40,40,40,1
Style: Title,{FONT},64,&H00FFFFFF,&H000000FF,&H64000000,&H96000000,-1,0,0,0,100,100,0,0,1,4,3,5,60,60,0,1
Style: Label,{FONT},33,&H00FFFFFF,&H000000FF,&H00101A26,&H78000000,-1,0,0,0,100,100,0,0,1,2,1,4,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []

    def dlg(start, end, style, text):
        ev.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{text}")

    # title card (floating text over the darkened first image)
    dlg(0.15, TITLE_DUR, "Title", f"{{\\pos({CX},770)\\fs46\\c{CYAN}}}{SERIES}")
    dlg(0.15, TITLE_DUR, "Title", f"{{\\pos({CX},910)\\fs108\\b1}}第{epn}話")
    dlg(0.15, TITLE_DUR, "Title", f"{{\\pos({CX},1055)\\fs54}}{title}")

    # persistent top badge: 第N話 (cyan) + title (white), inside the drawn box
    dlg(TITLE_DUR, es, "Label",
        f"{{\\pos({BADGE_X+26},{BADGE_Y + BADGE_H//2})\\c{CYAN}\\b1}}第{epn}話　{{\\r}}{title}")

    # content subtitles, shifted by +TITLE_DUR, laid out inside the dialogue frame
    for i, s in enumerate(scenes):
        start = float(s["start"]) + TITLE_DUR
        end = (float(scenes[i + 1]["start"]) if i + 1 < len(scenes) else content) + TITLE_DUR
        if end <= start:
            end = start + 0.8
        raw = (s.get("dialogue") or "").replace("{", "(").replace("}", ")").replace("\n", "")
        if not raw:
            continue
        speaker = (s.get("speaker") or "").strip()
        body = wrap_jp(raw)
        pos = f"\\pos({TEXT_X},{TEXT_Y})"
        text = (f"{{{pos}\\fs40\\c{CYAN}\\b1}}{speaker}{{\\r}}\\N{body}"
                if speaker else f"{{{pos}}}{body}")
        dlg(start, end, "KB", text)

    # end card (floating text over the darkened last image)
    if epn < 12:
        dlg(es, total, "Title", f"{{\\pos({CX},740)\\fs46\\c{CYAN}}}次回")
        dlg(es, total, "Title", f"{{\\pos({CX},880)\\fs96\\b1}}第{epn+1}話")
        dlg(es, total, "Title", f"{{\\pos({CX},1010)\\fs52}}{TITLES.get(epn+1,'')}")
        dlg(es, total, "Title", f"{{\\pos({CX},1230)\\fs40\\c{CYAN}}}チャンネル登録・高評価で応援してね")
    else:
        dlg(es, total, "Title", f"{{\\pos({CX},820)\\fs120\\b1}}完")
        dlg(es, total, "Title", f"{{\\pos({CX},990)\\fs50}}ご視聴ありがとうございました")
        dlg(es, total, "Title", f"{{\\pos({CX},1210)\\fs40\\c{CYAN}}}チャンネル登録・高評価で応援してね")

    ass.write_text(header + "\n".join(ev) + "\n", encoding="utf-8")

    # --- ffmpeg ---
    SC = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS}"
    cmd = [FF, "-y", "-loop", "1", "-t", f"{TITLE_DUR}", "-i", str(first_img)]      # 0: title bg
    for (p, _st), d in zip(cuts, durs):
        cmd += ["-loop", "1", "-t", f"{d:.3f}", "-i", str(p)]                       # 1..N: cuts
    cmd += ["-loop", "1", "-t", f"{END_DUR}", "-i", str(last_img)]                  # N+1: end bg
    cmd += ["-i", str(audio)]                                                       # N+2: voice
    n = len(cuts)
    aidx = n + 2

    v = [f"[0:v]{SC},drawbox=0:0:{W}:{H}:black@0.62:t=fill[vt]"]
    for i in range(1, n + 1):
        v.append(f"[{i}:v]{SC}[v{i}]")
    v.append(f"[{n+1}:v]{SC},drawbox=0:0:{W}:{H}:black@0.58:t=fill[ve]")
    v.append("[vt]" + "".join(f"[v{i}]" for i in range(1, n + 1)) + f"[ve]concat=n={n+2}:v=1:a=0[cat]")
    en = f"between(t\\,{TITLE_DUR}\\,{es:.2f})"  # frame + badge: episode body only
    v.append(
        f"[cat]drawbox=x={FX}:y={FY}:w={FW}:h={FH}:color=0x0C1322@0.86:t=fill:enable={en},"
        f"drawbox=x={FX}:y={FY}:w={FW}:h={FH}:color=0x53E5FF@0.70:t=3:enable={en},"
        f"drawbox=x={BADGE_X}:y={BADGE_Y}:w={badge_w}:h={BADGE_H}:color=0x0C1322@0.86:t=fill:enable={en},"
        f"drawbox=x={BADGE_X}:y={BADGE_Y}:w={badge_w}:h={BADGE_H}:color=0x53E5FF@0.70:t=3:enable={en},"
        f"subtitles={ass.name}[vmid]"
    )
    # progress bar: a cyan strip slid in from the left, revealing width = W*t/total
    v.append(f"color=c=0x53E5FF@0.92:s={W}x10:d={total:.2f},setsar=1[pbar]")
    v.append(f"[vmid][pbar]overlay=x='-{W}*(1-t/{total:.2f})':y={H-10}[vout]")

    a = [
        f"sine=f=130.81:r=44100:d={total:.2f}[b1]",
        f"sine=f=164.81:r=44100:d={total:.2f}[b2]",
        f"sine=f=196.00:r=44100:d={total:.2f}[b3]",
        f"sine=f=261.63:r=44100:d={total:.2f}[b4]",
        f"[b1][b2][b3][b4]amix=inputs=4:normalize=0,lowpass=f=850,tremolo=f=0.1:d=0.4,"
        f"aecho=0.8:0.5:70|130:0.25|0.18,volume={BGM_VOL},"
        f"afade=t=in:d=4,afade=t=out:st={total-5:.2f}:d=5[bgm]",
        f"[{aidx}:a]adelay={int(TITLE_DUR*1000)}:all=1,volume=0.92[vox]",
        "[vox][bgm]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.89[aout]",
    ]

    cmd += ["-filter_complex", ";".join(v + a),
            "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
            "-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", str(out)]

    print(f"EP{ep}: cuts={n} content={content:.1f}s total={total:.1f}s lines={len(scenes)} badge_w={badge_w} -> {out.name}")
    r = subprocess.run(cmd, cwd=str(REPO))
    if r.returncode == 0 and out.exists():
        print(f"OK -> {out}  ({out.stat().st_size/1_000_000:.1f} MB)")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())

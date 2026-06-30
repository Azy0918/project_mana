# -*- coding: utf-8 -*-
"""Cloud TTS で指定キャラ/行を再生成して raw clip を上書き。
日次の壁が無いので決定済みの声変更・読み修正をまとめて反映できる。
今回: エリ全26行=Laomedeia(素よみ), #098=Iapetus, #129=Charon(淡々prompt)。"""
import sys, re, io, time, wave, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_tts

OD = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ")
REV = OD / "13th-register-kamishibai" / "scripts" / "ep01_revised.md"
CLIP = OD / "outputs" / "ep01_gemini" / "raw"
TOOLS = Path(__file__).resolve().parent
OVR = json.load(open(TOOLS / "ep01_reading_overrides.json", encoding="utf-8"))


def parse():
    rows = []
    for l in io.open(REV, encoding="utf-8"):
        s = l.strip()
        if not s or s.startswith("#") or s.startswith(">"):
            continue
        m = re.match(r"^([^：:]{1,12})[：:](.+)$", s)
        if m:
            rows.append((m.group(1).strip(), m.group(2).strip()))
    return rows


def save(lid, pcm, fr):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm)
    (CLIP / f"{lid}.wav").write_bytes(b.getvalue())


def main():
    rows = parse()
    FLASH = "gemini-2.5-flash-tts"
    # 対象: (lid, voice, model, prompt)
    targets = []
    for n, (sp, t) in enumerate(rows, 1):
        lid = f"ep01_v{n:03d}"
        if sp == "エリ":
            targets.append((lid, "Laomedeia", FLASH, ""))            # 素よみ(感情ゼロ)
        elif lid == "ep01_v098":
            targets.append((lid, "Iapetus", FLASH, ""))
        elif lid == "ep01_v129":
            targets.append((lid, "Charon", "gemini-3.1-flash-tts-preview", "感情を込めず、淡々と、静かに低めで読む。"))
    print(f"Cloud TTS 再生成 {len(targets)}行", flush=True)
    ok = 0
    for i, (lid, voice, model, prompt) in enumerate(targets, 1):
        n = int(lid[6:9]); text = OVR.get(lid, rows[n - 1][1])
        try:
            pcm, fr = cloud_tts.synth_safe(text, voice, model=model, prompt=prompt)
            save(lid, pcm, fr); ok += 1
            print(f"OK {lid} {voice} {len(pcm)/2/fr:.2f}s  {text[:16]}", flush=True)
        except Exception as e:
            print(f"X {lid} {voice}: {str(e)[:70]}", flush=True)
        time.sleep(7)  # 分上限対策スロットル
    print(f"=== 完了 {ok}/{len(targets)}", flush=True)


if __name__ == "__main__":
    main()

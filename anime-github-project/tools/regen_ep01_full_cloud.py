# -*- coding: utf-8 -*-
"""EP01 全行を Cloud TTS で再生成(raw clip上書き)。
- 各キャラ voices.yaml の voice/cloud_model/pitch/tts_prompt
- タクミのツッコミ行(ep01_takumi_tsukkomi.json)は tts_prompt + 「。<tsukkomi_prompt>。」
- 誤読/二重発話/プロンプト読み上げ漏れ対策: 尺が想定の1.7倍超なら作り直し→最短テイク採用
"""
import sys, re, io, time, wave, json, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_tts

TOOLS = Path(__file__).resolve().parent
OD = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ")
REV = TOOLS.parent / "ep01_revised.md"   # OneDrive外の正本(同期復元対策)
CLIP = OD / "outputs" / "ep01_gemini" / "raw"
OVR = json.load(open(TOOLS / "ep01_reading_overrides.json", encoding="utf-8"))
SEL = set(json.load(open(TOOLS / "ep01_takumi_tsukkomi.json", encoding="utf-8")))
V = yaml.safe_load(open(TOOLS.parent / "voices.yaml", encoding="utf-8"))["characters"]
FB = {"レシート": "第十三レジ"}
CLOUD_DEFAULT = {"ナレーション": "gemini-3.1-flash-tts-preview", "第十三レジ": "gemini-3.1-flash-tts-preview",
                 "未来の会社員": "gemini-2.5-pro-tts"}


def model_for(ch, c):
    return c.get("cloud_model") or CLOUD_DEFAULT.get(ch) or "gemini-2.5-flash-tts"


def gen_robust(text, voice, model, prompt, pitch):
    """素: 1テイク・自然な速さ。明らかな二重発話(想定2倍超)のみ1回だけ作り直し短い方を採用。
    トーン(prompt)は使わないので漏れは原理的に発生しない。"""
    exp = len(text) * 0.13 + 0.6
    pcm, fr = cloud_tts.synth_safe(text, voice, model=model, prompt=prompt, pitch=pitch)
    dur = len(pcm) / 2 / fr
    if dur > exp * 2.0 + 1.0:   # 二重発話の疑いのみ介入
        time.sleep(4)
        p2, f2 = cloud_tts.synth_safe(text, voice, model=model, prompt=prompt, pitch=pitch)
        if len(p2) / 2 / f2 < dur:
            return p2, f2, len(p2) / 2 / f2, "retry"
    return pcm, fr, dur, "ok"


def main():
    rows = []
    for l in io.open(REV, encoding="utf-8"):
        s = l.strip()
        if not s or s.startswith("#") or s.startswith(">"):
            continue
        m = re.match(r"^([^：:]{1,12})[：:](.+)$", s)
        if m:
            rows.append((m.group(1).strip(), m.group(2).strip()))
    print(f"全{len(rows)}行 Cloud TTS再生成", flush=True)
    for n, (sp, t) in enumerate(rows, 1):
        lid = f"ep01_v{n:03d}"; ch = sp if sp in V else FB.get(sp, sp); c = V.get(ch, {})
        voice = c.get("voice", "Charon"); model = model_for(ch, c)
        pitch = c.get("pitch", 0); base = c.get("tts_prompt", "")
        prompt = base
        if sp == "タクミ" and lid in SEL:
            ts = c.get("tsukkomi_prompt", "ツッコミ気味で")
            prompt = (base + "。" if base else "") + ts + "。"
        text = OVR.get(lid, t)
        pcm, fr, dur, takes = gen_robust(text, voice, model, prompt, pitch)
        b = io.BytesIO()
        with wave.open(b, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm)
        (CLIP / f"{lid}.wav").write_bytes(b.getvalue())
        flag = " (★二重発話回避)" if takes == "retry" else ""
        if n % 10 == 0 or flag:
            print(f"  {n}/{len(rows)} {lid} {dur:.1f}s{flag}", flush=True)
    print("=== 完了", flush=True)


if __name__ == "__main__":
    main()

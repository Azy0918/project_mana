# -*- coding: utf-8 -*-
"""指定エピソードの音声を Cloud TTS(Gemini) で生成し、scene_manifest を retime して
連結wavと一緒に4コピーへ配置する汎用スクリプト。
使い方: python gen_episode_cloud.py ep02
- セリフ源 = scene_manifest_<ep>.json の dialogue（数字は算用数字化・第十三レジ→第13レジ）
- 声/モデル/pitch/prompt = voices.yaml（エリ=Leda+pitch8+JK淡々萌え 等）
- テンポ = EP01 と同じ(前後無音トリム+行間ポーズ+ナレ境界の間)
- raw clip は outputs/<ep>_gemini/raw に保存（再開可）
"""
import sys, json, io, re, time, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_tts
import yaml

EP = sys.argv[1] if len(sys.argv) > 1 else "ep02"
TOOLS = Path(__file__).resolve().parent
ANIME = TOOLS.parent
OD = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ")
CODEX = Path(r"C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages")
DESTS = [(r, s) for r in (CODEX, OD) for s in ("13th-register-kamishibai", "site")]
SCENE_NAME = f"scene_manifest_{EP}.json"
WAV_NAME = f"{EP}_full_voice_reading_hiragana.wav"
CLIP_DIR = OD / "outputs" / f"{EP}_gemini" / "raw"
VOICES = yaml.safe_load(open(ANIME / "voices.yaml", encoding="utf-8"))["characters"]
FB = {"レシート": "第十三レジ"}

# テンポ(EP01と同一)
PAUSE = {"ナレーション": 240, "第十三レジ": 205}
PAUSE_DEFAULT = 175
TRIM_HEAD_MS, TRIM_TAIL_MS = 60, 90
NARR_EDGE_MS = 260
RATE = 24000
# Cloud TTS モデル(キャラ別既定。voices.yaml cloud_model優先)
CLOUD_DEFAULT = {"ナレーション": "gemini-3.1-flash-tts-preview", "第十三レジ": "gemini-3.1-flash-tts-preview",
                 "未来の会社員": "gemini-2.5-pro-tts"}

# 数字→算用数字(EP01と同一ロジック)
D = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
SM = {"十": 10, "百": 100, "千": 1000}; BIG = {"万": 10000, "億": 10**8}
def k2i(s):
    if "〇" in s:
        return int("".join(str(D[c]) for c in s))
    tot = sec = cur = 0
    for ch in s:
        if ch in D: cur = D[ch]
        elif ch in SM: sec += (cur or 1) * SM[ch]; cur = 0
        elif ch in BIG: sec += cur; tot += sec * BIG[ch]; sec = 0; cur = 0
    return tot + sec + cur
KN = "〇一二三四五六七八九十百千万億"
def num_convert(text):
    prot = {}
    for i, nm in enumerate(["第十二", "第十三", "第十四"]):
        ph = f"\x00{i}\x00"; prot[ph] = nm.replace("十二", "12").replace("十三", "13").replace("十四", "14"); text = text.replace(nm, ph)
    text = re.sub(rf"([{KN}]+)(?=[時分秒円年つ文月日個])", lambda m: str(k2i(m.group(1))), text)
    for ph, nm in prot.items():
        text = text.replace(ph, nm)
    return text


def trim_edges(pcm, fr, head_ms=TRIM_HEAD_MS, tail_ms=TRIM_TAIL_MS, thr=300):
    import numpy as np
    a = np.frombuffer(pcm, dtype=np.int16)
    if a.size == 0: return pcm
    amp = np.abs(a.astype(np.int32)); peak = int(amp.max())
    t = max(thr, int(0.03 * peak)); idx = np.where(amp > t)[0]
    if idx.size == 0: return pcm
    head = max(0, int(idx[0]) - int(fr * head_ms / 1000))
    tail = min(a.size, int(idx[-1]) + int(fr * tail_ms / 1000))
    return a[head:tail].tobytes()


def model_for(ch, conf):
    return conf.get("cloud_model") or CLOUD_DEFAULT.get(ch) or "gemini-2.5-flash-tts"


def main():
    src = json.load(open(CODEX / "13th-register-kamishibai" / SCENE_NAME, encoding="utf-8"))
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{EP}: {len(src)}行 生成開始", flush=True)
    clips = []
    for i, sc in enumerate(src, 1):
        sp = sc["speaker"]; ch = sp if sp in VOICES else FB.get(sp, sp)
        conf = VOICES.get(ch, {})
        voice = conf.get("voice", "Charon"); model = model_for(ch, conf)
        pitch = conf.get("pitch", 0); prompt = conf.get("tts_prompt", "")
        text = num_convert(sc.get("dialogue", ""))
        sc["dialogue"] = text  # 数字反映
        lid = sc["id"]; cp = CLIP_DIR / f"{lid}.wav"
        if cp.exists():
            with wave.open(str(cp), "rb") as w:
                fr = w.getframerate(); pcm = w.readframes(w.getnframes())
        else:
            pcm, fr = cloud_tts.synth_safe(text, voice, model=model, prompt=prompt, pitch=pitch)
            b = io.BytesIO()
            with wave.open(b, "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm)
            cp.write_bytes(b.getvalue())
            time.sleep(7)
        pcm = trim_edges(pcm, fr)
        clips.append({"sc": sc, "ch": ch, "pcm": pcm, "fr": fr})
        if i % 10 == 0:
            print(f"  {i}/{len(src)}", flush=True)

    rate = clips[0]["fr"] if clips else RATE
    cursor = 0.0; full = bytearray(); NARR = "ナレーション"
    for vi, c in enumerate(clips):
        ch = c["ch"]; pcm = c["pcm"]; sc = c["sc"]
        prev = clips[vi - 1]["ch"] if vi >= 1 else None
        nxt = clips[vi + 1]["ch"] if vi + 1 < len(clips) else None
        if ch == NARR and prev != NARR and NARR_EDGE_MS:
            full += b"\x00\x00" * int(rate * NARR_EDGE_MS / 1000); cursor += NARR_EDGE_MS / 1000.0
        start = cursor; dur = len(pcm) / 2 / rate; full += pcm; cursor += dur
        sc["start"] = round(start, 3); sc["end"] = round(cursor, 3)
        pa = PAUSE.get(ch, PAUSE_DEFAULT)
        if ch == NARR and nxt != NARR:
            pa = max(pa, NARR_EDGE_MS)
        if pa:
            full += b"\x00\x00" * int(rate * pa / 1000); cursor += pa / 1000.0

    buf = io.BytesIO()
    with wave.open(buf, "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(rate); o.writeframes(bytes(full))
    wav = buf.getvalue()
    for root, sub in DESTS:
        base = root / sub
        (base / "assets").mkdir(parents=True, exist_ok=True)
        (base / "assets" / WAV_NAME).write_bytes(wav)
        json.dump(src, open(base / SCENE_NAME, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  書込 {root.name}/{sub}", flush=True)
    print(f"完了: {len(src)}行 / 総尺 {cursor:.1f}s / wav {len(wav)//1024}KB", flush=True)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""指定エピソードを AivisSpeech で生成し、scene_manifest を retime して4コピー配置。
使い方: python gen_episode_aivis.py ep02   (AivisSpeechエンジン 10101 起動必須)
- セリフ源 = scene_manifest_<ep>.json の dialogue(数字算用化・エリ済)
- 声/パラメータ = ep01_voice_cast.csv(キャラ→style_id/速度/抑揚/ピッチ)
- テンポ = EP01 aivisと同一(ナレ450/レジ350/既定250ms)
"""
import sys, json, io, time, wave, csv, urllib.parse, urllib.request
from pathlib import Path

EP = sys.argv[1] if len(sys.argv) > 1 else "ep02"
API = "http://127.0.0.1:10101"
RATE = 44100
PARAM_KEYS = ("speedScale", "intonationScale", "tempoDynamicsScale", "pitchScale",
              "volumeScale", "prePhonemeLength", "postPhonemeLength")
TOOLS = Path(__file__).resolve().parent
CODEX = Path(r"C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages")
OD = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ")
DESTS = [(CODEX, s) for s in ("13th-register-kamishibai", "site")]  # Codexのみ(OneDrive不使用)
SCENE_NAME = f"scene_manifest_{EP}.json"
WAV_NAME = f"{EP}_full_voice_reading_hiragana.wav"
CLIP_DIR = Path(r"C:\Users\qvf03\Documents\anime_clips") / f"{EP}_aivis" / "raw"  # OneDrive外
CAST_CSV = TOOLS / "ep01_voice_cast.csv"
FB = {"レシート": "第十三レジ"}
PAUSE = {"ナレーション": 450, "第十三レジ": 350}
PAUSE_DEFAULT = 250
VOICE_MAN_NAME = f"manifest_reading_hiragana_{EP}.json"
# 発音矯正(読み)辞書: 表示セリフは漢字のまま、合成だけ かな読みに置換(EP01と統一)
READING_FIXES = {"時空": "じくう", "履歴": "りれき", "返金": "へんきん", "返品": "へんぴん", "汗田": "あせだ"}
def to_reading(text):
    for k, v in READING_FIXES.items():
        text = text.replace(k, v)
    return text
# 行単位の読み上書き(表示≠読みの個別指定)。{id: 読み}。辞書より優先
_OVR = TOOLS / "line_reading_overrides.json"
LINE_READING = json.loads(_OVR.read_text(encoding="utf-8")) if _OVR.exists() else {}
# 第13レジ登場の効果音を、指定行(登場の宣言/ナレーション)の直後に挿入。{id: wav(44.1kHz mono)}
_SFX = TOOLS / "sfx_register.wav"
SFX_AFTER = {k: _SFX for k in (
    "ep02_v024",  # 「第13レジ。ただいま営業中。」
    "ep03_v036", "ep04_v021", "ep05_v009", "ep06_v009", "ep07_v007",
    "ep08_v008", "ep09_v011", "ep10_v015", "ep11_v007", "ep12_v015",  # 各話「第十三レジが現れた」
)}
def _sfx_pcm(p):
    with wave.open(str(p), "rb") as w:
        return w.readframes(w.getnframes())


def post(url, payload=None, attempts=4):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, data=data, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            last = e; time.sleep(1.0 * (i + 1))
    raise last


def audio_query(text, sid):
    return json.loads(post(f"{API}/audio_query?{urllib.parse.urlencode({'text': text, 'speaker': sid})}").decode("utf-8"))


def synth(query, sid):
    return post(f"{API}/synthesis?{urllib.parse.urlencode({'speaker': sid})}", query)


def main():
    cast = {r["character"]: r for r in csv.DictReader(io.open(CAST_CSV, encoding="utf-8-sig"))}
    src = json.load(open(CODEX / "13th-register-kamishibai" / SCENE_NAME, encoding="utf-8"))
    # 画像を visual_cut_plan(確定版)から再同期: planned実在ならplanned、無ければfallback
    kami = CODEX / "13th-register-kamishibai"
    plan_path = kami / f"visual_cut_plan_{EP}.json"
    if plan_path.exists():
        plan = {c["visualCutId"]: c for c in json.load(open(plan_path, encoding="utf-8"))}
        for s in src:
            c = plan.get(s.get("visualCutId"))
            if not c:
                continue
            pi = (c.get("plannedImage") or "").split("?")[0]
            fb = (c.get("fallbackImage") or "").split("?")[0]
            img = pi if (pi and (kami / pi).exists()) else fb
            if img:
                s["image"] = img
                s["plannedImage"] = c.get("plannedImage", s.get("plannedImage", ""))
                s["fallbackImage"] = c.get("fallbackImage", s.get("fallbackImage", ""))
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    print(f"{EP}: {len(src)}行 AivisSpeech合成", flush=True)
    clips = []
    for i, sc in enumerate(src, 1):
        sp = sc["speaker"]; ch = sp if sp in cast else FB.get(sp, sp)
        info = cast.get(ch)
        if not info:
            print(f"  ★cast無し {sp}->skip", flush=True); continue
        sid = int(info["style_id"]); dialogue = sc.get("dialogue", "")
        reading = LINE_READING.get(sc["id"]) or to_reading(dialogue)   # 行上書き優先、無ければ辞書適用
        sc["reading"] = reading          # scene_manifestにも読みを格納
        cp = CLIP_DIR / f"{sc['id']}.wav"
        if not cp.exists():   # 再開: 既存クリップ再利用(AivisSpeechは決定的)
            q = audio_query(reading, sid)
            for k in PARAM_KEYS:
                q[k] = float(info[k])
            q["outputSamplingRate"] = RATE; q["outputStereo"] = False
            cp.write_bytes(synth(q, sid))
        with wave.open(str(cp), "rb") as w:
            fr = w.getframerate(); pcm = w.readframes(w.getnframes())
        clips.append({"sc": sc, "ch": ch, "pcm": pcm, "fr": fr, "info": info, "reading": reading})
        if i % 20 == 0:
            print(f"  {i}/{len(src)}", flush=True)
        time.sleep(0.15)

    rate = clips[0]["fr"] if clips else RATE
    cursor = 0.0; full = bytearray()
    for c in clips:
        sc = c["sc"]; pcm = c["pcm"]; ch = c["ch"]
        start = cursor; dur = len(pcm) / 2 / rate; full += pcm; cursor += dur
        sc["start"] = round(start, 3); sc["end"] = round(cursor, 3)
        pa = PAUSE.get(ch, PAUSE_DEFAULT)
        if pa:
            full += b"\x00\x00" * int(rate * pa / 1000); cursor += pa / 1000.0
        if sc["id"] in SFX_AFTER and SFX_AFTER[sc["id"]].exists():
            sfx = _sfx_pcm(SFX_AFTER[sc["id"]]); full += sfx; cursor += len(sfx) / 2 / rate

    buf = io.BytesIO()
    with wave.open(buf, "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(rate); o.writeframes(bytes(full))
    wav = buf.getvalue()
    # 音声マニフェスト(review.htmlが読む「よみ」表示用): 表示=dialogue / 読み=synthesis_text
    vman = []
    for c in clips:
        sc = c["sc"]; info = c["info"]
        vman.append({"id": sc["id"], "cut": sc.get("cut", ""), "visualCutId": sc.get("visualCutId", ""),
            "character": c["ch"], "speaker_name": info["speaker_name"], "style_name": info.get("style_name", ""),
            "style_id": info["style_id"], "text": sc.get("dialogue", ""), "synthesis_text": c["reading"],
            "synthesis_source": "aivis_auto", "clip": f"outputs/{EP}_aivis/raw/{sc['id']}.wav"})
    for root, sub in DESTS:
        base = root / sub
        (base / "assets").mkdir(parents=True, exist_ok=True)
        (base / "assets" / WAV_NAME).write_bytes(wav)
        json.dump(src, open(base / SCENE_NAME, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(vman, open(base / "assets" / VOICE_MAN_NAME, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  書込 {root.name}/{sub}", flush=True)
    print(f"完了: {len(src)}行 / 総尺 {cursor:.1f}s / wav {len(wav)//1024}KB", flush=True)


if __name__ == "__main__":
    main()

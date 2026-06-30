# -*- coding: utf-8 -*-
"""読み誤りの10行を、正しいかな読み(ep01_reading_overrides.json)で再生成。
本日は3.1/proが枠切れのため 2.5-flash で生成(声はキャラ準拠 Kore/Iapetus)。
※これらの行だけ2.5-flashになるので声色がわずかに変わる可能性あり(明日proで統一可)。"""
import sys, io, time, wave, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_voice_samples import generate_tts, load_env_key

TOOLS = Path(__file__).resolve().parent
OVR = json.load(open(TOOLS / "ep01_reading_overrides.json", encoding="utf-8"))
# キャラ→声(エリ=Kore, 未来の会社員=Iapetus)
VOICE = {
    "ep01_v007": "Kore", "ep01_v011": "Kore", "ep01_v024": "Kore",
    "ep01_v066": "Kore", "ep01_v076": "Kore", "ep01_v091": "Kore", "ep01_v115": "Kore",
    "ep01_v038": "Iapetus", "ep01_v058": "Iapetus", "ep01_v087": "Iapetus",
}
MODEL = "gemini-2.5-flash-preview-tts"
CLIP = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ\outputs\ep01_gemini\raw")


def save(path, pcm, fr):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm)
    path.write_bytes(b.getvalue())


def main():
    key = load_env_key()
    ok = []; fail = []
    for lid, kana in OVR.items():
        voice = VOICE[lid]; done = False
        for attempt in range(8):
            try:
                wb = generate_tts(key, MODEL, voice, kana, "", insecure_ssl=True)
                with wave.open(io.BytesIO(wb), "rb") as w:
                    fr = w.getframerate(); pcm = w.readframes(w.getnframes())
                dur = len(pcm) / 2 / fr
                if dur < 0.4:
                    raise RuntimeError(f"short {dur:.2f}")
                save(CLIP / f"{lid}.wav", pcm, fr)
                print(f"OK {lid} {voice} {dur:.2f}s  {kana[:18]}", flush=True)
                ok.append(lid); done = True; break
            except Exception as e:
                s = str(e)
                if "per_day" in s:
                    print(f"  {lid}: per_day枯渇→中断", flush=True); fail.append(lid); break
                print(f"  retry {lid}: {s[:38]}", flush=True); time.sleep(6)
        if not done and lid not in fail:
            fail.append(lid); print(f"X {lid} 失敗", flush=True)
        time.sleep(7)
    print(f"=== 完了 成功{len(ok)}/{len(OVR)} 失敗={fail}", flush=True)


if __name__ == "__main__":
    main()

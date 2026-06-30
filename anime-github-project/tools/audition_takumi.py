# -*- coding: utf-8 -*-
"""タクミの「ツッコミ感」を出す声＋抑揚の試聴。2.5-flashで方向性を決め、明日3.1へ適用。
明るく歯切れの良い若い男性声の候補＋一部にツッコミ指示。指示漏れは尺で判定。"""
import sys, io, time, wave, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_voice_samples import generate_tts, load_env_key

LINE = "この店、レジ二つしかないですよね。"
DIRECT = "新人バイトのツッコミ。歯切れよく、速めのテンポで、少し驚き呆れ気味に。"
MODEL = "gemini-2.5-flash-preview-tts"
OD = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ")
OUT = OD / "outputs" / "takumi_audition"
CUR = OD / "outputs" / "ep01_gemini" / "raw" / "ep01_v019.wav"  # 現行タクミ(3.1)参照: このセリフの行

# (label, voice, directive)
PLAN = [
    ("Puck_plain", "Puck", ""),
    ("Puck_tsukkomi", "Puck", DIRECT),
    ("Zephyr_plain", "Zephyr", ""),
    ("Zephyr_tsukkomi", "Zephyr", DIRECT),
    ("Fenrir_plain", "Fenrir", ""),
    ("Laomedeia_plain", "Laomedeia", ""),
    ("Sadachbia_plain", "Sadachbia", ""),
]


def save(path, pcm, fr):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm)
    path.write_bytes(b.getvalue())


def main():
    key = load_env_key()
    OUT.mkdir(parents=True, exist_ok=True)
    ref = []
    if CUR.exists():
        shutil.copy(CUR, OUT / "current_3.1_Puck.wav")
        with wave.open(str(CUR), "rb") as w:
            ref = [("current_3.1_Puck", round(w.getnframes() / w.getframerate(), 2), False)]
    done = []
    for label, voice, direct in PLAN:
        prompt = f"{direct}\n\n{LINE}" if direct else LINE
        for attempt in range(7):
            try:
                wb = generate_tts(key, MODEL, voice, prompt, "", insecure_ssl=True)
                with wave.open(io.BytesIO(wb), "rb") as w:
                    fr = w.getframerate(); pcm = w.readframes(w.getnframes())
                dur = len(pcm) / 2 / fr
                if dur < 0.6:
                    raise RuntimeError(f"short {dur:.2f}")
                leak = dur > 5.5  # 素~3s。長すぎ=指示漏れ疑い
                save(OUT / f"{label}.wav", pcm, fr)
                print(f"OK {label} {dur:.2f}s{' ★漏れ疑い' if leak else ''}", flush=True)
                done.append((label, round(dur, 2), leak)); break
            except Exception as e:
                s = str(e)
                if "per_day" in s:
                    print(f"  {label}: per_day枯渇", flush=True); break
                print(f"  retry {label}: {s[:38]}", flush=True); time.sleep(6)
        time.sleep(7)
    allrows = ref + done
    cards = "\n".join(
        f'<div class="c"><b>{l}</b> <span>({d}s){" ⚠️指示漏れ疑い" if leak else ""}</span><br>'
        f'<audio controls src="{l}.wav?cb={int(d*1000)}"></audio></div>'
        for l, d, leak in allrows)
    html = f"""<!doctype html><meta charset=utf-8><title>タクミ ツッコミ試聴</title>
<style>body{{font-family:sans-serif;background:#111;color:#eee;max-width:660px;margin:20px auto;padding:0 12px}}
.c{{background:#1c1c1c;border:1px solid #333;border-radius:8px;padding:12px;margin:10px 0}}
b{{font-size:17px;color:#7cf}} span{{color:#888}} audio{{width:100%;margin-top:6px}}</style>
<h2>タクミ ツッコミ感 試聴</h2>
<p>セリフ：「{LINE}」<br>
current_3.1_Puck＝現行(ツッコミ感弱い)。_plain＝素読み／_tsukkomi＝ツッコミ指示付き。<br>
※全て2.5-flash。本番は明日3.1で同じ声＋指示を適用します。⚠️は指示読み上げ疑い(不採用)。</p>
{cards}
<p style="color:#888">良い「声＋抑揚」のラベルを伝えてください。明日それで49行作り直します。</p>
"""
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"完了: {len(done)} / HTML={OUT/'index.html'}", flush=True)


if __name__ == "__main__":
    main()

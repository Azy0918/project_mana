# -*- coding: utf-8 -*-
"""#129 ナレーション「夜勤は、まだ終わらない。」を淡々と読ませる変種を試作。
2.5-flash / Charon。短い指示なら漏れにくいが、念のため尺で読み上げ漏れを判定。
現行(3.1)クリップも参照用にコピーして聴き比べ。"""
import sys, io, time, wave, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_voice_samples import generate_tts, load_env_key

TEXT = "夜勤は、まだ終わらない。"
MODEL = "gemini-2.5-flash-preview-tts"
VOICE = "Charon"
OD = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ")
OUT = OD / "outputs" / "narration129_audition"
RAW129 = OD / "outputs" / "ep01_gemini" / "raw" / "ep01_v129.wav"

# (ラベル, 送信プロンプト) — 漏れ判定用に素テキスト長も意識
VARIANTS = [
    ("plain1", TEXT),
    ("plain2", TEXT),
    ("flat_calm", f"感情を込めず、淡々と低い声で静かに読んでください。\n\n{TEXT}"),
    ("flat_news", f"ニュース原稿のように平坦に、抑揚を抑えて読んでください。\n\n{TEXT}"),
]


def save(path, pcm, fr):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm)
    path.write_bytes(b.getvalue())


def main():
    key = load_env_key()
    OUT.mkdir(parents=True, exist_ok=True)
    # 現行(3.1)参照
    ref = []
    if RAW129.exists():
        shutil.copy(RAW129, OUT / "current_3.1.wav")
        with wave.open(str(RAW129), "rb") as w:
            ref = [("current_3.1", round(w.getnframes() / w.getframerate(), 2), False)]
    done = []
    for label, prompt in VARIANTS:
        for attempt in range(6):
            try:
                wb = generate_tts(key, MODEL, VOICE, prompt, "", insecure_ssl=True)
                with wave.open(io.BytesIO(wb), "rb") as w:
                    fr = w.getframerate(); pcm = w.readframes(w.getnframes())
                dur = len(pcm) / 2 / fr
                if dur < 0.5:
                    raise RuntimeError(f"short {dur:.2f}")
                leak = dur > 4.0  # 素の行は~2.5s。長すぎ=指示読み上げ漏れ疑い
                save(OUT / f"{label}.wav", pcm, fr)
                print(f"OK {label} {dur:.2f}s{' ★漏れ疑い' if leak else ''}", flush=True)
                done.append((label, round(dur, 2), leak)); break
            except Exception as e:
                s = str(e)
                if "per_day" in s:
                    print(f"  {label}: per_day枯渇", flush=True); break
                print(f"  retry {label}: {s[:40]}", flush=True); time.sleep(6)
        time.sleep(7)
    allrows = ref + done
    cards = "\n".join(
        f'<div class="c"><b>{l}</b> <span>({d}s){" ⚠️指示漏れ疑い" if leak else ""}</span>'
        f'{" 〔現行3.1〕" if l.startswith("current") else " 〔2.5-flash〕"}<br>'
        f'<audio controls src="{l}.wav?cb={int(d*1000)}"></audio></div>'
        for l, d, leak in allrows)
    html = f"""<!doctype html><meta charset=utf-8><title>#129 ナレーション試聴</title>
<style>body{{font-family:sans-serif;background:#111;color:#eee;max-width:640px;margin:20px auto;padding:0 12px}}
.c{{background:#1c1c1c;border:1px solid #333;border-radius:8px;padding:12px;margin:10px 0}}
b{{font-size:18px;color:#7cf}} span{{color:#888}} audio{{width:100%;margin-top:6px}}</style>
<h2>#129 ナレーション 淡々版 試聴</h2>
<p>セリフ：「{TEXT}」／声＝Charon。<br>
「current_3.1」＝現行(感情過多)。plain＝素読み再ロール、flat_*＝淡々指示。<br>
⚠️は指示文を読み上げてしまった可能性（不採用）。</p>
{cards}
<p style="color:#888">一番ナレーションらしい(淡々)ラベルを伝えてください。差し替えます。</p>
"""
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"完了: 変種{len(done)} / HTML={OUT/'index.html'}", flush=True)


if __name__ == "__main__":
    main()

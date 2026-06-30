# -*- coding: utf-8 -*-
"""座木山辰哉の低音候補ボイスを試聴用に生成し、聴き比べHTMLを作る。
本日枠のある 2.5-flash で生成(短文でないので空応答は出にくい)。1行のみ。"""
import sys, io, time, wave, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_voice_samples import generate_tts, load_env_key

LINE = "コピー、白黒でいいよ。色がつくと、記憶が増えるから。"
MODEL = "gemini-2.5-flash-preview-tts"
# 未使用・低音/落ち着き系の候補
CANDS = ["Algieba", "Gacrux", "Rasalgethi", "Sadaltager", "Alnilam", "Zubenelgenubi"]
OUT = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ\outputs\zakiyama_audition")


def save_wav(path, pcm, fr):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm)
    path.write_bytes(b.getvalue())


def main():
    key = load_env_key()
    OUT.mkdir(parents=True, exist_ok=True)
    done = []
    for v in CANDS:
        ok = False
        for attempt in range(6):
            try:
                wb = generate_tts(key, MODEL, v, LINE, "", insecure_ssl=True)
                with wave.open(io.BytesIO(wb), "rb") as w:
                    fr = w.getframerate(); pcm = w.readframes(w.getnframes())
                dur = len(pcm) / 2 / fr
                if dur < 0.5:
                    raise RuntimeError(f"too short {dur:.2f}s")
                save_wav(OUT / f"zakiyama_{v}.wav", pcm, fr)
                print(f"OK {v} {dur:.2f}s", flush=True); done.append((v, round(dur, 2))); ok = True; break
            except Exception as e:
                s = str(e)
                if "per_day" in s:
                    print(f"  {v}: per_day(枯渇) 中断", flush=True); break
                print(f"  retry {v}: {s[:40]}", flush=True); time.sleep(6)
        if not ok and not any(d[0] == v for d in done):
            print(f"X {v} 失敗", flush=True)
        time.sleep(7)
    # 聴き比べHTML
    rows = "\n".join(
        f'<div class="c"><b>{v}</b> <span>({d}s)</span><br>'
        f'<audio controls src="zakiyama_{v}.wav?cb={int(d*1000)}"></audio></div>'
        for v, d in done)
    html = f"""<!doctype html><meta charset=utf-8>
<title>座木山 低音ボイス試聴</title>
<style>body{{font-family:sans-serif;background:#111;color:#eee;max-width:640px;margin:20px auto;padding:0 12px}}
.c{{background:#1c1c1c;border:1px solid #333;border-radius:8px;padding:12px;margin:10px 0}}
b{{font-size:18px;color:#7cf}} span{{color:#888}} audio{{width:100%;margin-top:6px}}
.cur{{color:#fa6}}</style>
<h2>座木山辰哉 低音ボイス試聴</h2>
<p>セリフ：「{LINE}」<br>現在の声＝<span class=cur>Fenrir</span>（やや高め）。モデル＝2.5-flash。</p>
{rows}
<p style="color:#888">気に入った声の名前を伝えてください。その声で本番1行を作り直します。</p>
"""
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print(f"完了: 生成 {len(done)}/{len(CANDS)} / HTML={OUT/'index.html'}", flush=True)


if __name__ == "__main__":
    main()

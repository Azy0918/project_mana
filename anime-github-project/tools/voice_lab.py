# -*- coding: utf-8 -*-
"""『深夜二時の第十三レジ』 声オーディション・ラボ（ローカルWebアプリ）。

Streamlit を使わない stdlib のみの軽量サーバ。ブラウザ自動翻訳による
removeChild クラッシュや SSL の問題を回避し、30種の Gemini ボイスを
自由に切り替えてその場で生成→再生→保存できる。

起動:
    python tools/voice_lab.py            # http://127.0.0.1:8770
    python tools/voice_lab.py --port 9000

APIキー: .env / 環境変数 GEMINI_API_KEY を使用（CLIと共通）。
保存した wav は voice_samples/ に置かれ、site/ ミラーへ publish も可能。
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve()
TOOLS = APP.parent
REPO = APP.parents[1]
sys.path.insert(0, str(TOOLS))
from gen_voice_samples import (  # noqa: E402  CLIと同じ生成ロジック/キャラ定義を再利用
    CHARACTERS, generate_tts, load_env_key, OUT_DIR,
)

# audition アプリと同じ 30 ボイス
VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]
MODELS = ["gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"]

# キャラ -> {line, style, slug}（フロントのプリセット用）
CHAR_PRESET = {
    ch: {"line": info["line"], "style": info["style"], "slug": info["slug"]}
    for ch, info in CHARACTERS.items()
}


def _page() -> bytes:
    data = json.dumps(
        {"voices": VOICES, "models": MODELS, "characters": CHAR_PRESET},
        ensure_ascii=False,
    )
    html = """<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="google" content="notranslate"><meta name="viewport"
 content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>第十三レジ ｜ 声オーディション・ラボ</title><style>
:root{--bg:#05070b;--panel:#101720;--line:#26384a;--text:#edf7ff;--muted:#98a7b8;--cyan:#53e5ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.6;padding:18px 14px 80px}
.wrap{max-width:600px;margin:0 auto}h1{font-size:18px;margin:0 0 2px}
.note{color:var(--muted);font-size:12px;margin:0 0 16px}
label{display:block;font-size:12px;color:var(--cyan);margin:12px 0 4px;font-weight:700}
select,textarea,input{width:100%;background:#0a0f16;color:var(--text);border:1px solid var(--line);
border-radius:10px;padding:10px;font-size:14px;font-family:inherit}
textarea{resize:vertical}.row{display:flex;gap:10px}.row>div{flex:1}
button{margin-top:16px;width:100%;padding:13px;border:1px solid var(--cyan);border-radius:11px;
background:rgba(83,229,255,.14);color:var(--cyan);font-weight:800;font-size:15px}
button:disabled{opacity:.5}button.sec{background:transparent;font-size:13px;padding:10px;margin-top:8px}
audio{width:100%;margin-top:14px}.msg{margin-top:12px;font-size:13px;min-height:1.2em}
.err{color:#ff9aa2}.ok{color:#7CFFB2}
.saved{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px;margin-top:18px}
.saved h2{font-size:13px;margin:0 0 6px;color:var(--cyan)}.saved a{color:var(--cyan);font-size:12px}
.sline{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:12px}.sline b{flex:0 0 130px}
</style></head><body><div class="wrap">
<h1>🎙️ 第十三レジ ｜ 声オーディション・ラボ</h1>
<p class="note">キャラを選ぶとセリフ/演技指示が入ります。声(30種)やセリフを自由に変えて試聴 → 気に入ったら保存。</p>

<label>キャラクター（プリセット）</label>
<select id="char"></select>

<div class="row">
  <div><label>ボイス（30種）</label><select id="voice"></select></div>
  <div><label>モデル</label><select id="model"></select></div>
</div>

<label>演技指示（スタイル）</label>
<textarea id="style" rows="2"></textarea>
<label>セリフ</label>
<textarea id="text" rows="3"></textarea>

<button id="gen">▶ 生成して再生</button>
<audio id="player" controls preload="none"></audio>
<div class="msg" id="msg"></div>
<button id="save" class="sec" disabled>💾 この声を保存（voice_samples へ）</button>

<div class="saved"><h2>保存済みサンプル</h2><div id="savedlist">（まだありません）</div>
<button id="publish" class="sec">🌐 公開ページへ反映（site/ ミラー）</button></div>
</div>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id);
const charSel=$('char'), voiceSel=$('voice'), modelSel=$('model');
Object.keys(D.characters).forEach(c=>charSel.add(new Option(c,c)));
D.voices.forEach(v=>voiceSel.add(new Option(v,v)));
D.models.forEach(m=>modelSel.add(new Option(m,m)));
let lastWavUrl=null, lastMeta=null;
function applyPreset(){const p=D.characters[charSel.value];$('style').value=p.style;$('text').value=p.line;}
charSel.onchange=applyPreset; applyPreset();
async function refreshSaved(){
  const r=await fetch('/api/saved'); const j=await r.json();
  const el=$('savedlist');
  if(!j.items.length){el.textContent='（まだありません）';return;}
  el.innerHTML=j.items.map(it=>`<div class="sline"><b>${it.label}</b>
    <audio controls preload="none" src="/samples/${it.file}"></audio></div>`).join('');
}
$('gen').onclick=async()=>{
  const btn=$('gen'); btn.disabled=true; $('msg').textContent='生成中…'; $('msg').className='msg';
  $('save').disabled=true;
  try{
    const body={character:charSel.value,voice:voiceSel.value,model:modelSel.value,
                style:$('style').value,text:$('text').value};
    const r=await fetch('/api/gen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(!r.ok){const e=await r.json();throw new Error(e.error||('HTTP '+r.status));}
    const blob=await r.blob();
    if(lastWavUrl)URL.revokeObjectURL(lastWavUrl);
    lastWavUrl=URL.createObjectURL(blob);
    $('player').src=lastWavUrl; $('player').play().catch(()=>{});
    lastMeta=body; $('save').disabled=false;
    $('msg').textContent='✓ 生成しました（'+body.voice+'）'; $('msg').className='msg ok';
  }catch(err){$('msg').textContent='✗ '+err.message; $('msg').className='msg err';}
  finally{btn.disabled=false;}
};
$('save').onclick=async()=>{
  if(!lastMeta)return; $('msg').textContent='保存中…'; $('msg').className='msg';
  const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(lastMeta)});
  const j=await r.json();
  if(r.ok){$('msg').textContent='💾 保存: '+j.file; $('msg').className='msg ok'; refreshSaved();}
  else{$('msg').textContent='✗ '+(j.error||'保存失敗'); $('msg').className='msg err';}
};
$('publish').onclick=async()=>{
  $('msg').textContent='公開ページへ反映中…'; $('msg').className='msg';
  const r=await fetch('/api/publish',{method:'POST'}); const j=await r.json();
  if(r.ok){$('msg').textContent='🌐 '+j.message; $('msg').className='msg ok';}
  else{$('msg').textContent='✗ '+(j.error||'失敗'); $('msg').className='msg err';}
};
refreshSaved();
</script></body></html>"""
    return html.replace("__DATA__", data).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静かに
        pass

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = _page()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/saved":
            items = []
            slug2ch = {i["slug"]: c for c, i in CHARACTERS.items()}
            for wav in sorted(OUT_DIR.glob("*.wav")):
                stem = wav.stem
                ch = next((c for s, c in slug2ch.items() if stem.startswith(s + "_")), "?")
                voice = stem.split("_")[-1]
                items.append({"file": wav.name, "label": f"{ch} / {voice}"})
            self._json(200, {"items": items})
        elif self.path.startswith("/samples/"):
            fp = OUT_DIR / self.path[len("/samples/"):]
            if fp.exists() and fp.suffix == ".wav" and fp.parent == OUT_DIR:
                data = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._json(404, {"error": "not found"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        key = load_env_key()
        if self.path == "/api/gen":
            if not key:
                return self._json(401, {"error": ".env の GEMINI_API_KEY が未設定です"})
            try:
                p = self._read_json()
                wav = generate_tts(key, p.get("model") or MODELS[0], p["voice"],
                                   p.get("text", ""), p.get("style", ""), insecure_ssl=True)
                self.send_response(200)
                self.send_header("Content-Type", "audio/wav")
                self.send_header("Content-Length", str(len(wav)))
                self.end_headers()
                self.wfile.write(wav)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "RESOURCE_EXHAUSTED" in msg and "per" in msg.lower():
                    msg = "レート上限(10回/分)です。1分ほど待って再実行してください。"
                elif "RESOURCE_EXHAUSTED" in msg:
                    msg = "前払い残高が不足しています(429)。"
                self._json(500, {"error": msg[:200]})
        elif self.path == "/api/save":
            try:
                p = self._read_json()
                if not key:
                    return self._json(401, {"error": ".env の GEMINI_API_KEY が未設定です"})
                slug = CHARACTERS.get(p.get("character"), {}).get("slug") or "custom"
                fname = f"{slug}_{p['voice']}.wav"
                wav = generate_tts(key, p.get("model") or MODELS[0], p["voice"],
                                   p.get("text", ""), p.get("style", ""), insecure_ssl=True)
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                (OUT_DIR / fname).write_bytes(wav)
                self._json(200, {"file": fname})
            except Exception as e:  # noqa: BLE001
                self._json(500, {"error": str(e)[:200]})
        elif self.path == "/api/publish":
            try:
                import shutil
                from gen_voice_samples import build_index_html, scan_existing_results
                results = scan_existing_results()
                (OUT_DIR / "index.html").write_text(build_index_html(results), encoding="utf-8")
                n = 0
                for dest in (REPO.parent / "site" / "voice_samples",
                             REPO.parent / "13th-register-kamishibai" / "voice_samples"):
                    dest.mkdir(parents=True, exist_ok=True)
                    for f in OUT_DIR.glob("*"):
                        if f.suffix in (".wav", ".html"):
                            shutil.copy2(f, dest / f.name)
                            n += 1
                self._json(200, {"message": f"{len(results)}本をミラーへ反映。git add/commit/push は手動で。"})
            except Exception as e:  # noqa: BLE001
                self._json(500, {"error": str(e)[:200]})
        else:
            self._json(404, {"error": "not found"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()
    if not load_env_key():
        print("警告: .env の GEMINI_API_KEY が未設定です。", file=sys.stderr)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"声ラボ起動: http://127.0.0.1:{args.port}  (Ctrl+C で停止)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Gemini(Cloud TTS)対応 声・セリフ・トーン レビューアプリ。
各行のキャラ声/テキスト/トーン(prompt)/モデルを変えて、その場で生成・再生できる。
使い方: python voice_review_server.py [port]   → http://localhost:8020/
"""
import http.server, socketserver, json, io, sys, os, wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud_tts
import yaml

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8020
TOOLS = Path(__file__).resolve().parent
ANIME = TOOLS.parent
CODEX = Path(r"C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages")  # OneDrive離脱: Codex正本
SCENE = CODEX / "13th-register-kamishibai" / "scene_manifest.json"
VOICES_YAML = ANIME / "voices.yaml"
OVR_PATH = TOOLS / "ep01_reading_overrides.json"
TSUKKOMI_PATH = TOOLS / "ep01_takumi_tsukkomi.json"   # タクミのツッコミ行id一覧


def takumi_data():
    sm = json.load(open(SCENE, encoding="utf-8"))
    lines = [{"id": x["id"], "text": x.get("dialogue", "")} for x in sm if x["speaker"] == "タクミ"]
    sel = json.load(open(TSUKKOMI_PATH, encoding="utf-8")) if TSUKKOMI_PATH.exists() else []
    return {"lines": lines, "tsukkomi": sel}

# Gemini TTS 30声(ラベル=トーン傾向)
VOICES = [
    ("Zephyr", "明るい"), ("Puck", "元気"), ("Charon", "低め情報的"), ("Kore", "硬め中立"),
    ("Fenrir", "快活"), ("Leda", "若々しい"), ("Orus", "硬め"), ("Aoede", "軽やか"),
    ("Callirrhoe", "おっとり"), ("Autonoe", "明るい"), ("Enceladus", "息混じり低"), ("Iapetus", "クリア"),
    ("Umbriel", "落ち着き"), ("Algieba", "滑らか低"), ("Despina", "滑らか"), ("Erinome", "クリア"),
    ("Algenib", "しゃがれ"), ("Rasalgethi", "低め説明"), ("Laomedeia", "アップビート"), ("Achernar", "柔らか"),
    ("Alnilam", "硬め低"), ("Schedar", "均一"), ("Gacrux", "成熟"), ("Pulcherrima", "前向き"),
    ("Achird", "親しみ"), ("Zubenelgenubi", "カジュアル低"), ("Vindemiatrix", "優しい"),
    ("Sadachbia", "生き生き"), ("Sadaltager", "知的"), ("Sulafat", "温かい"),
]
MODELS = ["gemini-2.5-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-tts"]

# 体感ベースの性別分類(公式は男女明記なし。最終判断は耳で)。女=F/男=M/中性=N。
GENDER = {
    "Zephyr": "F", "Puck": "M", "Charon": "M", "Kore": "F", "Fenrir": "M",
    "Leda": "F", "Orus": "M", "Aoede": "F", "Callirrhoe": "F", "Autonoe": "F",
    "Enceladus": "M", "Iapetus": "M", "Umbriel": "M", "Algieba": "M", "Despina": "F",
    "Erinome": "F", "Algenib": "M", "Rasalgethi": "M", "Laomedeia": "F", "Achernar": "F",
    "Alnilam": "M", "Schedar": "M", "Gacrux": "N", "Pulcherrima": "F", "Achird": "M",
    "Zubenelgenubi": "M", "Vindemiatrix": "F", "Sadachbia": "N", "Sadaltager": "M", "Sulafat": "F",
}
GENDER_JA = {"F": "女", "M": "男", "N": "中性/要確認"}
# 本作キャスト(声→キャラ)
CAST = {"Charon": "ナレーション", "Achird": "タクミ", "Leda": "エリ", "Enceladus": "汗田竜司",
        "Umbriel": "第十三レジ", "Despina": "ナビ", "Iapetus": "未来の会社員", "Algieba": "座木山辰哉",
        "Algenib": "唐沢栄治", "Orus": "トラック運転手"}


def load_init():
    sm = json.load(open(SCENE, encoding="utf-8"))
    chars = yaml.safe_load(open(VOICES_YAML, encoding="utf-8"))["characters"]
    ovr = json.load(open(OVR_PATH, encoding="utf-8")) if OVR_PATH.exists() else {}
    char_voice = {c: chars[c].get("voice", "") for c in chars}
    fb = {"レシート": "第十三レジ"}
    lines = []
    for x in sm:
        sp = x["speaker"]; ch = sp if sp in char_voice else fb.get(sp, sp)
        # 今合成に使われている漢字セリフ(オーバーライドがあればそれ、無ければ原文)
        synth = ovr.get(x["id"], x.get("dialogue", ""))
        lines.append({"id": x["id"], "speaker": sp,
                      "voice": char_voice.get(ch, "Charon"),
                      "text": synth,
                      "dialogue": x.get("dialogue", "")})
    return {"lines": lines, "charVoice": char_voice,
            "voices": VOICES, "models": MODELS,
            "genders": GENDER, "genderJa": GENDER_JA, "cast": CAST}


def pcm_to_wav(pcm, fr):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fr); w.writeframes(pcm)
    return b.getvalue()


HTML = """<!doctype html><html lang=ja><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>声・セリフ・トーン レビュー (Gemini/Cloud TTS)</title>
<style>
*{box-sizing:border-box} body{font-family:system-ui,sans-serif;background:#101216;color:#e8e8ea;margin:0;padding:0 0 60px}
header{position:sticky;top:0;background:#161922;border-bottom:1px solid #2a2f3a;padding:10px 14px;z-index:5}
h1{font-size:16px;margin:0 0 6px} .muted{color:#8a92a0;font-size:12px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
select,input,textarea,button{font:inherit;background:#1d212b;color:#e8e8ea;border:1px solid #333a47;border-radius:7px;padding:6px 8px}
button{cursor:pointer;background:#2a3340;border-color:#3a4658} button.go{background:#2f6df6;border-color:#2f6df6}
button:disabled{opacity:.5;cursor:wait}
.charbar{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}
.chip{display:flex;align-items:center;gap:4px;background:#1d212b;border:1px solid #333a47;border-radius:20px;padding:3px 6px 3px 10px;font-size:12px}
.chip b{color:#7fc6ff}
main{padding:12px 14px;max-width:980px;margin:0 auto}
.line{background:#161922;border:1px solid #262b36;border-radius:10px;padding:10px;margin:8px 0}
.line .head{display:flex;gap:8px;align-items:center;margin-bottom:6px}
.badge{font-size:11px;padding:2px 8px;border-radius:12px;background:#243047;color:#9cc4ff}
.line textarea{width:100%;min-height:38px;resize:vertical}
.ctl{display:grid;grid-template-columns:140px 1fr 150px auto;gap:8px;align-items:center;margin-top:6px}
.ctl label{font-size:11px;color:#8a92a0}
audio{height:34px}
.small{font-size:11px;color:#8a92a0}
.note{color:#ffd479}
.idtag{font-size:11px;color:#6b7280;font-family:monospace}
</style>
<header>
  <h1>声・セリフ・トーン レビュー <span class=muted>Gemini / Cloud TTS（日次制限なし）</span> · <a href="/gallery" style="color:#7fc6ff">声ギャラリー(男女表)→</a></h1>
  <div class=row>
    <label class=muted>モデル(既定)</label><select id=gmodel></select>
    <label class=muted>トーン(全体)</label><input id=gtone placeholder="例: 淡々と / 明るく元気に" size=24>
    <button id=genprompt class=go style="background:#2f6df6;border-color:#2f6df6">変更プロンプト生成</button>
    <span id=status class=muted></span>
  </div>
  <div class=charbar id=charbar></div>
  <div class=small>キャラの声を変えると、その話者の全行のデフォルト声が変わります。各行は個別に上書き可。</div>
</header>
<main id=list></main>
<div id=modal style="display:none;position:fixed;inset:0;background:#000a;z-index:20;padding:16px">
  <div style="max-width:760px;margin:16px auto;background:#161922;border:1px solid #333a47;border-radius:10px;padding:14px">
    <h3 style="margin:0 0 8px">変更プロンプト（コピーしてClaudeへ貼り付け）</h3>
    <textarea id=promptOut style="width:100%;height:300px;font-size:13px"></textarea>
    <div style="margin-top:8px;display:flex;gap:8px">
      <button class=go onclick="navigator.clipboard.writeText($('#promptOut').value);this.textContent='コピーした'">コピー</button>
      <button onclick="$('#modal').style.display='none'">閉じる</button>
    </div>
  </div>
</div>
<script>
let DATA=null;
const $=s=>document.querySelector(s);
async function init(){
  DATA=await (await fetch('/api/init')).json();
  const gm=$('#gmodel'); DATA.models.forEach(m=>gm.add(new Option(m,m)));
  renderChars(); renderLines();
  $('#genprompt').onclick=genPrompt;
}
function genPrompt(){
  const rows=document.querySelectorAll('.line'); const ch=[];
  DATA.lines.forEach((ln,i)=>{
    const cur=rows[i].querySelector('.tx').value.trim();
    if(cur!==(ln.text||'').trim()) ch.push({id:ln.id,sp:ln.speaker,o:ln.text,n:cur});
  });
  if(!ch.length){ $('#status').textContent='変更なし'; return; }
  let p='# EP01 セリフ変更依頼\\n以下の行を変更し、音声も再生成してください。\\n\\n';
  ch.forEach(c=>{ p+=`- ${c.id}（${c.sp}）\\n  旧: ${c.o}\\n  新: ${c.n}\\n\\n`; });
  $('#promptOut').value=p; $('#modal').style.display='block';
}
function voiceOptions(sel){
  return DATA.voices.map(([v,t])=>`<option value="${v}" ${v===sel?'selected':''}>${v} (${t})</option>`).join('');
}
function renderChars(){
  const cb=$('#charbar'); cb.innerHTML='';
  Object.entries(DATA.charVoice).forEach(([ch,v])=>{
    const d=document.createElement('div'); d.className='chip';
    d.innerHTML=`<b>${ch}</b><select data-char="${ch}">${voiceOptions(v)}</select>`;
    d.querySelector('select').onchange=e=>{
      DATA.charVoice[ch]=e.target.value;
      document.querySelectorAll(`select.lv[data-sp="${ch}"]`).forEach(s=>{ if(!s.dataset.touched) s.value=e.target.value; });
    };
    cb.appendChild(d);
  });
}
function renderLines(){
  const L=$('#list'); L.innerHTML='';
  DATA.lines.forEach(ln=>{
    const sp=ln.speaker, cv=DATA.charVoice[sp]||ln.voice;
    const el=document.createElement('div'); el.className='line';
    el.innerHTML=`
      <div class=head><span class=badge>${sp}</span><span class=idtag>${ln.id}</span>
        <span class=small>原文: ${ln.dialogue||''}</span></div>
      <textarea class=tx>${ln.text||''}</textarea>
      <div class=ctl>
        <select class=lv data-sp="${sp}">${voiceOptions(cv)}</select>
        <input class=tone placeholder="トーン(prompt) 任意">
        <select class=lm><option value="">(既定モデル)</option>${DATA.models.map(m=>`<option>${m}</option>`).join('')}</select>
        <button class=go>生成▶</button>
      </div>
      <div class=player style="margin-top:6px"></div>`;
    el.querySelector('.lv').addEventListener('change',e=>e.target.dataset.touched='1');
    el.querySelector('.go').onclick=()=>gen(el,ln);
    L.appendChild(el);
  });
}
async function gen(el,ln){
  const btn=el.querySelector('.go'); const pl=el.querySelector('.player');
  const text=el.querySelector('.tx').value.trim();
  const voice=el.querySelector('.lv').value;
  const tone=el.querySelector('.tone').value.trim() || $('#gtone').value.trim();
  const model=el.querySelector('.lm').value || $('#gmodel').value;
  btn.disabled=true; btn.textContent='生成中…'; pl.innerHTML='<span class=small>合成中（分上限時は最大35秒待機）…</span>';
  try{
    const r=await fetch('/api/synth',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text,voice,model,prompt:tone})});
    if(!r.ok){ pl.innerHTML='<span class=note>失敗: '+(await r.text()).slice(0,160)+'</span>'; }
    else{
      const blob=await r.blob(); const url=URL.createObjectURL(blob);
      pl.innerHTML=`<audio controls autoplay src="${url}"></audio> <span class=small>${voice} / ${model}${tone?' / 「'+tone+'」':''}</span>`;
    }
  }catch(e){ pl.innerHTML='<span class=note>エラー: '+e+'</span>'; }
  btn.disabled=false; btn.textContent='生成▶';
}
init();
</script>
</html>"""


GALLERY_HTML = """<!doctype html><html lang=ja><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>声ギャラリー（男女・トーン一覧 / Gemini Cloud TTS）</title>
<style>
*{box-sizing:border-box} body{font-family:system-ui,sans-serif;background:#101216;color:#e8e8ea;margin:0;padding:0 0 60px}
header{position:sticky;top:0;background:#161922;border-bottom:1px solid #2a2f3a;padding:10px 14px;z-index:5}
h1{font-size:16px;margin:0 0 6px} .muted{color:#8a92a0;font-size:12px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
input,select,button{font:inherit;background:#1d212b;color:#e8e8ea;border:1px solid #333a47;border-radius:7px;padding:6px 8px}
button{cursor:pointer} button:disabled{opacity:.5}
main{padding:12px 14px;max-width:980px;margin:0 auto}
h2{font-size:14px;margin:18px 0 6px;color:#9cc4ff}
table{width:100%;border-collapse:collapse} td,th{border-bottom:1px solid #232833;padding:7px 6px;text-align:left;font-size:13px;vertical-align:middle}
th{color:#8a92a0;font-weight:600}
.g-F{color:#ff9ec4} .g-M{color:#7fc6ff} .g-N{color:#ffd479}
.tone{color:#9aa3b2;font-size:12px} .cast{color:#7fe0a0;font-size:12px}
.play{background:#2a3340;border-color:#3a4658} a{color:#7fc6ff}
audio{height:30px;vertical-align:middle}
</style>
<header>
  <h1>声ギャラリー <span class=muted>男女・トーン一覧（体感ベース／耳で要確認）</span> · <a href="/">← レビューに戻る</a></h1>
  <div class=row>
    <label class=muted>試聴セリフ</label><input id=line size=30 value="第十三レジ。ただいま営業中。">
    <label class=muted>モデル</label><select id=model></select>
    <span class=muted>♀<span class=g-F>女</span> / ♂<span class=g-M>男</span> / <span class=g-N>中性</span></span>
  </div>
</header>
<main id=main></main>
<script>
let D=null; const $=s=>document.querySelector(s);
async function init(){
  D=await (await fetch('/api/init')).json();
  const m=$('#model'); D.models.forEach(x=>m.add(new Option(x,x)));
  render();
}
function render(){
  const order={F:0,M:1,N:2};
  const rows=D.voices.map(([v,t])=>({v,t,g:D.genders[v]||'N',cast:D.cast[v]||''}));
  const groups={F:[],M:[],N:[]}; rows.forEach(r=>groups[r.g].push(r));
  const titles={F:'女性ボイス',M:'男性ボイス',N:'中性/要確認'};
  let html='';
  ['F','M','N'].forEach(g=>{
    if(!groups[g].length) return;
    html+=`<h2>${titles[g]}（${groups[g].length}）</h2><table><tr><th>声</th><th>性別</th><th>トーン</th><th>本作キャスト</th><th>試聴</th></tr>`;
    groups[g].forEach(r=>{
      html+=`<tr><td><b>${r.v}</b></td><td class="g-${r.g}">${D.genderJa[r.g]}</td>
        <td class=tone>${r.t}</td><td class=cast>${r.cast||'—'}</td>
        <td><button class=play data-v="${r.v}">▶ 試聴</button> <span class=pl></span></td></tr>`;
    });
    html+='</table>';
  });
  $('#main').innerHTML=html;
  document.querySelectorAll('button.play').forEach(b=>b.onclick=()=>play(b));
}
async function play(b){
  const v=b.dataset.v, pl=b.parentElement.querySelector('.pl');
  b.disabled=true; const o=b.textContent; b.textContent='生成中…';
  try{
    const r=await fetch('/api/synth',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text:$('#line').value,voice:v,model:$('#model').value,prompt:''})});
    if(r.ok){ const u=URL.createObjectURL(await r.blob()); pl.innerHTML=`<audio controls autoplay src="${u}"></audio>`; }
    else pl.textContent='失敗';
  }catch(e){ pl.textContent='エラー'; }
  b.disabled=false; b.textContent=o;
}
init();
</script></html>"""


TAKUMI_HTML = """<!doctype html><html lang=ja><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>タクミ ツッコミ判定</title>
<style>
*{box-sizing:border-box} body{font-family:system-ui,sans-serif;background:#101216;color:#e8e8ea;margin:0;padding:0 0 80px}
header{position:sticky;top:0;background:#161922;border-bottom:1px solid #2a2f3a;padding:10px 14px;z-index:5}
h1{font-size:16px;margin:0 0 6px} .muted{color:#8a92a0;font-size:12px}
.bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
button{font:inherit;cursor:pointer;background:#2a3340;color:#e8e8ea;border:1px solid #3a4658;border-radius:7px;padding:7px 12px}
button.save{background:#2f6df6;border-color:#2f6df6} button:disabled{opacity:.5}
main{padding:10px 14px;max-width:820px;margin:0 auto}
.row{display:flex;gap:10px;align-items:flex-start;background:#161922;border:1px solid #262b36;border-radius:8px;padding:9px 11px;margin:6px 0;cursor:pointer}
.row.on{background:#1e2b1e;border-color:#3a6b3a}
.row input{width:20px;height:20px;margin-top:2px;flex:none}
.idtag{font-size:11px;color:#6b7280;font-family:monospace;flex:none;width:64px}
.tx{font-size:14px}
.cnt{color:#ff9ec4;font-weight:600}
a{color:#7fc6ff}
</style>
<header>
  <h1>タクミ ツッコミ判定 <span class=muted>チェック＝「！！」＋「ツッコミ気味で」適用</span> · <a href="/">← 戻る</a></h1>
  <div class=bar>
    <button id=all type=button>全選択</button>
    <button id=none type=button>全解除</button>
    <span class=muted>選択中 <span id=cnt class=cnt>0</span> / <span id=tot></span> 行</span>
    <button id=save class=save type=button>保存</button>
    <span id=status class=muted></span>
  </div>
</header>
<main id=list></main>
<script>
let D=null;
const $=s=>document.querySelector(s);
async function init(){
  D=await (await fetch('/api/takumi')).json();
  const sel=new Set(D.tsukkomi);
  $('#tot').textContent=D.lines.length;
  const L=$('#list'); L.innerHTML='';
  D.lines.forEach(ln=>{
    const on=sel.has(ln.id);
    const el=document.createElement('label'); el.className='row'+(on?' on':'');
    el.innerHTML=`<input type=checkbox ${on?'checked':''} data-id="${ln.id}"><span class=idtag>${ln.id.replace('ep01_','')}</span><span class=tx>${ln.text}</span>`;
    const cb=el.querySelector('input');
    cb.addEventListener('change',()=>{ el.classList.toggle('on',cb.checked); updcnt(); });
    L.appendChild(el);
  });
  updcnt();
  $('#all').onclick=()=>{document.querySelectorAll('#list input').forEach(c=>{c.checked=true;c.closest('.row').classList.add('on')});updcnt();};
  $('#none').onclick=()=>{document.querySelectorAll('#list input').forEach(c=>{c.checked=false;c.closest('.row').classList.remove('on')});updcnt();};
  $('#save').onclick=save;
}
function updcnt(){ $('#cnt').textContent=document.querySelectorAll('#list input:checked').length; }
async function save(){
  const ids=[...document.querySelectorAll('#list input:checked')].map(c=>c.dataset.id);
  $('#save').disabled=true; $('#status').textContent='保存中…';
  const r=await fetch('/api/save_tsukkomi',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tsukkomi:ids})});
  $('#status').textContent = r.ok ? `保存しました（${ids.length}行）。Claudeに「保存した」と伝えてください。` : '保存失敗';
  $('#save').disabled=false;
}
init();
</script></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, HTML, "text/html; charset=utf-8")
        elif self.path.startswith("/gallery"):
            self._send(200, GALLERY_HTML, "text/html; charset=utf-8")
        elif self.path.startswith("/takumi"):
            self._send(200, TAKUMI_HTML, "text/html; charset=utf-8")
        elif self.path == "/api/takumi":
            self._send(200, json.dumps(takumi_data(), ensure_ascii=False))
        elif self.path == "/api/init":
            self._send(200, json.dumps(load_init(), ensure_ascii=False))
        else:
            self._send(404, "{}")

    def do_POST(self):
        if self.path == "/api/save_tsukkomi":
            n = int(self.headers.get("Content-Length", 0))
            try:
                req = json.loads((self.rfile.read(n) or b"{}").decode("utf-8"))
            except Exception:
                self._send(400, "parse失敗", "text/plain; charset=utf-8"); return
            ids = [str(x) for x in req.get("tsukkomi", [])]
            json.dump(ids, open(TSUKKOMI_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            self._send(200, json.dumps({"saved": len(ids)})); return
        if self.path != "/api/synth":
            self._send(404, "{}"); return
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n) or b"{}"
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send(400, "JSON parse失敗(UTF-8で送ってください)", "text/plain; charset=utf-8"); return
        text = (req.get("text") or "").strip()
        voice = req.get("voice") or "Charon"
        model = req.get("model") or "gemini-2.5-flash-tts"
        prompt = (req.get("prompt") or "").strip()
        if not text:
            self._send(400, "text空"); return
        try:
            pcm, fr = cloud_tts.synth_safe(text, voice, model=model, prompt=prompt)
            self._send(200, pcm_to_wav(pcm, fr), "audio/wav")
        except Exception as e:
            self._send(500, str(e)[:300], "text/plain; charset=utf-8")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"声レビューアプリ起動: http://localhost:{PORT}/", flush=True)
    httpd.serve_forever()

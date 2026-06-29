# -*- coding: utf-8 -*-
"""AivisSpeech キャラ別 声/テンポ調整アプリ。
各キャラの 話者/スタイル・速度/抑揚/テンポ/ピッチ/音量/前後無音 を調整して
その場で試聴し、cast CSV(ep01_voice_cast.csv)に保存できる。
使い方: python aivis_tuner_server.py [port]  (AivisSpeechエンジン10101起動必須)
"""
import http.server, json, io, sys, csv, time, urllib.parse, urllib.request, wave
from pathlib import Path

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8030
API = "http://127.0.0.1:10101"
TOOLS = Path(__file__).resolve().parent
CAST_CSV = TOOLS / "ep01_voice_cast.csv"
VOICES_YAML = TOOLS.parent / "voices.yaml"
PARAM_KEYS = ("speedScale", "intonationScale", "tempoDynamicsScale", "pitchScale",
              "volumeScale", "prePhonemeLength", "postPhonemeLength")
# スライダー範囲 (min, max, step, 既定)
RANGES = {
    "speedScale": (0.5, 2.0, 0.01, 1.0), "intonationScale": (0.0, 2.0, 0.01, 1.0),
    "tempoDynamicsScale": (0.0, 2.0, 0.01, 1.0), "pitchScale": (-0.15, 0.15, 0.005, 0.0),
    "volumeScale": (0.0, 2.0, 0.01, 1.0), "prePhonemeLength": (0.0, 1.5, 0.01, 0.1),
    "postPhonemeLength": (0.0, 1.5, 0.01, 0.1),
}
PARAM_JA = {"speedScale": "速度", "intonationScale": "抑揚", "tempoDynamicsScale": "テンポ緩急",
            "pitchScale": "ピッチ", "volumeScale": "音量", "prePhonemeLength": "前の無音",
            "postPhonemeLength": "後の無音"}


def post(url, payload=None, attempts=5):
    # バッチ再生成等とエンジン(10101)を取り合うと接続リセット(WinError 10054)が出るため
    # 指数バックオフでリトライして弾かれを吸収する。
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    last = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, data=data, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            last = e; time.sleep(0.6 * (i + 1))
    raise last


def audio_query(text, sid):
    return json.loads(post(f"{API}/audio_query?{urllib.parse.urlencode({'text': text, 'speaker': sid})}").decode("utf-8"))


def synth(query, sid):
    return post(f"{API}/synthesis?{urllib.parse.urlencode({'speaker': sid})}", query)


def load_cast():
    return list(csv.DictReader(io.open(CAST_CSV, encoding="utf-8-sig")))


def speaker_list():
    sp = json.loads(urllib.request.urlopen(f"{API}/speakers", timeout=20).read())
    flat = []
    for s in sp:
        for st in s["styles"]:
            flat.append({"label": f"{s['name']} / {st['name']}", "id": st["id"],
                         "speaker": s["name"], "style": st["name"]})
    return flat


def default_lines():
    try:
        import yaml
        v = yaml.safe_load(open(VOICES_YAML, encoding="utf-8"))["characters"]
        return {k: c.get("line", "") for k, c in v.items()}
    except Exception:
        return {}


HTML = """<!doctype html><html lang=ja><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>AivisSpeech 声/テンポ調整</title>
<style>
*{box-sizing:border-box} body{font-family:system-ui,sans-serif;background:#101216;color:#e8e8ea;margin:0;padding:0 0 40px}
header{position:sticky;top:0;background:#161922;border-bottom:1px solid #2a2f3a;padding:12px 14px;z-index:5}
h1{font-size:16px;margin:0 0 8px}
select,input,textarea,button{font:inherit;background:#1d212b;color:#e8e8ea;border:1px solid #333a47;border-radius:7px;padding:7px 9px}
button{cursor:pointer;background:#2a3340;border-color:#3a4658} button.go{background:#2f6df6;border-color:#2f6df6} button.save{background:#2f9e5a;border-color:#2f9e5a}
button:disabled{opacity:.5}
main{padding:14px;max-width:720px;margin:0 auto}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:6px 0}
.row label{min-width:84px;font-size:13px;color:#9cc4ff}
.slider{display:grid;grid-template-columns:90px 1fr 64px;gap:10px;align-items:center;margin:8px 0}
.slider .nm{font-size:13px;color:#9aa3b2} .slider input[type=range]{width:100%} .slider .val{font-family:monospace;text-align:right;color:#7fc6ff}
.muted{color:#8a92a0;font-size:12px} audio{width:100%;margin-top:8px}
.bar{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
#status{color:#ffd479;font-size:12px}
</style>
<header>
  <h1>AivisSpeech 声/テンポ 調整 <span class=muted>キャラ別に試聴→cast CSV保存</span></h1>
  <div class=row>
    <label>キャラ</label><select id=char></select>
    <label>声/スタイル</label><select id=style style="max-width:260px"></select>
  </div>
</header>
<main>
  <div id=sliders></div>
  <div class=row><label>試聴セリフ</label><textarea id=text style="flex:1;min-height:44px"></textarea></div>
  <div class=bar>
    <button id=gen class=go>生成して再生 ▶</button>
    <button id=reset>このキャラの保存値に戻す</button>
    <button id=save class=save>cast CSVに保存</button>
    <span id=status></span>
  </div>
  <div id=player></div>
</main>
<script>
let D=null, CUR=null;
const $=s=>document.querySelector(s);
const PKEYS=["speedScale","intonationScale","tempoDynamicsScale","pitchScale","volumeScale","prePhonemeLength","postPhonemeLength"];
const PJA={speedScale:"速度",intonationScale:"抑揚",tempoDynamicsScale:"テンポ緩急",pitchScale:"ピッチ",volumeScale:"音量",prePhonemeLength:"前の無音",postPhonemeLength:"後の無音"};
async function init(){
  D=await (await fetch('/api/init')).json();
  const cs=$('#char'); D.cast.forEach(c=>cs.add(new Option(c.character,c.character)));
  const ss=$('#style'); D.speakers.forEach(s=>ss.add(new Option(s.label,s.id)));
  buildSliders();
  cs.onchange=loadChar; loadChar();
  $('#gen').onclick=gen; $('#save').onclick=save; $('#reset').onclick=loadChar;
}
function buildSliders(){
  const box=$('#sliders'); box.innerHTML='';
  for(const k of PKEYS){ const r=D.ranges[k];
    box.insertAdjacentHTML('beforeend',
      `<div class=slider><span class=nm>${PJA[k]}</span>
       <input type=range id=s_${k} min=${r[0]} max=${r[1]} step=${r[2]}>
       <span class=val id=v_${k}></span></div>`);
    const sl=$('#s_'+k); sl.oninput=()=>$('#v_'+k).textContent=(+sl.value).toFixed(3);
  }
}
function curCast(){ return D.cast.find(c=>c.character===$('#char').value); }
function loadChar(){
  const c=curCast(); CUR=c;
  $('#style').value=c.style_id;
  for(const k of PKEYS){ $('#s_'+k).value=c[k]; $('#v_'+k).textContent=(+c[k]).toFixed(3); }
  $('#text').value=(D.lines[c.character]||'これはテスト音声です。');
  $('#status').textContent='';
}
function getParams(){ const p={}; for(const k of PKEYS) p[k]=+$('#s_'+k).value; return p; }
async function gen(){
  const sid=+$('#style').value, text=$('#text').value.trim(), params=getParams();
  $('#gen').disabled=true; $('#player').innerHTML='<span class=muted>合成中…</span>';
  try{
    const r=await fetch('/api/synth',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({style_id:sid,text,params})});
    if(r.ok){ const u=URL.createObjectURL(await r.blob()); $('#player').innerHTML=`<audio controls autoplay src="${u}"></audio>`; }
    else $('#player').innerHTML='<span style=color:#ff9ec4>失敗: '+(await r.text()).slice(0,120)+'</span>';
  }catch(e){ $('#player').innerHTML='<span style=color:#ff9ec4>エラー(エンジン起動?): '+e+'</span>'; }
  $('#gen').disabled=false;
}
async function save(){
  const ss=$('#style'), sid=+ss.value, opt=ss.options[ss.selectedIndex].text;
  const [sp,st]=opt.split(' / ');
  const body={character:$('#char').value, speaker_name:sp, style_name:st, style_id:sid, params:getParams()};
  $('#save').disabled=true; $('#status').textContent='保存中…';
  const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(r.ok){ const c=curCast(); Object.assign(c,{speaker_name:sp,style_name:st,style_id:String(sid)}); for(const k of PKEYS) c[k]=String(getParams()[k]);
    $('#status').textContent='保存しました。次回の生成からこの設定が使われます。'; }
  else $('#status').textContent='保存失敗';
  $('#save').disabled=false;
}
init();
</script></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, HTML, "text/html; charset=utf-8")
        elif self.path == "/api/init":
            try:
                sp = speaker_list()
            except Exception as e:
                sp = []
            self._send(200, json.dumps({"cast": load_cast(), "speakers": sp,
                                        "ranges": RANGES, "lines": default_lines()}, ensure_ascii=False))
        else:
            self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads((self.rfile.read(n) or b"{}").decode("utf-8"))
        except Exception:
            self._send(400, "parse失敗", "text/plain; charset=utf-8"); return
        if self.path == "/api/synth":
            try:
                sid = int(req["style_id"]); text = (req.get("text") or "").strip() or "テスト。"
                q = audio_query(text, sid)
                for k, v in (req.get("params") or {}).items():
                    if k in PARAM_KEYS:
                        q[k] = float(v)
                q["outputSamplingRate"] = 24000; q["outputStereo"] = False
                self._send(200, synth(q, sid), "audio/wav")
            except Exception as e:
                self._send(500, str(e)[:200], "text/plain; charset=utf-8")
        elif self.path == "/api/save":
            try:
                rows = load_cast()
                ch = req["character"]; p = req.get("params") or {}
                for r in rows:
                    if r["character"] == ch:
                        r["speaker_name"] = req.get("speaker_name", r["speaker_name"])
                        r["style_name"] = req.get("style_name", r.get("style_name", ""))
                        r["style_id"] = str(req["style_id"])
                        for k in PARAM_KEYS:
                            if k in p:
                                r[k] = str(p[k])
                fields = list(rows[0].keys())
                with io.open(CAST_CSV, "w", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
                self._send(200, json.dumps({"saved": ch}))
            except Exception as e:
                self._send(500, str(e)[:200], "text/plain; charset=utf-8")
        else:
            self._send(404, "{}")

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"AivisSpeech調整アプリ: http://localhost:{PORT}/", flush=True)
    httpd.serve_forever()

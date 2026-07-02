# -*- coding: utf-8 -*-
"""EP01 を改訂版131行で AivisSpeech 再合成し、紙芝居データ一式を再生成する。

- ep01_revised.md(131行) を読み、確定カット境界で20カットへ割当
- AivisSpeech(127.0.0.1:10101) で各行を合成、連結wav + 各clip
- voice manifest / scene_manifest / visual_cut_plan(lineStart/End) を再構築
- 画像は確定済み20枚(plannedImage)を維持
出力は Codex / OneDrive の両リポコピー(13th-register-kamishibai と site)へ。
"""
from __future__ import annotations
import csv, io, json, re, time, urllib.parse, urllib.request, wave
from pathlib import Path

API = "http://127.0.0.1:10101"
RATE = 44100
PARAM_KEYS = ("speedScale","intonationScale","tempoDynamicsScale","pitchScale",
              "volumeScale","prePhonemeLength","postPhonemeLength")

ONEDRIVE = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ")
CODEX = Path(r"C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages")
REV_MD = CODEX / "anime-github-project" / "ep01_revised.md"  # OneDrive外の正本
CAST_CSV = CODEX / "anime-github-project" / "tools" / "ep01_voice_cast.csv"
CLIP_DIR = Path(r"C:\Users\qvf03\Documents\anime_clips") / "ep01_aivis" / "raw"  # OneDrive外
# (root, sub) の宛先 = Codexのみ(OneDriveは同期巻き戻し事故のため不使用)
DESTS = [(CODEX, s) for s in ("13th-register-kamishibai",)]  # siteミラー廃止(2026-07 棚卸し)

# 確定カット境界: 各カットの開始行(1始まり)。vc01..vc20  ※6行削除(v105,106,108,109,111,118)で再計算済=121行
CUT_START = [1, 3, 4, 28, 29, 35, 38, 50, 58, 62, 68, 72, 83, 89, 98, 106, 113, 115, 118, 118]
SPEAKER_FALLBACK = {"レシート": "第十三レジ"}
PAUSE = {"ナレーション":450, "第十三レジ":350}  # ms、その他は既定
# 行の直後に効果音wav(44.1kHz mono)を挿入。{line_id: wavパス}
SFX_AFTER = {"ep01_v029": Path(__file__).resolve().parent / "sfx_register.wav"}
def _sfx_pcm(p):
    with wave.open(str(p), "rb") as w:
        return w.readframes(w.getnframes())


def post(url, payload=None, attempts=4):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type":"application/json"} if payload is not None else {}
    last=None
    for i in range(attempts):
        try:
            req=urllib.request.Request(url, data=data, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r: return r.read()
        except Exception as e:
            last=e; time.sleep(1.0*(i+1))
    raise last


def audio_query(text, sid):
    return json.loads(post(f"{API}/audio_query?{urllib.parse.urlencode({'text':text,'speaker':sid})}").decode("utf-8"))

def synth(query, sid):
    return post(f"{API}/synthesis?{urllib.parse.urlencode({'speaker':sid})}", query)

def parse_lines():
    rows=[]
    for l in io.open(REV_MD, encoding="utf-8"):
        s=l.strip()
        if not s or s.startswith("#") or s.startswith(">"): continue
        m=re.match(r"^([^：:]{1,12})[：:](.+)$", s)
        if m:
            disp, _, read = m.group(2).strip().partition("｜")  # ｜以降=読み(発音優先)、無ければ表示=読み
            disp=disp.strip(); read=read.strip() or disp
            rows.append((m.group(1).strip(), disp, read))
    return rows

def cut_for(line_no):  # 1始まり行 -> (index1, vcId)
    idx=0
    for i,st in enumerate(CUT_START):
        if line_no>=st: idx=i
    return idx+1, f"vc{idx+1:02d}"


def main():
    cast={r["character"]:r for r in csv.DictReader(io.open(CAST_CSV, encoding="utf-8-sig"))}
    lines=parse_lines()
    assert len(lines)==120, f"想定120行≠{len(lines)}"
    CLIP_DIR.mkdir(parents=True, exist_ok=True)

    # 既存 visual_cut_plan(Codex版・新画像入り)を雛形に、lineStart/Endを更新
    vp=json.load(open(CODEX/"13th-register-kamishibai"/"visual_cut_plan.json", encoding="utf-8"))
    vp_by={c["visualCutId"]:c for c in vp}

    manifest=[]; clips=[]
    print(f"合成開始: {len(lines)}行", flush=True)
    for i,(sp,dialogue,reading) in enumerate(lines,1):
        ch = sp if sp in cast else SPEAKER_FALLBACK.get(sp, sp)
        info = cast.get(ch)
        if not info:
            print(f"  ★cast無し {sp}->skip", flush=True); continue
        sid=int(info["style_id"]); lid=f"ep01_v{i:03d}"
        cp=CLIP_DIR/f"{lid}.wav"
        if not cp.exists():   # 再開: 既存クリップは再利用(AivisSpeechは決定的=同一)
            q=audio_query(reading, sid)   # 合成は「読み」を使う(表示セリフとは別)
            for k in PARAM_KEYS: q[k]=float(info[k])
            q["outputSamplingRate"]=RATE; q["outputStereo"]=False
            cp.write_bytes(synth(q, sid))
        with wave.open(str(cp),"rb") as w:
            dur=w.getnframes()/float(w.getframerate()); pcm=w.readframes(w.getnframes())
        idx1,vc=cut_for(i)
        pause=PAUSE.get(ch,250)
        manifest.append({"id":lid,"cut":f"ep01_{i:03d}","visualCutId":vc,"character":ch,
            "speaker_name":info["speaker_name"],"style_name":info["style_name"],"style_id":info["style_id"],
            "text":dialogue,"synthesis_text":reading,"synthesis_source":"aivis_auto","pause_after_ms":pause,
            "duration":dur,"pcm":pcm})
        if i%20==0: print(f"  {i}/129", flush=True)
        time.sleep(0.2)

    # lineStart/End を更新(各vcの最小/最大行ID)
    for vc in vp_by:
        ids=[m["id"] for m in manifest if m["visualCutId"]==vc]
        if ids:
            vp_by[vc]["lineStart"]=ids[0]; vp_by[vc]["lineEnd"]=ids[-1]

    # 連結wav + scene_manifest(build_line_scene_manifest 準拠) を構築
    total=len(manifest); cursor=0.0; scenes=[]; full=bytearray()
    def log_for(ch,idx):
        base=[f"発話ログ　{idx:02d}/{total:02d}", f"担当　{ch}"]
        if ch=="エリ": return base+["声　中2 / ノーマル"]
        if ch=="第十三レジ": return base+["第十三レジ　応答中"]
        if "未来" in ch: return base+["未来案件　処理中"]
        if ch=="ナレーション": return base+["深夜帯　進行中"]
        return base+["本日の営業　継続中"]
    for vi,m in enumerate(manifest,1):
        start=cursor; end=cursor+m["duration"]
        full += m["pcm"]
        c=vp_by[m["visualCutId"]]
        planned=c["plannedImage"]; fb=c.get("fallbackImage","")
        img = planned if (CODEX/"13th-register-kamishibai"/planned).exists() else fb
        scenes.append({"id":m["id"],"cut":m["cut"],"visualCutId":m["visualCutId"],
            "visualCutTitle":c.get("title",""),"visualCutIndex":c.get("index",0) or (int(m["visualCutId"][2:])),
            "start":round(start,3),"end":round(end,3),"image":img,"plannedImage":planned,
            "fallbackImage":fb,"imagePrompt":c.get("prompt",""),"speaker":m["character"],
            "dialogue":m["text"],"reading":m["synthesis_text"],"log":log_for(m["character"],vi),
            "visualLabel":f"{int(m['visualCutId'][2:]):02d}/20　{c.get('title','')}",
            "progressLabel":f"{vi:02d}/{total:02d}　{m['character']}"})
        cursor=end
        if m["pause_after_ms"]>0:
            sil=b"\x00\x00"*int(RATE*m["pause_after_ms"]/1000); full+=sil; cursor+=m["pause_after_ms"]/1000.0
        if m["id"] in SFX_AFTER and SFX_AFTER[m["id"]].exists():
            sfx=_sfx_pcm(SFX_AFTER[m["id"]]); full+=sfx; cursor+=len(sfx)/2/RATE

    # voice manifest(pcm除く)
    vman=[{k:v for k,v in m.items() if k not in ("pcm","duration")} | {"clip":f"outputs/ep01_revised_aivis/raw/{m['id']}.wav"} for m in manifest]

    # 連結wavバイト列を作成
    import io as _io
    buf=_io.BytesIO()
    with wave.open(buf,"wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(RATE); o.writeframes(bytes(full))
    wav_bytes=buf.getvalue()

    # 4宛先へ書き出し
    for root,sub in DESTS:
        base=root/sub
        (base/"assets").mkdir(parents=True, exist_ok=True)
        (base/"assets"/"ep01_full_voice_reading_hiragana_mina_mao.wav").write_bytes(wav_bytes)
        json.dump(vman, open(base/"assets"/"manifest_reading_hiragana_mina_mao.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(vp, open(base/"visual_cut_plan.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(scenes, open(base/"scene_manifest.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  書込: {root.name}/{sub}", flush=True)

    print(f"完了: {len(scenes)}行 / 総尺 {cursor:.1f}s / wav {len(wav_bytes)//1024}KB", flush=True)

if __name__=="__main__":
    main()

# -*- coding: utf-8 -*-
"""第十三レジ エピソードスタジオ — セルフ紙芝居制作サーバー。
スマホ/PCのブラウザから: 台本アップロード → カット割り編集 → 読み編集 →
音声生成(一括/個別・エンジン自動再起動付き) → プレイヤー反映 → YouTube動画生成 → gh-pages公開。

起動:  python episode_studio_server.py            (0.0.0.0:8040)
       set STUDIO_PIN=1234 で簡易PIN認証を有効化(Tailscale外へ晒す場合)
前提:  AivisSpeechエンジン(127.0.0.1:10101)。落ちていれば自動起動を試みる。
"""
import csv, io, json, os, re, subprocess, sys, threading, time, urllib.parse, urllib.request, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parents[1]                      # project_mana_gh_pages
KAMI = ROOT / "13th-register-kamishibai"
PLANNED = KAMI / "assets" / "scenes" / "planned"
VIDEO_DIR = ROOT / "video"
DOCS = TOOLS.parent                          # anime-github-project
CLIP_BASE = Path(r"C:\Users\qvf03\Documents\anime_clips")
CAST_CSV = TOOLS / "ep01_voice_cast.csv"
AIVIS_EXE = r"C:\Users\qvf03\AppData\Local\Programs\AivisSpeech\AivisSpeech.exe"
API = "http://127.0.0.1:10101"
PORT = int(os.environ.get("STUDIO_PORT", "8040"))
PIN = os.environ.get("STUDIO_PIN", "")
RATE = 44100
PARAM_KEYS = ("speedScale", "intonationScale", "tempoDynamicsScale", "pitchScale",
              "volumeScale", "prePhonemeLength", "postPhonemeLength")
PAUSE = {"ナレーション": 450, "第十三レジ": 350}
PAUSE_DEFAULT = 250
NARR_SFX_REGISTER = "第十三レジ。ただいま営業中。"
READING_FIXES = {"時空": "じくう", "履歴": "りれき", "返金": "へんきん", "返品": "へんぴん", "汗田": "あせだ"}
FB_CAST = {"レシート": "第十三レジ"}
SFX_FILES = {"register": TOOLS / "sfx_register.wav", "scan": TOOLS / "sfx_scan.wav"}
EPS = [f"ep{n:02d}" for n in range(1, 13)]

LOCK = threading.Lock()
JOB = {"running": False, "kind": "", "ep": "", "total": 0, "done": 0,
       "msg": "", "log": [], "error": "", "finished_at": 0}


# ---------- 共通ヘルパ ----------
def ep_paths(ep):
    if ep == "ep01":
        return (KAMI / "scene_manifest.json",
                KAMI / "assets" / "ep01_full_voice_reading_hiragana_mina_mao.wav",
                KAMI / "assets" / "manifest_reading_hiragana_ep01.json")
    return (KAMI / f"scene_manifest_{ep}.json",
            KAMI / "assets" / f"{ep}_full_voice_reading_hiragana.wav",
            KAMI / "assets" / f"manifest_reading_hiragana_{ep}.json")


def clip_dir(ep):
    d = CLIP_BASE / f"{ep}_aivis" / "raw"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_manifest(ep):
    p = ep_paths(ep)[0]
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_manifest(ep, entries):
    ep_paths(ep)[0].write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cast():
    return {r["character"]: r for r in csv.DictReader(io.open(CAST_CSV, encoding="utf-8-sig"))}


def load_plan(ep):
    p = KAMI / f"visual_cut_plan_{ep}.json"
    if p.exists():
        return {c["visualCutId"]: c for c in json.loads(p.read_text(encoding="utf-8"))}
    return {}


def to_reading(text):
    for k, v in READING_FIXES.items():
        text = text.replace(k, v)
    return text


def cut_image(ep, vc, plan_by_vc):
    """カット画像の解決: plan.plannedImage → epNN_vcNN_*.png の最新 → fallback → 空"""
    c = plan_by_vc.get(vc, {})
    pi = (c.get("plannedImage") or "").split("?")[0]
    if pi and (KAMI / pi).exists():
        return pi
    g = sorted(PLANNED.glob(f"{ep}_{vc}_*.png"), key=lambda p: p.stat().st_mtime)
    if g:
        return f"assets/scenes/planned/{g[-1].name}"
    fb = (c.get("fallbackImage") or "").split("?")[0]
    if fb and (KAMI / fb).exists():
        return fb
    return ""


def relabel(ep, entries):
    """id連番・カットラベル・進行ラベルを再計算し、画像をカットへ同期"""
    plan = load_plan(ep)
    total = len(entries)
    ncuts = max((e.get("visualCutIndex") or 1) for e in entries) if entries else 20
    ncuts = max(ncuts, len(plan) or 20)
    for i, e in enumerate(entries, 1):
        e["id"] = f"{ep}_v{i:03d}"
        e["cut"] = f"{ep}_{i:03d}"
        vc = e.get("visualCutId") or "vc01"
        e["visualCutIndex"] = int(vc[2:])
        c = plan.get(vc, {})
        e["visualCutTitle"] = e.get("visualCutTitle") or c.get("title", "")
        img = cut_image(ep, vc, plan)
        if img:
            e["image"] = img
        e.setdefault("plannedImage", c.get("plannedImage", e.get("image", "")))
        e.setdefault("fallbackImage", c.get("fallbackImage", e.get("image", "")))
        e.setdefault("imagePrompt", c.get("prompt", ""))
        e["log"] = [f"発話ログ　{i}/{total}", f"担当　{e['speaker']}"]
        e["visualLabel"] = f"{e['visualCutIndex']:02d}/{ncuts}　{e['visualCutTitle']}"
        e["progressLabel"] = f"{i}/{total}　{e['speaker']}"
    return entries


def renumber_clips(ep, entries, old_ids):
    """行の追加/削除/並べ替え後、既存クリップを新idへ引っ越す(内容が同じ行は再合成不要)"""
    d = clip_dir(ep)
    for o in set(old_ids):
        p = d / f"{o}.wav"
        if p.exists():
            p.rename(d / f"tmp_{o}.wav")
    for e, o in zip(entries, old_ids):
        t = d / f"tmp_{o}.wav"
        if o and t.exists():
            t.rename(d / f"{e['id']}.wav")
    for t in d.glob("tmp_*.wav"):
        t.unlink()


# ---------- AivisSpeech ----------
def post_api(url, payload=None, timeout=120):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def engine_up(timeout_s=5):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(f"{API}/version", timeout=3) as r:
                r.read()
            return True
        except Exception:
            time.sleep(1)
    return False


def restart_engine(log):
    log.append("AivisSpeech を再起動します…")
    subprocess.run(["taskkill", "/F", "/IM", "AivisSpeech.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "run.exe"], capture_output=True)
    time.sleep(3)
    subprocess.Popen([AIVIS_EXE])
    for _ in range(36):
        if engine_up(5):
            time.sleep(3)
            log.append("エンジン復帰")
            return True
    log.append("★エンジンが復帰しません")
    return False


def synth_one(ep, entry, cast, log, restarts_left=[2]):
    """1行合成(接続リセット時はエンジン再起動して同行をリトライ)"""
    ch = entry["speaker"] if entry["speaker"] in cast else FB_CAST.get(entry["speaker"], entry["speaker"])
    info = cast.get(ch)
    if not info:
        log.append(f"★cast無し: {entry['speaker']} ({entry['id']})")
        return False
    reading = entry.get("reading") or to_reading(entry.get("dialogue", ""))
    sid = int(info["style_id"])
    for attempt in range(3):
        try:
            if not engine_up(3):
                if not restart_engine(log):
                    return False
            q = json.loads(post_api(
                f"{API}/audio_query?{urllib.parse.urlencode({'text': reading, 'speaker': sid})}").decode("utf-8"))
            for k in PARAM_KEYS:
                q[k] = float(info[k])
            q["outputSamplingRate"] = RATE
            q["outputStereo"] = False
            (clip_dir(ep) / f"{entry['id']}.wav").write_bytes(
                post_api(f"{API}/synthesis?{urllib.parse.urlencode({'speaker': sid})}", q))
            return True
        except Exception as e:
            log.append(f"{entry['id']} 失敗({type(e).__name__}) → エンジン再起動リトライ")
            if not restart_engine(log):
                return False
    return False


# ---------- ジョブ(直列ワーカー) ----------
def start_job(kind, ep, fn):
    with LOCK:
        if JOB["running"]:
            return False
        JOB.update({"running": True, "kind": kind, "ep": ep, "total": 0, "done": 0,
                    "msg": "開始", "log": [], "error": "", "finished_at": 0})

    def run():
        try:
            fn()
            JOB["msg"] = "完了"
        except Exception as e:
            JOB["error"] = f"{type(e).__name__}: {e}"
            JOB["msg"] = "失敗"
        finally:
            JOB["running"] = False
            JOB["finished_at"] = time.time()
    threading.Thread(target=run, daemon=True).start()
    return True


def job_synth(ep, ids):
    entries = load_manifest(ep)
    by_id = {e["id"]: e for e in entries}
    targets = [by_id[i] for i in ids if i in by_id]
    cast = load_cast()
    JOB["total"] = len(targets)
    ok = 0
    for e in targets:
        JOB["msg"] = f"合成中 {e['id']} {e['speaker']}"
        if synth_one(ep, e, cast, JOB["log"]):
            ok += 1
        JOB["done"] += 1
        time.sleep(0.15)
    JOB["log"].append(f"合成 {ok}/{len(targets)} 完了")
    save_manifest(ep, entries)


def job_apply(ep):
    """クリップ連結 → タイミング確定 → wav/manifest/読みマニフェスト書込 → キャッシュバスト"""
    entries = load_manifest(ep)
    cast = load_cast()
    d = clip_dir(ep)
    missing = [e["id"] for e in entries if not (d / f"{e['id']}.wav").exists()]
    if missing:
        raise RuntimeError(f"未生成クリップ {len(missing)}本: {missing[:5]}…")
    JOB["total"] = len(entries)
    cursor = 0.0
    fullpcm = bytearray()
    rate = RATE
    vman = []
    for e in entries:
        with wave.open(str(d / f"{e['id']}.wav"), "rb") as w:
            rate = w.getframerate()
            pcm = w.readframes(w.getnframes())
        start = cursor
        dur = len(pcm) / 2 / rate
        fullpcm += pcm
        cursor += dur
        e["start"] = round(start, 3)
        e["end"] = round(cursor, 3)
        ch = e["speaker"] if e["speaker"] in cast else FB_CAST.get(e["speaker"], e["speaker"])
        pa = PAUSE.get(ch, PAUSE_DEFAULT)
        fullpcm += b"\x00\x00" * int(rate * pa / 1000)
        cursor += pa / 1000.0
        sfx = e.get("sfxAfter") or ("register" if e.get("dialogue") == NARR_SFX_REGISTER else "")
        if sfx and SFX_FILES.get(sfx, Path("x")).exists():
            with wave.open(str(SFX_FILES[sfx]), "rb") as w:
                spcm = w.readframes(w.getnframes())
            fullpcm += spcm
            cursor += len(spcm) / 2 / rate
        info = cast.get(ch, {})
        vman.append({"id": e["id"], "cut": e.get("cut", ""), "visualCutId": e.get("visualCutId", ""),
                     "character": ch, "speaker_name": info.get("speaker_name", ""),
                     "style_name": info.get("style_name", ""), "style_id": info.get("style_id", ""),
                     "text": e.get("dialogue", ""), "synthesis_text": e.get("reading", ""),
                     "synthesis_source": "studio", "clip": f"outputs/{ep}_aivis/raw/{e['id']}.wav"})
        JOB["done"] += 1
    buf = io.BytesIO()
    with wave.open(buf, "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(rate)
        o.writeframes(bytes(fullpcm))
    mpath, wpath, vpath = ep_paths(ep)
    wpath.write_bytes(buf.getvalue())
    save_manifest(ep, entries)
    vpath.write_text(json.dumps(vman, ensure_ascii=False, indent=2), encoding="utf-8")
    # index.html の該当話 ?v= を +1
    idx = KAMI / "index.html"
    html = idx.read_text(encoding="utf-8")
    pat = re.compile(rf'({re.escape(wpath.name)}\?v=)(\d+)')
    html2 = pat.sub(lambda m: m.group(1) + str(int(m.group(2)) + 1), html)
    if html2 != html:
        idx.write_text(html2, encoding="utf-8")
        JOB["log"].append("index.html キャッシュバスト更新")
    JOB["log"].append(f"反映完了: {len(entries)}行 / 総尺 {cursor:.1f}s")


def job_video(ep):
    JOB["msg"] = "動画レンダリング中(数分かかります)"
    r = subprocess.run([sys.executable, str(TOOLS / "build_episode_video.py"), ep[2:]],
                       capture_output=True, text=True, cwd=str(ROOT), encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()[-3:] + (r.stderr or "").strip().splitlines()[-3:]
    JOB["log"].extend(tail)
    if r.returncode != 0:
        raise RuntimeError("動画ビルド失敗(ログ参照)")


def job_publish(ep):
    mpath, wpath, vpath = ep_paths(ep)
    paths = [str(mpath.relative_to(ROOT)), str(wpath.relative_to(ROOT)), str(vpath.relative_to(ROOT)),
             "13th-register-kamishibai/index.html"]
    for extra in (KAMI / f"visual_cut_plan_{ep}.json",
                  VIDEO_DIR / f"{ep}_youtube_vertical_1080x1920.mp4",
                  DOCS / f"{ep}_revised.md"):
        if extra.exists():
            paths.append(str(extra.relative_to(ROOT)))
    paths += [f"13th-register-kamishibai/assets/scenes/planned/{p.name}"
              for p in PLANNED.glob(f"{ep}_vc*.png")]
    def git(*args):
        r = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        JOB["log"].append(f"$ git {' '.join(args[:2])} → {r.returncode}")
        if r.stdout.strip():
            JOB["log"].extend(r.stdout.strip().splitlines()[-4:])
        if r.returncode != 0 and r.stderr.strip():
            JOB["log"].extend(r.stderr.strip().splitlines()[-4:])
        return r.returncode
    git("add", "--", *paths)
    n = int(ep[2:])
    if git("commit", "-m", f"第{n}話をエピソードスタジオから更新する") not in (0, 1):
        raise RuntimeError("commit失敗")
    if git("push", "origin", "gh-pages") != 0:
        raise RuntimeError("push失敗")
    JOB["log"].append("公開完了(github.io反映まで1〜2分)")


# ---------- 台本取り込み ----------
def import_script(ep, text):
    lines = []
    for raw in text.splitlines():
        raw = raw.strip().lstrip("﻿")
        if not raw or raw.startswith("#"):
            continue
        sp, sep, rest = raw.partition("：")
        if not sep:
            sp, sep, rest = raw.partition(":")
        if not sep or not rest.strip():
            continue
        sp = sp.strip()
        disp, _, yomi = rest.strip().partition("｜")
        if "SE" in sp:                      # 効果音行 → 直前行にSFXマーカー
            if lines:
                lines[-1]["sfxAfter"] = "scan"
            continue
        lines.append({"speaker": sp, "dialogue": disp.strip(),
                      "reading": (yomi.strip() or to_reading(disp.strip()))})
    if not lines:
        raise RuntimeError("セリフ行が見つかりません(形式: 話者：セリフ)")
    old = load_manifest(ep)
    plan = load_plan(ep)
    vcs = sorted(plan.keys(), key=lambda v: int(v[2:])) or [f"vc{i:02d}" for i in range(1, 21)]
    entries = []
    for i, ln in enumerate(lines):
        if len(old) == len(lines):          # 行数一致なら既存カット割りを継承
            vc = old[i].get("visualCutId", "vc01")
            title = old[i].get("visualCutTitle", "")
        else:                               # 新規はカットへ均等割り
            vc = vcs[min(len(vcs) - 1, i * len(vcs) // len(lines))]
            title = plan.get(vc, {}).get("title", "")
        e = {"id": "", "cut": "", "visualCutId": vc, "visualCutTitle": title,
             "visualCutIndex": int(vc[2:]), "start": 0.0, "end": 0.0,
             "image": "", "speaker": ln["speaker"], "dialogue": ln["dialogue"],
             "reading": ln["reading"]}
        if ln.get("sfxAfter"):
            e["sfxAfter"] = ln["sfxAfter"]
        entries.append(e)
    relabel(ep, entries)
    # 旧クリップで同一(話者+読み)の行は流用
    d = clip_dir(ep)
    oldkey = {}
    for o in old:
        k = (o.get("speaker"), o.get("reading") or "")
        p = d / f"{o['id']}.wav"
        if p.exists():
            oldkey.setdefault(k, []).append(p)
    for t in list(d.glob("*.wav")):
        t.rename(t.with_name("tmp_" + t.name))
    reused = 0
    for e in entries:
        k = (e["speaker"], e["reading"])
        cand = oldkey.get(k)
        if cand:
            src = cand.pop(0)
            tmp = d / ("tmp_" + src.name)
            if tmp.exists():
                tmp.rename(d / f"{e['id']}.wav")
                reused += 1
    for t in d.glob("tmp_*.wav"):
        t.unlink()
    save_manifest(ep, entries)
    n = int(ep[2:])
    (DOCS / f"{ep}_revised.md").write_text(
        f"# 第{n}話 {ep}_revised（エピソードスタジオ取込 {time.strftime('%Y-%m-%d %H:%M')}）\n"
        f"# 形式: 話者：セリフ｜読み\n\n" +
        "\n".join(f"{l['speaker']}：{l['dialogue']}" +
                  (f"｜{l['reading']}" if l["reading"] != to_reading(l["dialogue"]) else "")
                  for l in lines) + "\n", encoding="utf-8")
    return {"lines": len(entries), "reused_clips": reused}


# ---------- 状態API ----------
def episode_state(ep):
    mpath, wpath, _ = ep_paths(ep)
    entries = load_manifest(ep)
    d = CLIP_BASE / f"{ep}_aivis" / "raw"
    clips = {p.stem for p in d.glob("*.wav")} if d.exists() else set()
    have = sum(1 for e in entries if e["id"] in clips)
    vid = VIDEO_DIR / f"{ep}_youtube_vertical_1080x1920.mp4"
    return {"ep": ep, "lines": len(entries), "clips": have,
            "wav": wpath.exists(), "video": vid.exists(),
            "video_mb": round(vid.stat().st_size / 1e6, 1) if vid.exists() else 0,
            "duration": round(entries[-1]["end"], 1) if entries and entries[-1].get("end") else 0}


def episode_detail(ep):
    entries = load_manifest(ep)
    plan = load_plan(ep)
    d = CLIP_BASE / f"{ep}_aivis" / "raw"
    clips = {p.stem for p in d.glob("*.wav")} if d.exists() else set()
    lines = [{"id": e["id"], "speaker": e["speaker"], "dialogue": e.get("dialogue", ""),
              "reading": e.get("reading", ""), "vc": e.get("visualCutId", ""),
              "sfxAfter": e.get("sfxAfter", ""), "clip": e["id"] in clips,
              "start": e.get("start", 0)} for e in entries]
    cuts = []
    seen = {}
    for i, e in enumerate(entries, 1):
        vc = e.get("visualCutId", "")
        if vc not in seen:
            seen[vc] = {"vc": vc, "title": e.get("visualCutTitle", ""), "from": i, "to": i,
                        "image": e.get("image", ""),
                        "planned": (plan.get(vc, {}).get("plannedImage") or
                                    f"assets/scenes/planned/{ep}_{vc}_scene.png"),
                        "imageExists": bool(e.get("image")) and (KAMI / e.get("image", "x")).exists()}
            cuts.append(seen[vc])
        seen[vc]["to"] = i
    cast = sorted(load_cast().keys())
    return {"ep": ep, "lines": lines, "cuts": cuts, "cast": cast,
            "engine": engine_up(2)}


def codex_doc(ep):
    det = episode_detail(ep)
    n = int(ep[2:])
    rows = "\n".join(
        f"| {c['vc']} | v{c['from']:03d}-v{c['to']:03d} | {c['title'] or '(無題)'} | "
        f"`{Path(c['planned']).name}` | {'あり' if c['imageExists'] else '★未着'} |"
        for c in det["cuts"])
    return (f"# Codexへ: 第{n}話 画像作成依頼(エピソードスタジオ自動生成)\n\n"
            f"保存先: `13th-register-kamishibai/assets/scenes/planned/`(同名上書き、site/コピー不要)\n"
            f"9:16縦・セルルックVN風・下部30〜40%セーフエリア・画像内の長文/ロゴ禁止。\n"
            f"キャラ外見は `assets/character_sheets/` のデザインシート固定。\n\n"
            f"| vc | 行範囲 | 場面タイトル | ファイル名 | 状態 |\n|---|---|---|---|---|\n{rows}\n\n"
            f"行ごとのセリフは `13th-register-kamishibai/scene_manifest_{ep}.json` 参照。\n")


# ---------- HTTP ----------
class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # keep-alive必須: HTTP/1.0だとclose時に送信バッファが破棄され大きな応答が途切れる

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        mv = memoryview(data)          # wfileは非バッファ=部分送信があるためループで全送
        try:
            while mv:
                n = self.wfile.write(mv)
                if n is None:
                    break              # バッファ層が全量書いた場合
                mv = mv[n:]
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass                       # クライアント切断は無視

    def _auth(self):
        if not PIN:
            return True
        if self.headers.get("X-Pin") == PIN or \
           urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("pin", [""])[0] == PIN:
            return True
        self._send(401, {"error": "PINが必要です"})
        return False

    def log_message(self, *a):
        pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == "/":
            html = (TOOLS / "episode_studio.html").read_bytes()
            return self._send(200, html, "text/html; charset=utf-8")
        if not self._auth():
            return
        try:
            if u.path == "/api/state":
                return self._send(200, {"episodes": [episode_state(e) for e in EPS],
                                        "busy": JOB["running"], "pin": bool(PIN)})
            if u.path == "/api/episode":
                return self._send(200, episode_detail(q["ep"]))
            if u.path == "/api/job":
                return self._send(200, JOB)
            if u.path == "/api/codexdoc":
                return self._send(200, {"doc": codex_doc(q["ep"])})
            if u.path == "/clip":
                p = clip_dir(q["ep"]) / f"{q['id']}.wav"
                if p.exists():
                    return self._send(200, p.read_bytes(), "audio/wav")
                return self._send(404, {"error": "clip無し"})
            if u.path == "/img":
                rel = q.get("p", "").replace("\\", "/").lstrip("/")
                p = (KAMI / rel).resolve()
                if p.is_file() and str(p).startswith(str(KAMI.resolve())):
                    ct = "image/png" if p.suffix == ".png" else "image/jpeg"
                    return self._send(200, p.read_bytes(), ct)
                return self._send(404, {"error": "img無し"})
            if u.path == "/wav":
                p = ep_paths(q["ep"])[1]
                if p.exists():
                    return self._send(200, p.read_bytes(), "audio/wav")
                return self._send(404, {"error": "wav無し"})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        if not self._auth():
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            path = urllib.parse.urlparse(self.path).path
            ep = body.get("ep", "")
            if ep and ep not in EPS:
                return self._send(400, {"error": "不正なep"})
            if path == "/api/import":
                return self._send(200, import_script(ep, body.get("text", "")))
            if path == "/api/line":
                entries = load_manifest(ep)
                by_id = {e["id"]: e for e in entries}
                e = by_id.get(body["id"])
                if not e:
                    return self._send(404, {"error": "行が見つかりません"})
                changed_voice = False
                for k in ("dialogue", "reading", "speaker"):
                    if k in body and body[k] != e.get(k):
                        e[k] = body[k]
                        changed_voice = changed_voice or k in ("reading", "speaker")
                        if k == "dialogue" and not body.get("reading"):
                            e["reading"] = to_reading(body[k])
                            changed_voice = True
                if "sfxAfter" in body:
                    e["sfxAfter"] = body["sfxAfter"]
                if changed_voice:
                    (clip_dir(ep) / f"{e['id']}.wav").unlink(missing_ok=True)
                save_manifest(ep, entries)
                return self._send(200, {"ok": True, "clipDeleted": changed_voice})
            if path == "/api/lines_edit":
                entries = load_manifest(ep)
                old_ids = [e["id"] for e in entries]
                i = int(body["index"])          # 0始まり
                if body["op"] == "delete":
                    (clip_dir(ep) / f"{entries[i]['id']}.wav").unlink(missing_ok=True)
                    old_ids.pop(i)
                    entries.pop(i)
                elif body["op"] == "insert":
                    base = entries[min(i, len(entries) - 1)]
                    e = {k: base.get(k) for k in ("visualCutId", "visualCutTitle", "visualCutIndex",
                                                  "image", "plannedImage", "fallbackImage", "imagePrompt")}
                    e.update({"id": "", "cut": "", "start": 0.0, "end": 0.0,
                              "speaker": body.get("speaker", "ナレーション"),
                              "dialogue": body.get("dialogue", ""),
                              "reading": to_reading(body.get("dialogue", ""))})
                    entries.insert(i + 1, e)
                    old_ids.insert(i + 1, "")
                relabel(ep, entries)
                renumber_clips(ep, entries, old_ids)
                save_manifest(ep, entries)
                return self._send(200, {"ok": True, "lines": len(entries)})
            if path == "/api/cuts":
                # starts: [{line:1始まり, vc?: "vc15", title?}] 昇順。vc省略時は未使用番号を割当
                entries = load_manifest(ep)
                starts = sorted(body.get("starts", []), key=lambda s: s["line"])
                if not starts or starts[0]["line"] != 1:
                    return self._send(400, {"error": "先頭行はカット1の開始である必要があります"})
                used = {s.get("vc") for s in starts if s.get("vc")}
                nxt = 1
                for s in starts:
                    if not s.get("vc"):
                        while f"vc{nxt:02d}" in used:
                            nxt += 1
                        s["vc"] = f"vc{nxt:02d}"
                        used.add(s["vc"])
                bounds = [(s["line"], s["vc"], s.get("title", "")) for s in starts]
                for i, e in enumerate(entries, 1):
                    b, vc, t = next((b, v, t) for b, v, t in reversed(bounds) if b <= i)
                    e["visualCutId"] = vc
                    e["visualCutTitle"] = t
                relabel(ep, entries)
                save_manifest(ep, entries)
                return self._send(200, {"ok": True, "cuts": len(bounds)})
            if path == "/api/synth":
                entries = load_manifest(ep)
                d = clip_dir(ep)
                mode = body.get("mode", "missing")
                if mode == "ids":
                    ids = body.get("ids", [])
                elif mode == "all":
                    ids = [e["id"] for e in entries]
                else:
                    ids = [e["id"] for e in entries if not (d / f"{e['id']}.wav").exists()]
                if not ids:
                    return self._send(200, {"ok": True, "queued": 0, "msg": "生成対象なし"})
                if not start_job("synth", ep, lambda: job_synth(ep, ids)):
                    return self._send(409, {"error": "他のジョブ実行中"})
                return self._send(200, {"ok": True, "queued": len(ids)})
            if path == "/api/apply":
                if not start_job("apply", ep, lambda: job_apply(ep)):
                    return self._send(409, {"error": "他のジョブ実行中"})
                return self._send(200, {"ok": True})
            if path == "/api/video":
                if not start_job("video", ep, lambda: job_video(ep)):
                    return self._send(409, {"error": "他のジョブ実行中"})
                return self._send(200, {"ok": True})
            if path == "/api/publish":
                if not start_job("publish", ep, lambda: job_publish(ep)):
                    return self._send(409, {"error": "他のジョブ実行中"})
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    print(f"エピソードスタジオ http://0.0.0.0:{PORT}/  (PIN {'有効' if PIN else '無効'})")
    print(f"リポジトリ: {ROOT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()

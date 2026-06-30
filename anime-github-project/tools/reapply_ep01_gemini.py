# -*- coding: utf-8 -*-
"""EP01 を改訂版131行で Gemini TTS 再合成し、紙芝居データ一式を作り直す。

- ep01_revised.md(131行) を確定カット境界で20カットへ割当(AivisSpeech版と同一)
- voices.yaml の Gemini声(エリ=Kore等)で各行を合成(10req/分・throttle/429リトライ)
- 連結wav(24kHz) + scene_manifest + visual_cut_plan(lineStart/End) を再構築
- 画像は確定20枚を維持、reading(かな)は既存scene_manifestから引き継ぐ
出力は Codex / OneDrive の4コピー。
"""
from __future__ import annotations
import io, json, re, sys, time, wave
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))
from gen_voice_samples import generate_tts, load_env_key  # noqa: E402
import yaml  # noqa: E402

ONEDRIVE = Path(r"C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ")
CODEX = Path(r"C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages")
REV_MD = TOOLS.parent / "ep01_revised.md"   # OneDrive外の正本(同期復元対策)
VOICES = TOOLS.parent / "voices.yaml"      # anime-github-project/voices.yaml
CLIP_DIR = ONEDRIVE / "outputs" / "ep01_gemini" / "raw"
DESTS = [(r, s) for r in (CODEX, ONEDRIVE) for s in ("13th-register-kamishibai", "site")]
# 読みオーバーライド: 漢字直読みでGeminiが誤読する行を、正しいかな読みで合成・表示する。
_OVR = TOOLS / "ep01_reading_overrides.json"
READING_OVERRIDES = json.load(open(_OVR, encoding="utf-8")) if _OVR.exists() else {}

CUT_START = [1, 3, 4, 26, 29, 35, 38, 50, 58, 62, 68, 72, 83, 89, 98, 110, 119, 121, 124, 127]
SPEAKER_FALLBACK = {"レシート": "第十三レジ"}
# テンポ: リセット(2026-06-29)。均一・素の間。
PAUSE = {}
PAUSE_DEFAULT = 280
# 各クリップの前後無音トリム(頭/尻に残すマージンms)。間延びの主因=発話前後の無音パディング除去。
TRIM_HEAD_MS = 60
TRIM_TAIL_MS = 90
# リセット: ナレーション前後の特別な間を廃止(0)。
NARR_EDGE_MS = 0
RATE = 24000  # Gemini TTS 出力
# TTS日次上限=100/日(モデル単位)対策: キャラを2モデルに分担し各100以内に収める。
# 主要キャラ(タクミ/エリ)は選定元の2.5-flashに、他は3.1-flashに固定。
# 2026-06-28 改: 2.5-flash は本日空応答多発(1/3)のため不使用。
# 安定の3.1-flash(3/3)に最重要・最多キャラを寄せ、残りを2.5-pro(2/3・高品質)へ。
CHAR_MODEL = {
    "タクミ": "gemini-3.1-flash-tts-preview",        # 49行(最多・短文多い→安定が要)
    "ナレーション": "gemini-3.1-flash-tts-preview",  # 28行(最重要)
    "第十三レジ": "gemini-3.1-flash-tts-preview",    # 12行(+レシート1=DEFAULTで3.1)
    "座木山辰哉": "gemini-3.1-flash-tts-preview",    # 1行
    "エリ": "gemini-2.5-pro-preview-tts",            # 26行
    "未来の会社員": "gemini-2.5-pro-preview-tts",    # 12行
}
DEFAULT_MODEL = "gemini-3.1-flash-tts-preview"


def model_for(ch):
    return CHAR_MODEL.get(ch, DEFAULT_MODEL)


def parse_lines():
    rows = []
    for l in io.open(REV_MD, encoding="utf-8"):
        s = l.strip()
        if not s or s.startswith("#") or s.startswith(">"):
            continue
        m = re.match(r"^([^：:]{1,12})[：:](.+)$", s)
        if m:
            rows.append((m.group(1).strip(), m.group(2).strip()))
    return rows


def cut_for(line_no):
    idx = 0
    for i, st in enumerate(CUT_START):
        if line_no >= st:
            idx = i
    return f"vc{idx+1:02d}"


class QuotaDayError(Exception):
    """日次クォータ枯渇。部分デプロイを避けるため全体を中断する。"""


def gemini_pcm(key, model, voice, text, style):
    """Gemini合成。分上限/空応答はリトライ、日次上限は QuotaDayError で中断。"""
    last = ""; empties = 0
    for attempt in range(14):
        try:
            wav_bytes = generate_tts(key, model, voice, text, style, insecure_ssl=True)
            with wave.open(io.BytesIO(wav_bytes), "rb") as w:
                fr = w.getframerate(); pcm = w.readframes(w.getnframes())
            dur = len(pcm) / 2 / fr
            return pcm, dur, fr
        except Exception as e:
            last = str(e)
            if "per_day" in last.lower() or "perday" in last.lower():
                raise QuotaDayError(last)
            if "RESOURCE_EXHAUSTED" in last and "per" in last.lower():
                # 分上限の429は枠を消費しないので待って再試行
                print("      レート上限。62秒待機…", flush=True); time.sleep(62); continue
            if any(x in last for x in ("パートなし", "候補なし", "空")):
                # 空応答(200)は日次枠を消費するため最大2回まで
                empties += 1
                if empties >= 2:
                    break
                print("      空応答。5秒待って再試行…", flush=True); time.sleep(5); continue
            break
    raise RuntimeError(last or "gemini失敗")


def main():
    key = load_env_key()
    assert key, ".env の GEMINI_API_KEY が必要"
    voices = yaml.safe_load(open(VOICES, encoding="utf-8"))["characters"]
    lines = parse_lines()
    assert len(lines) == 127, f"想定127≠{len(lines)}"
    CLIP_DIR.mkdir(parents=True, exist_ok=True)

    # 既存scene_manifest(Codex)から reading を引き継ぐ
    old_sm = json.load(open(CODEX / "13th-register-kamishibai" / "scene_manifest.json", encoding="utf-8"))
    old_reading = {x["id"]: x.get("reading", "") for x in old_sm}
    # visual_cut_plan 雛形(画像入り)
    vp = json.load(open(CODEX / "13th-register-kamishibai" / "visual_cut_plan.json", encoding="utf-8"))
    vp_by = {c["visualCutId"]: c for c in vp}

    manifest = []
    print(f"Gemini合成開始: {len(lines)}行", flush=True)
    for i, (sp, text) in enumerate(lines, 1):
        ch = sp if sp in voices else SPEAKER_FALLBACK.get(sp, sp)
        conf = voices.get(ch)
        if not conf:
            print(f"  ★voices.yaml無し {sp}->skip", flush=True); continue
        lid = f"ep01_v{i:03d}"
        clip_path = CLIP_DIR / f"{lid}.wav"
        if clip_path.exists():  # 再開: 生成済みは読み込み
            with wave.open(str(clip_path), "rb") as w:
                fr = w.getframerate(); pcm = w.readframes(w.getnframes())
            dur = len(pcm) / 2 / fr
        else:
            try:
                # style文は渡さない: Geminiが演技指示文を読み上げる不具合(「変な設定行」)を防ぐ。
                # 声色はプリセット(Kore等)が担保する。プロソディ調整が必要なら別途検討。
                # 誤読対策: オーバーライドがあれば漢字textでなく正しいかな読みを合成入力にする。
                synth = READING_OVERRIDES.get(lid, text)
                pcm, dur, fr = gemini_pcm(key, model_for(ch), conf["voice"], synth, "")
            except QuotaDayError:  # 日次上限: 部分デプロイせず中断(再開可能)
                done = sum(1 for _ in CLIP_DIR.glob("*.wav"))
                print(f"  ! 日次上限到達。生成済み {done}/129。デプロイせず中断(明日再開)。", flush=True)
                return
            except Exception as e:  # 1行失敗で全体を止めない: 0.6s無音で継続
                print(f"  X {lid} 合成失敗→0.6s無音で継続: {str(e)[:50]}", flush=True)
                fr = RATE; pcm = bytes(int(RATE * 0.6) * 2); dur = 0.6
            clip_path.write_bytes(pcm_to_wav(pcm, fr))
            time.sleep(8)  # 10req/分対策(新規生成時のみ)
        pcm = trim_edges(pcm, fr)  # 前後無音トリム(軽快化)
        dur = len(pcm) / 2 / fr
        manifest.append({"id": lid, "cut": f"ep01_{i:03d}", "visualCutId": cut_for(i),
                         "character": ch, "voice": conf["voice"], "text": text,
                         "reading": READING_OVERRIDES.get(lid, old_reading.get(lid, "")), "pause_after_ms": PAUSE.get(ch, PAUSE_DEFAULT),
                         "pcm": pcm, "duration": dur, "rate": fr})
        if i % 10 == 0:
            print(f"  {i}/129", flush=True)

    rate = manifest[0]["rate"] if manifest else RATE
    # lineStart/End 更新
    for vc in vp_by:
        ids = [m["id"] for m in manifest if m["visualCutId"] == vc]
        if ids:
            vp_by[vc]["lineStart"] = ids[0]; vp_by[vc]["lineEnd"] = ids[-1]

    # 連結 + scene_manifest
    total = len(manifest); cursor = 0.0; scenes = []; full = bytearray()
    def log_for(ch, idx):
        base = [f"発話ログ　{idx:02d}/{total:02d}", f"担当　{ch}"]
        if ch == "エリ": return base + ["声　Kore"]
        if ch == "第十三レジ": return base + ["第十三レジ　応答中"]
        if "未来" in ch: return base + ["未来案件　処理中"]
        if ch == "ナレーション": return base + ["深夜帯　進行中"]
        return base + ["本日の営業　継続中"]
    NARR = "ナレーション"
    for vi, m in enumerate(manifest, 1):
        ch = m["character"]
        prev_ch = manifest[vi - 2]["character"] if vi >= 2 else None
        # ナレーション開始(直前が非ナレ/先頭)の直前に少し間
        if ch == NARR and prev_ch != NARR and NARR_EDGE_MS > 0:
            full += b"\x00\x00" * int(rate * NARR_EDGE_MS / 1000); cursor += NARR_EDGE_MS / 1000.0
        start = cursor; end = cursor + m["duration"]; full += m["pcm"]
        c = vp_by[m["visualCutId"]]; planned = c["plannedImage"]; fb = c.get("fallbackImage", "")
        img = planned if (CODEX / "13th-register-kamishibai" / planned).exists() else fb
        scenes.append({"id": m["id"], "cut": m["cut"], "visualCutId": m["visualCutId"],
            "visualCutTitle": c.get("title", ""), "visualCutIndex": int(m["visualCutId"][2:]),
            "start": round(start, 3), "end": round(end, 3), "image": img, "plannedImage": planned,
            "fallbackImage": fb, "imagePrompt": c.get("prompt", ""), "speaker": m["character"],
            "dialogue": m["text"], "reading": m["reading"], "log": log_for(m["character"], vi),
            "visualLabel": f"{int(m['visualCutId'][2:]):02d}/20　{c.get('title','')}",
            "progressLabel": f"{vi:02d}/{total:02d}　{m['character']}"})
        cursor = end
        next_ch = manifest[vi]["character"] if vi < total else None
        pa = m["pause_after_ms"]
        # ナレーション終了(直後が非ナレ/末尾)の後に少し間
        if ch == NARR and next_ch != NARR:
            pa = max(pa, NARR_EDGE_MS)
        if pa > 0:
            sil = b"\x00\x00" * int(rate * pa / 1000); full += sil; cursor += pa / 1000.0

    vman = [{"id": m["id"], "cut": m["cut"], "visualCutId": m["visualCutId"], "character": m["character"],
             "speaker_name": "Gemini", "style_name": m["voice"], "style_id": m["voice"],
             "text": m["text"], "synthesis_text": m["reading"] or m["text"], "synthesis_source": "gemini",
             "pause_after_ms": m["pause_after_ms"], "clip": f"outputs/ep01_gemini/raw/{m['id']}.wav"} for m in manifest]

    buf = io.BytesIO()
    with wave.open(buf, "wb") as o:
        o.setnchannels(1); o.setsampwidth(2); o.setframerate(rate); o.writeframes(bytes(full))
    wav_bytes = buf.getvalue()

    for root, sub in DESTS:
        base = root / sub
        (base / "assets").mkdir(parents=True, exist_ok=True)
        (base / "assets" / "ep01_full_voice_reading_hiragana_mina_mao.wav").write_bytes(wav_bytes)
        json.dump(vman, open(base / "assets" / "manifest_reading_hiragana_mina_mao.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(vp, open(base / "visual_cut_plan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.dump(scenes, open(base / "scene_manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"  書込: {root.name}/{sub}", flush=True)
    print(f"完了: {len(scenes)}行 / 総尺 {cursor:.1f}s / wav {len(wav_bytes)//1024}KB / rate {rate}", flush=True)


def pcm_to_wav(pcm, rate):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return b.getvalue()


def trim_edges(pcm, fr, head_ms=TRIM_HEAD_MS, tail_ms=TRIM_TAIL_MS, thr=300):
    """発話前後の無音パディングを除去(頭head_ms/尻tail_msのマージンは残す)。
    間延びの主因。ピッチ・話速は変えず無音だけ削るので安全。"""
    import numpy as np
    a = np.frombuffer(pcm, dtype=np.int16)
    if a.size == 0:
        return pcm
    amp = np.abs(a.astype(np.int32))
    peak = int(amp.max())
    t = max(thr, int(0.03 * peak))  # 相対閾値(ノイズ耐性)
    idx = np.where(amp > t)[0]
    if idx.size == 0:  # 全部無音(フォールバック無音クリップ等)はそのまま
        return pcm
    head = max(0, int(idx[0]) - int(fr * head_ms / 1000))
    tail = min(a.size, int(idx[-1]) + int(fr * tail_ms / 1000))
    return a[head:tail].tobytes()


if __name__ == "__main__":
    main()

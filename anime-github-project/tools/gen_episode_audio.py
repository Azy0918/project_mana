# -*- coding: utf-8 -*-
"""『深夜二時の第十三レジ』 エピソード本番音声 通し生成（Gemini TTS）。

脚本 .md（「話者：セリフ」形式）を1行ずつ確定ボイス(voices.yaml)で読み上げ、
連番 wav として保存する。レート制限(10req/分)対策のスロットル・429リトライ・
既存スキップ(中断/再開可)つき。manifest.json も出力する。

使い方:
    python tools/gen_episode_audio.py \
        --script ../13th-register-kamishibai/scripts/ep01_revised.md \
        --out ../13th-register-kamishibai/audio/ep01

APIキー: .env / 環境変数 GEMINI_API_KEY。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve()
TOOLS = APP.parent
REPO = APP.parents[1]
sys.path.insert(0, str(TOOLS))
from gen_voice_samples import generate_tts, load_env_key  # noqa: E402

import yaml  # noqa: E402

VOICES_YAML = REPO / "voices.yaml"
# voices.yaml に無い話者のフォールバック割当
SPEAKER_FALLBACK = {
    "レシート": "第十三レジ",   # 機械の印字 → レジ端末の声
}


def load_voice_map() -> dict:
    data = yaml.safe_load(VOICES_YAML.read_text(encoding="utf-8")) or {}
    return data.get("characters", {})


def parse_script(path: Path) -> list[dict]:
    """「話者：セリフ」行を抽出。# 見出し / > 引用 / 空行は無視。"""
    rows = []
    for raw in io.open(path, encoding="utf-8"):
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith(">"):
            continue
        m = re.match(r"^([^：:]{1,12})[：:](.+)$", s)
        if m:
            rows.append({"speaker": m.group(1).strip(), "text": m.group(2).strip()})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--model", default=None, help="未指定なら voices.yaml の各話者 model")
    ap.add_argument("--throttle", type=float, default=7.0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    key = args.api_key or load_env_key()
    if not key:
        print("APIキーがありません(.env の GEMINI_API_KEY)。", file=sys.stderr)
        return 2

    vmap = load_voice_map()
    script_path = Path(args.script)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = parse_script(script_path)
    print(f"脚本: {script_path.name} / セリフ {len(rows)} 行 → {out}", flush=True)

    manifest = []
    ok = skip = fail = 0
    for i, r in enumerate(rows, 1):
        spk = r["speaker"]
        ch = spk if spk in vmap else SPEAKER_FALLBACK.get(spk)
        if not ch or ch not in vmap:
            print(f"[{i:03d}] ★話者未割当: {spk} → スキップ", file=sys.stderr)
            fail += 1
            manifest.append({**r, "index": i, "voice": None, "file": None, "status": "no_voice"})
            continue
        conf = vmap[ch]
        voice = conf["voice"]
        model = args.model or conf.get("model") or "gemini-2.5-flash-preview-tts"
        style = conf.get("style", "")
        fname = f"{i:03d}_{conf.get('voice','')}_{ch}.wav"
        fpath = out / fname
        if fpath.exists() and not args.force:
            skip += 1
            manifest.append({**r, "index": i, "character": ch, "voice": voice,
                             "file": fname, "status": "exists"})
            continue
        print(f"[{i:03d}] {spk}({voice}): {r['text'][:24]}…", flush=True)
        done = False
        last_err = ""
        for attempt in range(6):  # 429/空応答を粘り強くリトライ
            try:
                wav = generate_tts(key, model, voice, r["text"], style, insecure_ssl=True)
                fpath.write_bytes(wav)
                ok += 1
                manifest.append({**r, "index": i, "character": ch, "voice": voice,
                                 "file": fname, "status": "ok"})
                done = True
                break
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                if "RESOURCE_EXHAUSTED" in last_err and "per" in last_err.lower():
                    # 分あたり上限。固定62秒待つ(分リミットは60秒で回復)
                    print(f"      レート上限。62秒待機…", flush=True)
                    time.sleep(62)
                    continue
                if "パートなし" in last_err or "候補なし" in last_err or "空" in last_err:
                    # 空応答は一時的なことが多い。短く待って再試行
                    print(f"      空応答。8秒待って再試行({attempt+1})…", flush=True)
                    time.sleep(8)
                    continue
                break  # それ以外(認証等)は即中断
        if not done:
            print(f"      ✗ 確定失敗: {last_err[:90]}", file=sys.stderr)
            fail += 1
            manifest.append({**r, "index": i, "character": ch, "voice": voice,
                             "file": fname, "status": "fail", "error": last_err[:140]})
        time.sleep(args.throttle)  # 成否に関わらず必ず間隔を空ける(連射防止)

    (out / "manifest.json").write_text(
        json.dumps({"script": script_path.name, "rows": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # ffmpeg 連結用リスト（成功分のみ、台本順）
    concat = [f"file '{m['file']}'" for m in manifest if m.get("status") in ("ok", "exists")]
    (out / "concat.txt").write_text("\n".join(concat) + "\n", encoding="utf-8")
    print(f"\n完了: OK {ok} / 既存 {skip} / 失敗 {fail} / 全 {len(rows)}。"
          f" manifest.json・concat.txt 出力。", flush=True)
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""スタジオが保存する音声マニフェスト(セリフの最新版)から scene_manifest を再構築する。
使い方: python sync_scene_from_voice.py ep04
スタジオの「セリフ保存」は manifest_reading_hiragana_<ep>.json にしか書かないため、
音声再生成の前にこれで scene_manifest_<ep>.json のセリフ・カット割りを同期する。
タイミングは「既存scene_manifestの同一idを継承、無ければ文字数推定」で埋める
(0.0だとプレイヤーが最初の画像で固定されるため禁止)。
※これは中間状態。公開前に必ず gen_episode_aivis.py で実測retimeすること。
"""
import sys, os, json
from pathlib import Path

EP = sys.argv[1] if len(sys.argv) > 1 else "ep04"
ROOT = Path(os.environ.get("MANA_REPO_ROOT",
            r"C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages"))
KAMI = ROOT / "13th-register-kamishibai"

vm_path = KAMI / "assets" / f"manifest_reading_hiragana_{EP}.json"
if not vm_path.exists():
    print(f"{EP}: 音声マニフェストなし -> 同期スキップ")
    sys.exit(0)
vm = json.load(open(vm_path, encoding="utf-8"))
if not any(v.get("synthesis_source") == "aivis_studio" for v in vm):
    print(f"{EP}: スタジオ編集の痕跡なし(aivis_studioなし) -> 同期スキップ")
    sys.exit(0)
plan_path = KAMI / f"visual_cut_plan_{EP}.json"
plan = {c["visualCutId"]: c for c in json.load(open(plan_path, encoding="utf-8"))} if plan_path.exists() else {}

# 既存scene_manifestのタイミングを引き継ぐ(同一idのみ)。無い行は文字数から推定
sc_path = KAMI / f"scene_manifest_{EP}.json"
old_timing = {}
if sc_path.exists():
    for s in json.load(open(sc_path, encoding="utf-8")):
        if s.get("end"):
            old_timing[s["id"]] = (s["start"], s["end"])

def estimate_sec(text):
    return max(0.6, len(text) * 0.14)

scenes = []
cursor = 0.0
for i, v in enumerate(vm, 1):
    vc = v.get("visualCutId") or "vc01"
    c = plan.get(vc, {})
    pi = (c.get("plannedImage") or "").split("?")[0]
    fb = (c.get("fallbackImage") or "").split("?")[0]
    image = pi if (pi and (KAMI / pi).exists()) else fb
    idx = int(vc[2:]) if vc[2:].isdigit() else 1
    title = c.get("title", "")
    # タイミング: 既存id一致なら継承(単調性が崩れたらカーソルから推定し直し)
    ot = old_timing.get(v["id"])
    if ot and ot[0] >= cursor - 0.001:
        start, end = ot
    else:
        start = cursor
        end = cursor + estimate_sec(v.get("text", ""))
    cursor = end + 0.35
    scenes.append({
        "id": v["id"],
        "cut": f"{EP}_{i:03d}",
        "visualCutId": vc,
        "visualCutTitle": title,
        "visualCutIndex": idx,
        "start": round(start, 3),
        "end": round(end, 3),
        "image": image,
        "plannedImage": c.get("plannedImage", ""),
        "fallbackImage": fb,
        "imagePrompt": c.get("prompt", ""),
        "speaker": v.get("character", ""),
        "dialogue": v.get("text", ""),
        "log": [],
        "visualLabel": f"{idx:02d}/20　{title}",
        "progressLabel": f"{i:02d}/{len(vm)}　{v.get('character', '')}",
    })

out = KAMI / f"scene_manifest_{EP}.json"
json.dump(scenes, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"{EP}: {len(scenes)}行を音声マニフェストから同期 -> {out.name}")
print("※タイミングは暫定(既存継承+推定)。公開前に gen_episode_aivis.py で実測retime必須")

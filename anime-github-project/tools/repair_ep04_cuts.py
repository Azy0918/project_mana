# -*- coding: utf-8 -*-
"""ep04のカット割りを既知の正常版(8965295)から復元する(1回限りの修復)。
スタジオが古い行番号のカット範囲と照合できず全行をカット1に落とした事故の修復。
セリフをdifflibで対応付け、一致行は旧visualCutIdを引き継ぎ、
改稿行は直前の行のカットを引き継ぐ(単調非減少を保証)。
visual_cut_plan / voiceマニフェスト / image_assignment を書き直し、
scene_manifest は sync_scene_from_voice.py で再構築する。
"""
import json, subprocess, difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KAMI = ROOT / "13th-register-kamishibai"
GOOD_REF = "8965295"

good = json.loads(subprocess.run(
    ["git", "-C", str(ROOT), "show", f"{GOOD_REF}:13th-register-kamishibai/scene_manifest_ep04.json"],
    capture_output=True).stdout.decode("utf-8"))
vm_path = KAMI / "assets" / "manifest_reading_hiragana_ep04.json"
vm = json.load(open(vm_path, encoding="utf-8"))

old_texts = [s["dialogue"] for s in good]
new_texts = [v["text"] for v in vm]
sm = difflib.SequenceMatcher(a=old_texts, b=new_texts)
vc_new = [None] * len(vm)
for tag, i1, i2, j1, j2 in sm.get_opcodes():
    if tag == "equal":
        for k in range(j2 - j1):
            vc_new[j1 + k] = good[i1 + k]["visualCutId"]

# 未対応行は直前のカットを引き継ぐ(先頭はvc01)。単調非減少を保証
prev = "vc01"
for i, vc in enumerate(vc_new):
    if vc is None or int(vc[2:]) < int(prev[2:]):
        vc_new[i] = prev
    prev = vc_new[i]

# 1) voiceマニフェストへ反映
for v, vc in zip(vm, vc_new):
    v["visualCutId"] = vc
json.dump(vm, open(vm_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# 2) visual_cut_plan の lineStart/lineEnd を再構築
plan_path = KAMI / "visual_cut_plan_ep04.json"
plan = json.load(open(plan_path, encoding="utf-8"))
by_vc = {}
for v, vc in zip(vm, vc_new):
    by_vc.setdefault(vc, []).append(v["id"])
for c in plan:
    ids = by_vc.get(c["visualCutId"], [])
    c["lineStart"] = ids[0] if ids else ""
    c["lineEnd"] = ids[-1] if ids else ""
json.dump(plan, open(plan_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

# 3) image_assignment を再構築
ia_path = KAMI / "image_assignment_ep04.json"
plan_img = {c["visualCutId"]: (c.get("plannedImage") or "").split("?")[0] for c in plan}
assignments = {v["id"]: plan_img.get(vc, "") for v, vc in zip(vm, vc_new)}
json.dump({"version": 1, "episode": "ep04", "assetVersion": "cut-repair-20260710",
           "assignments": assignments},
          open(ia_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

from collections import Counter
print("復元結果:", sorted(Counter(vc_new).items()))

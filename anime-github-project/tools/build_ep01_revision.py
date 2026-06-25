from __future__ import annotations

"""Apply the EP01 script-consistency revision and rebuild scene_manifest.

Stage 'reading' edits the EP01 reading-hiragana manifest (manifest_reading_
hiragana_mina_mao.json) in both player trees:
  * Mina's history-memo line becomes two lines (matches EP02's "二行" line).
  * Takumi's tsukkomi "二文字で通るんだ！" -> "そんなメモで通るんだ！".
  * Receipt narration "歴史メモ" -> "履歴メモ" (term unification).
Then synthesize with generate_ep02_full_voice.py pointed at this manifest.
Stage 'scene' rebuilds scene_manifest.json from the edited manifest, the fresh
synth timeline, and the per-line visual data carried by the old manifest.
"""

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KAMI = REPO / "13th-register-kamishibai"
SITE = REPO / "site"
MANIFEST_REL = "assets/manifest_reading_hiragana_mina_mao.json"
TIMELINE = REPO / "outputs" / "ep01_voice_reading_hiragana" / "ep01_full_voice_reading_hiragana_mina_mao_timeline.json"


def edit_manifest(entries: list[dict]) -> list[dict]:
    out: list[dict] = []
    for e in entries:
        eid = e["id"]
        if eid == "ep01_v066_g2":  # Mina memo line 1 (was "ちゃんと作る。")
            e = dict(e)
            e["text"] = "このおにぎりは、ちゃんと作る。"
            e["synthesis_text"] = "このおにぎりワ、ちゃんとつくる。"
            out.append(e)
            # Mina memo line 2 (new) — inherits Mina cast from g2.
            g3 = dict(e)
            g3["id"] = "ep01_v066_g3"
            g3["text"] = "なくなると困る人がいる。"
            g3["synthesis_text"] = "なくなるとこまるひとがいる。"
            g3["clip"] = "outputs\\ep01_voice_reading_hiragana\\clips\\ep01_v066_g3.wav"
            out.append(g3)
            continue
        if eid == "ep01_v068":  # Takumi tsukkomi
            e = dict(e)
            e["text"] = "そんなメモで通るんだ！"
            e["synthesis_text"] = "そんなめもで、とおるんだ！"
        elif eid == "ep01_v076":  # receipt narration 歴史メモ -> 履歴メモ
            e = dict(e)
            e["text"] = e["text"].replace("歴史メモ", "履歴メモ")
            e["synthesis_text"] = e["synthesis_text"].replace("れきしめも", "りれきめも")
        out.append(e)
    return out


def build_reading() -> None:
    src = KAMI / MANIFEST_REL
    entries = json.loads(src.read_text(encoding="utf-8"))
    # Guard against double-apply.
    if any(x["id"] == "ep01_v066_g3" for x in entries):
        print("reading: already revised (ep01_v066_g3 present) — re-applying edits idempotently")
        entries = [x for x in entries if x["id"] != "ep01_v066_g3"]
    new = edit_manifest(entries)
    blob = json.dumps(new, ensure_ascii=False, indent=2)
    for base in (KAMI, SITE):
        p = base / MANIFEST_REL
        if base is KAMI or p.exists():
            p.write_text(blob, encoding="utf-8")
            print(f"reading -> {p}  ({len(new)} lines)")


def build_scene() -> None:
    manifest = json.loads((KAMI / MANIFEST_REL).read_text(encoding="utf-8"))
    tl = {e["id"]: e for e in json.loads(TIMELINE.read_text(encoding="utf-8"))}
    old = json.loads((KAMI / "scene_manifest.json").read_text(encoding="utf-8"))
    oldbyid = {e["id"]: e for e in old}

    VIS = ("visualCutId", "visualCutTitle", "visualCutIndex", "image",
           "plannedImage", "fallbackImage", "imagePrompt", "visualLabel")
    total = len(manifest)
    scenes = []
    last_vis = None
    for i, e in enumerate(manifest, 1):
        ref = oldbyid.get(e["id"])
        if ref is not None:
            last_vis = {k: ref.get(k) for k in VIS}
        vis = last_vis  # new line (g3) inherits the previous line's visual cut
        t = tl[e["id"]]
        ch = e["character"]
        scenes.append({
            "id": e["id"],
            "cut": e.get("cut"),
            "visualCutId": vis["visualCutId"],
            "visualCutTitle": vis["visualCutTitle"],
            "visualCutIndex": vis["visualCutIndex"],
            "start": t["start"],
            "end": t["end"],
            "image": vis["image"],
            "plannedImage": vis["plannedImage"],
            "fallbackImage": vis["fallbackImage"],
            "imagePrompt": vis["imagePrompt"],
            "speaker": ch,
            "dialogue": e["text"],
            "reading": e["synthesis_text"],
            "log": [f"発話ログ　{i:02d}/{total}", f"担当　{ch}", "本日の営業　継続中"],
            "visualLabel": vis["visualLabel"],
            "progressLabel": f"{i:02d}/{total}　{ch}",
        })
    blob = json.dumps(scenes, ensure_ascii=False, indent=2)
    for base in (KAMI, SITE):
        p = base / "scene_manifest.json"
        if base is KAMI or p.exists():
            p.write_text(blob, encoding="utf-8")
            print(f"scene   -> {p}  ({len(scenes)} lines, last end={scenes[-1]['end']:.1f}s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["reading", "scene"])
    args = ap.parse_args()
    {"reading": build_reading, "scene": build_scene}[args.stage]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

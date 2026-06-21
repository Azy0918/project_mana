from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# Repo root is two levels up from anime-github-project/tools/.
REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_MANIFEST = REPO_ROOT / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_ep05.json"
TIMELINE = REPO_ROOT / "outputs" / "ep05_voice_reading_hiragana" / "ep05_full_voice_reading_hiragana_timeline.json"
# Image assignment source of truth. Default is Codex's file; EP05 ships from Claude's
# content-based proposal (62 final line ids -> Codex's 20 images) until Codex adopts it.
DEFAULT_ASSIGNMENT = REPO_ROOT / "ep05_image_assignment_proposal.json"
OUT_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "scene_manifest_ep05.json",
    REPO_ROOT / "site" / "scene_manifest_ep05.json",
]

# Claude-owned (台本): visual-cut titles keyed by the IMAGE vc number. Codex segmented EP05
# into 20 image beats (more than the 19 dialogue cuts), so visualCut* follows the image.
TITLE_BY_CUT = {
    1: "古い紙束", 2: "昭和五十八年", 3: "伝票は諦めない", 4: "レジ読み込み", 5: "未来の封印記録",
    6: "古紙の匂い", 7: "銀色の繊維", 8: "偽装ログ", 9: "仕分け作業", 10: "分類精度六十八",
    11: "昔の雑貨屋", 12: "夜の人を助けた店", 13: "判断保留", 14: "処理選択", 15: "保留のハンコ",
    16: "未処理から保留へ", 17: "レシート", 18: "テプラ", 19: "伝票ファイル", 20: "夜勤のマニュアル",
}
CUT_TOTAL = 20

# Claude-owned (台本): the 13th register's printed receipt for the receipt cut (image vc17).
# Surfaced in the player's operation-log overlay (the player filters the generic 発話ログ lines).
LOG_BY_CUT = {
    17: [
        "昭和伝票　整理済み",
        "牛乳・食パン・乾電池　過去処理",
        "記憶返品タグ　保留",
        "危険知識封印　開封厳禁",
        "店長確認　未了",
        "伝票ファイル　背表紙不明",
    ],
}


def vc_from_path(path: str) -> int:
    """Reverse-look up the vc number from an image path (ignoring any ?v= suffix)."""
    match = re.search(r"vc(\d+)", path or "")
    return int(match.group(1)) if match else 0


def versioned(path: str, asset_version: str) -> str:
    if not asset_version:
        return path
    return f"{path}{'&' if '?' in path else '?'}v={asset_version}"


def load_assignment(path: Path) -> tuple[dict[str, str], str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("assignments", {}), str(data.get("assetVersion", "")).strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build episode 5 scene manifest from the voice manifest, audio timeline and image assignment."
    )
    parser.add_argument("--assignment", type=Path, default=DEFAULT_ASSIGNMENT)
    parser.add_argument("--no-visual-plan", action="store_true", help="Accepted for parity; visual_cut_plan is Codex-managed.")
    args = parser.parse_args()

    voice = json.loads(VOICE_MANIFEST.read_text(encoding="utf-8"))
    timeline = {row["id"]: row for row in json.loads(TIMELINE.read_text(encoding="utf-8"))}
    assignments, asset_version = load_assignment(args.assignment)

    skipped = [entry["id"] for entry in voice if entry["id"] not in timeline]
    if skipped:
        print(f"skipping lines missing from audio timeline: {', '.join(skipped)}")
    voice = [entry for entry in voice if entry["id"] in timeline]

    missing = [entry["id"] for entry in voice if entry["id"] not in assignments]
    if missing:
        print(f"ERROR: {args.assignment.name} missing {len(missing)} line(s): {', '.join(missing)}")
        return 1

    total = len(voice)
    fallback = versioned(assignments[voice[0]["id"]], asset_version) if voice else ""
    scenes: list[dict] = []
    for index, entry in enumerate(voice, start=1):
        line_id = entry["id"]
        character = entry["character"]
        assigned = assignments[line_id]
        image_vc = vc_from_path(assigned)
        image = versioned(assigned, asset_version)
        title = TITLE_BY_CUT.get(image_vc, entry.get("cut", ""))
        tl = timeline.get(line_id, {})
        log = LOG_BY_CUT.get(image_vc) or [
            f"発話ログ　{index:02d}/{total}",
            f"担当　{character}",
            "深夜帯　進行中",
        ]
        scenes.append(
            {
                "id": line_id,
                "cut": entry.get("cut"),
                "visualCutId": f"vc{image_vc:02d}",
                "visualCutTitle": title,
                "visualCutIndex": image_vc,
                "start": tl.get("start", 0.0),
                "end": tl.get("end", 0.0),
                "image": image,
                "plannedImage": image,
                "fallbackImage": fallback,
                "imagePrompt": "",
                "speaker": character,
                "dialogue": entry["text"],
                "reading": entry["synthesis_text"],
                "log": log,
                "visualLabel": f"{image_vc:02d}/{CUT_TOTAL}　{title}",
                "progressLabel": f"{index:02d}/{total}　{character}",
            }
        )

    payload = json.dumps(scenes, ensure_ascii=False, indent=2) + "\n"
    for out_path in OUT_PATHS:
        out_path.write_text(payload, encoding="utf-8")
        print(f"wrote {out_path}  ({len(scenes)} scenes)")

    seen = set()
    print("cut -> image")
    for scene in scenes:
        key = (scene["visualCutIndex"], scene["image"])
        if key in seen:
            continue
        seen.add(key)
        print(f"  vc{scene['visualCutIndex']:02d} {scene['visualCutTitle']} -> {Path(scene['image'].split('?')[0]).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

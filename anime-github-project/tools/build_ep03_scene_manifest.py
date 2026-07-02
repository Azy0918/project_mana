from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# Repo root is two levels up from anime-github-project/tools/.
REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_MANIFEST = REPO_ROOT / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_ep03.json"
TIMELINE = REPO_ROOT / "outputs" / "ep03_voice_reading_hiragana" / "ep03_full_voice_reading_hiragana_timeline.json"
# Codex-owned source of truth for per-line image assignment (Claude only reads it).
DEFAULT_ASSIGNMENT = REPO_ROOT / "13th-register-kamishibai" / "image_assignment_ep03.json"
OUT_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "scene_manifest_ep03.json",
]

# Claude-owned: cut titles shown in the player (台本). Derived from the EP03 script beats.
TITLE_BY_CUT = {
    1: "冷凍庫に昨日", 2: "昨日バニラ", 3: "味は？", 4: "温度上昇", 5: "昨日の売上",
    6: "戻ったコーヒー", 7: "汗田、来店", 8: "アイスを差し出す", 9: "時間保存媒体", 10: "昨日に戻る店内",
    11: "第十三レジ出現", 12: "記憶は残る", 13: "昨日に食われた掃除", 14: "それはまずい", 15: "袋分けの提案",
    16: "袋分けの理屈", 17: "袋二枚", 18: "青白い処理", 19: "保冷剤と完了", 20: "レシートと夜勤",
}

# Claude-owned (台本): the 13th register's printed receipt for the closing cut. Surfaced
# in the player's operation-log overlay (the player filters out the generic 発話ログ/担当/深夜帯).
LOG_BY_CUT = {
    20: [
        "時刻分離処理　一件",
        "昨日保存　一件",
        "明日ミルク　保留　一件",
        "スタッフ休憩　未取得",
        "袋代　二円",
    ],
}

# Codex-owned: per-image-vc prompt text (image_vc -> prompt string). Empty until Codex
# populates it; while empty, scene_manifest.imagePrompt is "" (a placeholder for the
# provisional build). The scene intent for each cut lives in ep03_image_request_sheet.md.
EP03_IMAGE_PROMPTS: dict[int, str] = {}


def cut_number(cut: str) -> int:
    match = re.search(r"vc(\d+)", cut or "")
    return int(match.group(1)) if match else 0


def vc_from_path(path: str) -> int:
    """Reverse-look up the vc number from an image path (ignoring any ?v= suffix)."""
    match = re.search(r"vc(\d+)", path or "")
    return int(match.group(1)) if match else 0


def versioned(path: str, asset_version: str) -> str:
    """Append ?v=assetVersion for image cache busting (data-driven; player uses it as-is)."""
    if not asset_version:
        return path
    return f"{path}{'&' if '?' in path else '?'}v={asset_version}"


def load_assignment(path: Path) -> tuple[dict[str, str], str]:
    """Read the per-line image assignment (Codex source of truth). Claude never edits its content."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("assignments", {}), str(data.get("assetVersion", "")).strip()


def image_prompt(image_vc: int) -> str:
    return EP03_IMAGE_PROMPTS.get(image_vc, "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build episode 3 scene manifest from the voice manifest, audio timeline and image_assignment."
    )
    parser.add_argument(
        "--assignment",
        type=Path,
        default=DEFAULT_ASSIGNMENT,
        help="Image assignment JSON (Codex source of truth). Use a proposal file for provisional builds.",
    )
    parser.add_argument(
        "--no-visual-plan",
        action="store_true",
        help="Accepted for command parity with EP02; EP03 visual_cut_plan is Codex-managed and never written here.",
    )
    args = parser.parse_args()

    voice = json.loads(VOICE_MANIFEST.read_text(encoding="utf-8"))
    timeline = {row["id"]: row for row in json.loads(TIMELINE.read_text(encoding="utf-8"))}
    assignments, asset_version = load_assignment(args.assignment)

    skipped = [entry["id"] for entry in voice if entry["id"] not in timeline]
    if skipped:
        print(f"skipping lines missing from audio timeline: {', '.join(skipped)}")
    voice = [entry for entry in voice if entry["id"] in timeline]

    # Image assignment is the sole source; no implicit fallback. Error on any gap.
    missing = [entry["id"] for entry in voice if entry["id"] not in assignments]
    if missing:
        print(f"ERROR: {args.assignment.name} missing {len(missing)} line(s): {', '.join(missing)}")
        return 1

    total = len(voice)
    fallback = versioned(assignments[voice[0]["id"]], asset_version) if voice else ""
    scenes: list[dict] = []
    for index, entry in enumerate(voice, start=1):
        line_id = entry["id"]
        cut = entry["cut"]
        cut_num = cut_number(cut)
        character = entry["character"]
        title = TITLE_BY_CUT.get(cut_num, cut)
        assigned = assignments[line_id]            # Codex source-of-truth path (no ?v)
        image_vc = vc_from_path(assigned)
        image = versioned(assigned, asset_version)  # append ?v=assetVersion for cache busting
        tl = timeline.get(line_id, {})
        log = LOG_BY_CUT.get(cut_num) or [
            f"発話ログ　{index:02d}/{total}",
            f"担当　{character}",
            "深夜帯　進行中",
        ]
        scenes.append(
            {
                "id": line_id,
                "cut": cut,
                "visualCutId": f"vc{cut_num:02d}",
                "visualCutTitle": title,
                "visualCutIndex": cut_num,
                "start": tl.get("start", 0.0),
                "end": tl.get("end", 0.0),
                "image": image,
                "plannedImage": image,
                "fallbackImage": fallback,
                "imagePrompt": image_prompt(image_vc),
                "speaker": character,
                "dialogue": entry["text"],
                "reading": entry["synthesis_text"],
                "log": log,
                "visualLabel": f"{cut_num:02d}/20　{title}",
                "progressLabel": f"{index:02d}/{total}　{character}",
            }
        )

    payload = json.dumps(scenes, ensure_ascii=False, indent=2) + "\n"
    for out_path in OUT_PATHS:
        out_path.write_text(payload, encoding="utf-8")
        print(f"wrote {out_path}  ({len(scenes)} scenes)")

    # Quick report: which image each cut resolved to.
    seen = set()
    print("cut -> image")
    for scene in scenes:
        key = (scene["visualCutIndex"], scene["image"])
        if key in seen:
            continue
        seen.add(key)
        print(f"  cut{scene['visualCutIndex']:02d} {scene['visualCutTitle']:　<12} -> {Path(scene['image'].split('?')[0]).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

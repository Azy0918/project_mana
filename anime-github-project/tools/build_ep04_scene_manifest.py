from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


# Repo root is two levels up from anime-github-project/tools/.
REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_MANIFEST = REPO_ROOT / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_ep04.json"
TIMELINE = REPO_ROOT / "outputs" / "ep04_voice_reading_hiragana" / "ep04_full_voice_reading_hiragana_timeline.json"
# Codex-owned source of truth for per-line image assignment (Claude only reads it).
DEFAULT_ASSIGNMENT = REPO_ROOT / "13th-register-kamishibai" / "image_assignment_ep04.json"
OUT_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "scene_manifest_ep04.json",
]

# Claude-owned: cut titles shown in the player (台本). Derived from the EP04 script beats.
TITLE_BY_CUT = {
    1: "コピー機起動", 2: "未来クレーム印刷", 3: "未来クレーム", 4: "座木山来店", 5: "先に謝る",
    6: "第十三レジ出現", 7: "思い出の温度", 8: "汗田登場", 9: "謝りすぎ注意", 10: "商品が謝る",
    11: "まず挨拶", 12: "運転手来店", 13: "気持ちは熱め", 14: "一口の記憶", 15: "袋はいらない",
    16: "クレーム回避", 17: "謝罪を返品", 18: "レシート", 19: "返品済み青年", 20: "夜勤のノート",
}

# Claude-owned (台本): the 13th register's printed receipt for the closing cut. Surfaced
# in the player's operation-log overlay (the player filters out the generic 発話ログ/担当/深夜帯).
LOG_BY_CUT = {
    18: [
        "未来クレーム予告　一件",
        "唐揚げ棒　販売完了",
        "未使用謝罪　返品",
        "お客様の思い出　温度一致",
        "コピー代　十円",
        "返品済み青年　記憶封印状態　確認不能",
        "開封厳禁",
    ],
}

# Codex-owned: per-image-vc prompt text (image_vc -> prompt string). Empty until Codex
# populates it; while empty, scene_manifest.imagePrompt is "". The scene intent for each
# cut lives in the EP04 image request (handed to Codex).
EP04_IMAGE_PROMPTS: dict[int, str] = {}


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
    return EP04_IMAGE_PROMPTS.get(image_vc, "")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build episode 4 scene manifest from the voice manifest, audio timeline and image_assignment."
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
        help="Accepted for command parity with EP02/03; EP04 visual_cut_plan is Codex-managed and never written here.",
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

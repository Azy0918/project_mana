from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_MANIFEST = REPO_ROOT / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_ep06.json"
TIMELINE = REPO_ROOT / "outputs" / "ep06_voice_reading_hiragana" / "ep06_full_voice_reading_hiragana_timeline.json"
# EP06 ships from Claude's content-based proposal (60 final line ids -> Codex's 20 images);
# Codex's image_assignment_ep06.json draft assumed 100 lines and is not used.
DEFAULT_ASSIGNMENT = REPO_ROOT / "ep06_image_assignment_proposal.json"
OUT_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "scene_manifest_ep06.json",
    REPO_ROOT / "site" / "scene_manifest_ep06.json",
]

# Claude-owned (台本): visual-cut titles keyed by the IMAGE vc number (Codex's 20 EP06 beats).
TITLE_BY_VC = {
    1: "パン棚の袋", 2: "賞味期限がない", 3: "古い紙と焼きたての匂い", 4: "概念成立前", 5: "思い出鮮度",
    6: "古い判断基準", 7: "パンの自己主張", 8: "売れない捨てられない", 9: "試食という難題", 10: "唐沢、巡回",
    11: "売場には出せない", 12: "不明は保留", 13: "保留を受理", 14: "付箋を貼る", 15: "付箋で安定",
    16: "レシート", 17: "バックヤードに明記", 18: "保留箱のパン", 19: "店長確認待ち", 20: "夜勤のマニュアル",
}

# Claude-owned (台本): the 13th register's printed receipt, keyed by the IMAGE vc it appears on.
LOG_BY_VC = {
    16: [
        "賞味期限未成立パン　一件",
        "販売不可　一件",
        "廃棄不可　一件",
        "現代店舗保留　一件",
        "唐沢指摘　有効",
        "店長確認　未了",
    ],
}


def vc_from_path(path: str) -> int:
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
        description="Build episode 6 scene manifest from the voice manifest, audio timeline and image assignment."
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
    # Distinct images in playback order -> a clean ascending scene counter, robust to
    # Codex numbering images out of script order (EP06: vc20 manual precedes vc18/19).
    total_cuts = len({assignments[entry["id"]] for entry in voice})
    fallback = versioned(assignments[voice[0]["id"]], asset_version) if voice else ""
    scenes: list[dict] = []
    prev_image: str | None = None
    seq = 0
    for index, entry in enumerate(voice, start=1):
        line_id = entry["id"]
        character = entry["character"]
        assigned = assignments[line_id]
        if assigned != prev_image:
            seq += 1
            prev_image = assigned
        image_vc = vc_from_path(assigned)
        image = versioned(assigned, asset_version)
        title = TITLE_BY_VC.get(image_vc, entry.get("cut", ""))
        tl = timeline.get(line_id, {})
        log = LOG_BY_VC.get(image_vc) or [
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
                "visualCutIndex": seq,
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
                "visualLabel": f"{seq:02d}/{total_cuts}　{title}",
                "progressLabel": f"{index:02d}/{total}　{character}",
            }
        )

    payload = json.dumps(scenes, ensure_ascii=False, indent=2) + "\n"
    for out_path in OUT_PATHS:
        out_path.write_text(payload, encoding="utf-8")
        print(f"wrote {out_path}  ({len(scenes)} scenes)")

    seen = set()
    print("playback order -> image")
    for scene in scenes:
        if scene["visualCutIndex"] in seen:
            continue
        seen.add(scene["visualCutIndex"])
        print(f"  {scene['visualCutIndex']:02d}/{total_cuts} {scene['visualCutTitle']} -> {Path(scene['image'].split('?')[0]).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

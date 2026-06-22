from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_MANIFEST = REPO_ROOT / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_ep07.json"
TIMELINE = REPO_ROOT / "outputs" / "ep07_voice_reading_hiragana" / "ep07_full_voice_reading_hiragana_timeline.json"
DEFAULT_ASSIGNMENT = REPO_ROOT / "ep07_image_assignment_proposal.json"
OUT_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "scene_manifest_ep07.json",
    REPO_ROOT / "site" / "scene_manifest_ep07.json",
]

# Claude-owned (台本): visual-cut titles keyed by the IMAGE vc number (Codex's 20 EP07 beats).
TITLE_BY_VC = {
    1: "宅配端末が鳴る", 2: "月面の店留め箱", 3: "受取番号は？", 4: "レジが読み取る", 5: "箱の中身",
    6: "無重力プリン", 7: "銀河流通監査局ラベル", 8: "監査局からの通知", 9: "座木山と月面地図", 10: "受取人確認",
    11: "レシートで本人確認", 12: "危険署名の経路", 13: "再配送の判断", 14: "店留め保管料", 15: "再配送ラベル",
    16: "監査局へ通知", 17: "レシート", 18: "月面地図を読む", 19: "宇宙宅配のマニュアル", 20: "地球の物流、夜",
}

# Claude-owned (台本): the 13th register's printed receipt, keyed by the IMAGE vc it appears on.
LOG_BY_VC = {
    17: [
        "宇宙宅配便　再配送　一件",
        "無重力プリン　未開封",
        "月面重力差額　対象外",
        "危険知識署名　一部一致",
        "銀河流通監査局　接続確認",
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
        description="Build episode 7 scene manifest from the voice manifest, audio timeline and image assignment."
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

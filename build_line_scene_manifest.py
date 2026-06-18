import json
import wave
from pathlib import Path


SOURCE_MANIFEST = Path("outputs/ep01_voice_reading_hiragana/manifest_reading_hiragana_mina_mao.json")
VISUAL_CUT_PLAN = Path("13th-register-kamishibai/visual_cut_plan.json")
OUT_PATHS = [
    Path("13th-register-kamishibai/scene_manifest.json"),
    Path("site/scene_manifest.json"),
]


def line_number(line_id: str) -> int:
    return int((line_id or "ep01_v000").split("_v")[-1])


def load_visual_cuts() -> list[dict]:
    cuts = json.loads(VISUAL_CUT_PLAN.read_text(encoding="utf-8"))
    for index, cut in enumerate(cuts, start=1):
        cut["index"] = index
        cut["startNumber"] = line_number(cut["lineStart"])
        cut["endNumber"] = line_number(cut["lineEnd"])
    return cuts


def visual_cut_for_row(row: dict, cuts: list[dict]) -> dict:
    number = line_number(row.get("id"))
    for cut in cuts:
        if cut["startNumber"] <= number <= cut["endNumber"]:
            return cut
    return cuts[-1]


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def log_for(row: dict, index: int) -> list[str]:
    character = row.get("character") or row.get("speaker_name") or ""
    base = [f"発話ログ　{index:02d}/83", f"担当　{character}"]
    if character == "ミナ":
        return base + ["声　まお / ふつー"]
    if character == "第十三レジ":
        return base + ["第十三レジ　応答中"]
    if "未来" in character:
        return base + ["未来案件　処理中"]
    if character == "ナレーション":
        return base + ["深夜帯　進行中"]
    return base + ["本日の営業　継続中"]


def main() -> None:
    rows = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    visual_cuts = load_visual_cuts()
    scenes = []
    cursor = 0.0
    voiced_index = 0

    for row in rows:
        clip = row.get("clip")
        pause = (row.get("pause_after_ms") or 0) / 1000
        if not clip:
            cursor += pause
            continue

        clip_path = Path(clip)
        duration = wav_duration(clip_path)
        start = cursor
        end = cursor + duration
        voiced_index += 1
        character = row.get("character") or row.get("speaker_name") or ""
        visual_cut = visual_cut_for_row(row, visual_cuts)
        visual_label = f"{visual_cut['index']:02d}/{len(visual_cuts)}　{visual_cut['title']}"

        scenes.append(
            {
                "id": row.get("id") or f"line_{voiced_index:03d}",
                "cut": row.get("cut"),
                "visualCutId": visual_cut["visualCutId"],
                "visualCutTitle": visual_cut["title"],
                "visualCutIndex": visual_cut["index"],
                "start": round(start, 3),
                "end": round(end, 3),
                "image": visual_cut["fallbackImage"],
                "plannedImage": visual_cut["plannedImage"],
                "fallbackImage": visual_cut["fallbackImage"],
                "imagePrompt": visual_cut["prompt"],
                "speaker": character,
                "dialogue": row.get("text") or "",
                "reading": row.get("synthesis_text") or "",
                "log": log_for(row, voiced_index),
                "visualLabel": visual_label,
                "progressLabel": f"{voiced_index:02d}/83　{character}",
            }
        )
        cursor = end + pause

    for out_path in OUT_PATHS:
        out_path.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {len(scenes)} scenes, duration {cursor:.3f}s")


if __name__ == "__main__":
    main()

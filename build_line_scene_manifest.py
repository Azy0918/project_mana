import json
import wave
from pathlib import Path


SOURCE_MANIFEST = Path("outputs/ep01_voice_reading_hiragana/manifest_reading_hiragana_mina_mao.json")
OUT_PATHS = [
    Path("13th-register-kamishibai/scene_manifest.json"),
    Path("site/scene_manifest.json"),
]
def image_for_row(row: dict) -> str:
    number = int((row.get("id") or "ep01_v000").split("_v")[-1])
    if number <= 3:
        return "assets/scenes/scene_01_opening.jpg"
    if number <= 10:
        return "assets/scenes/scene_02_onigiri_shelf.jpg"
    if number <= 20:
        return "assets/scenes/scene_03_register.jpg"
    if number <= 42:
        return "assets/scenes/scene_04_future_worker_enters.jpg"
    if number <= 55:
        return "assets/scenes/scene_05_future_onigiri_scan.jpg"
    if number <= 68:
        return "assets/scenes/scene_06_microwave.jpg"
    if number <= 77:
        return "assets/scenes/scene_07_receipt.jpg"
    return "assets/scenes/scene_08_back_to_normal.jpg"


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

        scenes.append(
            {
                "id": row.get("id") or f"line_{voiced_index:03d}",
                "cut": row.get("cut"),
                "start": round(start, 3),
                "end": round(end, 3),
                "image": image_for_row(row),
                "speaker": character,
                "dialogue": row.get("text") or "",
                "reading": row.get("synthesis_text") or "",
                "log": log_for(row, voiced_index),
                "progressLabel": f"{voiced_index:02d}/83　{character}",
            }
        )
        cursor = end + pause

    for out_path in OUT_PATHS:
        out_path.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {len(scenes)} scenes, duration {cursor:.3f}s")


if __name__ == "__main__":
    main()

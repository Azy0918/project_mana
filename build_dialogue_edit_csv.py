import csv
import json
from pathlib import Path


SOURCE = Path("13th-register-kamishibai/scene_manifest.json")
OUT = Path("13th-register-kamishibai/assets/ep01_dialogue_edit.csv")
SITE_OUT = Path("site/assets/ep01_dialogue_edit.csv")


def main() -> None:
    rows = json.loads(SOURCE.read_text(encoding="utf-8"))
    fields = [
        "id",
        "cut",
        "visualCutId",
        "visualCutTitle",
        "visualCutIndex",
        "start",
        "end",
        "speaker",
        "dialogue",
        "reading",
        "visualLabel",
        "progressLabel",
        "image",
        "plannedImage",
        "fallbackImage",
        "imagePrompt",
        "log",
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    SITE_OUT.parent.mkdir(parents=True, exist_ok=True)

    for path in (OUT, SITE_OUT):
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "id": row.get("id", ""),
                        "cut": row.get("cut", ""),
                        "visualCutId": row.get("visualCutId", ""),
                        "visualCutTitle": row.get("visualCutTitle", ""),
                        "visualCutIndex": row.get("visualCutIndex", ""),
                        "start": row.get("start", ""),
                        "end": row.get("end", ""),
                        "speaker": row.get("speaker", ""),
                        "dialogue": row.get("dialogue", ""),
                        "reading": row.get("reading", ""),
                        "visualLabel": row.get("visualLabel", ""),
                        "progressLabel": row.get("progressLabel", ""),
                        "image": row.get("image", ""),
                        "plannedImage": row.get("plannedImage", ""),
                        "fallbackImage": row.get("fallbackImage", ""),
                        "imagePrompt": row.get("imagePrompt", ""),
                        "log": " / ".join(row.get("log", [])),
                    }
                )
        print(path)


if __name__ == "__main__":
    main()

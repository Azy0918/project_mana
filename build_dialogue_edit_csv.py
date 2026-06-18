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
        "start",
        "end",
        "speaker",
        "dialogue",
        "reading",
        "progressLabel",
        "image",
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
                        "start": row.get("start", ""),
                        "end": row.get("end", ""),
                        "speaker": row.get("speaker", ""),
                        "dialogue": row.get("dialogue", ""),
                        "reading": row.get("reading", ""),
                        "progressLabel": row.get("progressLabel", ""),
                        "image": row.get("image", ""),
                        "log": " / ".join(row.get("log", [])),
                    }
                )
        print(path)


if __name__ == "__main__":
    main()

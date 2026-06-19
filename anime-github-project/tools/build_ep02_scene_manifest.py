from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_MANIFEST = REPO_ROOT / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_ep02.json"
TIMELINE = REPO_ROOT / "outputs" / "ep02_voice_reading_hiragana" / "ep02_full_voice_reading_hiragana_timeline.json"
OUT_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "scene_manifest_ep02.json",
    REPO_ROOT / "site" / "scene_manifest_ep02.json",
]
IMG_DIR = "assets/scenes/planned"

# Short Japanese title per manifest cut (describes what is heard in that cut).
TITLE_BY_CUT = {
    1: "会社の駐輪場", 2: "ナビが点灯する", 3: "未来からの呼びかけ", 4: "夜の国道へ",
    5: "レシートの保管", 6: "汗田、来店", 7: "二時十七分から", 8: "第十三レジ出現",
    9: "ナビとの接続", 10: "在庫予測モデル", 11: "欠けた歴史メモ", 12: "足りない条件",
    13: "修正メモを入力", 14: "汗田、メモを書く", 15: "数値だけじゃない", 16: "メモ受理",
    17: "未来からの感謝", 18: "ブラックで", 19: "吐き出されたレシート", 20: "次の異常地点",
}

# The 20 published cut images, by their own vc number.
IMAGE_FILE = {
    1: "ep02_vc01_company_parking_asada.png",
    2: "ep02_vc02_nav_lights_up.png",
    3: "ep02_vc03_night_ride.png",
    4: "ep02_vc04_receipt_storage.png",
    5: "ep02_vc05_aseda_enters.png",
    6: "ep02_vc06_register_appears.png",
    7: "ep02_vc07_nav_scan.png",
    8: "ep02_vc08_inventory_model.png",
    9: "ep02_vc09_missing_conditions.png",
    10: "ep02_vc10_corrected_memo.png",
    11: "ep02_vc11_human_criterion.png",
    12: "ep02_vc12_memo_accepted.png",
    13: "ep02_vc13_future_thanks.png",
    14: "ep02_vc14_black_coffee.png",
    15: "ep02_vc15_operation_log.png",
    16: "ep02_vc16_freezer_label.png",
    17: "ep02_vc17_cleaning_first.png",
    18: "ep02_vc18_aseda_leaves.png",
    19: "ep02_vc19_next_anomaly_nav.png",
    20: "ep02_vc20_night_shift_continues.png",
}

# Content-aligned mapping: manifest cut number -> image vc number.
# The published images run ahead of the manifest cut tags, so this realigns each
# scene to the image that actually depicts it (verified by viewing all 20 images).
IMAGE_VC_BY_CUT = {
    1: 1, 2: 2, 3: 3, 4: 3, 5: 4, 6: 5, 7: 6, 8: 6, 9: 7, 10: 8,
    11: 9, 12: 9, 13: 9, 14: 10, 15: 11, 16: 12, 17: 13, 18: 14, 19: 15,
    20: None,  # final cut spreads its five lines across the five ending images
}

# Final cut (vc20) line -> image vc, so all 20 images are used.
PER_LINE_IMAGE_VC = {
    "ep02_v059": 16,  # 冷凍庫の青いラベルが光る
    "ep02_v060": 20,  # 次回予告より夜勤の通常運転へ戻す
    "ep02_v061": 20,  # 先に掃除
    "ep02_v062": 20,  # 夜勤は続く
    "ep02_v063": 18,  # 汗田、コーヒーを持って退店
}


def cut_number(cut: str) -> int:
    match = re.search(r"vc(\d+)", cut or "")
    return int(match.group(1)) if match else 0


def main() -> int:
    voice = json.loads(VOICE_MANIFEST.read_text(encoding="utf-8"))
    timeline = {row["id"]: row for row in json.loads(TIMELINE.read_text(encoding="utf-8"))}

    total = len(voice)
    scenes: list[dict] = []
    for index, entry in enumerate(voice, start=1):
        line_id = entry["id"]
        cut = entry["cut"]
        cut_num = cut_number(cut)
        character = entry["character"]
        title = TITLE_BY_CUT.get(cut_num, cut)
        image_vc = PER_LINE_IMAGE_VC.get(line_id) or IMAGE_VC_BY_CUT.get(cut_num) or cut_num
        image = f"{IMG_DIR}/{IMAGE_FILE[image_vc]}"
        tl = timeline.get(line_id, {})
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
                "fallbackImage": f"{IMG_DIR}/{IMAGE_FILE[1]}",
                "speaker": character,
                "dialogue": entry["text"],
                "reading": entry["synthesis_text"],
                "log": [
                    f"発話ログ　{index:02d}/{total}",
                    f"担当　{character}",
                    "深夜帯　進行中",
                ],
                "visualLabel": f"{cut_num:02d}/20　{title}",
                "progressLabel": f"{index:02d}/{total}　{character}",
            }
        )

    payload = json.dumps(scenes, ensure_ascii=False, indent=2)
    for out_path in OUT_PATHS:
        out_path.write_text(payload, encoding="utf-8")
        print(f"wrote {out_path}  ({len(scenes)} scenes)")

    # Quick report: which image each cut resolved to.
    seen_cut = set()
    print("cut -> image")
    for scene in scenes:
        c = scene["visualCutIndex"]
        key = (c, scene["image"])
        if key in seen_cut:
            continue
        seen_cut.add(key)
        print(f"  cut{c:02d} {scene['visualCutTitle']:　<10} -> {Path(scene['image']).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

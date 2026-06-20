from __future__ import annotations

import csv
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VOICE_MANIFEST = REPO_ROOT / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_ep02.json"
TIMELINE = REPO_ROOT / "outputs" / "ep02_voice_reading_hiragana" / "ep02_full_voice_reading_hiragana_timeline.json"
CHARACTER_LOCKS = REPO_ROOT / "13th-register-kamishibai" / "character_visual_locks.json"
OUT_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "scene_manifest_ep02.json",
    REPO_ROOT / "site" / "scene_manifest_ep02.json",
]
VISUAL_PLAN_JSON_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "visual_cut_plan_ep02.json",
    REPO_ROOT / "site" / "visual_cut_plan_ep02.json",
]
VISUAL_PLAN_CSV_PATHS = [
    REPO_ROOT / "13th-register-kamishibai" / "assets" / "ep02_visual_cut_plan.csv",
    REPO_ROOT / "site" / "assets" / "ep02_visual_cut_plan.csv",
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

IMAGE_TITLE = {
    1: "会社の駐輪場",
    2: "ナビが点灯する",
    3: "夜の国道へ",
    4: "レシートの保管",
    5: "汗田、来店",
    6: "第十三レジ出現",
    7: "ナビとの接続",
    8: "在庫予測モデル",
    9: "欠けた歴史メモ",
    10: "修正メモを書く",
    11: "数値だけじゃない",
    12: "メモ受理",
    13: "未来からの感謝",
    14: "ブラックで",
    15: "吐き出されたレシート",
    16: "冷凍庫の青いラベル",
    17: "清掃へ戻る",
    18: "汗田、退店",
    19: "次の異常地点ナビ",
    20: "夜勤は続く",
}

# Content-aligned mapping: manifest cut number -> image vc number.
# The published images run ahead of the manifest cut tags, so this realigns each
# scene to the image that actually depicts it (verified by viewing all 20 images).
IMAGE_VC_BY_CUT = {
    1: 1, 2: 2, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 6, 9: 7, 10: 8,
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

# Custom operation-log / receipt content per cut (overrides the generic status log).
# Surfaces the 13th register's printed receipt so audio-only viewers get the referent
# (e.g. タクミ's "店長、関係ありました？" reacts to the "店長確認　未了" line).
LOG_BY_CUT = {
    19: [
        "評価基準追加　一件",
        "食べた人間の表情　重要",
        "汗田竜司　接続登録",
        "ホットコーヒー　ブラック　一件",
        "店長確認　未了",
    ],
}

EP02_IMAGE_PROMPTS = {
    1: ("会社の駐輪場。雨の夜、汗田が黒いCB200X風アドベンチャーバイクの横に立ち、紫のフルフェイスヘルメットを自然に持つ。ヘルメットを持つ手は外側から縁またはストラップをつかみ、指がめり込まない。", ["aseda_ryuji", "navigation_terminal_ep02"]),
    2: ("雨の駐輪場で汗田がバイクのナビに話しかける。ナビ画面は汗田の方を向き、シアンに発光する地図を表示する。紫ヘルメットと黒いバイクは同じ形状で統一。", ["aseda_ryuji", "navigation_terminal_ep02"]),
    3: ("夜の国道へ走り出す汗田。黒いCB200X風アドベンチャーバイク、紫ヘルメット、シアンに光る小型ナビ端末。走行中も手と視線が自然で、ヘルメット形状を変えない。", ["aseda_ryuji", "navigation_terminal_ep02"]),
    4: ("深夜コンビニ店内。タクミが前話の時空返品レシートを透明袋に保管している。ミナは淡々と見守る。制服、髪型、名札位置を固定。", ["takumi", "mina"]),
    5: ("自動ドアが開き、汗田が紫ヘルメットを持ってコンビニに入る。タクミとミナがカウンター付近で対応する。汗田、タクミ、ミナの顔と制服を固定。", ["aseda_ryuji", "takumi", "mina"]),
    6: ("午前二時十七分、第十三レジが現れる。黒いセルフレジ端末の眠そうなシアン顔。汗田は状況を観察し、タクミは困惑、ミナは平常運転。", ["thirteenth_register", "aseda_ryuji", "takumi", "mina"]),
    7: ("第十三レジが汗田のバイクナビを読み取る。カウンター上のナビ端末は小型のまま、シアン発光。汗田の視線はナビとレジへ自然に向く。", ["thirteenth_register", "aseda_ryuji", "navigation_terminal_ep02", "takumi", "mina"]),
    8: ("第十三レジの画面に在庫予測モデルのようなシアンの図が映る。汗田が技術者として読み解く。ナビ端末と第十三レジのサイズ感を固定。", ["thirteenth_register", "aseda_ryuji", "navigation_terminal_ep02", "takumi", "mina"]),
    9: ("第十三レジが欠けた歴史メモを示す。レシート、端末画面、業務ログが静かに光る。人物は顔・髪型・制服を統一し、情報量を詰め込みすぎない。", ["thirteenth_register", "aseda_ryuji", "takumi", "mina"]),
    10: ("汗田がレシート紙を受け取り、ペンで修正メモを書く。空中UIには書かず、紙のレシートに直接書く。手指は自然で、ペンと紙が明確。", ["aseda_ryuji", "takumi", "mina", "thirteenth_register"]),
    11: ("タクミとミナが汗田の判断を見守る。第十三レジは無表情に処理を待つ。制服と髪型を固定し、タクミとミナを別人化しない。", ["takumi", "mina", "aseda_ryuji", "thirteenth_register"]),
    12: ("第十三レジが修正メモを受理する。レシート排出口から紙が出て、シアンの光が落ち着く。レジの顔は二本の水平な目と小さな口だけ。", ["thirteenth_register", "aseda_ryuji", "takumi", "mina"]),
    13: ("ナビ画面に未来からの感謝メッセージが浮かぶ。カウンター上のナビ端末は小型のバイク用ナビサイズで、巨大化しない。", ["navigation_terminal_ep02", "aseda_ryuji", "takumi", "mina", "thirteenth_register"]),
    14: ("ミナがブラックコーヒーを一杯だけ汗田へ渡す。汗田はまだコーヒーを持っておらず、受け取ろうとしている。二重のコーヒーを描かない。", ["mina", "aseda_ryuji", "takumi"]),
    15: ("第十三レジが運用ログのレシートを吐き出す。カウンター、レシート、黒いレジ端末を中心にした静かな業務オチ。", ["thirteenth_register", "takumi", "mina", "aseda_ryuji"]),
    16: ("バックヤードの冷凍庫の奥で、青いラベルが小さく光る。人物は出さず、次の異常を予告する静物カット。", []),
    17: ("閉店前ではなく深夜営業中の通常業務へ戻る。タクミとミナが清掃用具の前で次の作業を確認する。顔、髪型、制服を固定。", ["takumi", "mina"]),
    18: ("汗田がコーヒーを持って外へ出る。紫ヘルメット、黒いバイクジャケット、雨のコンビニ外観。汗田の顔と髪型を固定。", ["aseda_ryuji", "navigation_terminal_ep02"]),
    19: ("バイクナビに次の異常地点が小さく表示される。ナビ端末は小型、防水黒ケース、シアン画面。紫ヘルメットと雨のコンビニ外観を添える。", ["navigation_terminal_ep02", "aseda_ryuji"]),
    20: ("深夜コンビニの通常業務に戻る。タクミとミナ、床清掃、棚、レジ周り。大事件の後でも普通の夜勤が続く空気。", ["takumi", "mina", "thirteenth_register"]),
}


def cut_number(cut: str) -> int:
    match = re.search(r"vc(\d+)", cut or "")
    return int(match.group(1)) if match else 0


def load_locks() -> tuple[dict[str, str], str]:
    locks = json.loads(CHARACTER_LOCKS.read_text(encoding="utf-8"))
    by_id = {row["id"]: row["lockPrompt"] for row in locks["characters"]}
    return by_id, locks["styleLock"]


def image_prompt(image_vc: int, locks: dict[str, str], style_lock: str) -> str:
    base, lock_ids = EP02_IMAGE_PROMPTS[image_vc]
    lock_text = " ".join(locks[lock_id] for lock_id in lock_ids)
    return f"{base} {lock_text} {style_lock}"


def main() -> int:
    voice = json.loads(VOICE_MANIFEST.read_text(encoding="utf-8"))
    timeline = {row["id"]: row for row in json.loads(TIMELINE.read_text(encoding="utf-8"))}
    locks, style_lock = load_locks()
    skipped = [entry["id"] for entry in voice if entry["id"] not in timeline]
    if skipped:
        print(f"skipping lines missing from audio timeline: {', '.join(skipped)}")
    voice = [entry for entry in voice if entry["id"] in timeline]

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
                "fallbackImage": f"{IMG_DIR}/{IMAGE_FILE[1]}",
                "imagePrompt": image_prompt(image_vc, locks, style_lock),
                "speaker": character,
                "dialogue": entry["text"],
                "reading": entry["synthesis_text"],
                "log": log,
                "visualLabel": f"{cut_num:02d}/20　{title}",
                "progressLabel": f"{index:02d}/{total}　{character}",
            }
        )

    payload = json.dumps(scenes, ensure_ascii=False, indent=2)
    for out_path in OUT_PATHS:
        out_path.write_text(payload, encoding="utf-8")
        print(f"wrote {out_path}  ({len(scenes)} scenes)")

    visual_plan = []
    for image_vc in range(1, 21):
        image = f"{IMG_DIR}/{IMAGE_FILE[image_vc]}"
        title = IMAGE_TITLE.get(image_vc, f"vc{image_vc:02d}")
        visual_plan.append(
            {
                "visualCutId": f"vc{image_vc:02d}",
                "title": title,
                "plannedImage": image,
                "fallbackImage": f"{IMG_DIR}/{IMAGE_FILE[1]}",
                "prompt": image_prompt(image_vc, locks, style_lock),
            }
        )
    visual_plan_payload = json.dumps(visual_plan, ensure_ascii=False, indent=2)
    for out_path in VISUAL_PLAN_JSON_PATHS:
        out_path.write_text(visual_plan_payload, encoding="utf-8")
        print(f"wrote {out_path}  ({len(visual_plan)} visual cuts)")
    for out_path in VISUAL_PLAN_CSV_PATHS:
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["visualCutId", "title", "plannedImage", "fallbackImage", "prompt"],
            )
            writer.writeheader()
            writer.writerows(visual_plan)
        print(f"wrote {out_path}  ({len(visual_plan)} visual cuts)")

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

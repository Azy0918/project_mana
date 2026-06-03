from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path
from typing import Iterable


DEFAULT_DB = Path("data/cards.db")
DEFAULT_CSV = Path("data/cards.csv")
DEFAULT_REPORT = Path("data/reports/tag_enrichment_report.md")
DEFAULT_TAGGED_CSV = Path("data/cards_tagged.csv")


def norm(value) -> str:
    return "" if value is None else str(value)


def add(tags: set[str], *items: str) -> None:
    for item in items:
        if item:
            tags.add(item)


def contains_any(text: str, patterns: Iterable[str]) -> bool:
    return any(p in text for p in patterns)


def regex_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def safe_cost(card: dict) -> int:
    try:
        return int(float(str(card.get("cost") or "0").strip() or 0))
    except Exception:
        return 0


def safe_power_int(card: dict) -> int:
    text = str(card.get("power") or "").replace(",", "").replace("+", "").strip()
    m = re.search(r"\d+", text)
    if not m:
        return 0
    try:
        return int(m.group(0))
    except Exception:
        return 0


def infer_tags(card: dict) -> set[str]:
    name = norm(card.get("name"))
    civ = norm(card.get("civilization"))
    card_type = norm(card.get("card_type"))
    race = norm(card.get("race"))
    text = norm(card.get("text"))
    power = norm(card.get("power"))
    cost = safe_cost(card)
    power_i = safe_power_int(card)

    blob = "\n".join([name, civ, card_type, race, text, power])
    tags: set[str] = set()

    # Basic type tags
    if "クリーチャー" in card_type:
        add(tags, "クリーチャー")
    if "呪文" in card_type:
        add(tags, "呪文")
    if "タマシード" in card_type:
        add(tags, "タマシード")
    if "フィールド" in card_type:
        add(tags, "フィールド")
    if "城" in card_type:
        add(tags, "城")
    if "クロスギア" in card_type:
        add(tags, "クロスギア")
    if "/" in civ:
        add(tags, "多色")

    # Cost tags
    if 0 < cost <= 2:
        add(tags, "低コスト")
    if 0 < cost <= 3:
        add(tags, "軽量")
    if cost >= 7:
        add(tags, "高コスト")

    # True starters: ramp, draw/search, or cheap pressure. Do not tag every cheap card as starter.
    if 0 < cost <= 3 and (
        regex_any(text, [r"山札.*マナゾーンに置", r"マナゾーンに.*置く", r"マナゾーンに加え"])
        or regex_any(text, [r"カードを.*枚引", r"山札.*見て.*手札", r"探索"])
        or contains_any(text, ["チャージャー"])
    ):
        add(tags, "初動候補")

    # Defensive cards: S-trigger alone is not always a strong defense role.
    if "S・トリガー" in blob:
        add(tags, "S・トリガー")
    if "G・ストライク" in blob:
        add(tags, "G・ストライク", "受け札")
    if "ブロッカー" in blob:
        add(tags, "ブロッカー")
        if cost <= 5:
            add(tags, "受け札")
    if "S・トリガー" in blob and (
        contains_any(text, ["破壊する", "手札に戻す", "タップする", "山札の下", "シールド化"])
        or contains_any(blob, ["ブロッカー", "G・ストライク"])
    ):
        add(tags, "受け札")

    # Mana acceleration: require explicit movement to mana, not just "マナゾーンから".
    if contains_any(text, ["チャージャー"]):
        add(tags, "マナ加速")
    if regex_any(text, [
        r"自分の山札.*マナゾーンに置",
        r"山札の上.*マナゾーンに置",
        r"自分の手札.*マナゾーンに置",
        r"マナゾーンに加え",
        r"マナゾーンに置く",
    ]):
        add(tags, "マナ加速")
    if contains_any(text, ["マナゾーンから召喚", "マナゾーンから唱え", "マナゾーンから手札"]):
        add(tags, "マナ利用")

    # Draw/resource/search
    if regex_any(text, [r"カードを.*枚引", r"カードを引く"]):
        add(tags, "ドロー", "リソース")
    if regex_any(text, [r"山札.*見て.*手札に加", r"山札から.*手札に加", r"探索"]):
        add(tags, "サーチ候補", "リソース")
    if contains_any(text, ["手札に加える"]) and contains_any(text, ["山札", "墓地", "マナゾーン"]):
        add(tags, "リソース")

    # Removal: require target action. Do not tag generic "バトルゾーンから" as removal.
    if regex_any(text, [
        r"相手.*クリーチャー.*破壊",
        r"クリーチャーを.*破壊",
        r"相手.*選び.*破壊",
        r"相手.*手札に戻",
        r"クリーチャー.*手札に戻",
        r"相手.*山札の下",
        r"相手.*マナゾーンに置",
        r"相手.*シールド化",
        r"相手.*タップする",
    ]):
        add(tags, "除去")
    if regex_any(text, [r"手札に戻"]):
        add(tags, "バウンス")
    if regex_any(text, [r"破壊"]):
        add(tags, "破壊")
    if regex_any(text, [r"タップする", r"フリーズ", r"アンタップしない"]):
        add(tags, "タップ")

    # Lock / restrictions
    if contains_any(text, ["呪文を唱えられない", "呪文を唱えることができない"]):
        add(tags, "ロック", "呪文ロック")
    if contains_any(text, ["攻撃できない", "攻撃することができない"]):
        add(tags, "ロック", "攻撃制限")
    if contains_any(text, ["ブロックできない", "ブロックされない"]):
        add(tags, "ブロック制限")
    if contains_any(text, ["召喚できない", "召喚することができない", "出せない", "出すことができない"]):
        add(tags, "踏み倒しメタ", "ロック")
    if contains_any(text, ["選べない", "選ぶことができない"]):
        add(tags, "耐性")

    # Graveyard / recursion: distinguish use and actual cheating.
    if contains_any(text, ["墓地"]):
        add(tags, "墓地利用")
    if regex_any(text, [r"墓地から.*バトルゾーンに出", r"墓地から.*召喚"]):
        add(tags, "リアニメイト", "踏み倒し")

    # Cheating / cost reduction
    if contains_any(text, ["コストを支払わず"]):
        add(tags, "踏み倒し")
    if regex_any(text, [r"バトルゾーンに出す", r"召喚するコストを.*少なく", r"コストを.*少なく"]):
        add(tags, "踏み倒し")
    if regex_any(text, [r"コストを.*少なく", r"コストを軽減"]):
        add(tags, "コスト軽減")

    # Finisher / pressure
    if contains_any(blob, ["W・ブレイカー", "T・ブレイカー", "Q・ブレイカー", "ワールド・ブレイカー", "G・ブレイカー"]):
        add(tags, "打点")
    if contains_any(blob, ["スピードアタッカー"]):
        add(tags, "即効性", "打点")
    if contains_any(blob, ["マッハファイター"]):
        add(tags, "盤面処理")
    if cost >= 5 and ("打点" in tags or power_i >= 7000):
        add(tags, "フィニッシャー候補")
    if cost >= 6 and ("打点" in tags or contains_any(blob, ["スピードアタッカー"])):
        add(tags, "フィニッシャー")

    # Combo / deck manipulation
    if contains_any(text, ["追加ターン", "ターンを追加", "もう一度", "アンタップする", "コストを支払わず"]):
        add(tags, "コンボ")
    if contains_any(text, ["山札を見る", "山札の上", "山札の下", "山札を見て"]):
        add(tags, "山札操作")

    # Hand/shield pressure
    if contains_any(text, ["手札を捨て", "捨てさせる"]):
        add(tags, "ハンデス")
    if contains_any(text, ["シールドを追加", "シールド化", "シールドゾーンに置く"]):
        add(tags, "シールド追加")
    if contains_any(text, ["シールドをブレイク", "シールド焼却", "ブレイクするシールド"]):
        add(tags, "シールド圧力")

    # Race hints
    if "ドラゴン" in race:
        add(tags, "ドラゴン")
    if "サイバー" in race:
        add(tags, "サイバー")
    if "デーモン" in race:
        add(tags, "デーモン")
    if "スノーフェアリー" in race:
        add(tags, "スノーフェアリー")

    return tags


def enrich_db(db_path: Path = DEFAULT_DB) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS card_tags (
            card_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY (card_id, tag)
        )
        """
    )
    cur.execute("DELETE FROM card_tags")

    cards = [dict(row) for row in cur.execute("SELECT * FROM cards").fetchall()]
    tag_counts: dict[str, int] = {}
    cards_with_tags = 0
    total_tags = 0

    for card in cards:
        tags = infer_tags(card)
        if tags:
            cards_with_tags += 1
        for tag in sorted(tags):
            cur.execute("INSERT OR IGNORE INTO card_tags (card_id, tag) VALUES (?, ?)", (card["card_id"], tag))
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
            total_tags += 1

    con.commit()
    con.close()

    return {
        "cards": len(cards),
        "cards_with_tags": cards_with_tags,
        "total_tags": total_tags,
        "tag_counts": tag_counts,
    }


def write_tagged_csv(csv_path: Path = DEFAULT_CSV, out_path: Path = DEFAULT_TAGGED_CSV) -> int:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    for row in rows:
        card = {
            "card_id": row.get("card_id", ""),
            "name": row.get("name") or row.get("card_name", ""),
            "civilization": row.get("civilization") or row.get("culture", ""),
            "cost": row.get("cost", ""),
            "card_type": row.get("card_type", ""),
            "power": row.get("power") or row.get("power_disp", ""),
            "race": row.get("race") or row.get("race_text", ""),
            "text": row.get("text") or row.get("body_text", ""),
        }
        tags = infer_tags(card)
        row["tags"] = ";".join(sorted(tags))
        out_rows.append(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(out_rows[0].keys()) if out_rows else []
    if "tags" not in fieldnames:
        fieldnames.append("tags")

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)
    return len(out_rows)


def write_report(summary: dict, report_path: Path = DEFAULT_REPORT) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("# MANA tag enrichment report v2")
    lines.append("")
    lines.append("- mode: stricter role tagging")
    lines.append(f"- cards: {summary['cards']}")
    lines.append(f"- cards_with_tags: {summary['cards_with_tags']}")
    lines.append(f"- total_tags: {summary['total_tags']}")
    lines.append("")
    lines.append("## top tags")
    lines.append("")
    lines.append("| tag | count |")
    lines.append("| --- | --- |")
    for tag, count in sorted(summary["tag_counts"].items(), key=lambda x: x[1], reverse=True)[:100]:
        lines.append(f"| {tag} | {count} |")
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Infer stricter MANA role tags from official DMPS card text and insert into card_tags.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--tagged-csv", default=str(DEFAULT_TAGGED_CSV))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--no-csv", action="store_true")
    args = parser.parse_args()

    summary = enrich_db(Path(args.db))
    if not args.no_csv:
        write_tagged_csv(Path(args.csv), Path(args.tagged_csv))
    write_report(summary, Path(args.report))

    print("cards:", summary["cards"])
    print("cards_with_tags:", summary["cards_with_tags"])
    print("total_tags:", summary["total_tags"])
    print("report:", args.report)
    if not args.no_csv:
        print("tagged_csv:", args.tagged_csv)


if __name__ == "__main__":
    main()

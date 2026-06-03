"""カードデータ修復スクリプト。

公式API再取得データ(cards_dmps_official_raw_v2.csv)から種族(race/race_text)と
ND可否(nd_legal)を、既存のタグ付けデータ(cards_tagged.csv)からタグ(tags)を、
card_id をキーに既存 cards.csv へ統合する。

背景:
- cards.csv は race/race_text/tags がすべて空だった。
- 公式APIは種族を race1〜race4、ND可否を new_division で返す(fetch側で結合済み)。
- これにより「水コマンド」等の種族シナジー判定とND/AD判定が可能になる。

実行: python -m scripts.repair_card_data  (リポジトリ直下から)
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "cards_dmps_official_raw_v2.csv"
TAGGED = ROOT / "data" / "cards_tagged.csv"
CARDS = ROOT / "data" / "cards.csv"


def load_map(path: Path, *keys: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            cid = (row.get("card_id") or "").strip()
            if cid:
                result[cid] = {k: (row.get(k) or "").strip() for k in keys}
    return result


def main() -> None:
    race_map = load_map(RAW, "race", "race_text", "nd_legal")
    tag_map = load_map(TAGGED, "tags")

    with CARDS.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    if "nd_legal" not in fields:
        # race_text の直後に置くと種族関連が並んで見やすい。無ければ末尾。
        if "race_text" in fields:
            fields.insert(fields.index("race_text") + 1, "nd_legal")
        else:
            fields.append("nd_legal")

    race_updated = tags_updated = nd_legal_1 = 0
    for row in rows:
        cid = (row.get("card_id") or "").strip()

        info = race_map.get(cid)
        if info:
            if info["race"]:
                row["race"] = info["race"]
                row["race_text"] = info["race_text"]
                race_updated += 1
            row["nd_legal"] = info["nd_legal"]
            if info["nd_legal"] == "1":
                nd_legal_1 += 1
        else:
            row.setdefault("nd_legal", "")

        tags = tag_map.get(cid)
        if tags and tags["tags"]:
            row["tags"] = tags["tags"]
            tags_updated += 1

    with CARDS.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"rows={len(rows)} race_updated={race_updated} tags_updated={tags_updated} nd_legal_1={nd_legal_1}")


if __name__ == "__main__":
    main()

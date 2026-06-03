from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether specific card names exist in cards.csv.")
    parser.add_argument("--csv", default="data/cards.csv")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()

    names = args.names or [
        "若き大長老 アプル",
        "超哀樹 シンベロム",
        "煌ノ裁徒 ダイヤモン星",
        "YAGYU-真価G89",
        "「水晶の力に選ばれし者、それが私だ！」",
        "呪華のサトリ カナザー",
        "大集合！アカネ&アサギ&コハク",
        "豊潤フォージュン",
        "戦技の炎 ボルメテウス・ソル",
        "魂晶 リゲル-２",
        "アルカディアス・モモキング",
    ]

    path = Path(args.csv)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    for name in names:
        hits = [row for row in rows if row.get("name") == name]
        print(f"\n{name}: {len(hits)}件")
        for row in hits[:10]:
            print(
                f"  {row.get('card_id')} | {row.get('card_type')} | "
                f"{row.get('civilization')} | cost={row.get('cost')} | "
                f"race={row.get('race')}"
            )


if __name__ == "__main__":
    main()

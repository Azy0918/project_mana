from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from src.import_cards import DEFAULT_DB_PATH


DEFAULT_RAW = Path("data/cards_dmps_official_raw.csv")


def fill_races_from_official_csv(
    raw_csv: Path = DEFAULT_RAW,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    """公式スクレイプCSV(fetch_dmps_official_cardsの出力)からcards.raceを充填する。

    使い方(ネットワーク制限のない環境で):
        python -m src.fetch_dmps_official_cards --limit 6000
        python -m src.fill_card_races
        python -c "from src.card_effect_feature_store import rebuild_card_effect_features as r; r()"
        python -m src.route_rediscovery_checker   # 相方順位の改善を確認
    """
    if not raw_csv.exists():
        raise FileNotFoundError(
            f"{raw_csv} がありません。先に python -m src.fetch_dmps_official_cards を実行してください。"
        )

    race_by_name: dict[str, str] = {}
    with raw_csv.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("name") or row.get("card_name") or "").strip()
            race = (row.get("race") or row.get("race_text") or "").strip()
            if name and race and name not in race_by_name:
                race_by_name[name] = race

    updated = 0
    with sqlite3.connect(db_path) as conn:
        for name, race in race_by_name.items():
            cursor = conn.execute(
                "UPDATE cards SET race = ? WHERE name = ? AND (race IS NULL OR race = '')",
                (race, name),
            )
            updated += cursor.rowcount
        conn.commit()
        remaining = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE race IS NULL OR race = ''"
        ).fetchone()[0]

    return {
        "names_with_race": len(race_by_name),
        "rows_updated": updated,
        "rows_still_empty": remaining,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="公式CSVからcards.raceを充填する")
    parser.add_argument("--raw", default=str(DEFAULT_RAW))
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()
    result = fill_races_from_official_csv(Path(args.raw), Path(args.db))
    print(f"race付きカード名: {result['names_with_race']}件")
    print(f"更新行数: {result['rows_updated']}行")
    print(f"race未設定の残り: {result['rows_still_empty']}行")
    print("次に特徴量を再構築してください: python -c \"from src.card_effect_feature_store import rebuild_card_effect_features as r; r()\"")


if __name__ == "__main__":
    main()

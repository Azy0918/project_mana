from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CSV_PATH = ROOT_DIR / "data" / "cards.csv"
DEFAULT_DB_PATH = ROOT_DIR / "data" / "cards.db"


SCHEMA = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS card_tags;
DROP TABLE IF EXISTS cards;

CREATE TABLE cards (
    card_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    civilization TEXT NOT NULL,
    cost INTEGER NOT NULL,
    card_type TEXT NOT NULL,
    power INTEGER,
    race TEXT,
    text TEXT NOT NULL
);

CREATE TABLE card_tags (
    card_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (card_id, tag),
    FOREIGN KEY (card_id) REFERENCES cards(card_id) ON DELETE CASCADE
);

CREATE INDEX idx_cards_civilization ON cards(civilization);
CREATE INDEX idx_cards_cost ON cards(cost);
CREATE INDEX idx_card_tags_tag ON card_tags(tag);
"""


def _parse_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


def _split_tags(value: str | None) -> list[str]:
    if not value:
        return []
    tags = []
    for tag in value.replace(",", ";").split(";"):
        normalized = tag.strip()
        if normalized:
            tags.append(normalized)
    return tags


def import_cards(csv_path: Path = DEFAULT_CSV_PATH, db_path: Path = DEFAULT_DB_PATH) -> int:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)

        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                conn.execute(
                    """
                    INSERT INTO cards (
                        card_id, name, civilization, cost, card_type, power, race, text
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row["card_id"].strip(),
                        row["name"].strip(),
                        row["civilization"].strip(),
                        int(row["cost"]),
                        row["card_type"].strip(),
                        _parse_int(row.get("power")),
                        (row.get("race") or "").strip(),
                        row["text"].strip(),
                    ),
                )

                for tag in _split_tags(row.get("tags")):
                    conn.execute(
                        "INSERT OR IGNORE INTO card_tags (card_id, tag) VALUES (?, ?)",
                        (row["card_id"].strip(), tag),
                    )
                count += 1

        conn.commit()
        return count


def main() -> None:
    parser = argparse.ArgumentParser(description="cards.csv を SQLite に取り込みます。")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    count = import_cards(args.csv, args.db)
    print(f"{count} cards imported to {args.db}")


if __name__ == "__main__":
    main()

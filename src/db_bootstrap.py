from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd

from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH, import_cards


CARDS_CSV_PATH = DEFAULT_CSV_PATH
DB_PATH = DEFAULT_DB_PATH


def _count_csv_rows(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    return int(len(pd.read_csv(csv_path, dtype=str).fillna("")))


def _count_db_cards(db_path: Path) -> int:
    if not db_path.exists():
        return 0

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM cards").fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def _has_card_tags_table(db_path: Path) -> bool:
    if not db_path.exists():
        return False

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'card_tags'
                """
            ).fetchone()
            return row is not None
    except Exception:
        return False


def ensure_cards_db_from_csv(force: bool = False) -> int:
    """
    cards.csv の内容を SQLite DB に反映する。
    force=True の場合は cards / card_tags テーブルを作り直す。
    """
    if not CARDS_CSV_PATH.exists():
        return 0

    csv_count = _count_csv_rows(CARDS_CSV_PATH)
    current_count = _count_db_cards(DB_PATH)
    needs_schema_rebuild = not _has_card_tags_table(DB_PATH)

    if force or needs_schema_rebuild or current_count < csv_count:
        return import_cards(CARDS_CSV_PATH, DB_PATH)

    return current_count

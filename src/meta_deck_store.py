from __future__ import annotations

import csv
import sqlite3
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd

from src.import_cards import DEFAULT_DB_PATH


DB_PATH = DEFAULT_DB_PATH

META_DECK_COLUMNS = [
    "deck_name",
    "format",
    "tier",
    "civilizations",
    "deck_type",
    "key_cards",
    "good_matchups",
    "bad_matchups",
    "source_url",
    "confidence",
    "observed_at",
    "notes",
]


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_meta_deck_table(db_path: Path = DB_PATH) -> None:
    """Create or migrate the meta_decks table.

    The unique index on deck_name + format enables safe upsert imports.
    """
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta_decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deck_name TEXT NOT NULL,
                format TEXT DEFAULT 'ND',
                tier TEXT,
                civilizations TEXT,
                deck_type TEXT,
                key_cards TEXT,
                good_matchups TEXT,
                bad_matchups TEXT,
                source_url TEXT,
                confidence INTEGER,
                observed_at TEXT,
                notes TEXT
            )
            """
        )

        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(meta_decks)").fetchall()
        }
        optional_columns = {
            "format": "TEXT DEFAULT 'ND'",
            "tier": "TEXT",
            "civilizations": "TEXT",
            "deck_type": "TEXT",
            "key_cards": "TEXT",
            "good_matchups": "TEXT",
            "bad_matchups": "TEXT",
            "source_url": "TEXT",
            "confidence": "INTEGER",
            "observed_at": "TEXT",
            "notes": "TEXT",
        }
        for column, column_type in optional_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE meta_decks ADD COLUMN {column} {column_type}")

        conn.execute("UPDATE meta_decks SET format = 'ND' WHERE format IS NULL OR format = ''")
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_meta_decks_name_format
            ON meta_decks(deck_name, format)
            """
        )
        conn.commit()


def normalize_meta_deck_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one CSV/UI row to DB-ready values."""
    data: dict[str, Any] = {}
    for column in META_DECK_COLUMNS:
        value = row.get(column, "")
        if value is None:
            value = ""
        data[column] = str(value).strip()

    data["deck_name"] = data["deck_name"].strip()
    data["format"] = (data.get("format") or "ND").strip() or "ND"

    try:
        data["confidence"] = int(float(data.get("confidence") or 0))
    except Exception:
        data["confidence"] = 0

    return data


def save_meta_deck(row: dict[str, Any], db_path: Path = DB_PATH, upsert: bool = True) -> int:
    """Save one meta deck.

    If upsert=True, deck_name + format is treated as the replacement key.
    """
    ensure_meta_deck_table(db_path)
    data = normalize_meta_deck_row(row)

    if not data["deck_name"]:
        raise ValueError("deck_name is required")

    with get_connection(db_path) as conn:
        if upsert:
            cur = conn.execute(
                """
                INSERT INTO meta_decks (
                    deck_name, format, tier, civilizations, deck_type, key_cards,
                    good_matchups, bad_matchups, source_url, confidence, observed_at, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deck_name, format) DO UPDATE SET
                    tier = excluded.tier,
                    civilizations = excluded.civilizations,
                    deck_type = excluded.deck_type,
                    key_cards = excluded.key_cards,
                    good_matchups = excluded.good_matchups,
                    bad_matchups = excluded.bad_matchups,
                    source_url = excluded.source_url,
                    confidence = excluded.confidence,
                    observed_at = excluded.observed_at,
                    notes = excluded.notes
                """,
                tuple(data[column] for column in META_DECK_COLUMNS),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO meta_decks (
                    deck_name, format, tier, civilizations, deck_type, key_cards,
                    good_matchups, bad_matchups, source_url, confidence, observed_at, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(data[column] for column in META_DECK_COLUMNS),
            )
        conn.commit()
        return int(cur.lastrowid or 0)


def load_meta_decks(db_path: Path = DB_PATH) -> pd.DataFrame:
    ensure_meta_deck_table(db_path)
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                deck_name,
                format,
                tier,
                civilizations,
                deck_type,
                key_cards,
                good_matchups,
                bad_matchups,
                source_url,
                confidence,
                observed_at,
                notes
            FROM meta_decks
            ORDER BY
                CASE tier
                    WHEN 'S' THEN 1
                    WHEN 'A' THEN 2
                    WHEN 'B' THEN 3
                    WHEN 'C' THEN 4
                    ELSE 9
                END,
                format DESC,
                deck_name
            """,
            conn,
        )


def summarize_meta_decks(db_path: Path = DB_PATH) -> dict[str, Any]:
    df = load_meta_decks(db_path)
    if df.empty:
        return {
            "count": 0,
            "formats": {},
            "tiers": {},
            "deck_types": {},
            "latest_observed_at": "",
        }

    summary: dict[str, Any] = {
        "count": int(len(df)),
        "formats": df["format"].fillna("").replace("", "不明").value_counts().to_dict()
        if "format" in df.columns
        else {},
        "tiers": df["tier"].fillna("").replace("", "不明").value_counts().to_dict()
        if "tier" in df.columns
        else {},
        "deck_types": df["deck_type"].fillna("").replace("", "不明").value_counts().to_dict()
        if "deck_type" in df.columns
        else {},
        "latest_observed_at": "",
    }
    if "observed_at" in df.columns and df["observed_at"].notna().any():
        values = [str(v) for v in df["observed_at"].fillna("").tolist() if str(v).strip()]
        summary["latest_observed_at"] = max(values) if values else ""
    return summary


def export_meta_decks_to_csv(db_path: Path = DB_PATH) -> str:
    """Export current meta deck DB as UTF-8 CSV text."""
    df = load_meta_decks(db_path)
    if df.empty:
        return ",".join(META_DECK_COLUMNS) + "\n"

    export_columns = [column for column in META_DECK_COLUMNS if column in df.columns]
    output = StringIO()
    df[export_columns].to_csv(output, index=False)
    return output.getvalue()


def delete_all_meta_decks(db_path: Path = DB_PATH) -> int:
    ensure_meta_deck_table(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM meta_decks")
        conn.commit()
        return int(cur.rowcount)


def delete_meta_decks_by_format(format: str, db_path: Path = DB_PATH) -> int:
    ensure_meta_deck_table(db_path)
    target = str(format or "").strip()
    if not target:
        return 0
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM meta_decks WHERE format = ?", (target,))
        conn.commit()
        return int(cur.rowcount)


def delete_meta_decks_by_observed_at(observed_at: str, db_path: Path = DB_PATH) -> int:
    ensure_meta_deck_table(db_path)
    target = str(observed_at or "").strip()
    if not target:
        return 0
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM meta_decks WHERE observed_at = ?", (target,))
        conn.commit()
        return int(cur.rowcount)


def delete_meta_decks_by_names(deck_names: list[str], db_path: Path = DB_PATH) -> int:
    ensure_meta_deck_table(db_path)
    names = [str(name).strip() for name in deck_names if str(name).strip()]
    if not names:
        return 0

    placeholders = ",".join("?" for _ in names)
    with get_connection(db_path) as conn:
        cur = conn.execute(f"DELETE FROM meta_decks WHERE deck_name IN ({placeholders})", names)
        conn.commit()
        return int(cur.rowcount)


def parse_meta_decks_csv(csv_text: str) -> list[dict[str, Any]]:
    """Parse uploaded CSV text to normalized rows.

    Empty deck_name rows are skipped.
    """
    text = str(csv_text or "")
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV header is missing")

    missing = [column for column in ["deck_name", "format"] if column not in reader.fieldnames]
    if missing:
        raise ValueError(f"必須列が不足しています: {missing}")

    rows: list[dict[str, Any]] = []
    for raw in reader:
        row = normalize_meta_deck_row(raw)
        if not row["deck_name"]:
            continue
        rows.append(row)
    return rows


def import_meta_decks_from_csv_text(
    csv_text: str,
    mode: str = "upsert",
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Import meta decks from CSV text.

    mode:
      - append: always insert
      - upsert: update same deck_name + format, otherwise insert
      - replace_all: delete all then upsert imported rows
    """
    ensure_meta_deck_table(db_path)
    mode = str(mode or "upsert").strip()
    if mode not in {"append", "upsert", "replace_all"}:
        raise ValueError("mode must be append, upsert, or replace_all")

    rows = parse_meta_decks_csv(csv_text)
    deleted_count = 0
    inserted_or_updated_count = 0
    skipped_count = 0
    errors: list[str] = []

    if mode == "replace_all":
        deleted_count = delete_all_meta_decks(db_path)

    for index, row in enumerate(rows, start=2):
        try:
            save_meta_deck(row, db_path=db_path, upsert=(mode != "append"))
            inserted_or_updated_count += 1
        except Exception as exc:
            skipped_count += 1
            errors.append(f"{index}行目: {exc}")

    return {
        "mode": mode,
        "input_count": len(rows),
        "deleted_count": deleted_count,
        "imported_count": inserted_or_updated_count,
        "skipped_count": skipped_count,
        "errors": errors,
    }


def import_meta_decks_from_csv_path(
    csv_path: str | Path,
    mode: str = "upsert",
    db_path: Path = DB_PATH,
    encoding: str = "utf-8-sig",
) -> dict[str, Any]:
    csv_text = Path(csv_path).read_text(encoding=encoding)
    return import_meta_decks_from_csv_text(csv_text, mode=mode, db_path=db_path)


# Backward-compatible aliases for likely older app imports.
def import_meta_decks_from_csv(
    csv_text: str,
    db_path: Path = DB_PATH,
    mode: str = "upsert",
) -> dict[str, Any]:
    return import_meta_decks_from_csv_text(csv_text, mode=mode, db_path=db_path)


def list_meta_decks(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    return load_meta_decks(db_path).fillna("").to_dict("records")

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import sqlite3
from typing import Any

import pandas as pd

from src.import_cards import DEFAULT_DB_PATH


DB_PATH = DEFAULT_DB_PATH


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_generated_decks_table(db_path: Path = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generated_decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                deck_name TEXT NOT NULL,
                format TEXT,
                civilizations TEXT,
                deck_type TEXT,
                focus_tags TEXT,
                avoid_tags TEXT,
                strategy_note TEXT,
                deck_size INTEGER,
                deck_cards_json TEXT,
                condition_score INTEGER,
                civilization_match_rate REAL,
                starter_count INTEGER,
                defense_count INTEGER,
                finisher_count INTEGER,
                removal_count INTEGER,
                draw_count INTEGER,
                average_cost REAL,
                evaluation_score REAL,
                novelty_score REAL,
                meta_score REAL,
                candidate_origin TEXT
            )
            """
        )
        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(generated_decks)").fetchall()
        }
        optional_columns = {
            "format": "TEXT",
            "evaluation_score": "REAL",
            "novelty_score": "REAL",
            "meta_score": "REAL",
            "candidate_origin": "TEXT",
        }
        for column, column_type in optional_columns.items():
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE generated_decks ADD COLUMN {column} {column_type}")
        conn.execute("UPDATE generated_decks SET format = 'ND' WHERE format IS NULL OR format = ''")
        conn.execute("UPDATE generated_decks SET candidate_origin = 'tag_based' WHERE candidate_origin IS NULL OR candidate_origin = ''")
        conn.commit()


def _deck_size(deck_cards: list[dict[str, Any]]) -> int:
    total = 0
    for card in deck_cards:
        try:
            total += int(card.get("quantity", 1))
        except Exception:
            total += 1
    return total


def save_generated_deck(
    deck_name: str,
    civilizations: list[str],
    deck_type: str,
    focus_tags: list[str],
    avoid_tags: list[str],
    strategy_note: str,
    deck_cards: list[dict[str, Any]],
    analysis: Any,
    evaluation: dict[str, Any] | None = None,
    format: str = "ND",
    candidate_origin: str = "tag_based",
    db_path: Path = DB_PATH,
) -> int:
    ensure_generated_decks_table(db_path)
    evaluation = evaluation or {}

    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO generated_decks (
                created_at,
                deck_name,
                format,
                civilizations,
                deck_type,
                focus_tags,
                avoid_tags,
                strategy_note,
                deck_size,
                deck_cards_json,
                condition_score,
                civilization_match_rate,
                starter_count,
                defense_count,
                finisher_count,
                removal_count,
                draw_count,
                average_cost,
                evaluation_score,
                novelty_score,
                meta_score,
                candidate_origin
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                deck_name.strip() or "生成デッキ",
                format.strip() or "ND",
                ";".join(civilizations),
                deck_type,
                ";".join(focus_tags),
                ";".join(avoid_tags),
                strategy_note,
                _deck_size(deck_cards),
                json.dumps(deck_cards, ensure_ascii=False),
                analysis.condition_score,
                analysis.civilization_match_rate,
                analysis.starter_count,
                analysis.defense_count,
                analysis.finisher_count,
                analysis.removal_count,
                analysis.draw_count,
                analysis.average_cost,
                evaluation.get("score"),
                evaluation.get("novelty_score"),
                evaluation.get("meta_score"),
                _normalize_candidate_origin(candidate_origin),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def load_generated_decks(db_path: Path = DB_PATH) -> pd.DataFrame:
    ensure_generated_decks_table(db_path)

    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                id,
                created_at,
                deck_name,
                format,
                civilizations,
                deck_type,
                focus_tags,
                avoid_tags,
                deck_size,
                condition_score,
                civilization_match_rate,
                starter_count,
                defense_count,
                finisher_count,
                removal_count,
                draw_count,
                average_cost,
                evaluation_score,
                novelty_score,
                meta_score,
                candidate_origin
            FROM generated_decks
            ORDER BY id DESC
            """,
            conn,
        )


def load_generated_deck_detail(deck_id: int, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    ensure_generated_decks_table(db_path)

    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM generated_decks WHERE id = ?",
            (deck_id,),
        ).fetchone()

    if row is None:
        return None

    data = dict(row)
    try:
        data["deck_cards"] = json.loads(data.get("deck_cards_json") or "[]")
    except Exception:
        data["deck_cards"] = []

    return data


def _normalize_candidate_origin(value: str) -> str:
    allowed = {
        "tag_based",
        "route_based",
        "proof_based",
        "combo_based",
        "meta_counter_based",
        "human_imported",
        "novel_combo_discovery",
    }
    value = str(value or "").strip()
    return value if value in allowed else "tag_based"

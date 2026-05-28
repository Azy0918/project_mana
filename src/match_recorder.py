from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any

from src.match_log_validator import validate_match_log
from src.research_logger import connect
from src.search_cards import DEFAULT_DB_PATH


MATCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS real_match_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deck_name TEXT,
    deck_text TEXT,
    opponent_deck_type TEXT,
    play_order TEXT,
    result TEXT,
    finish_turn INTEGER,
    win_reason TEXT,
    lose_reason TEXT,
    key_cards TEXT,
    dead_cards TEXT,
    mistake_notes TEXT,
    video_ref TEXT,
    memo TEXT
);
"""


def ensure_match_log_table(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(MATCH_SCHEMA)
        conn.commit()


def save_match_log(log: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> int:
    ensure_match_log_table(db_path)
    errors = validate_match_log(log)
    if errors:
        raise ValueError(" / ".join(errors))

    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO real_match_logs (
                deck_name, deck_text, opponent_deck_type, play_order, result,
                finish_turn, win_reason, lose_reason, key_cards, dead_cards,
                mistake_notes, video_ref, memo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(log.get("deck_name", "")).strip(),
                str(log.get("deck_text", "")).strip(),
                str(log.get("opponent_deck_type", "")).strip(),
                log.get("play_order"),
                log.get("result"),
                int(log.get("finish_turn")),
                str(log.get("win_reason", "")).strip(),
                str(log.get("lose_reason", "")).strip(),
                str(log.get("key_cards", "")).strip(),
                str(log.get("dead_cards", "")).strip(),
                str(log.get("mistake_notes", "")).strip(),
                str(log.get("video_ref", "")).strip(),
                str(log.get("memo", "")).strip(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def list_match_logs(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_match_log_table(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                id, created_at, deck_name, opponent_deck_type, play_order,
                result, finish_turn, win_reason, lose_reason, key_cards,
                dead_cards, mistake_notes, video_ref, memo
            FROM real_match_logs
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def win_rate_by_deck(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_match_log_table(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                deck_name,
                COUNT(*) AS matches,
                SUM(CASE WHEN result = '勝ち' THEN 1 ELSE 0 END) AS wins,
                ROUND(AVG(CASE WHEN result = '勝ち' THEN 1.0 ELSE 0.0 END) * 100, 1) AS win_rate
            FROM real_match_logs
            GROUP BY deck_name
            ORDER BY win_rate DESC, matches DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def win_rate_by_opponent(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_match_log_table(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                opponent_deck_type,
                COUNT(*) AS matches,
                SUM(CASE WHEN result = '勝ち' THEN 1 ELSE 0 END) AS wins,
                ROUND(AVG(CASE WHEN result = '勝ち' THEN 1.0 ELSE 0.0 END) * 100, 1) AS win_rate
            FROM real_match_logs
            GROUP BY opponent_deck_type
            ORDER BY win_rate DESC, matches DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def export_match_logs_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()

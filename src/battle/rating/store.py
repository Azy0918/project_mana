from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "cards.db"


def ensure_rating_tables(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sim_battle_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                deck_a_name TEXT NOT NULL,
                deck_b_name TEXT NOT NULL,
                games INTEGER NOT NULL,
                wins_a INTEGER NOT NULL,
                wins_b INTEGER NOT NULL,
                draws INTEGER NOT NULL,
                win_rate_a REAL NOT NULL,
                ci95_low_a REAL NOT NULL,
                ci95_high_a REAL NOT NULL,
                average_turns REAL NOT NULL,
                finish_reasons_json TEXT,
                seed INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sim_ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                deck_name TEXT NOT NULL,
                opponent_scope TEXT NOT NULL,
                opponents INTEGER NOT NULL,
                games_total INTEGER NOT NULL,
                win_rate REAL NOT NULL,
                strength_score REAL NOT NULL,
                average_turns REAL NOT NULL,
                details_json TEXT
            )
            """
        )


def save_sim_battle_log(
    deck_a_name: str,
    deck_b_name: str,
    summary: Any,
    seed: int | None,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    ensure_rating_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO sim_battle_logs (
                created_at, deck_a_name, deck_b_name, games, wins_a, wins_b, draws,
                win_rate_a, ci95_low_a, ci95_high_a, average_turns, finish_reasons_json, seed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                deck_a_name,
                deck_b_name,
                summary.games,
                summary.wins_a,
                summary.wins_b,
                summary.draws,
                summary.win_rate_a,
                summary.ci95_low_a,
                summary.ci95_high_a,
                summary.average_turns,
                json.dumps(summary.finish_reasons, ensure_ascii=False),
                seed,
            ),
        )
        return int(cursor.lastrowid)


def save_sim_rating(
    deck_name: str,
    opponent_scope: str,
    details: list[dict[str, Any]],
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    ensure_rating_tables(db_path)
    games_total = sum(int(detail["games"]) for detail in details)
    wins_total = sum(int(detail["wins"]) for detail in details)
    win_rate = wins_total / games_total if games_total else 0.0
    average_turns = (
        sum(float(detail["average_turns"]) * int(detail["games"]) for detail in details) / games_total
        if games_total
        else 0.0
    )
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO sim_ratings (
                created_at, deck_name, opponent_scope, opponents, games_total,
                win_rate, strength_score, average_turns, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                deck_name,
                opponent_scope,
                len(details),
                games_total,
                win_rate,
                round(win_rate * 100, 1),
                average_turns,
                json.dumps(details, ensure_ascii=False),
            ),
        )
        return int(cursor.lastrowid)


def list_sim_ratings(db_path: Path = DEFAULT_DB_PATH, limit: int = 50) -> list[dict[str, Any]]:
    ensure_rating_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM sim_ratings ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    results = []
    for row in rows:
        record = dict(row)
        record["details"] = json.loads(record.pop("details_json") or "[]")
        results.append(record)
    return results

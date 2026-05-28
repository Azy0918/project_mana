from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any

from src.search_cards import DEFAULT_DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS deck_logs (
    deck_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source TEXT NOT NULL,
    deck_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evaluation_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deck_id TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    novelty_score INTEGER NOT NULL,
    meta_score INTEGER NOT NULL,
    early_count INTEGER NOT NULL,
    defense_count INTEGER NOT NULL,
    finisher_count INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (deck_id) REFERENCES deck_logs(deck_id)
);

CREATE TABLE IF NOT EXISTS battle_logs (
    battle_id TEXT PRIMARY KEY,
    deck_a_id TEXT NOT NULL,
    deck_b_id TEXT NOT NULL,
    deck_a_win_rate REAL NOT NULL,
    deck_b_win_rate REAL NOT NULL,
    avg_finish_turn REAL NOT NULL,
    trials INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (deck_a_id) REFERENCES deck_logs(deck_id),
    FOREIGN KEY (deck_b_id) REFERENCES deck_logs(deck_id)
);

CREATE TABLE IF NOT EXISTS evolution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    best_score REAL NOT NULL,
    best_novelty_score INTEGER NOT NULL,
    best_meta_score INTEGER NOT NULL,
    focus_mode TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_log_tables(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def make_deck_id() -> str:
    return f"deck_{uuid.uuid4().hex[:12]}"


def save_deck_log(
    name: str,
    source: str,
    deck_text: str,
    db_path: Path = DEFAULT_DB_PATH,
    deck_id: str | None = None,
) -> str:
    ensure_log_tables(db_path)
    resolved_id = deck_id or make_deck_id()
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO deck_logs (deck_id, name, source, deck_text)
            VALUES (?, ?, ?, ?)
            """,
            (resolved_id, name.strip() or "無題デッキ", source.strip() or "manual", deck_text.strip()),
        )
        conn.commit()
    return resolved_id


def save_evaluation_log(
    deck_id: str,
    summary: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    ensure_log_tables(db_path)
    role_counts = summary["role_counts"]
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO evaluation_logs (
                deck_id, total_score, novelty_score, meta_score,
                early_count, defense_count, finisher_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deck_id,
                int(summary["score"]),
                int(summary["novelty_score"]),
                int(summary["meta_score"]),
                int(role_counts["初動"]),
                int(role_counts["受け札"]),
                int(role_counts["フィニッシャー"]),
            ),
        )
        conn.commit()


def save_deck_with_evaluation(
    name: str,
    source: str,
    deck_text: str,
    summary: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
) -> str:
    deck_id = save_deck_log(name, source, deck_text, db_path)
    save_evaluation_log(deck_id, summary, db_path)
    return deck_id


def save_battle_log(
    deck_a_id: str,
    deck_b_id: str,
    battle_result: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
    battle_id: str | None = None,
) -> str:
    ensure_log_tables(db_path)
    resolved_id = battle_id or f"battle_{uuid.uuid4().hex[:12]}"
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO battle_logs (
                battle_id, deck_a_id, deck_b_id,
                deck_a_win_rate, deck_b_win_rate, avg_finish_turn, trials
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_id,
                deck_a_id,
                deck_b_id,
                float(battle_result["deck_a_win_rate"]),
                float(battle_result["deck_b_win_rate"]),
                float(battle_result["average_finish_turn"]),
                int(battle_result["trials"]),
            ),
        )
        conn.commit()
    return resolved_id


def save_evolution_logs(
    evolution_result: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
    run_id: str | None = None,
) -> str:
    ensure_log_tables(db_path)
    resolved_id = run_id or f"evo_{uuid.uuid4().hex[:12]}"
    focus = evolution_result.get("focus", "不明")
    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO evolution_logs (
                run_id, generation, best_score,
                best_novelty_score, best_meta_score, focus_mode
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    resolved_id,
                    int(item["generation"]),
                    float(item["fitness"]),
                    int(item["novelty_score"]),
                    int(item["meta_score"]),
                    focus,
                )
                for item in evolution_result.get("history", [])
            ],
        )
        conn.commit()
    return resolved_id

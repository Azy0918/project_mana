from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any

from src.research_logger import connect
from src.search_cards import DEFAULT_DB_PATH


TEST_PLAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS test_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deck_version_id INTEGER,
    deck_name TEXT,
    version_name TEXT,
    purpose TEXT,
    target_matches INTEGER,
    target_win_rate REAL,
    target_avg_finish_turn REAL,
    status TEXT,
    memo TEXT
);

CREATE TABLE IF NOT EXISTS test_plan_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_plan_id INTEGER NOT NULL,
    opponent_deck_type TEXT,
    target_matches INTEGER,
    target_win_rate REAL,
    FOREIGN KEY (test_plan_id) REFERENCES test_plans(id)
);
"""


def ensure_test_plan_tables(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(TEST_PLAN_SCHEMA)
        conn.commit()


def save_test_plan(
    plan: dict[str, Any],
    targets: list[dict[str, Any]],
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    ensure_test_plan_tables(db_path)
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO test_plans (
                deck_version_id, deck_name, version_name, purpose,
                target_matches, target_win_rate, target_avg_finish_turn,
                status, memo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.get("deck_version_id"),
                str(plan.get("deck_name", "")).strip(),
                str(plan.get("version_name", "")).strip(),
                str(plan.get("purpose", "")).strip(),
                int(plan.get("target_matches", 0)),
                float(plan.get("target_win_rate", 0)),
                float(plan.get("target_avg_finish_turn", 0)),
                str(plan.get("status", "検証中")).strip() or "検証中",
                str(plan.get("memo", "")).strip(),
            ),
        )
        plan_id = int(cursor.lastrowid)
        conn.executemany(
            """
            INSERT INTO test_plan_targets (
                test_plan_id, opponent_deck_type, target_matches, target_win_rate
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    plan_id,
                    str(target.get("opponent_deck_type", "")).strip(),
                    int(target.get("target_matches", 0)),
                    float(target.get("target_win_rate", 0)),
                )
                for target in targets
                if str(target.get("opponent_deck_type", "")).strip()
            ],
        )
        conn.commit()
        return plan_id


def update_test_plan_status(plan_id: int, status: str, db_path: Path = DEFAULT_DB_PATH) -> None:
    ensure_test_plan_tables(db_path)
    with connect(db_path) as conn:
        conn.execute("UPDATE test_plans SET status = ? WHERE id = ?", (status, plan_id))
        conn.commit()


def list_test_plans(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_test_plan_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM test_plans
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_test_plan_targets(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_test_plan_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM test_plan_targets
            ORDER BY test_plan_id DESC, id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def targets_for_plan(plan_id: int, db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_test_plan_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM test_plan_targets
            WHERE test_plan_id = ?
            ORDER BY id ASC
            """,
            (plan_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def export_rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any

from src.research_logger import connect
from src.search_cards import DEFAULT_DB_PATH


VERSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS deck_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deck_name TEXT NOT NULL,
    version_name TEXT,
    parent_version_id INTEGER,
    deck_text TEXT NOT NULL,
    reason TEXT,
    total_score REAL,
    novelty_score REAL,
    meta_score REAL,
    memo TEXT,
    FOREIGN KEY (parent_version_id) REFERENCES deck_versions(id)
);

CREATE TABLE IF NOT EXISTS deck_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    change_type TEXT,
    card_name TEXT,
    count INTEGER,
    reason TEXT,
    FOREIGN KEY (version_id) REFERENCES deck_versions(id)
);
"""


def ensure_version_tables(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(VERSION_SCHEMA)
        conn.commit()


def save_deck_version(
    deck_name: str,
    deck_text: str,
    version_name: str = "",
    parent_version_id: int | None = None,
    reason: str = "",
    summary: dict[str, Any] | None = None,
    memo: str = "",
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    ensure_version_tables(db_path)
    summary = summary or {}
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO deck_versions (
                deck_name, version_name, parent_version_id, deck_text,
                reason, total_score, novelty_score, meta_score, memo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                deck_name.strip() or "未設定デッキ",
                version_name.strip(),
                parent_version_id,
                deck_text.strip(),
                reason.strip(),
                summary.get("score"),
                summary.get("novelty_score"),
                summary.get("meta_score"),
                memo.strip(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def save_deck_changes(
    version_id: int,
    changes: list[dict[str, Any]],
    db_path: Path = DEFAULT_DB_PATH,
) -> None:
    ensure_version_tables(db_path)
    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO deck_changes (version_id, change_type, card_name, count, reason)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    version_id,
                    str(change.get("change_type", "")).strip(),
                    str(change.get("card_name", "")).strip(),
                    int(change.get("count", 0)),
                    str(change.get("reason", "")).strip(),
                )
                for change in changes
            ],
        )
        conn.commit()


def list_deck_versions(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_version_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM deck_versions
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_deck_changes(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_version_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                c.id,
                c.version_id,
                v.deck_name,
                v.version_name,
                c.change_type,
                c.card_name,
                c.count,
                c.reason
            FROM deck_changes c
            JOIN deck_versions v ON v.id = c.version_id
            ORDER BY c.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_version(version_id: int, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    ensure_version_tables(db_path)
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM deck_versions WHERE id = ?", (version_id,)).fetchone()
    return dict(row) if row else None


def list_versions_for_deck(deck_name: str, db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_version_tables(db_path)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM deck_versions
            WHERE deck_name = ?
            ORDER BY created_at ASC, id ASC
            """,
            (deck_name,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_lineage(version_id: int, db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    versions = {version["id"]: version for version in list_deck_versions(db_path)}
    lineage = []
    current = versions.get(version_id)
    while current:
        lineage.append(current)
        parent_id = current.get("parent_version_id")
        current = versions.get(parent_id) if parent_id else None
    return list(reversed(lineage))


def export_rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()

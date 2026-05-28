from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "cards.db"


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _like(value: str) -> str:
    return f"%{value.strip()}%"


def search_cards(
    db_path: Path = DEFAULT_DB_PATH,
    civilization: str = "",
    min_cost: int | None = None,
    max_cost: int | None = None,
    tag: str = "",
    keyword: str = "",
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []

    if civilization:
        where.append("c.civilization LIKE ?")
        params.append(_like(civilization))

    if min_cost is not None:
        where.append("c.cost >= ?")
        params.append(min_cost)

    if max_cost is not None:
        where.append("c.cost <= ?")
        params.append(max_cost)

    if tag:
        where.append(
            """
            EXISTS (
                SELECT 1
                FROM card_tags ct_filter
                WHERE ct_filter.card_id = c.card_id
                  AND ct_filter.tag LIKE ?
            )
            """
        )
        params.append(_like(tag))

    if keyword:
        where.append(
            """
            (
                c.name LIKE ?
                OR c.card_type LIKE ?
                OR c.race LIKE ?
                OR c.text LIKE ?
            )
            """
        )
        params.extend([_like(keyword)] * 4)

    sql = """
        SELECT
            c.card_id,
            c.name,
            c.civilization,
            c.cost,
            c.card_type,
            c.power,
            c.race,
            c.text,
            COALESCE(GROUP_CONCAT(ct.tag, ';'), '') AS tags
        FROM cards c
        LEFT JOIN card_tags ct ON ct.card_id = c.card_id
    """

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += """
        GROUP BY c.card_id
        ORDER BY c.cost ASC, c.name ASC
    """

    with connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]


def list_civilizations(db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT civilization FROM cards ORDER BY civilization"
        ).fetchall()
    return [row["civilization"] for row in rows]


def list_tags(db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT tag FROM card_tags ORDER BY tag").fetchall()
    return [row["tag"] for row in rows]

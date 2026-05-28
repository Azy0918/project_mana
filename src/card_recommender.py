from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.search_cards import DEFAULT_DB_PATH


def recommend_cards_by_tags(
    db_path: str | Path = DEFAULT_DB_PATH,
    tags: list[str] | set[str] | tuple[str, ...] | None = None,
    civilizations: list[str] | set[str] | tuple[str, ...] | None = None,
    exclude_names: list[str] | set[str] | tuple[str, ...] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    target_tags = [tag for tag in dict.fromkeys(tags or []) if tag]
    if not target_tags:
        return []

    civilization_values = [civ for civ in dict.fromkeys(civilizations or []) if civ]
    excluded = {name for name in (exclude_names or []) if name}

    tag_placeholders = ",".join(["?"] * len(target_tags))
    where = [
        f"""
        EXISTS (
            SELECT 1
            FROM card_tags ct_filter
            WHERE ct_filter.card_id = c.card_id
              AND ct_filter.tag IN ({tag_placeholders})
        )
        """
    ]
    params: list[Any] = list(target_tags)

    if civilization_values:
        civ_clauses = []
        for civ in civilization_values:
            civ_clauses.append("c.civilization LIKE ?")
            params.append(f"%{civ}%")
        where.append("(" + " OR ".join(civ_clauses) + ")")

    sql = f"""
        SELECT
            c.card_id,
            c.name,
            c.civilization,
            c.cost,
            c.card_type,
            c.power,
            c.race,
            c.text,
            COALESCE(GROUP_CONCAT(ct.tag, ';'), '') AS tags,
            COUNT(DISTINCT matched.tag) AS matched_tag_count
        FROM cards c
        LEFT JOIN card_tags ct ON ct.card_id = c.card_id
        LEFT JOIN card_tags matched
          ON matched.card_id = c.card_id
         AND matched.tag IN ({tag_placeholders})
        WHERE {" AND ".join(where)}
        GROUP BY c.card_id
        ORDER BY matched_tag_count DESC, c.cost ASC, c.name ASC
        LIMIT ?
    """
    params = list(target_tags) + params + [limit]

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows if row["name"] not in excluded]

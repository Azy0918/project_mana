from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data/cards.db")
VALID_STATUSES = {"queued", "used", "archived", "rejected"}


def get_connection(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_meta_research_seed_table(db_path: str | Path = DEFAULT_DB) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta_research_seeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                seed_status TEXT NOT NULL DEFAULT 'queued',
                source_type TEXT,
                source_category TEXT,
                source_name TEXT,
                source_url TEXT,
                format TEXT,
                note_text TEXT,
                memo TEXT,
                seed_type TEXT,
                priority TEXT,
                confidence REAL,
                detected_cards_json TEXT,
                detected_deck_names_json TEXT,
                detected_matchups_json TEXT,
                detected_external_zone_cards_json TEXT,
                detected_result_keywords_json TEXT,
                detected_rate_keywords_json TEXT,
                detected_tournament_keywords_json TEXT,
                detected_region_keywords_json TEXT,
                paper_diff_flag INTEGER DEFAULT 0,
                mana_action TEXT,
                strategy_hint TEXT,
                required_tags_json TEXT,
                avoid_tags_json TEXT,
                candidate_origin TEXT
            )
            """
        )
        existing = {row[1] for row in conn.execute("PRAGMA table_info(meta_research_seeds)").fetchall()}
        for column_name, column_type in {
            "created_at": "TEXT",
            "updated_at": "TEXT",
            "seed_status": "TEXT NOT NULL DEFAULT 'queued'",
            "source_type": "TEXT",
            "source_category": "TEXT",
            "source_name": "TEXT",
            "source_url": "TEXT",
            "format": "TEXT",
            "note_text": "TEXT",
            "memo": "TEXT",
            "seed_type": "TEXT",
            "priority": "TEXT",
            "confidence": "REAL",
            "detected_cards_json": "TEXT",
            "detected_deck_names_json": "TEXT",
            "detected_matchups_json": "TEXT",
            "detected_external_zone_cards_json": "TEXT",
            "detected_result_keywords_json": "TEXT",
            "detected_rate_keywords_json": "TEXT",
            "detected_tournament_keywords_json": "TEXT",
            "detected_region_keywords_json": "TEXT",
            "paper_diff_flag": "INTEGER DEFAULT 0",
            "mana_action": "TEXT",
            "strategy_hint": "TEXT",
            "required_tags_json": "TEXT",
            "avoid_tags_json": "TEXT",
            "candidate_origin": "TEXT",
        }.items():
            if column_name not in existing:
                conn.execute(f"ALTER TABLE meta_research_seeds ADD COLUMN {column_name} {column_type}")
        conn.commit()


def save_meta_research_seed(parsed: dict[str, Any], db_path: str | Path = DEFAULT_DB, seed_status: str = "queued") -> int:
    ensure_meta_research_seed_table(db_path)
    status = seed_status if seed_status in VALID_STATUSES else "queued"
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO meta_research_seeds (
                created_at, updated_at, seed_status, source_type, source_category,
                source_name, source_url, format, note_text, memo, seed_type,
                priority, confidence, detected_cards_json, detected_deck_names_json,
                detected_matchups_json, detected_external_zone_cards_json,
                detected_result_keywords_json, detected_rate_keywords_json,
                detected_tournament_keywords_json, detected_region_keywords_json,
                paper_diff_flag, mana_action, strategy_hint, required_tags_json,
                avoid_tags_json, candidate_origin
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                status,
                parsed.get("source_type", ""),
                parsed.get("source_category", ""),
                parsed.get("source_name", ""),
                parsed.get("source_url", ""),
                parsed.get("format", ""),
                parsed.get("note_text", ""),
                parsed.get("memo", ""),
                parsed.get("seed_type", ""),
                parsed.get("priority", ""),
                float(parsed.get("confidence", 0) or 0),
                _dump(parsed.get("detected_cards", [])),
                _dump(parsed.get("detected_deck_names", [])),
                _dump(parsed.get("detected_matchups", [])),
                _dump(parsed.get("detected_external_zone_cards", [])),
                _dump(parsed.get("detected_result_keywords", [])),
                _dump(parsed.get("detected_rate_keywords", [])),
                _dump(parsed.get("detected_tournament_keywords", [])),
                _dump(parsed.get("detected_region_keywords", [])),
                1 if parsed.get("paper_diff_flag") else 0,
                parsed.get("mana_action", ""),
                parsed.get("strategy_hint", ""),
                _dump(parsed.get("required_tags", [])),
                _dump(parsed.get("avoid_tags", [])),
                parsed.get("candidate_origin", ""),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def load_meta_research_seeds(
    db_path: str | Path = DEFAULT_DB,
    seed_status: str | None = None,
    seed_type: str | None = None,
    format_name: str | None = None,
    priority: str | None = None,
    source_type: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    ensure_meta_research_seed_table(db_path)
    where = []
    params: list[Any] = []
    if seed_status:
        where.append("seed_status = ?")
        params.append(seed_status)
    if seed_type:
        where.append("seed_type = ?")
        params.append(seed_type)
    if format_name:
        where.append("format = ?")
        params.append(format_name)
    if priority:
        where.append("priority = ?")
        params.append(priority)
    if source_type:
        where.append("source_type = ?")
        params.append(source_type)
    sql = "SELECT * FROM meta_research_seeds"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    with get_connection(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) for row in rows]


def load_queued_meta_research_seeds(db_path: str | Path = DEFAULT_DB, limit: int = 50) -> list[dict[str, Any]]:
    return load_meta_research_seeds(db_path, seed_status="queued", limit=limit)


def update_seed_status(seed_id: int, seed_status: str, db_path: str | Path = DEFAULT_DB) -> None:
    if seed_status not in VALID_STATUSES:
        raise ValueError(f"invalid seed_status: {seed_status}")
    ensure_meta_research_seed_table(db_path)
    with get_connection(db_path) as conn:
        conn.execute(
            "UPDATE meta_research_seeds SET seed_status = ?, updated_at = ? WHERE id = ?",
            (seed_status, datetime.now().isoformat(timespec="seconds"), int(seed_id)),
        )
        conn.commit()


def seed_strategy_memo(seed: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"seed_id: {seed.get('id')}",
            f"seed_type: {seed.get('seed_type')}",
            f"source_name: {seed.get('source_name')}",
            f"source_url: {seed.get('source_url')}",
            f"mana_action: {seed.get('mana_action')}",
            f"strategy_hint: {seed.get('strategy_hint')}",
        ]
    )


def summarize_seed_queue(db_path: str | Path = DEFAULT_DB) -> dict[str, Any]:
    ensure_meta_research_seed_table(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT seed_status, seed_type, priority, COUNT(*) AS n
            FROM meta_research_seeds
            GROUP BY seed_status, seed_type, priority
            """
        ).fetchall()
    return {"rows": [dict(row) for row in rows]}


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    for key in [
        "detected_cards",
        "detected_deck_names",
        "detected_matchups",
        "detected_external_zone_cards",
        "detected_result_keywords",
        "detected_rate_keywords",
        "detected_tournament_keywords",
        "detected_region_keywords",
        "required_tags",
        "avoid_tags",
    ]:
        json_key = key + "_json"
        data[key] = _load(data.get(json_key))
    data["paper_diff_flag"] = bool(data.get("paper_diff_flag"))
    return data


def _dump(value: Any) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def _load(value: Any) -> list[Any]:
    try:
        return json.loads(value or "[]")
    except Exception:
        return []

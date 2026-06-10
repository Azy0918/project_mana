from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.battle.effects.draft_generator import generate_draft_effect_script
from src.battle.effects.schema import validate_effect_script

# src.import_cards はStreamlit依存を含むため、ルールカーネルからは参照しない
ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "cards.db"

REVIEW_STATUSES = {"draft", "approved", "rejected"}


def ensure_card_effects_table(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS card_effects (
                card_id TEXT PRIMARY KEY,
                name TEXT,
                effect_json TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'draft',
                notes TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )


def upsert_effect_script(
    script: dict[str, Any],
    review_status: str = "draft",
    db_path: Path = DEFAULT_DB_PATH,
) -> list[str]:
    """EffectScriptを保存する。検証エラーがあれば保存せずエラー一覧を返す。"""
    if review_status not in REVIEW_STATUSES:
        return [f"未知のreview_status '{review_status}' (対応: {sorted(REVIEW_STATUSES)})"]
    errors = validate_effect_script(script)
    if errors:
        return errors
    ensure_card_effects_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO card_effects (card_id, name, effect_json, review_status, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                name = excluded.name,
                effect_json = excluded.effect_json,
                review_status = excluded.review_status,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                script["card_id"],
                script.get("name", ""),
                json.dumps(script, ensure_ascii=False),
                review_status,
                "\n".join(script.get("notes", [])),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
    return []


def get_effect_script(
    card_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    approved_only: bool = False,
) -> dict[str, Any] | None:
    ensure_card_effects_table(db_path)
    query = "SELECT effect_json, review_status FROM card_effects WHERE card_id = ?"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(query, (card_id,)).fetchone()
    if row is None:
        return None
    if approved_only and row[1] != "approved":
        return None
    script = json.loads(row[0])
    script["review_status"] = row[1]
    return script


def list_effect_scripts(
    db_path: Path = DEFAULT_DB_PATH,
    review_status: str | None = None,
) -> list[dict[str, Any]]:
    ensure_card_effects_table(db_path)
    query = "SELECT card_id, name, effect_json, review_status, notes, updated_at FROM card_effects"
    params: tuple[Any, ...] = ()
    if review_status:
        query += " WHERE review_status = ?"
        params = (review_status,)
    query += " ORDER BY card_id"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    results = []
    for card_id, name, effect_json, status, notes, updated_at in rows:
        script = json.loads(effect_json)
        results.append(
            {
                "card_id": card_id,
                "name": name,
                "abilities": script.get("abilities", []),
                "review_status": status,
                "notes": notes,
                "updated_at": updated_at,
            }
        )
    return results


def load_approved_effects_map(db_path: Path = DEFAULT_DB_PATH) -> dict[str, list[dict[str, Any]]]:
    """承認済みEffectScriptを card_id -> abilities のマップで返す(カーネル実行用)。"""
    ensure_card_effects_table(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT card_id, effect_json FROM card_effects WHERE review_status = 'approved'"
        ).fetchall()
    effects: dict[str, list[dict[str, Any]]] = {}
    for card_id, effect_json in rows:
        abilities = json.loads(effect_json).get("abilities", [])
        if abilities:
            effects[card_id] = abilities
    return effects


def generate_drafts_for_missing_cards(db_path: Path = DEFAULT_DB_PATH) -> int:
    """card_effects未登録のカードに対してEffectScript下書きを生成・保存する。"""
    ensure_card_effects_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT c.card_id, c.name, c.civilization, c.cost, c.card_type, c.power, c.text
            FROM cards c
            LEFT JOIN card_effects e ON e.card_id = c.card_id
            WHERE e.card_id IS NULL
            """
        ).fetchall()
    created = 0
    for row in rows:
        script = generate_draft_effect_script(dict(row))
        if not upsert_effect_script(script, review_status="draft", db_path=db_path):
            created += 1
    return created


def coverage_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """カードDB全体に対するEffectScript整備状況を返す(ダッシュボード表示用)。"""
    ensure_card_effects_table(db_path)
    with sqlite3.connect(db_path) as conn:
        total_cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        status_rows = conn.execute(
            "SELECT review_status, COUNT(*) FROM card_effects GROUP BY review_status"
        ).fetchall()
    status_counts = {status: count for status, count in status_rows}
    registered = sum(status_counts.values())
    approved = status_counts.get("approved", 0)
    return {
        "total_cards": total_cards,
        "registered": registered,
        "status_counts": status_counts,
        "approved_rate": approved / total_cards if total_cards else 0.0,
        "registered_rate": registered / total_cards if total_cards else 0.0,
    }

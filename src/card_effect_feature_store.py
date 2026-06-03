from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from src.card_effect_feature_builder import build_card_effect_features
from src.import_cards import DEFAULT_DB_PATH


DEFAULT_FEATURE_CSV_PATH = Path("data/card_effect_features.csv")

FEATURE_COLUMNS = [
    "card_id",
    "name",
    "trigger",
    "timing",
    "source_zone",
    "target_zone",
    "target_scope",
    "condition_signals",
    "cost_signals",
    "output_signals",
    "restriction_breaks",
    "repeatability",
    "uncertainty",
    "vulnerability",
    "win_contribution",
    "matchup_roles",
    "earliest_turn",
    "state_delta_json",
]


def ensure_card_effect_features(
    db_path: Path = DEFAULT_DB_PATH,
    csv_path: Path = DEFAULT_FEATURE_CSV_PATH,
    force: bool = False,
) -> int:
    ensure_card_effect_features_table(db_path)
    card_count = _count_table(db_path, "cards")
    feature_count = _count_table(db_path, "card_effect_features")
    if force or feature_count < card_count:
        return rebuild_card_effect_features(db_path=db_path, csv_path=csv_path)
    return feature_count


def ensure_card_effect_features_table(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS card_effect_features (
                card_id TEXT PRIMARY KEY,
                name TEXT,
                trigger TEXT,
                timing TEXT,
                source_zone TEXT,
                target_zone TEXT,
                target_scope TEXT,
                condition_signals TEXT,
                cost_signals TEXT,
                output_signals TEXT,
                restriction_breaks TEXT,
                repeatability TEXT,
                uncertainty TEXT,
                vulnerability TEXT,
                win_contribution TEXT,
                matchup_roles TEXT,
                earliest_turn INTEGER,
                state_delta_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def rebuild_card_effect_features(
    db_path: Path = DEFAULT_DB_PATH,
    csv_path: Path = DEFAULT_FEATURE_CSV_PATH,
) -> int:
    features = build_card_effect_features(db_path)
    ensure_card_effect_features_table(db_path)
    now = datetime.now().isoformat(timespec="seconds")

    rows = []
    for feature in features:
        rows.append({**feature, "created_at": now, "updated_at": now})

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM card_effect_features")
        conn.executemany(
            """
            INSERT INTO card_effect_features (
                card_id,
                name,
                trigger,
                timing,
                source_zone,
                target_zone,
                target_scope,
                condition_signals,
                cost_signals,
                output_signals,
                restriction_breaks,
                repeatability,
                uncertainty,
                vulnerability,
                win_contribution,
                matchup_roles,
                earliest_turn,
                state_delta_json,
                created_at,
                updated_at
            )
            VALUES (
                :card_id,
                :name,
                :trigger,
                :timing,
                :source_zone,
                :target_zone,
                :target_scope,
                :condition_signals,
                :cost_signals,
                :output_signals,
                :restriction_breaks,
                :repeatability,
                :uncertainty,
                :vulnerability,
                :win_contribution,
                :matchup_roles,
                :earliest_turn,
                :state_delta_json,
                :created_at,
                :updated_at
            )
            """,
            rows,
        )
        conn.commit()

    export_card_effect_features_csv(db_path=db_path, csv_path=csv_path)
    return len(rows)


def load_card_effect_features(
    db_path: Path = DEFAULT_DB_PATH,
    limit: int | None = None,
) -> pd.DataFrame:
    ensure_card_effect_features_table(db_path)
    sql = "SELECT * FROM card_effect_features ORDER BY card_id"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(sql, conn)


def export_card_effect_features_csv(
    db_path: Path = DEFAULT_DB_PATH,
    csv_path: Path = DEFAULT_FEATURE_CSV_PATH,
) -> Path:
    df = load_card_effect_features(db_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return csv_path


def summarize_card_effect_features(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_card_effect_features_table(db_path)
    with sqlite3.connect(db_path) as conn:
        feature_count = int(conn.execute("SELECT COUNT(*) FROM card_effect_features").fetchone()[0])
        card_count = _count_table(db_path, "cards")
        timing_rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(timing, ''), '不明') AS timing, COUNT(*) AS n
            FROM card_effect_features
            GROUP BY timing
            ORDER BY n DESC
            """
        ).fetchall()
        role_rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(win_contribution, ''), 'なし') AS win_contribution, COUNT(*) AS n
            FROM card_effect_features
            GROUP BY win_contribution
            ORDER BY n DESC
            LIMIT 20
            """
        ).fetchall()
    return {
        "card_count": card_count,
        "feature_count": feature_count,
        "complete": feature_count >= card_count and card_count > 0,
        "timings": dict(timing_rows),
        "win_contributions": dict(role_rows),
    }


def _count_table(db_path: Path, table: str) -> int:
    try:
        with sqlite3.connect(db_path) as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:
        return 0

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import Any

from src.research_logger import connect, ensure_log_tables
from src.search_cards import DEFAULT_DB_PATH


def _rows(sql: str, params: tuple[Any, ...] = (), db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_log_tables(db_path)
    with connect(db_path) as conn:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def list_evaluations(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT
            e.id,
            e.deck_id,
            d.name,
            d.source,
            e.total_score,
            e.novelty_score,
            e.meta_score,
            e.early_count,
            e.defense_count,
            e.finisher_count,
            e.created_at
        FROM evaluation_logs e
        JOIN deck_logs d ON d.deck_id = e.deck_id
        ORDER BY e.created_at DESC, e.id DESC
        """,
        db_path=db_path,
    )


def average_scores(db_path: Path = DEFAULT_DB_PATH) -> dict[str, float]:
    rows = _rows(
        """
        SELECT
            COUNT(*) AS count,
            AVG(total_score) AS avg_total_score,
            AVG(novelty_score) AS avg_novelty_score,
            AVG(meta_score) AS avg_meta_score
        FROM evaluation_logs
        """,
        db_path=db_path,
    )
    row = rows[0] if rows else {}
    return {
        "count": int(row.get("count") or 0),
        "avg_total_score": round(float(row.get("avg_total_score") or 0), 2),
        "avg_novelty_score": round(float(row.get("avg_novelty_score") or 0), 2),
        "avg_meta_score": round(float(row.get("avg_meta_score") or 0), 2),
    }


def top_deck_by(metric: str, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    allowed = {"total_score", "novelty_score", "meta_score"}
    if metric not in allowed:
        raise ValueError(f"Unsupported metric: {metric}")
    rows = _rows(
        f"""
        SELECT
            e.deck_id,
            d.name,
            d.source,
            d.deck_text,
            e.total_score,
            e.novelty_score,
            e.meta_score,
            e.created_at
        FROM evaluation_logs e
        JOIN deck_logs d ON d.deck_id = e.deck_id
        ORDER BY e.{metric} DESC, e.created_at DESC
        LIMIT 1
        """,
        db_path=db_path,
    )
    return rows[0] if rows else None


def best_score_deck(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    return top_deck_by("total_score", db_path)


def best_novelty_deck(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    return top_deck_by("novelty_score", db_path)


def best_meta_deck(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    return top_deck_by("meta_score", db_path)


def list_battles(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT
            b.battle_id,
            da.name AS deck_a_name,
            db.name AS deck_b_name,
            b.deck_a_win_rate,
            b.deck_b_win_rate,
            b.avg_finish_turn,
            b.trials,
            b.created_at
        FROM battle_logs b
        JOIN deck_logs da ON da.deck_id = b.deck_a_id
        JOIN deck_logs db ON db.deck_id = b.deck_b_id
        ORDER BY b.created_at DESC
        """,
        db_path=db_path,
    )


def evolution_score_history(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    return _rows(
        """
        SELECT
            run_id,
            generation,
            best_score,
            best_novelty_score,
            best_meta_score,
            focus_mode,
            created_at
        FROM evolution_logs
        ORDER BY created_at DESC, run_id DESC, generation ASC
        """,
        db_path=db_path,
    )


def export_rows_to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()

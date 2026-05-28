from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.research_logger import ensure_log_tables
from src.search_cards import DEFAULT_DB_PATH


def fetch_real_match_logs(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    ensure_log_tables(Path(db_path))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS real_match_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deck_name TEXT,
                deck_text TEXT,
                opponent_deck_type TEXT,
                play_order TEXT,
                result TEXT,
                finish_turn INTEGER,
                win_reason TEXT,
                lose_reason TEXT,
                key_cards TEXT,
                dead_cards TEXT,
                mistake_notes TEXT,
                video_ref TEXT,
                memo TEXT
            )
            """
        )
        rows = conn.execute(
            """
            SELECT *
            FROM real_match_logs
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def fetch_latest_evaluation_by_deck_name(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, dict[str, Any]]:
    ensure_log_tables(Path(db_path))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                d.name,
                e.total_score,
                e.novelty_score,
                e.meta_score,
                e.created_at
            FROM evaluation_logs e
            JOIN deck_logs d ON d.deck_id = e.deck_id
            ORDER BY e.created_at DESC, e.id DESC
            """
        ).fetchall()
    finally:
        conn.close()

    latest = {}
    for row in rows:
        name = row["name"] or "未設定"
        if name not in latest:
            latest[name] = dict(row)
    return latest


def calc_win_rate(logs: list[dict[str, Any]]) -> dict[str, Any]:
    if not logs:
        return {"matches": 0, "wins": 0, "losses": 0, "win_rate": 0.0}

    wins = sum(1 for log in logs if log.get("result") == "勝ち")
    losses = sum(1 for log in logs if log.get("result") == "負け")
    total = wins + losses
    return {
        "matches": len(logs),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
    }


def group_by_deck(logs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for log in logs:
        grouped[log.get("deck_name") or "未設定"].append(log)
    return dict(grouped)


def group_by_opponent_type(logs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for log in logs:
        grouped[log.get("opponent_deck_type") or "未設定"].append(log)
    return dict(grouped)


def group_by_play_order(logs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for log in logs:
        grouped[log.get("play_order") or "未設定"].append(log)
    return dict(grouped)


def calc_average_finish_turn(logs: list[dict[str, Any]]) -> float | None:
    turns = []
    for log in logs:
        value = log.get("finish_turn")
        if value in (None, ""):
            continue
        try:
            turns.append(int(value))
        except ValueError:
            continue
    if not turns:
        return None
    return round(sum(turns) / len(turns), 2)


def split_cards(text: str | None) -> list[str]:
    if not text:
        return []
    normalized = text.replace("、", "\n").replace(",", "\n").replace(";", "\n")
    return [item.strip() for item in normalized.splitlines() if item.strip()]


def count_card_mentions(logs: list[dict[str, Any]], field_name: str) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for log in logs:
        for card in split_cards(log.get(field_name, "")):
            counter[card] += 1
    return counter.most_common()


def analyze_deck_performance(
    logs: list[dict[str, Any]],
    evaluations_by_name: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    evaluations_by_name = evaluations_by_name or {}
    result = {}

    for deck_name, deck_logs in group_by_deck(logs).items():
        opponent_stats = {
            opponent: calc_win_rate(items)
            for opponent, items in group_by_opponent_type(deck_logs).items()
        }
        play_order_stats = {
            order: calc_win_rate(items)
            for order, items in group_by_play_order(deck_logs).items()
        }
        evaluation = evaluations_by_name.get(deck_name)
        overall = calc_win_rate(deck_logs)

        result[deck_name] = {
            "overall": overall,
            "average_finish_turn": calc_average_finish_turn(deck_logs),
            "by_opponent": opponent_stats,
            "by_play_order": play_order_stats,
            "key_cards": count_card_mentions(deck_logs, "key_cards"),
            "dead_cards": count_card_mentions(deck_logs, "dead_cards"),
            "evaluation": evaluation,
            "score_gap": round(overall["win_rate"] - float(evaluation["total_score"]), 1)
            if evaluation
            else None,
            "meta_gap": round(overall["win_rate"] - float(evaluation["meta_score"]), 1)
            if evaluation
            else None,
        }

    return result

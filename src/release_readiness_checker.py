from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.card_db_completion_checker import check_completion, load_cards
from src.db_bootstrap import ensure_cards_db_from_csv
from src.deck_builder import build_deck_for_request
from src.deck_condition_analyzer import analyze_deck_condition
from src.deck_generation_request import DeckGenerationRequest, parse_tag_input
from src.generated_deck_store import ensure_generated_decks_table
from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH


REQUIRED_RELEASE_TABLES = [
    "cards",
    "card_tags",
    "generated_decks",
    "deck_logs",
    "evaluation_logs",
    "real_match_logs",
    "deck_versions",
    "test_plans",
]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _count_table(conn: sqlite3.Connection, table_name: str) -> int:
    if not _table_exists(conn, table_name):
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0])


def _check_sample_deck_generation() -> dict[str, Any]:
    request = DeckGenerationRequest(
        deck_name="公開前診断サンプル",
        civilizations=["火", "自然"],
        deck_type="ランプ",
        focus_tags=parse_tag_input("マナ加速;フィニッシャー;除去;受け札"),
        avoid_tags=parse_tag_input("ハンデス"),
        strategy_note="公開前診断用のサンプル生成です。",
        deck_size=40,
        early_ratio=30,
        defense_ratio=30,
        finisher_ratio=20,
    )
    deck = build_deck_for_request(request, DEFAULT_DB_PATH, seed=1)
    analysis = analyze_deck_condition(
        deck_cards=deck,
        civilizations=request.civilizations,
        focus_tags=request.focus_tags,
        avoid_tags=request.avoid_tags,
        target_starter_count=round(request.deck_size * request.early_ratio / 100),
        target_defense_count=round(request.deck_size * request.defense_ratio / 100),
        target_finisher_count=round(request.deck_size * request.finisher_ratio / 100),
    )
    deck_size = sum(int(card.get("quantity", 1)) for card in deck)
    return {
        "deck_size": deck_size,
        "condition_score": analysis.condition_score,
        "civilization_match_rate": analysis.civilization_match_rate,
        "starter_count": analysis.starter_count,
        "defense_count": analysis.defense_count,
        "finisher_count": analysis.finisher_count,
        "warnings": analysis.warnings,
    }


def check_release_readiness(
    csv_path: Path = DEFAULT_CSV_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    issues: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []

    if not csv_path.exists():
        return {
            "ok": False,
            "status": "NG",
            "score": 0,
            "checks": [],
            "issues": [f"cards.csv が見つかりません: {csv_path}"],
            "warnings": [],
        }

    df = load_cards(csv_path)
    completion = check_completion(df)
    csv_count = int(completion.total_cards)
    checks.append({"項目": "cards.csv 件数", "結果": csv_count, "判定": "OK" if csv_count >= 1000 else "要確認"})
    if csv_count < 1000:
        issues.append(f"cards.csv が1000枚未満です: {csv_count}")
    if csv_count < 1250:
        warnings.append(f"現在の仮DB目標1250枚に届いていません: {csv_count}")

    if completion.score < 90:
        issues.append(f"仮カードDB完成度スコアが低めです: {completion.score}")
    checks.append({"項目": "仮DB完成度スコア", "結果": completion.score, "判定": "OK" if completion.score >= 90 else "要確認"})

    imported_count = ensure_cards_db_from_csv()
    ensure_generated_decks_table(db_path)
    checks.append({"項目": "CSV→DB自動反映", "結果": imported_count, "判定": "OK" if imported_count >= csv_count else "要確認"})

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
        checks.append({"項目": "SQLite quick_check", "結果": quick_check, "判定": "OK" if quick_check == "ok" else "NG"})
        if quick_check != "ok":
            issues.append(f"SQLite quick_check: {quick_check}")

        db_card_count = _count_table(conn, "cards")
        card_tag_count = _count_table(conn, "card_tags")
        checks.append({"項目": "cards テーブル件数", "結果": db_card_count, "判定": "OK" if db_card_count == csv_count else "要確認"})
        checks.append({"項目": "card_tags 件数", "結果": card_tag_count, "判定": "OK" if card_tag_count > 0 else "要確認"})

        if db_card_count != csv_count:
            issues.append(f"cards.csv とDB件数が一致していません: CSV {csv_count} / DB {db_card_count}")
        if card_tag_count <= 0:
            issues.append("card_tags が空です。デッキ生成のタグ参照が機能しません。")

        for table_name in REQUIRED_RELEASE_TABLES:
            exists = _table_exists(conn, table_name)
            checks.append({"項目": f"{table_name} テーブル", "結果": "あり" if exists else "なし", "判定": "OK" if exists else "NG"})
            if not exists:
                issues.append(f"公開前に必要なテーブルがありません: {table_name}")

    sample = _check_sample_deck_generation()
    checks.append({"項目": "サンプルデッキ生成枚数", "結果": sample["deck_size"], "判定": "OK" if sample["deck_size"] == 40 else "要確認"})
    checks.append({"項目": "サンプル条件適合スコア", "結果": sample["condition_score"], "判定": "OK" if sample["condition_score"] >= 70 else "要確認"})
    if sample["deck_size"] != 40:
        issues.append(f"サンプルデッキが40枚で生成されません: {sample['deck_size']}")
    if sample["condition_score"] < 70:
        warnings.append(f"サンプルデッキの条件適合スコアが低めです: {sample['condition_score']}")

    score = 100
    score -= len(issues) * 15
    score -= len(warnings) * 5
    score = max(0, min(100, score))
    ok = not issues and score >= 90

    return {
        "ok": ok,
        "status": "公開OK" if ok else "要確認",
        "score": score,
        "checks": checks,
        "issues": issues,
        "warnings": warnings,
        "sample_generation": sample,
    }

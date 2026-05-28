from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.analytics import list_evaluations
from src.card_csv_validator import validate_cards_csv
from src.data_health_checker import health_summary
from src.deck_change_analyzer import attach_match_stats_to_versions, compare_parent_child_stats
from src.deck_version_manager import list_deck_versions
from src.environment_checker import collect_environment_report
from src.import_cards import DEFAULT_CSV_PATH
from src.match_recorder import list_match_logs, win_rate_by_deck
from src.performance_analyzer import fetch_real_match_logs
from src.search_cards import DEFAULT_DB_PATH
from src.test_plan_manager import list_test_plan_targets, list_test_plans
from src.test_result_analyzer import analyze_test_plan


def collect_card_db_stats(
    db_path: Path = DEFAULT_DB_PATH,
    csv_path: Path = DEFAULT_CSV_PATH,
) -> dict[str, Any]:
    stats = {"card_count": 0, "missing_tag_count": 0, "csv_errors": 0, "csv_warnings": 0}

    if Path(db_path).exists():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            stats["card_count"] = int(conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
            stats["missing_tag_count"] = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM cards c
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM card_tags ct
                        WHERE ct.card_id = c.card_id
                    )
                    """
                ).fetchone()[0]
            )

    validation = validate_cards_csv(csv_path)
    stats["csv_errors"] = len(validation.get("errors", []))
    stats["csv_warnings"] = len(validation.get("warnings", []))
    return stats


def collect_research_stats(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    plans = list_test_plans(db_path)
    return {
        "evaluation_count": len(list_evaluations(db_path)),
        "match_log_count": len(fetch_real_match_logs(db_path)),
        "deck_version_count": len(list_deck_versions(db_path)),
        "active_test_plan_count": sum(1 for plan in plans if plan.get("status") == "検証中"),
    }


def collect_test_plan_status(db_path: Path = DEFAULT_DB_PATH) -> dict[str, list[dict[str, Any]]]:
    logs = fetch_real_match_logs(db_path)
    plans = list_test_plans(db_path)
    targets = list_test_plan_targets(db_path)
    targets_by_plan: dict[int, list[dict[str, Any]]] = {}
    for target in targets:
        targets_by_plan.setdefault(target["test_plan_id"], []).append(target)

    insufficient = []
    rework = []
    active = []
    for plan in plans:
        analysis = analyze_test_plan(plan, targets_by_plan.get(plan["id"], []), logs)
        progress = analysis["progress"]
        row = {
            "ID": plan["id"],
            "デッキ": plan.get("deck_name"),
            "バージョン": plan.get("version_name"),
            "目的": plan.get("purpose"),
            "状態": plan.get("status"),
            "判定": analysis["judgement"],
            "試合数": progress["matches"],
            "目標試合数": plan.get("target_matches"),
            "勝率": progress["win_rate"],
            "コメント": " / ".join(analysis["comments"][:2]),
        }
        if plan.get("status") == "検証中":
            active.append(row)
        if analysis["judgement"] == "継続":
            insufficient.append(row)
        if analysis["judgement"] == "再改良" or plan.get("status") == "再改良":
            rework.append(row)

    return {"active": active, "insufficient": insufficient, "rework": rework}


def collect_declining_decks(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    versions = attach_match_stats_to_versions(list_deck_versions(db_path), fetch_real_match_logs(db_path))
    rows = compare_parent_child_stats(versions)
    declining = [row for row in rows if float(row.get("勝率差") or 0) < 0]
    return sorted(declining, key=lambda row: float(row.get("勝率差") or 0))[:5]


def collect_dashboard_data(db_path: Path = DEFAULT_DB_PATH, csv_path: Path = DEFAULT_CSV_PATH) -> dict[str, Any]:
    card_stats = collect_card_db_stats(db_path, csv_path)
    research_stats = collect_research_stats(db_path)
    data_health = health_summary(db_path)
    environment = collect_environment_report()
    plan_status = collect_test_plan_status(db_path)
    recent_logs = list_match_logs(db_path)[:8]
    top_decks = win_rate_by_deck(db_path)[:5]
    declining_decks = collect_declining_decks(db_path)
    next_actions = build_next_actions(card_stats, research_stats, plan_status, declining_decks)
    if data_health["issue_count"]:
        next_actions.insert(0, "データ保守画面でDB健全性の問題を確認してください。")
    if environment["warnings"]:
        next_actions.insert(0, "設定画面で環境警告を確認してください。")

    return {
        "card_stats": card_stats,
        "research_stats": research_stats,
        "data_health": data_health,
        "environment": {
            "status": "OK" if environment["ok"] else "要確認",
            "warning_count": len(environment["warnings"]),
        },
        "recent_logs": recent_logs,
        "top_decks": top_decks,
        "declining_decks": declining_decks,
        "active_plans": plan_status["active"],
        "rework_candidates": plan_status["rework"],
        "insufficient_alerts": plan_status["insufficient"],
        "next_actions": next_actions,
    }


def build_next_actions(
    card_stats: dict[str, Any],
    research_stats: dict[str, Any],
    plan_status: dict[str, list[dict[str, Any]]],
    declining_decks: list[dict[str, Any]],
) -> list[str]:
    actions = []
    if card_stats["csv_errors"] or card_stats["csv_warnings"] or card_stats["missing_tag_count"]:
        actions.append("CSV管理でカードDBの警告、エラー、タグ未設定カードを確認してください。")
    if plan_status["insufficient"]:
        first = plan_status["insufficient"][0]
        actions.append(f'{first.get("デッキ") or "未設定デッキ"} の検証試合数が不足しています。追加ログを優先してください。')
    if plan_status["rework"]:
        first = plan_status["rework"][0]
        actions.append(f'{first.get("デッキ") or "未設定デッキ"} は再改良候補です。デッキ改良候補と履歴を確認してください。')
    if declining_decks:
        actions.append("親子比較で勝率低下しているバージョンがあります。差し替え履歴を見直してください。")
    if research_stats["match_log_count"] == 0:
        actions.append("まず対戦ログを数件保存すると、フィードバックとレポートが機能し始めます。")
    if not actions:
        actions.append("研究データは安定しています。次の検証計画を作るか、研究レポートを出力してください。")
    return actions

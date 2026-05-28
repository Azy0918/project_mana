from __future__ import annotations

from typing import Any

from src.deck_change_analyzer import attach_match_stats_to_versions, summarize_changes
from src.deck_feedback import generate_feedback
from src.deck_version_manager import list_deck_changes, list_deck_versions
from src.performance_analyzer import (
    analyze_deck_performance,
    fetch_latest_evaluation_by_deck_name,
    fetch_real_match_logs,
)
from src.search_cards import DEFAULT_DB_PATH
from src.test_plan_manager import list_test_plan_targets, list_test_plans
from src.test_result_analyzer import analyze_test_plan


def collect_report_context(deck_name: str, version_id: int | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    logs = fetch_real_match_logs(db_path)
    evaluations = fetch_latest_evaluation_by_deck_name(db_path)
    performance = analyze_deck_performance(logs, evaluations)
    versions = list_deck_versions(db_path)
    changes = list_deck_changes(db_path)
    test_plans = list_test_plans(db_path)
    test_targets = list_test_plan_targets(db_path)
    enriched_versions = attach_match_stats_to_versions(versions, logs)

    selected_version = None
    if version_id is not None:
        selected_version = next((version for version in enriched_versions if version["id"] == version_id), None)
        if selected_version:
            deck_name = selected_version["deck_name"]

    deck_versions = [version for version in enriched_versions if version.get("deck_name") == deck_name]
    deck_changes = [change for change in changes if change.get("version_id") in {version["id"] for version in deck_versions}]
    deck_plans = [
        plan
        for plan in test_plans
        if plan.get("deck_name") == deck_name
        or (selected_version and plan.get("deck_version_id") == selected_version["id"])
        or (selected_version and selected_version.get("version_name") and plan.get("version_name") == selected_version.get("version_name"))
    ]
    targets_by_plan: dict[int, list[dict[str, Any]]] = {}
    for target in test_targets:
        targets_by_plan.setdefault(target["test_plan_id"], []).append(target)

    plan_summaries = []
    for plan in deck_plans:
        analysis = analyze_test_plan(plan, targets_by_plan.get(plan["id"], []), logs)
        plan_summaries.append({"plan": plan, "analysis": analysis})

    performance_key = deck_name
    if selected_version and selected_version.get("version_name") in performance:
        performance_key = selected_version["version_name"]

    return {
        "deck_name": deck_name,
        "selected_version": selected_version,
        "performance": performance.get(performance_key),
        "versions": deck_versions,
        "changes": deck_changes,
        "plans": plan_summaries,
    }


def generate_research_report(deck_name: str, version_id: int | None = None, db_path=DEFAULT_DB_PATH) -> dict[str, Any]:
    context = collect_report_context(deck_name, version_id, db_path)
    title = _report_title(context)
    markdown = render_markdown_report(context, title)
    rows = build_report_rows(context)
    return {
        "title": title,
        "markdown": markdown,
        "rows": rows,
        "context": context,
    }


def render_markdown_report(context: dict[str, Any], title: str) -> str:
    performance = context.get("performance") or {}
    overall = performance.get("overall", {})
    evaluation = performance.get("evaluation") or _latest_version_scores(context.get("versions", []))
    lines = [f"# {title}", ""]

    lines.extend(
        [
            "## 概要",
            f"- 総合スコア: {_value(evaluation.get('total_score'))}",
            f"- 未知性スコア: {_value(evaluation.get('novelty_score'))}",
            f"- メタ適性スコア: {_value(evaluation.get('meta_score'))}",
            f"- 実戦勝率: {_value(overall.get('win_rate'), suffix='%')}",
            f"- 試合数: {_value(overall.get('matches'))}",
            f"- 平均決着ターン: {_value(performance.get('average_finish_turn'))}",
            "",
        ]
    )

    lines.extend(["## 対面別成績"])
    lines.extend(_stat_lines(performance.get("by_opponent", {}), "相手デッキタイプ"))
    lines.append("")

    lines.extend(["## 先攻/後攻別成績"])
    lines.extend(_stat_lines(performance.get("by_play_order", {}), "先攻/後攻"))
    lines.append("")

    lines.extend(["## 活躍カード"])
    lines.extend(_card_lines(performance.get("key_cards", [])))
    lines.append("")

    lines.extend(["## 腐ったカード"])
    lines.extend(_card_lines(performance.get("dead_cards", [])))
    lines.append("")

    lines.extend(["## 改良履歴"])
    lines.extend(_change_lines(context.get("versions", []), context.get("changes", [])))
    lines.append("")

    lines.extend(["## 検証計画"])
    lines.extend(_plan_lines(context.get("plans", [])))
    lines.append("")

    lines.extend(["## 次の改善方針"])
    lines.extend(_next_action_lines(context))
    lines.append("")

    return "\n".join(lines)


def build_report_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    performance = context.get("performance") or {}
    overall = performance.get("overall", {})
    evaluation = performance.get("evaluation") or _latest_version_scores(context.get("versions", []))
    rows = [
        {"section": "概要", "item": "デッキ名", "value": context["deck_name"]},
        {"section": "概要", "item": "総合スコア", "value": evaluation.get("total_score")},
        {"section": "概要", "item": "未知性スコア", "value": evaluation.get("novelty_score")},
        {"section": "概要", "item": "メタ適性スコア", "value": evaluation.get("meta_score")},
        {"section": "概要", "item": "実戦勝率", "value": overall.get("win_rate")},
        {"section": "概要", "item": "試合数", "value": overall.get("matches")},
    ]
    for opponent, item in (performance.get("by_opponent") or {}).items():
        rows.append({"section": "対面別成績", "item": opponent, "value": item.get("win_rate")})
    for plan in context.get("plans", []):
        rows.append({"section": "検証計画", "item": plan["plan"].get("purpose"), "value": plan["analysis"]["judgement"]})
    return rows


def _report_title(context: dict[str, Any]) -> str:
    version = context.get("selected_version")
    if version and version.get("version_name"):
        return f'{context["deck_name"]} {version["version_name"]} 研究レポート'
    return f'{context["deck_name"]} 研究レポート'


def _latest_version_scores(versions: list[dict[str, Any]]) -> dict[str, Any]:
    if not versions:
        return {}
    version = sorted(versions, key=lambda item: item["id"])[-1]
    return {
        "total_score": version.get("total_score"),
        "novelty_score": version.get("novelty_score"),
        "meta_score": version.get("meta_score"),
    }


def _stat_lines(stats: dict[str, dict[str, Any]], label: str) -> list[str]:
    if not stats:
        return [f"- {label}: データなし"]
    return [
        f"- {name}: {item.get('win_rate', 0)}% ({item.get('wins', 0)}勝/{item.get('matches', 0)}戦)"
        for name, item in stats.items()
    ]


def _card_lines(cards: list[tuple[str, int]]) -> list[str]:
    if not cards:
        return ["- データなし"]
    return [f"- {name}: {count}回" for name, count in cards[:10]]


def _change_lines(versions: list[dict[str, Any]], changes: list[dict[str, Any]]) -> list[str]:
    if not versions:
        return ["- バージョン履歴なし"]
    version_names = {version["id"]: version.get("version_name") or f'#{version["id"]}' for version in versions}
    grouped: dict[int, list[dict[str, Any]]] = {}
    for change in changes:
        grouped.setdefault(change["version_id"], []).append(change)
    lines = []
    for version in sorted(versions, key=lambda item: item["id"]):
        parent = version.get("parent_version_id")
        header = version_names[version["id"]] if not parent else f"{version_names.get(parent, '#' + str(parent))} -> {version_names[version['id']]}"
        lines.append(f"- {header}: {summarize_changes(grouped.get(version['id'], []))}")
    return lines


def _plan_lines(plans: list[dict[str, Any]]) -> list[str]:
    if not plans:
        return ["- 検証計画なし"]
    lines = []
    for item in plans:
        plan = item["plan"]
        progress = item["analysis"]["progress"]
        lines.append(
            f"- {plan.get('purpose') or '無題計画'}: {progress['matches']} / {plan.get('target_matches')}戦、"
            f"勝率 {progress['win_rate']}%、判定 {item['analysis']['judgement']}"
        )
    return lines


def _next_action_lines(context: dict[str, Any]) -> list[str]:
    comments = []
    performance = context.get("performance")
    if performance:
        comments.extend(generate_feedback(context["deck_name"], performance))
    for item in context.get("plans", []):
        comments.extend(item["analysis"].get("comments", []))
    if not comments:
        comments.append("追加の実戦ログと検証計画を作成すると、次の改善方針を具体化できます。")
    return [f"- {comment}" for comment in comments[:8]]


def _value(value: Any, suffix: str = "") -> str:
    if value is None:
        return "データなし"
    return f"{value}{suffix}"

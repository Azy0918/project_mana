from __future__ import annotations

from collections import defaultdict
from typing import Any


def logs_for_plan(plan: dict[str, Any], logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = {plan.get("deck_name") or "未設定"}
    if plan.get("version_name"):
        names.add(plan["version_name"])
    return [log for log in logs if (log.get("deck_name") or "未設定") in names]


def calc_basic_progress(logs: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(1 for log in logs if log.get("result") == "勝ち")
    losses = sum(1 for log in logs if log.get("result") == "負け")
    total = wins + losses
    turns = []
    for log in logs:
        value = log.get("finish_turn")
        if value in (None, ""):
            continue
        try:
            turns.append(int(value))
        except ValueError:
            continue
    return {
        "matches": len(logs),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
        "avg_finish_turn": round(sum(turns) / len(turns), 2) if turns else None,
    }


def calc_opponent_progress(
    logs: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for log in logs:
        grouped[log.get("opponent_deck_type") or "未設定"].append(log)

    rows = []
    for target in targets:
        opponent = target.get("opponent_deck_type") or "未設定"
        target_logs = grouped.get(opponent, [])
        progress = calc_basic_progress(target_logs)
        target_matches = int(target.get("target_matches") or 0)
        target_win_rate = float(target.get("target_win_rate") or 0)
        rows.append(
            {
                "相手デッキタイプ": opponent,
                "試合数": progress["matches"],
                "目標試合数": target_matches,
                "不足": max(0, target_matches - progress["matches"]),
                "勝率": progress["win_rate"],
                "目標勝率": target_win_rate,
                "試合数達成": progress["matches"] >= target_matches,
                "勝率達成": progress["win_rate"] >= target_win_rate if progress["matches"] else False,
            }
        )
    return rows


def analyze_test_plan(
    plan: dict[str, Any],
    targets: list[dict[str, Any]],
    logs: list[dict[str, Any]],
) -> dict[str, Any]:
    matched_logs = logs_for_plan(plan, logs)
    progress = calc_basic_progress(matched_logs)
    opponent_rows = calc_opponent_progress(matched_logs, targets)

    target_matches = int(plan.get("target_matches") or 0)
    target_win_rate = float(plan.get("target_win_rate") or 0)
    target_avg_finish_turn = float(plan.get("target_avg_finish_turn") or 0)

    match_ok = progress["matches"] >= target_matches
    win_rate_ok = progress["win_rate"] >= target_win_rate if progress["matches"] else False
    avg_turn = progress["avg_finish_turn"]
    turn_ok = True if not target_avg_finish_turn else avg_turn is not None and avg_turn <= target_avg_finish_turn
    targets_ok = all(row["試合数達成"] and row["勝率達成"] for row in opponent_rows) if opponent_rows else True

    comments = build_judgement_comments(
        progress=progress,
        opponent_rows=opponent_rows,
        target_matches=target_matches,
        target_win_rate=target_win_rate,
        target_avg_finish_turn=target_avg_finish_turn,
        match_ok=match_ok,
        win_rate_ok=win_rate_ok,
        turn_ok=turn_ok,
        targets_ok=targets_ok,
    )

    if match_ok and win_rate_ok and turn_ok and targets_ok:
        judgement = "検証完了"
    elif match_ok and (not win_rate_ok or not turn_ok or not targets_ok):
        judgement = "再改良"
    else:
        judgement = "継続"

    return {
        "matched_logs": matched_logs,
        "progress": progress,
        "opponent_progress": opponent_rows,
        "judgement": judgement,
        "comments": comments,
        "achieved": {
            "matches": match_ok,
            "win_rate": win_rate_ok,
            "avg_finish_turn": turn_ok,
            "opponent_targets": targets_ok,
        },
    }


def build_judgement_comments(
    progress: dict[str, Any],
    opponent_rows: list[dict[str, Any]],
    target_matches: int,
    target_win_rate: float,
    target_avg_finish_turn: float,
    match_ok: bool,
    win_rate_ok: bool,
    turn_ok: bool,
    targets_ok: bool,
) -> list[str]:
    comments = []
    if not match_ok:
        comments.append(f"まだ試行数不足です。あと{max(0, target_matches - progress['matches'])}戦追加してください。")
    if match_ok and not win_rate_ok:
        comments.append(f"全体勝率が目標の{target_win_rate}%に届いていません。再改良候補です。")
    if target_avg_finish_turn and not turn_ok:
        comments.append(f"平均決着ターンが目標の{target_avg_finish_turn}以下に届いていません。速度か防御配分を確認してください。")

    for row in opponent_rows:
        if not row["試合数達成"]:
            comments.append(f"{row['相手デッキタイプ']}対面をあと{row['不足']}戦追加してください。")
        elif not row["勝率達成"]:
            comments.append(f"{row['相手デッキタイプ']}対面の勝率が目標未達です。対策カードの再検討が必要です。")

    if match_ok and win_rate_ok and turn_ok and targets_ok:
        comments.append("検証条件を満たしています。このバージョンは一旦採用候補です。")
    elif not comments:
        comments.append("検証は継続中です。重点対面のログを増やしてください。")
    return comments


def summarize_plan_rows(
    plans: list[dict[str, Any]],
    targets_by_plan: dict[int, list[dict[str, Any]]],
    logs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for plan in plans:
        analysis = analyze_test_plan(plan, targets_by_plan.get(plan["id"], []), logs)
        progress = analysis["progress"]
        rows.append(
            {
                "ID": plan["id"],
                "デッキ": plan.get("deck_name"),
                "バージョン": plan.get("version_name"),
                "目的": plan.get("purpose"),
                "状態": plan.get("status"),
                "判定": analysis["judgement"],
                "試合数": progress["matches"],
                "目標試合数": plan.get("target_matches"),
                "勝率": progress["win_rate"],
                "目標勝率": plan.get("target_win_rate"),
                "平均決着ターン": progress["avg_finish_turn"],
                "目標平均決着ターン": plan.get("target_avg_finish_turn"),
            }
        )
    return rows

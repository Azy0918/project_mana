from __future__ import annotations

from dataclasses import dataclass
from typing import Any


MANA_CORE_HYPOTHESIS = (
    "Project MANAが目指すものは未知の勝利ルート探索。"
    "未知コンボは部品、未知シナジーは接続、未知勝利ルートが成果物である。"
    "MANAは、既知カード群の中から人間がまだ十分に評価していない状態変換連鎖を見つけ、"
    "それが既存環境に対して有効な勝利状態へ到達するルートを発見することを目的とする。"
    "探索は、未知シナジー、状態変換連鎖、勝利条件到達、環境への有効性の順に進める。"
)


@dataclass(frozen=True)
class WinCondition:
    key: str
    name: str
    summary: str
    required_states: list[str]
    supporting_states: list[str]
    risk_states: list[str]
    mana_question: str


WIN_CONDITIONS = [
    WinCondition(
        key="direct_attack_win",
        name="直接攻撃勝利",
        summary="相手のシールドを割り切り、最後の攻撃を通す勝ち筋。",
        required_states=["damage_pressure", "attack_permission"],
        supporting_states=["tempo", "board", "turn_count"],
        risk_states=["trigger_window", "defense"],
        mana_question="攻撃可能な打点が、相手のシールドと防御を超えているか。",
    ),
    WinCondition(
        key="damage_overflow_win",
        name="打点過剰勝利",
        summary="複数打点や連続攻撃で、受け札を踏んでも押し切る勝ち筋。",
        required_states=["damage_pressure", "board"],
        supporting_states=["attack_permission", "tempo", "action_window"],
        risk_states=["trigger_window", "replacement_shield", "opponent_action_lock"],
        mana_question="過剰打点があり、S・トリガーやブロッカーを踏んでも勝ち切れるか。",
    ),
    WinCondition(
        key="alternate_effect_win",
        name="特殊勝利",
        summary="カード効果の条件を満たしてゲーム勝利へ到達する勝ち筋。",
        required_states=["alternate_win_progress"],
        supporting_states=["hand", "shield", "board", "resource_loop", "turn_count"],
        risk_states=["effect_permission", "opponent_action_lock"],
        mana_question="特殊勝利条件を満たすための前提状態が連鎖で作れているか。",
    ),
    WinCondition(
        key="opponent_deckout_win",
        name="相手山札切れ勝利",
        summary="相手に山札切れや強制ドローを迫る勝ち筋。",
        required_states=["opponent_deck_pressure"],
        supporting_states=["disruption", "defense", "opponent_action_lock", "resource_loop"],
        risk_states=["deck_out_prevention", "turn_count"],
        mana_question="相手の山札やリソースを削り、こちらが先に負けない状態か。",
    ),
    WinCondition(
        key="lock_confirmed_win",
        name="ロック完了による実質勝利",
        summary="相手の有効行動を封じ、こちらの勝利手段だけが残る状態。",
        required_states=["opponent_action_lock"],
        supporting_states=["cast_permission", "summon_permission", "attack_permission", "board_persistence", "defense"],
        risk_states=["zone_change_permission", "effect_permission"],
        mana_question="相手の召喚、詠唱、攻撃、効果のどれを止め、こちらの勝ち筋は残っているか。",
    ),
    WinCondition(
        key="loop_converted_win",
        name="ループ変換勝利",
        summary="リソースループを打点、特殊勝利、山札切れ、追加ターンなどへ変換する勝ち筋。",
        required_states=["resource_loop"],
        supporting_states=["action_window", "turn_count", "win_progress", "alternate_win_progress", "damage_pressure"],
        risk_states=["opponent_action_lock", "effect_permission"],
        mana_question="ループの出力が、実際の勝利状態へ変換されているか。",
    ),
]


def list_win_conditions() -> list[dict[str, Any]]:
    return [
        {
            "key": condition.key,
            "勝利条件": condition.name,
            "概要": condition.summary,
            "必須状態": ";".join(condition.required_states),
            "補助状態": ";".join(condition.supporting_states),
            "リスク状態": ";".join(condition.risk_states),
            "MANA確認質問": condition.mana_question,
        }
        for condition in WIN_CONDITIONS
    ]


def assess_win_condition_reach(state_delta: dict[str, int]) -> dict[str, Any]:
    candidates = []
    for condition in WIN_CONDITIONS:
        required_score = sum(max(0, int(state_delta.get(key, 0))) for key in condition.required_states)
        support_score = sum(max(0, int(state_delta.get(key, 0))) for key in condition.supporting_states)
        risk_score = sum(abs(min(0, int(state_delta.get(key, 0)))) for key in condition.risk_states)

        score = required_score * 28 + support_score * 9 - risk_score * 6
        if condition.key == "opponent_deckout_win":
            score += max(0, state_delta.get("disruption", 0)) * 8
        if condition.key == "lock_confirmed_win":
            score += max(0, state_delta.get("disruption", 0)) * 5
        if condition.key == "loop_converted_win" and (
            state_delta.get("alternate_win_progress", 0) > 0
            or state_delta.get("damage_pressure", 0) > 0
            or state_delta.get("turn_count", 0) > 0
        ):
            score += 18

        score = max(0, min(100, score))
        if score <= 0:
            continue
        candidates.append(
            {
                "勝利条件": condition.name,
                "到達スコア": score,
                "根拠状態": _active_states(
                    state_delta,
                    condition.required_states + condition.supporting_states,
                ),
                "確認質問": condition.mana_question,
            }
        )

    candidates.sort(key=lambda item: item["到達スコア"], reverse=True)
    best = candidates[0] if candidates else None
    return {
        "best_condition": best["勝利条件"] if best else "未到達",
        "best_score": best["到達スコア"] if best else 0,
        "candidates": candidates[:3],
        "comment": _build_comment(best),
    }


def summarize_mana_core_hypothesis() -> dict[str, Any]:
    return {
        "設計思想": MANA_CORE_HYPOTHESIS,
        "勝利条件数": len(WIN_CONDITIONS),
        "勝利条件": [condition.name for condition in WIN_CONDITIONS],
    }


def _active_states(state_delta: dict[str, int], keys: list[str]) -> str:
    parts = [f"{key}:{state_delta.get(key):+d}" for key in keys if state_delta.get(key)]
    return " / ".join(parts) if parts else "なし"


def _build_comment(best: dict[str, Any] | None) -> str:
    if not best:
        return "この状態変換連鎖は、まだ明確な勝利状態へ接続していません。"
    return f"{best['勝利条件']}へ近づく状態変換連鎖候補です。{best['確認質問']}"

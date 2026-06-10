from __future__ import annotations

from typing import Any


def _quantity(card: dict[str, Any]) -> int:
    try:
        return int(card.get("quantity", 1))
    except Exception:
        return 1


def _tag_count(deck: list[dict[str, Any]], keywords: list[str]) -> int:
    count = 0
    for card in deck:
        tags = str(card.get("tags", ""))
        if any(keyword in tags for keyword in keywords):
            count += _quantity(card)
    return count


def _multicolor_count(deck: list[dict[str, Any]]) -> int:
    count = 0
    for card in deck:
        civilization = str(card.get("civilization", ""))
        if "/" in civilization or "多色" in str(card.get("tags", "")):
            count += _quantity(card)
    return count


def score_deck_candidate(
    evaluation: dict[str, Any],
    condition_analysis: Any,
    deck: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evaluation_score = float(evaluation.get("score", 0))
    novelty_score = float(evaluation.get("novelty_score", 0))
    meta_score = float(evaluation.get("meta_score", 0))
    condition_score = float(getattr(condition_analysis, "condition_score", 0))
    deck = deck or []

    role_bonus = 0
    if getattr(condition_analysis, "starter_count", 0) >= 8:
        role_bonus += 5
    if getattr(condition_analysis, "defense_count", 0) >= 8:
        role_bonus += 5
    if getattr(condition_analysis, "finisher_count", 0) >= 4:
        role_bonus += 5
    if getattr(condition_analysis, "removal_count", 0) >= 6:
        role_bonus += 3
    if getattr(condition_analysis, "draw_count", 0) >= 6:
        role_bonus += 3

    unknown_tag_count = _tag_count(deck, ["未知", "コンボ", "踏み倒し", "ロック", "墓地利用"])
    combo_tag_count = _tag_count(deck, ["コンボ", "踏み倒し", "連鎖", "墓地利用"])
    multicolor_count = _multicolor_count(deck)

    unknown_bonus = min(8, unknown_tag_count)
    combo_bonus = min(8, combo_tag_count)
    multicolor_bonus = min(6, multicolor_count // 2)

    shortage_penalty = 0
    if getattr(condition_analysis, "starter_count", 0) < 8:
        shortage_penalty += 8
    if getattr(condition_analysis, "defense_count", 0) < 8:
        shortage_penalty += 8
    if getattr(condition_analysis, "finisher_count", 0) < 4:
        shortage_penalty += 8

    warning_penalty = len(getattr(condition_analysis, "warnings", [])) * 5
    candidate_score = round(
        evaluation_score * 0.35
        + condition_score * 0.35
        + novelty_score * 0.15
        + meta_score * 0.15
        + role_bonus
        + unknown_bonus
        + combo_bonus
        + multicolor_bonus
        - shortage_penalty
        - warning_penalty,
        1,
    )
    candidate_score = max(0.0, min(120.0, candidate_score))

    return {
        "candidate_score": candidate_score,
        "evaluation_score": evaluation_score,
        "condition_score": condition_score,
        "novelty_score": novelty_score,
        "meta_score": meta_score,
        "role_bonus": role_bonus,
        "unknown_bonus": unknown_bonus,
        "combo_bonus": combo_bonus,
        "multicolor_bonus": multicolor_bonus,
        "shortage_penalty": shortage_penalty,
        "warning_penalty": warning_penalty,
    }


def apply_sim_strength(
    score_result: dict[str, Any],
    sim_win_rate: float,
    weight: float = 0.3,
) -> dict[str, Any]:
    """厳密シミュレーションの対メタ勝率を候補スコアに合成する。

    weight はシミュレーション側の比重(0〜1)。既定0.3は暫定値で、
    実勝率との回帰により今後調整する。
    """
    weight = max(0.0, min(1.0, weight))
    sim_strength_score = round(sim_win_rate * 100, 1)
    base_score = float(score_result.get("candidate_score", 0))
    blended = round(base_score * (1 - weight) + (sim_win_rate * 120) * weight, 1)
    result = dict(score_result)
    result["sim_win_rate"] = sim_win_rate
    result["sim_strength_score"] = sim_strength_score
    result["sim_weight"] = weight
    result["candidate_score_with_sim"] = max(0.0, min(120.0, blended))
    return result

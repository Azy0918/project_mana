from __future__ import annotations

from collections import Counter
from typing import Any

from src.matchup_estimator import estimate_meta_matchups
from src.novelty_score import calculate_novelty_score


EARLY_TAGS = {"初動", "マナ加速"}
RAMP_TAGS = {"マナ加速"}
DEFENSE_TAGS = {"受け札", "S・トリガー", "防御", "除去", "バウンス", "タップ"}
FINISHER_TAGS = {"フィニッシャー", "W・ブレイカー", "進化", "ドラゴン", "ロック"}


def split_tags(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [tag for tag in value if tag]
    return [tag.strip() for tag in value.split(";") if tag.strip()]


def expand_deck(deck: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded = []
    for card in deck:
        quantity = int(card.get("quantity", 1))
        for _ in range(quantity):
            expanded.append(card)
    return expanded


def _civilizations(card: dict[str, Any]) -> list[str]:
    return [civ.strip() for civ in str(card.get("civilization", "")).split("/") if civ.strip()]


def _count_cards_with_tags(cards: list[dict[str, Any]], target_tags: set[str]) -> int:
    return sum(1 for card in cards if target_tags.intersection(split_tags(card.get("tags"))))


def _score_range(value: int, low: int, high: int, max_points: int) -> int:
    if low <= value <= high:
        return max_points
    distance = low - value if value < low else value - high
    return max(0, max_points - distance * 5)


def evaluate_deck(
    deck: list[dict[str, Any]],
    known_decks: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    expanded = expand_deck(deck)
    total_cards = len(expanded)

    name_counts = Counter(card["name"] for card in expanded)
    cost_curve = Counter(int(card["cost"]) for card in expanded)
    tag_counts: Counter[str] = Counter()
    civilization_counts: Counter[str] = Counter()

    for card in expanded:
        tag_counts.update(split_tags(card.get("tags")))
        civilization_counts.update(_civilizations(card))

    early_count = _count_cards_with_tags(expanded, EARLY_TAGS)
    ramp_count = _count_cards_with_tags(expanded, RAMP_TAGS)
    defense_count = _count_cards_with_tags(expanded, DEFENSE_TAGS)
    finisher_count = _count_cards_with_tags(expanded, FINISHER_TAGS)
    low_cost_count = sum(count for cost, count in cost_curve.items() if cost <= 3)

    size_score = 20 if total_cards == 40 else max(0, 20 - abs(40 - total_cards) * 2)
    duplicate_penalty = sum(max(0, count - 4) * 5 for count in name_counts.values())
    role_score = (
        _score_range(early_count, 8, 14, 20)
        + _score_range(ramp_count, 4, 10, 15)
        + _score_range(defense_count, 8, 14, 20)
        + _score_range(finisher_count, 4, 8, 15)
    )
    curve_score = _score_range(low_cost_count, 12, 20, 20)
    civ_score = 10 if 1 <= len(civilization_counts) <= 3 else 5
    total_score = max(0, min(100, size_score + role_score + curve_score + civ_score - duplicate_penalty))
    novelty = calculate_novelty_score(deck, known_decks)
    meta_matchups = estimate_meta_matchups(deck)

    warnings = []
    if total_cards != 40:
        warnings.append(f"デッキ枚数が{total_cards}枚です。40枚にしてください。")
    over_limit = [name for name, count in name_counts.items() if count > 4]
    if over_limit:
        warnings.append("同名4枚を超えているカードがあります: " + "、".join(over_limit))
    if early_count < 8:
        warnings.append("初動またはマナ加速が少なめです。")
    if defense_count < 8:
        warnings.append("受け札が少なめです。")
    if finisher_count < 4:
        warnings.append("フィニッシャー候補が少なめです。")
    if len(civilization_counts) > 3:
        warnings.append("文明が多く、色事故のリスクがあります。")

    return {
        "total_cards": total_cards,
        "score": total_score,
        "novelty_score": novelty["score"],
        "novelty": novelty,
        "meta_score": meta_matchups["overall_score"],
        "meta_matchups": meta_matchups,
        "role_counts": {
            "初動": early_count,
            "マナ加速": ramp_count,
            "受け札": defense_count,
            "フィニッシャー": finisher_count,
        },
        "cost_curve": dict(sorted(cost_curve.items())),
        "tag_counts": dict(tag_counts.most_common()),
        "civilization_counts": dict(civilization_counts.most_common()),
        "name_counts": dict(name_counts.most_common()),
        "warnings": warnings,
    }

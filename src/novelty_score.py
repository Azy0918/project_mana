from __future__ import annotations

from collections import Counter
from typing import Any


COMMON_ROLE_TAGS = {
    "初動",
    "マナ加速",
    "受け札",
    "S・トリガー",
    "防御",
    "除去",
    "フィニッシャー",
    "W・ブレイカー",
}


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


def _normalize(counter: Counter[Any]) -> dict[Any, float]:
    total = sum(counter.values())
    if total <= 0:
        return {}
    return {key: value / total for key, value in counter.items()}


def _civilizations(card: dict[str, Any]) -> list[str]:
    return [civ.strip() for civ in str(card.get("civilization", "")).split("/") if civ.strip()]


def card_distribution(deck: list[dict[str, Any]]) -> dict[str, float]:
    cards = expand_deck(deck)
    return _normalize(Counter(card["name"] for card in cards))


def tag_distribution(deck: list[dict[str, Any]]) -> dict[str, float]:
    counter: Counter[str] = Counter()
    for card in expand_deck(deck):
        counter.update(split_tags(card.get("tags")))
    return _normalize(counter)


def civilization_distribution(deck: list[dict[str, Any]]) -> dict[str, float]:
    counter: Counter[str] = Counter()
    for card in expand_deck(deck):
        counter.update(_civilizations(card))
    return _normalize(counter)


def cost_distribution(deck: list[dict[str, Any]]) -> dict[int, float]:
    cards = expand_deck(deck)
    return _normalize(Counter(int(card["cost"]) for card in cards))


def jaccard_similarity(left: set[Any], right: set[Any]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def deck_card_similarity(deck: list[dict[str, Any]], other_deck: list[dict[str, Any]]) -> float:
    left = set(card_distribution(deck).keys())
    right = set(card_distribution(other_deck).keys())
    return jaccard_similarity(left, right)


def tag_similarity(deck: list[dict[str, Any]], other_deck: list[dict[str, Any]]) -> float:
    left = set(tag_distribution(deck).keys())
    right = set(tag_distribution(other_deck).keys())
    return jaccard_similarity(left, right)


def distribution_distance(left: dict[Any, float], right: dict[Any, float]) -> float:
    keys = set(left) | set(right)
    if not keys:
        return 0.0
    return sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in keys) / 2


def cost_distribution_difference(deck: list[dict[str, Any]], other_deck: list[dict[str, Any]]) -> float:
    return distribution_distance(cost_distribution(deck), cost_distribution(other_deck))


def deck_similarity(deck: list[dict[str, Any]], other_deck: list[dict[str, Any]]) -> dict[str, float]:
    card_sim = deck_card_similarity(deck, other_deck)
    tag_sim = tag_similarity(deck, other_deck)
    civ_distance = distribution_distance(civilization_distribution(deck), civilization_distribution(other_deck))
    cost_distance = cost_distribution_difference(deck, other_deck)
    weighted_similarity = (
        card_sim * 0.45
        + tag_sim * 0.25
        + (1 - civ_distance) * 0.15
        + (1 - cost_distance) * 0.15
    )
    return {
        "card_jaccard": card_sim,
        "tag_jaccard": tag_sim,
        "civilization_distance": civ_distance,
        "cost_distance": cost_distance,
        "weighted_similarity": max(0.0, min(1.0, weighted_similarity)),
    }


def _rarity_without_reference(deck: list[dict[str, Any]]) -> dict[str, float]:
    cards = expand_deck(deck)
    card_dist = card_distribution(deck)
    tag_dist = tag_distribution(deck)
    civ_dist = civilization_distribution(deck)
    cost_dist = cost_distribution(deck)

    duplicate_pressure = max(card_dist.values(), default=0.0)
    card_variety = 1 - duplicate_pressure
    off_role_tags = [tag for tag in tag_dist if tag not in COMMON_ROLE_TAGS]
    tag_variety = min(1.0, len(tag_dist) / 14)
    off_role_ratio = sum(tag_dist[tag] for tag in off_role_tags)
    civ_mix = 1 - max(civ_dist.values(), default=1.0)
    high_cost_ratio = sum(value for cost, value in cost_dist.items() if int(cost) >= 7)
    unusual_curve = min(1.0, high_cost_ratio * 2)

    rarity = (
        card_variety * 0.25
        + tag_variety * 0.25
        + off_role_ratio * 0.20
        + civ_mix * 0.15
        + unusual_curve * 0.15
    )

    if len(cards) == 0:
        rarity = 0.0

    return {
        "card_variety": card_variety,
        "tag_variety": tag_variety,
        "off_role_tag_ratio": off_role_ratio,
        "civilization_mix": civ_mix,
        "unusual_curve": unusual_curve,
        "rarity": max(0.0, min(1.0, rarity)),
    }


def calculate_novelty_score(
    deck: list[dict[str, Any]],
    known_decks: list[list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    known_decks = known_decks or []
    rarity = _rarity_without_reference(deck)

    similarities = [deck_similarity(deck, known_deck) for known_deck in known_decks]
    max_similarity = max((item["weighted_similarity"] for item in similarities), default=0.0)
    similarity_novelty = 1 - max_similarity

    if similarities:
        novelty = similarity_novelty * 0.70 + rarity["rarity"] * 0.30
    else:
        novelty = rarity["rarity"]

    return {
        "score": round(max(0.0, min(1.0, novelty)) * 100),
        "reference_deck_count": len(known_decks),
        "max_similarity": max_similarity,
        "rarity": rarity,
        "similarities": similarities,
    }

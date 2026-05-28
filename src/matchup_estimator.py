from __future__ import annotations

from collections import Counter
from typing import Any

from src.meta_profiles import META_PROFILES, MetaProfile


EARLY_TAGS = {"初動", "マナ加速"}
RAMP_TAGS = {"マナ加速"}
DEFENSE_TAGS = {"受け札", "S・トリガー", "防御", "除去", "バウンス", "タップ"}
FINISHER_TAGS = {"フィニッシャー", "W・ブレイカー", "進化", "ドラゴン", "ロック"}
RESOURCE_TAGS = {"ドロー", "リソース", "ハンデス", "マナ加速"}
INTERACTION_TAGS = {"除去", "バウンス", "タップ", "ロック", "ハンデス"}


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


def _count_cards_with_tags(cards: list[dict[str, Any]], tags: set[str]) -> int:
    return sum(1 for card in cards if tags.intersection(split_tags(card.get("tags"))))


def _tag_counter(cards: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for card in cards:
        counter.update(split_tags(card.get("tags")))
    return counter


def _ratio(value: int, target: int) -> float:
    if target <= 0:
        return 1.0
    return min(1.0, value / target)


def _deck_features(deck: list[dict[str, Any]]) -> dict[str, Any]:
    cards = expand_deck(deck)
    total = max(1, len(cards))
    cost_counts = Counter(int(card["cost"]) for card in cards)
    low_cost = sum(count for cost, count in cost_counts.items() if cost <= 3)
    mid_cost = sum(count for cost, count in cost_counts.items() if 4 <= cost <= 6)
    high_cost = sum(count for cost, count in cost_counts.items() if cost >= 7)
    tags = _tag_counter(cards)

    early = _count_cards_with_tags(cards, EARLY_TAGS)
    ramp = _count_cards_with_tags(cards, RAMP_TAGS)
    defense = _count_cards_with_tags(cards, DEFENSE_TAGS)
    finisher = _count_cards_with_tags(cards, FINISHER_TAGS)
    resource = _count_cards_with_tags(cards, RESOURCE_TAGS)
    interaction = _count_cards_with_tags(cards, INTERACTION_TAGS)

    return {
        "total": total,
        "tags": tags,
        "early": early,
        "ramp": ramp,
        "defense": defense,
        "finisher": finisher,
        "resource": resource,
        "interaction": interaction,
        "low_cost": low_cost,
        "mid_cost": mid_cost,
        "high_cost": high_cost,
        "speed_index": _ratio(low_cost + early, 22),
        "defense_index": _ratio(defense, 14),
        "resource_index": _ratio(resource, 12),
        "finish_index": _ratio(finisher + high_cost, 12),
    }


def _tag_coverage_score(profile: MetaProfile, tags: Counter[str]) -> float:
    if not profile.required_tags:
        return 0.5
    covered = sum(1 for tag in profile.required_tags if tags.get(tag, 0) > 0)
    return covered / len(profile.required_tags)


def _bounded_score(value: float) -> int:
    return round(max(0.0, min(1.0, value)) * 100)


def _factors(profile: MetaProfile, features: dict[str, Any], score: int) -> tuple[list[str], list[str]]:
    favorable = []
    unfavorable = []

    if features["early"] >= 8:
        favorable.append("初動枚数が十分で、序盤の再現性があります。")
    else:
        unfavorable.append("初動枚数が少なく、序盤に出遅れる可能性があります。")

    if features["defense"] >= 10:
        favorable.append("受け札が厚く、攻めを止める余地があります。")
    elif profile.speed >= 4:
        unfavorable.append("速い相手に対して受け札が不足気味です。")

    if features["resource"] >= 8:
        favorable.append("リソース札があり、長期戦で息切れしにくい構成です。")
    elif profile.resource >= 4:
        unfavorable.append("リソース性能の高い相手に付き合うと息切れしやすいです。")

    if features["interaction"] >= 6:
        favorable.append("除去や妨害タグがあり、相手の勝ち筋に触れます。")
    elif profile.name in {"コンボ", "コントロール"}:
        unfavorable.append("妨害タグが少なく、相手の主導権を崩しにくいです。")

    if features["finisher"] >= 6:
        favorable.append("フィニッシャー候補があり、勝ち切る手段を確保しています。")
    elif profile.defense >= 4:
        unfavorable.append("受けの厚い相手を突破する決定力が不足気味です。")

    if score >= 70:
        favorable.append(f"{profile.name}に対して総合的に戦える見込みがあります。")
    elif score <= 45:
        unfavorable.append(f"{profile.name}への対策は追加検証が必要です。")

    return favorable[:4], unfavorable[:4]


def estimate_matchup(deck: list[dict[str, Any]], profile: MetaProfile) -> dict[str, Any]:
    features = _deck_features(deck)
    tag_score = _tag_coverage_score(profile, features["tags"])
    speed_score = features["speed_index"]
    defense_score = features["defense_index"]
    resource_score = features["resource_index"]
    finish_score = features["finish_index"]
    interaction_score = _ratio(features["interaction"], 10)

    if profile.name == "速攻":
        raw = defense_score * 0.40 + speed_score * 0.25 + interaction_score * 0.20 + tag_score * 0.15
    elif profile.name == "中速":
        raw = speed_score * 0.25 + defense_score * 0.20 + resource_score * 0.20 + finish_score * 0.20 + tag_score * 0.15
    elif profile.name == "コントロール":
        raw = resource_score * 0.35 + finish_score * 0.25 + interaction_score * 0.20 + tag_score * 0.20
    elif profile.name == "コンボ":
        raw = speed_score * 0.25 + interaction_score * 0.35 + resource_score * 0.20 + tag_score * 0.20
    else:
        raw = finish_score * 0.35 + resource_score * 0.25 + interaction_score * 0.20 + tag_score * 0.20

    score = _bounded_score(raw)
    favorable, unfavorable = _factors(profile, features, score)
    return {
        "profile": profile.name,
        "score": score,
        "tag_coverage": round(tag_score, 3),
        "favorable_factors": favorable,
        "unfavorable_factors": unfavorable,
    }


def estimate_meta_matchups(deck: list[dict[str, Any]]) -> dict[str, Any]:
    matchups = {name: estimate_matchup(deck, profile) for name, profile in META_PROFILES.items()}
    overall = round(sum(item["score"] for item in matchups.values()) / max(1, len(matchups)))
    return {
        "overall_score": overall,
        "matchups": matchups,
    }

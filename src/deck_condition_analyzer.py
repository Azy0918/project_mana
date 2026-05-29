from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class DeckConditionAnalysis:
    deck_size: int
    civilization_match_count: int
    civilization_match_rate: float
    focus_tag_hits: dict[str, int]
    avoid_tag_hits: dict[str, int]
    starter_count: int
    defense_count: int
    finisher_count: int
    removal_count: int
    draw_count: int
    average_cost: float
    condition_score: int
    warnings: list[str]
    comments: list[str]


def _split_tags(value: str) -> list[str]:
    if not value:
        return []

    tags: list[str] = []
    for tag in str(value).replace(",", ";").replace("、", ";").split(";"):
        tag = tag.strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _has_tag(card: dict[str, Any], tag: str) -> bool:
    return tag in _split_tags(str(card.get("tags", "")))


def _has_tag_contains(card: dict[str, Any], keyword: str) -> bool:
    return keyword in str(card.get("tags", ""))


def _card_matches_civilization(card: dict[str, Any], civilizations: list[str]) -> bool:
    card_civ = str(card.get("civilization", ""))
    if not civilizations:
        return True

    if card_civ == "無色":
        return True

    return any(civ in card_civ.split("/") for civ in civilizations)


def _safe_cost(card: dict[str, Any]) -> int | None:
    try:
        return int(float(str(card.get("cost", "")).strip()))
    except Exception:
        return None


def _quantity(card: dict[str, Any]) -> int:
    try:
        return max(1, int(card.get("quantity", 1)))
    except Exception:
        return 1


def analyze_deck_condition(
    deck_cards: list[dict[str, Any]],
    civilizations: list[str],
    focus_tags: list[str],
    avoid_tags: list[str],
    target_starter_count: int | None = None,
    target_defense_count: int | None = None,
    target_finisher_count: int | None = None,
) -> DeckConditionAnalysis:
    deck_size = sum(_quantity(card) for card in deck_cards)

    if deck_size == 0:
        return DeckConditionAnalysis(
            deck_size=0,
            civilization_match_count=0,
            civilization_match_rate=0.0,
            focus_tag_hits={},
            avoid_tag_hits={},
            starter_count=0,
            defense_count=0,
            finisher_count=0,
            removal_count=0,
            draw_count=0,
            average_cost=0.0,
            condition_score=0,
            warnings=["デッキが空です。"],
            comments=[],
        )

    civilization_match_count = sum(
        _quantity(card)
        for card in deck_cards
        if _card_matches_civilization(card, civilizations)
    )
    civilization_match_rate = civilization_match_count / deck_size * 100

    focus_tag_hits = {
        tag: sum(_quantity(card) for card in deck_cards if _has_tag_contains(card, tag))
        for tag in focus_tags
    }

    avoid_tag_hits = {
        tag: sum(_quantity(card) for card in deck_cards if _has_tag_contains(card, tag))
        for tag in avoid_tags
    }

    starter_count = sum(_quantity(card) for card in deck_cards if _has_tag_contains(card, "初動"))
    defense_count = sum(
        _quantity(card)
        for card in deck_cards
        if _has_tag_contains(card, "受け札") or _has_tag_contains(card, "S・トリガー")
    )
    finisher_count = sum(_quantity(card) for card in deck_cards if _has_tag_contains(card, "フィニッシャー"))
    removal_count = sum(_quantity(card) for card in deck_cards if _has_tag_contains(card, "除去"))
    draw_count = sum(
        _quantity(card)
        for card in deck_cards
        if _has_tag_contains(card, "ドロー") or _has_tag_contains(card, "リソース")
    )

    weighted_costs = []
    for card in deck_cards:
        cost = _safe_cost(card)
        if cost is not None:
            weighted_costs.extend([cost] * _quantity(card))
    average_cost = round(sum(weighted_costs) / len(weighted_costs), 2) if weighted_costs else 0.0

    warnings: list[str] = []
    comments: list[str] = []

    score = 100

    if civilization_match_rate < 85:
        warnings.append(f"文明一致率が低めです: {civilization_match_rate:.1f}%")
        score -= 15

    avoid_total = sum(avoid_tag_hits.values())
    if avoid_total > 0:
        warnings.append(f"避けたいタグを含むカードが {avoid_total} 枚あります。")
        score -= min(30, avoid_total * 5)

    missing_focus_tags = [tag for tag, count in focus_tag_hits.items() if count == 0]
    if missing_focus_tags:
        warnings.append(f"重視タグが入っていません: {', '.join(missing_focus_tags)}")
        score -= len(missing_focus_tags) * 5

    if target_starter_count is not None and starter_count < target_starter_count:
        warnings.append(f"初動が目標より少なめです: {starter_count} / {target_starter_count}")
        score -= 10

    if target_defense_count is not None and defense_count < target_defense_count:
        warnings.append(f"受け札が目標より少なめです: {defense_count} / {target_defense_count}")
        score -= 10

    if target_finisher_count is not None and finisher_count < target_finisher_count:
        warnings.append(f"フィニッシャーが目標より少なめです: {finisher_count} / {target_finisher_count}")
        score -= 10

    if starter_count >= 8:
        comments.append("初動は十分に確保されています。")
    if defense_count >= 6:
        comments.append("受け札は一定数あります。")
    if finisher_count >= 3:
        comments.append("勝ち筋になるカードが入っています。")
    if removal_count >= 6:
        comments.append("除去札が多く、盤面対応力があります。")
    if draw_count >= 6:
        comments.append("ドロー・リソース札があり、手札補充が期待できます。")

    score = max(0, min(100, score))

    return DeckConditionAnalysis(
        deck_size=deck_size,
        civilization_match_count=civilization_match_count,
        civilization_match_rate=round(civilization_match_rate, 1),
        focus_tag_hits=focus_tag_hits,
        avoid_tag_hits=avoid_tag_hits,
        starter_count=starter_count,
        defense_count=defense_count,
        finisher_count=finisher_count,
        removal_count=removal_count,
        draw_count=draw_count,
        average_cost=average_cost,
        condition_score=score,
        warnings=warnings,
        comments=comments,
    )

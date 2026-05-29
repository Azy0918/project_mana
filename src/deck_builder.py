from __future__ import annotations

import random
from collections import Counter
from pathlib import Path
from typing import Any

from src.deck_condition_analyzer import analyze_deck_condition
from src.deck_generation_request import DeckGenerationRequest
from src.evaluate_deck import DEFENSE_TAGS, EARLY_TAGS, FINISHER_TAGS, RAMP_TAGS, split_tags
from src.generate_deck import MAX_COPIES
from src.search_cards import DEFAULT_DB_PATH, search_cards


def score_card_for_request(card: dict[str, Any], request: DeckGenerationRequest) -> int:
    score = 0

    card_civ = str(card.get("civilization", ""))
    card_tags = str(card.get("tags", ""))

    if any(civ in card_civ for civ in request.civilizations):
        score += 5

    for tag in request.focus_tags:
        if tag in card_tags:
            score += 10

    if request.deck_type and request.deck_type != "ランダム" and request.deck_type in card_tags:
        score += 8

    for tag in request.avoid_tags:
        if tag in card_tags:
            score -= 20

    return score


def summarize_request_fit(deck: list[dict[str, Any]], request: DeckGenerationRequest) -> dict[str, Any]:
    analysis = analyze_deck_condition(
        deck_cards=deck,
        civilizations=request.civilizations,
        focus_tags=request.focus_tags,
        avoid_tags=request.avoid_tags,
        target_starter_count=_target_count(request.deck_size, request.early_ratio),
        target_defense_count=_target_count(request.deck_size, request.defense_ratio),
        target_finisher_count=_target_count(request.deck_size, request.finisher_ratio),
    )
    return {
        "civilization_match_rate": analysis.civilization_match_rate / 100,
        "focus_tag_match_count": sum(analysis.focus_tag_hits.values()),
        "avoid_tag_count": sum(analysis.avoid_tag_hits.values()),
        "early_count": analysis.starter_count,
        "defense_count": analysis.defense_count,
        "finisher_count": analysis.finisher_count,
        "average_cost": analysis.average_cost,
        "condition_fit_score": analysis.condition_score,
    }


def _card_matches_tags(card: dict[str, Any], target_tags: set[str]) -> bool:
    return bool(target_tags.intersection(split_tags(card.get("tags"))))


def _card_has_avoid_tag(card: dict[str, Any], request: DeckGenerationRequest) -> bool:
    card_tags = str(card.get("tags", ""))
    return any(tag in card_tags for tag in request.avoid_tags)


def _card_in_civilizations(card: dict[str, Any], request: DeckGenerationRequest) -> bool:
    if not request.civilizations:
        return True
    card_civ = str(card.get("civilization", ""))
    return any(civ in card_civ for civ in request.civilizations)


def _target_count(deck_size: int, ratio: int) -> int:
    return max(0, round(deck_size * ratio / 100))


def _card_cost(card: dict[str, Any]) -> int:
    try:
        return int(card.get("cost") or 0)
    except (TypeError, ValueError):
        return 0


def _add_card(deck: Counter[str], card: dict[str, Any], deck_size: int) -> bool:
    if sum(deck.values()) >= deck_size:
        return False
    card_id = card["card_id"]
    if deck[card_id] >= MAX_COPIES:
        return False
    deck[card_id] += 1
    return True


def _rank_cards(cards: list[dict[str, Any]], request: DeckGenerationRequest) -> list[dict[str, Any]]:
    return sorted(
        cards,
        key=lambda card: (
            score_card_for_request(card, request),
            -_card_cost(card),
            card.get("name", ""),
        ),
        reverse=True,
    )


def _add_role_cards(
    deck: Counter[str],
    candidates: list[dict[str, Any]],
    request: DeckGenerationRequest,
    target_tags: set[str],
    target_count: int,
) -> None:
    role_cards = [card for card in candidates if _card_matches_tags(card, target_tags)]
    role_cards = _rank_cards(role_cards, request)
    if not role_cards:
        return

    while sum(deck[card["card_id"]] for card in role_cards) < target_count:
        before = sum(deck.values())
        for card in role_cards:
            _add_card(deck, card, request.deck_size)
            if sum(deck[card["card_id"]] for card in role_cards) >= target_count:
                break
        if sum(deck.values()) == before:
            break


def build_deck_for_request(
    request: DeckGenerationRequest,
    db_path: Path = DEFAULT_DB_PATH,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    all_cards = search_cards(db_path)
    if not all_cards:
        return []

    preferred_cards = [
        card
        for card in all_cards
        if _card_in_civilizations(card, request) and not _card_has_avoid_tag(card, request)
    ]
    if not preferred_cards:
        preferred_cards = [card for card in all_cards if _card_in_civilizations(card, request)]
    if not preferred_cards:
        preferred_cards = all_cards

    deck: Counter[str] = Counter()

    role_targets = [
        (EARLY_TAGS | RAMP_TAGS, _target_count(request.deck_size, request.early_ratio)),
        (DEFENSE_TAGS, _target_count(request.deck_size, request.defense_ratio)),
        (FINISHER_TAGS, _target_count(request.deck_size, request.finisher_ratio)),
    ]
    for target_tags, target_count in role_targets:
        _add_role_cards(deck, preferred_cards, request, target_tags, target_count)

    ranked_cards = _rank_cards(preferred_cards, request)
    while sum(deck.values()) < request.deck_size:
        available = [card for card in ranked_cards if deck[card["card_id"]] < MAX_COPIES]
        if not available:
            fallback = [card for card in all_cards if deck[card["card_id"]] < MAX_COPIES]
            available = _rank_cards(fallback, request)
        if not available:
            break

        top_window = available[: min(12, len(available))]
        card = rng.choice(top_window)
        _add_card(deck, card, request.deck_size)

    cards_by_id = {card["card_id"]: card for card in all_cards}
    grouped_deck = []
    for card_id, quantity in deck.most_common():
        card = dict(cards_by_id[card_id])
        card["quantity"] = quantity
        card["request_score"] = score_card_for_request(card, request)
        grouped_deck.append(card)

    return sorted(grouped_deck, key=lambda card: (_card_cost(card), card["name"]))

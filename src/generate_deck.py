from __future__ import annotations

import random
from collections import Counter
from pathlib import Path
from typing import Any

from src.evaluate_deck import DEFENSE_TAGS, EARLY_TAGS, FINISHER_TAGS, RAMP_TAGS, split_tags
from src.search_cards import DEFAULT_DB_PATH, search_cards


DECK_SIZE = 40
MAX_COPIES = 4


ROLE_TARGETS = [
    ("初動/マナ加速", EARLY_TAGS | RAMP_TAGS, 12),
    ("受け札", DEFENSE_TAGS, 12),
    ("フィニッシャー", FINISHER_TAGS, 8),
]


def _card_matches_tags(card: dict[str, Any], target_tags: set[str]) -> bool:
    return bool(target_tags.intersection(split_tags(card.get("tags"))))


def _add_card(deck: Counter[str], cards_by_id: dict[str, dict[str, Any]], card: dict[str, Any]) -> bool:
    if sum(deck.values()) >= DECK_SIZE:
        return False
    card_id = card["card_id"]
    if deck[card_id] >= MAX_COPIES:
        return False
    deck[card_id] += 1
    return True


def _weighted_candidates(cards: list[dict[str, Any]], target_tags: set[str]) -> list[dict[str, Any]]:
    candidates = [card for card in cards if _card_matches_tags(card, target_tags)]
    return sorted(candidates, key=lambda card: (int(card["cost"]), card["name"]))


def generate_deck(
    db_path: Path = DEFAULT_DB_PATH,
    preferred_civilizations: list[str] | None = None,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    all_cards = search_cards(db_path)
    if preferred_civilizations:
        cards = [
            card
            for card in all_cards
            if any(civ in card["civilization"].split("/") for civ in preferred_civilizations)
        ]
    else:
        cards = all_cards

    if not cards:
        cards = all_cards

    cards_by_id = {card["card_id"]: card for card in all_cards}
    deck: Counter[str] = Counter()

    for _role_name, target_tags, target_count in ROLE_TARGETS:
        candidates = _weighted_candidates(cards, target_tags)
        if not candidates:
            continue
        while sum(deck[card["card_id"]] for card in candidates) < target_count:
            before = sum(deck.values())
            for card in candidates:
                _add_card(deck, cards_by_id, card)
                if sum(deck[card["card_id"]] for card in candidates) >= target_count:
                    break
            if sum(deck.values()) == before:
                break

    fill_cards = sorted(cards, key=lambda card: (int(card["cost"]), card["name"]))
    while sum(deck.values()) < DECK_SIZE:
        available = [card for card in fill_cards if deck[card["card_id"]] < MAX_COPIES]
        if not available:
            available = [card for card in all_cards if deck[card["card_id"]] < MAX_COPIES]
        if not available:
            break
        card = rng.choice(available)
        _add_card(deck, cards_by_id, card)

    grouped_deck = []
    for card_id, quantity in deck.most_common():
        card = dict(cards_by_id[card_id])
        card["quantity"] = quantity
        grouped_deck.append(card)

    return sorted(grouped_deck, key=lambda card: (int(card["cost"]), card["name"]))

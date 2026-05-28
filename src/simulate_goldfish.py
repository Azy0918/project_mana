from __future__ import annotations

import random
from collections import Counter
from typing import Any

from src.evaluate_deck import DEFENSE_TAGS, EARLY_TAGS, FINISHER_TAGS, RAMP_TAGS, expand_deck, split_tags


def _card_snapshot(card: dict[str, Any]) -> dict[str, Any]:
    tags = set(split_tags(card.get("tags")))
    return {
        "name": card["name"],
        "cost": int(card["cost"]),
        "early": bool(EARLY_TAGS.intersection(tags)),
        "ramp": bool(RAMP_TAGS.intersection(tags)),
        "defense": bool(DEFENSE_TAGS.intersection(tags)),
        "finisher": bool(FINISHER_TAGS.intersection(tags)),
    }


def _charge_one(hand: list[dict[str, Any]]) -> None:
    if not hand:
        return
    # MVP: keep role cards when possible, otherwise charge the highest-cost card.
    charge_index = max(
        range(len(hand)),
        key=lambda index: (
            not (hand[index]["early"] or hand[index]["ramp"] or hand[index]["defense"] or hand[index]["finisher"]),
            hand[index]["cost"],
        ),
    )
    hand.pop(charge_index)


def _simulate_once(deck_cards: list[dict[str, Any]], max_turns: int, rng: random.Random) -> dict[str, Any]:
    shuffled = deck_cards[:]
    rng.shuffle(shuffled)

    hand = shuffled[:5]
    deck_pos = 5
    seen = hand[:]
    mana = 0
    early_turn: int | None = None

    for turn in range(1, max_turns + 1):
        if deck_pos < len(shuffled):
            drawn = shuffled[deck_pos]
            deck_pos += 1
            hand.append(drawn)
            seen.append(drawn)

        if hand:
            mana += 1
            _charge_one(hand)

        if early_turn is None and any(card["early"] and card["cost"] <= mana for card in hand):
            early_turn = turn

    return {
        "early_success": early_turn is not None,
        "early_turn": early_turn,
        "ramp_seen": any(card["ramp"] for card in seen),
        "defense_seen": any(card["defense"] for card in seen),
        "finisher_seen": any(card["finisher"] for card in seen),
    }


def simulate_goldfish(
    deck: list[dict[str, Any]],
    trials: int = 1000,
    max_turns: int = 5,
    seed: int | None = None,
) -> dict[str, Any]:
    expanded = [_card_snapshot(card) for card in expand_deck(deck)]
    if not expanded or trials <= 0:
        return {
            "trials": 0,
            "max_turns": max_turns,
            "deck_size": len(expanded),
            "early_success_rate": 0.0,
            "ramp_seen_rate": 0.0,
            "defense_seen_rate": 0.0,
            "finisher_seen_rate": 0.0,
            "early_turn_distribution": {},
        }

    rng = random.Random(seed)
    early_success = 0
    ramp_seen = 0
    defense_seen = 0
    finisher_seen = 0
    early_turn_distribution: Counter[str] = Counter()

    for _ in range(trials):
        result = _simulate_once(expanded, max_turns, rng)
        early_success += int(result["early_success"])
        ramp_seen += int(result["ramp_seen"])
        defense_seen += int(result["defense_seen"])
        finisher_seen += int(result["finisher_seen"])
        key = f'{result["early_turn"]}ターン目' if result["early_turn"] else "未達"
        early_turn_distribution[key] += 1

    return {
        "trials": trials,
        "max_turns": max_turns,
        "deck_size": len(expanded),
        "early_success_rate": early_success / trials,
        "ramp_seen_rate": ramp_seen / trials,
        "defense_seen_rate": defense_seen / trials,
        "finisher_seen_rate": finisher_seen / trials,
        "early_turn_distribution": dict(early_turn_distribution),
    }

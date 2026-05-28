from __future__ import annotations

import random
from collections import Counter
from pathlib import Path
from typing import Any

from src.evaluate_deck import evaluate_deck
from src.generate_deck import DECK_SIZE, MAX_COPIES, generate_deck
from src.search_cards import DEFAULT_DB_PATH, search_cards


WEIGHT_PRESETS = {
    "バランス": {"score": 0.45, "novelty": 0.25, "meta": 0.30},
    "強さ重視": {"score": 0.65, "novelty": 0.10, "meta": 0.25},
    "未知性重視": {"score": 0.30, "novelty": 0.50, "meta": 0.20},
    "メタ適性重視": {"score": 0.30, "novelty": 0.15, "meta": 0.55},
}


def _civilization_matches(card: dict[str, Any], civilizations: list[str]) -> bool:
    if not civilizations:
        return True
    card_civs = [civ.strip() for civ in card["civilization"].split("/") if civ.strip()]
    return any(civ in card_civs for civ in civilizations)


def _group_deck(counter: Counter[str], cards_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    deck = []
    for card_id, quantity in counter.items():
        if quantity <= 0 or card_id not in cards_by_id:
            continue
        card = dict(cards_by_id[card_id])
        card["quantity"] = min(MAX_COPIES, int(quantity))
        deck.append(card)
    return sorted(deck, key=lambda card: (int(card["cost"]), card["name"]))


def _deck_counter(deck: list[dict[str, Any]]) -> Counter[str]:
    return Counter({card["card_id"]: int(card.get("quantity", 1)) for card in deck})


def _repair(counter: Counter[str], pool: list[dict[str, Any]], cards_by_id: dict[str, dict[str, Any]], rng: random.Random) -> Counter[str]:
    for card_id in list(counter):
        counter[card_id] = max(0, min(MAX_COPIES, int(counter[card_id])))
        if counter[card_id] == 0:
            del counter[card_id]

    while sum(counter.values()) > DECK_SIZE:
        card_id = rng.choice(list(counter.keys()))
        counter[card_id] -= 1
        if counter[card_id] <= 0:
            del counter[card_id]

    available = [card for card in pool if counter[card["card_id"]] < MAX_COPIES]
    while sum(counter.values()) < DECK_SIZE and available:
        card = rng.choice(available)
        counter[card["card_id"]] += 1
        available = [candidate for candidate in pool if counter[candidate["card_id"]] < MAX_COPIES]

    if sum(counter.values()) < DECK_SIZE:
        fallback = [card for card in cards_by_id.values() if counter[card["card_id"]] < MAX_COPIES]
        while sum(counter.values()) < DECK_SIZE and fallback:
            card = rng.choice(fallback)
            counter[card["card_id"]] += 1
            fallback = [candidate for candidate in cards_by_id.values() if counter[candidate["card_id"]] < MAX_COPIES]

    return counter


def _mutate(deck: list[dict[str, Any]], pool: list[dict[str, Any]], cards_by_id: dict[str, dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    counter = _deck_counter(deck)
    mutation_count = rng.randint(1, 4)

    for _ in range(mutation_count):
        action = rng.choice(["swap", "plus_minus"])
        if action == "swap" and counter:
            remove_id = rng.choice(list(counter.keys()))
            counter[remove_id] -= 1
            if counter[remove_id] <= 0:
                del counter[remove_id]
            candidates = [card for card in pool if counter[card["card_id"]] < MAX_COPIES]
            if candidates:
                add_card = rng.choice(candidates)
                counter[add_card["card_id"]] += 1
        elif counter:
            card_id = rng.choice(list(counter.keys()))
            delta = rng.choice([-1, 1])
            counter[card_id] += delta

    repaired = _repair(counter, pool, cards_by_id, rng)
    return _group_deck(repaired, cards_by_id)


def _fitness(summary: dict[str, Any], focus: str) -> float:
    weights = WEIGHT_PRESETS.get(focus, WEIGHT_PRESETS["バランス"])
    return (
        summary["score"] * weights["score"]
        + summary["novelty_score"] * weights["novelty"]
        + summary["meta_score"] * weights["meta"]
    )


def _evaluate_population(population: list[list[dict[str, Any]]], focus: str) -> list[dict[str, Any]]:
    evaluated = []
    for deck in population:
        summary = evaluate_deck(deck)
        evaluated.append(
            {
                "deck": deck,
                "summary": summary,
                "fitness": round(_fitness(summary, focus), 2),
            }
        )
    return sorted(evaluated, key=lambda item: item["fitness"], reverse=True)


def run_evolutionary_search(
    db_path: Path = DEFAULT_DB_PATH,
    generations: int = 8,
    population_size: int = 12,
    civilizations: list[str] | None = None,
    focus: str = "バランス",
    seed: int | None = None,
) -> dict[str, Any]:
    rng = random.Random(seed)
    all_cards = search_cards(db_path)
    if not all_cards:
        return {
            "best_overall": None,
            "best_novelty": None,
            "best_meta": None,
            "history": [],
        }

    civilizations = civilizations or []
    pool = [card for card in all_cards if _civilization_matches(card, civilizations)] or all_cards
    cards_by_id = {card["card_id"]: card for card in all_cards}
    generations = max(1, int(generations))
    population_size = max(2, int(population_size))
    elite_count = max(1, min(population_size, population_size // 3))

    population = [
        generate_deck(db_path, preferred_civilizations=civilizations, seed=rng.randint(0, 1_000_000))
        for _ in range(population_size)
    ]

    best_overall = None
    best_novelty = None
    best_meta = None
    history = []

    for generation in range(1, generations + 1):
        evaluated = _evaluate_population(population, focus)
        best = evaluated[0]

        if best_overall is None or best["fitness"] > best_overall["fitness"]:
            best_overall = best
        novelty_candidate = max(evaluated, key=lambda item: item["summary"]["novelty_score"])
        if best_novelty is None or novelty_candidate["summary"]["novelty_score"] > best_novelty["summary"]["novelty_score"]:
            best_novelty = novelty_candidate
        meta_candidate = max(evaluated, key=lambda item: item["summary"]["meta_score"])
        if best_meta is None or meta_candidate["summary"]["meta_score"] > best_meta["summary"]["meta_score"]:
            best_meta = meta_candidate

        history.append(
            {
                "generation": generation,
                "fitness": best["fitness"],
                "score": best["summary"]["score"],
                "novelty_score": best["summary"]["novelty_score"],
                "meta_score": best["summary"]["meta_score"],
            }
        )

        elites = evaluated[:elite_count]
        next_population = [item["deck"] for item in elites]
        while len(next_population) < population_size:
            parent = rng.choice(elites)["deck"]
            next_population.append(_mutate(parent, pool, cards_by_id, rng))
        population = next_population

    return {
        "best_overall": best_overall,
        "best_novelty": best_novelty,
        "best_meta": best_meta,
        "history": history,
        "focus": focus,
        "generations": generations,
        "population_size": population_size,
    }

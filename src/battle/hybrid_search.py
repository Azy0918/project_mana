from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from src.battle.effects.store import load_approved_effects_map
from src.battle.kernel.combo import ComboPolicy
from src.battle.rating.meta_rating import load_meta_battle_decks
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.runner import simulate_matches
from src.evaluate_deck import evaluate_deck
from src.evolutionary_search import _civilization_matches, _group_deck, _mutate, _repair
from src.search_cards import search_cards

from collections import Counter


def _simulated_win_rate(
    deck: list[dict[str, Any]],
    opponents: list[dict[str, Any]],
    games: int,
    seed: float,
    effects: dict[str, list[dict[str, Any]]] | None,
) -> float:
    wins = 0
    total = 0
    for index, opponent in enumerate(opponents):
        summary = simulate_matches(
            deck,
            opponent["cards"],
            games=games,
            seed=int(seed * 100000) + index,
            effects=effects,
            policy_a=ComboPolicy(),
            policy_b=ComboPolicy(),
        )
        wins += summary.wins_a
        total += summary.games
    return wins / total if total else 0.0


def run_hybrid_search(
    db_path: Path = DEFAULT_DB_PATH,
    generations: int = 8,
    population_size: int = 12,
    civilizations: list[str] | None = None,
    seed: int | None = None,
    sim_games: int = 30,
    sim_opponents: int = 3,
    sim_weight: float = 0.7,
) -> dict[str, Any]:
    """世代内選別に厳密シミュレーション勝率を使う進化探索。

    各候補を「対メタ勝率×100 × sim_weight + ヒューリスティック評価 × (1-sim_weight)」で
    採点する。ヒューリスティック単独では見逃される実戦的に強い候補を残すための探索
    (背景は docs/sim_findings_2026-06.md)。
    """
    rng = random.Random(seed)
    sim_weight = max(0.0, min(1.0, sim_weight))

    all_cards = search_cards(db_path)
    if not all_cards:
        return {"best": None, "history": [], "warnings": ["カードDBが空です"]}
    pool = [card for card in all_cards if _civilization_matches(card, civilizations or [])] or all_cards
    cards_by_id = {card["card_id"]: card for card in all_cards}

    meta_decks, warnings = load_meta_battle_decks(db_path)
    if not meta_decks:
        return {"best": None, "history": [], "warnings": warnings + ["対戦相手となるメタデッキがありません"]}
    if len(meta_decks) > sim_opponents:
        opponents = rng.sample(meta_decks, sim_opponents)
    else:
        opponents = meta_decks
    effects = load_approved_effects_map(db_path)

    population = [
        _group_deck(_repair(Counter(), pool, cards_by_id, rng), cards_by_id)
        for _ in range(max(2, population_size))
    ]

    history: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    elite_count = max(1, len(population) // 3)

    for generation in range(1, max(1, generations) + 1):
        evaluated = []
        for deck in population:
            heuristic = float(evaluate_deck(deck)["score"])
            win_rate = _simulated_win_rate(deck, opponents, sim_games, rng.random(), effects)
            combined = round(win_rate * 100 * sim_weight + heuristic * (1 - sim_weight), 2)
            evaluated.append(
                {
                    "deck": deck,
                    "heuristic_score": heuristic,
                    "sim_win_rate": round(win_rate, 4),
                    "combined_score": combined,
                }
            )
        evaluated.sort(key=lambda item: item["combined_score"], reverse=True)
        top = evaluated[0]
        if best is None or top["combined_score"] > best["combined_score"]:
            best = top
        history.append(
            {
                "generation": generation,
                "best_combined": top["combined_score"],
                "best_sim_win_rate": top["sim_win_rate"],
                "best_heuristic": top["heuristic_score"],
            }
        )

        elites = [entry["deck"] for entry in evaluated[:elite_count]]
        next_population = elites[:]
        while len(next_population) < len(population):
            parent = rng.choice(elites)
            next_population.append(_mutate(parent, pool, cards_by_id, rng))
        population = next_population

    return {
        "best": best,
        "history": history,
        "opponents": [deck["deck_name"] for deck in opponents],
        "sim_weight": sim_weight,
        "sim_games": sim_games,
        "warnings": warnings,
    }

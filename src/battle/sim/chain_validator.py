from __future__ import annotations

import random
from collections import Counter
from typing import Any

from src.battle.kernel.cards import BattleCard, battle_deck_from_dicts
from src.battle.sim.goldfish import _simulate_once


def _is_subsequence(chain: list[str], sequence: list[str]) -> bool:
    position = 0
    for played in sequence:
        if position < len(chain) and played == chain[position]:
            position += 1
    return position == len(chain)


def validate_chain_playable(
    chain_card_ids: list[str],
    deck: list[dict[str, Any]] | list[BattleCard],
    trials: int = 300,
    max_turns: int = 6,
    seed: int | None = None,
    effects: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """state_transition_model等が提案したチェーンが実ルール上プレイできるかを検証する。

    一人回し(実コスト支払い)を繰り返し、チェーンのカードが指定順に
    プレイされた試行の割合を返す。0%なら現実的に成立しないチェーン。
    """
    cards = deck if deck and isinstance(deck[0], BattleCard) else battle_deck_from_dicts(deck)  # type: ignore[arg-type]
    deck_ids = {card.card_id for card in cards}
    missing = [card_id for card_id in chain_card_ids if card_id not in deck_ids]
    if not chain_card_ids or missing or not cards or trials <= 0:
        return {
            "chain": chain_card_ids,
            "trials": 0,
            "success_rate": 0.0,
            "partial_rates": {},
            "completion_turn_distribution": {},
            "warnings": [f"チェーンのカードがデッキにありません: {missing}"] if missing else ["チェーンまたはデッキが空です"],
        }

    rng = random.Random(seed)
    effects = effects or {}
    successes = 0
    partial_counts = Counter({card_id: 0 for card_id in chain_card_ids})
    completion_turns: Counter[str] = Counter()

    for _ in range(trials):
        result = _simulate_once(cards, max_turns, rng, effects)
        sequence: list[str] = result["play_sequence"]
        position = 0
        completion_turn: int | None = None
        played_turns: list[int] = []
        # plays_by_turnからターン列を復元する
        for turn in sorted(result["plays_by_turn"]):
            played_turns.extend([turn] * result["plays_by_turn"][turn])
        for index, played in enumerate(sequence):
            if position < len(chain_card_ids) and played == chain_card_ids[position]:
                partial_counts[chain_card_ids[position]] += 1
                position += 1
                if position == len(chain_card_ids):
                    completion_turn = played_turns[index] if index < len(played_turns) else max_turns
                    break
        if position == len(chain_card_ids):
            successes += 1
            completion_turns[f"{completion_turn}ターン目"] += 1

    return {
        "chain": chain_card_ids,
        "trials": trials,
        "max_turns": max_turns,
        "success_rate": successes / trials,
        "partial_rates": {card_id: count / trials for card_id, count in partial_counts.items()},
        "completion_turn_distribution": dict(completion_turns),
        "warnings": [],
    }

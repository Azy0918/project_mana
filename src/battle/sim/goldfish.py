from __future__ import annotations

import random
from collections import Counter
from typing import Any

from src.battle.kernel.cards import BattleCard, battle_deck_from_dicts
from src.battle.kernel.engine import select_mana_payment
from src.battle.kernel.state import ManaCard, make_mana_card

OPENING_HAND = 5

# 一人回しで実行する効果op(対戦相手を必要としないものだけ)
SOLO_OPS = {"draw", "deck_top_to_mana"}


def _solo_effects(card: BattleCard, effects: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    trigger = "on_cast" if card.is_spell else "on_play"
    actions = []
    for ability in effects.get(card.card_id, []):
        if ability.get("trigger") != trigger:
            continue
        actions.extend(action for action in ability.get("actions", []) if action.get("op") in SOLO_OPS)
    return actions


def _charge_index(hand: list[BattleCard], mana_count: int) -> int | None:
    if not hand:
        return None
    # 次のターンまでに出せない最高コストのカードをチャージに回す(貪欲方策と同じ基準)
    unplayable = [i for i, card in enumerate(hand) if card.cost > mana_count + 1]
    candidates = unplayable or list(range(len(hand)))
    return max(candidates, key=lambda i: hand[i].cost)


def _simulate_once(
    deck: list[BattleCard],
    max_turns: int,
    rng: random.Random,
    effects: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    shuffled = deck[:]
    rng.shuffle(shuffled)
    hand = shuffled[:OPENING_HAND]
    library = shuffled[OPENING_HAND:]
    mana_zone: list[ManaCard] = []

    first_play_turn: int | None = None
    total_plays = 0
    plays_by_turn: dict[int, int] = {}
    play_sequence: list[str] = []

    for turn in range(1, max_turns + 1):
        for mana in mana_zone:
            mana.tapped = False
        if library:
            hand.append(library.pop(0))

        charge = _charge_index(hand, len(mana_zone))
        if charge is not None:
            mana_zone.append(make_mana_card(hand.pop(charge)))

        # 出せる限り実コストを支払ってプレイする(高コスト優先)
        while True:
            playable = [i for i, card in enumerate(hand) if select_mana_payment(mana_zone, card) is not None]
            if not playable:
                break
            index = max(playable, key=lambda i: (hand[i].cost, hand[i].power))
            card = hand.pop(index)
            payment = select_mana_payment(mana_zone, card)
            if payment is None:
                hand.insert(index, card)
                break
            for mana in payment:
                mana.tapped = True
            total_plays += 1
            plays_by_turn[turn] = plays_by_turn.get(turn, 0) + 1
            play_sequence.append(card.card_id)
            if first_play_turn is None:
                first_play_turn = turn

            for action in _solo_effects(card, effects):
                count = int(action.get("count", 1))
                if action["op"] == "draw":
                    for _ in range(count):
                        if library:
                            hand.append(library.pop(0))
                elif action["op"] == "deck_top_to_mana":
                    for _ in range(count):
                        if library:
                            mana_zone.append(make_mana_card(library.pop(0)))

    return {
        "first_play_turn": first_play_turn,
        "total_plays": total_plays,
        "plays_by_turn": plays_by_turn,
        "play_sequence": play_sequence,
        "final_mana": len(mana_zone),
    }


def simulate_goldfish_strict(
    deck: list[dict[str, Any]] | list[BattleCard],
    trials: int = 1000,
    max_turns: int = 5,
    seed: int | None = None,
    effects: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """実コスト支払い(文明拘束込み)を伴う一人回しシミュレーション。

    タグではなく「実際にカードをプレイできたか」で初動を判定する。
    effects には承認済みEffectScriptを渡すと、ドロー/マナ加速効果も再現する。
    """
    cards = deck if deck and isinstance(deck[0], BattleCard) else battle_deck_from_dicts(deck)  # type: ignore[arg-type]
    if not cards or trials <= 0:
        return {
            "trials": 0,
            "max_turns": max_turns,
            "deck_size": len(cards),
            "first_play_rate": 0.0,
            "first_play_turn_distribution": {},
            "average_plays": 0.0,
            "average_plays_by_turn": {},
            "average_final_mana": 0.0,
        }

    rng = random.Random(seed)
    effects = effects or {}
    first_play_count = 0
    total_plays = 0
    total_final_mana = 0
    turn_distribution: Counter[str] = Counter()
    plays_by_turn_total: Counter[int] = Counter()

    for _ in range(trials):
        result = _simulate_once(cards, max_turns, rng, effects)
        if result["first_play_turn"] is not None:
            first_play_count += 1
            turn_distribution[f'{result["first_play_turn"]}ターン目'] += 1
        else:
            turn_distribution["未達"] += 1
        total_plays += result["total_plays"]
        total_final_mana += result["final_mana"]
        for turn, count in result["plays_by_turn"].items():
            plays_by_turn_total[turn] += count

    return {
        "trials": trials,
        "max_turns": max_turns,
        "deck_size": len(cards),
        "first_play_rate": first_play_count / trials,
        "first_play_turn_distribution": dict(turn_distribution),
        "average_plays": total_plays / trials,
        "average_plays_by_turn": {turn: count / trials for turn, count in sorted(plays_by_turn_total.items())},
        "average_final_mana": total_final_mana / trials,
    }

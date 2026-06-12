from __future__ import annotations

import random
from collections import Counter
from typing import Any

from src.battle.kernel.cards import BattleCard, battle_deck_from_dicts
from src.battle.kernel.engine import select_mana_payment
from src.battle.kernel.state import ManaCard, make_mana_card

OPENING_HAND = 5

# 一人回しで実行する効果op(対戦相手を必要としないものだけ)
SOLO_OPS = {
    "draw",
    "deck_top_to_mana",
    "deck_top_to_grave",
    "summon_from_grave",
    "summon_from_mana",
    "summon_from_hand",
}


def _solo_effects(card: BattleCard, effects: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    trigger = "on_cast" if card.is_spell else "on_play"
    actions = []
    for ability in effects.get(card.card_id, []):
        if ability.get("trigger") != trigger:
            continue
        actions.extend(action for action in ability.get("actions", []) if action.get("op") in SOLO_OPS)
    return actions


def _charge_index(
    hand: list[BattleCard],
    mana_count: int,
    effects: dict[str, list[dict[str, Any]]] | None = None,
    protected_ids: frozenset[str] | set[str] = frozenset(),
) -> int | None:
    if not hand:
        return None
    effects = effects or {}
    # 次のターンまでに出せない最高コストのカードをチャージに回す(貪欲方策と同じ基準)。
    # 効果なしカードを優先して埋め、コンボパーツをマナに沈めない。
    # protected_ids(検証対象チェーンの部品)は手札がそれだけにならない限り埋めない:
    # 「出せない最高コスト」基準はチェーンの環(中~高コスト)を系統的にマナへ沈め、
    # 成立率を偽って0%にする(チャージ規則がコンボを殺した事例: 第十一弾)。
    candidates_all = [i for i in range(len(hand)) if hand[i].card_id not in protected_ids]
    if not candidates_all:
        candidates_all = list(range(len(hand)))
    unplayable = [i for i in candidates_all if hand[i].cost > mana_count + 1]
    candidates = unplayable or candidates_all
    vanilla = [i for i in candidates if hand[i].card_id not in effects]
    pool = vanilla or candidates
    return max(pool, key=lambda i: hand[i].cost)


def _simulate_once(
    deck: list[BattleCard],
    max_turns: int,
    rng: random.Random,
    effects: dict[str, list[dict[str, Any]]],
    protected_ids: frozenset[str] | set[str] = frozenset(),
) -> dict[str, Any]:
    shuffled = deck[:]
    rng.shuffle(shuffled)
    hand = shuffled[:OPENING_HAND]
    library = shuffled[OPENING_HAND:]
    mana_zone: list[ManaCard] = []
    graveyard: list = []

    first_play_turn: int | None = None
    total_plays = 0
    plays_by_turn: dict[int, int] = {}
    play_sequence: list[str] = []

    for turn in range(1, max_turns + 1):
        for mana in mana_zone:
            mana.tapped = False
        if library:
            hand.append(library.pop(0))

        charge = _charge_index(hand, len(mana_zone), effects, protected_ids)
        if charge is not None:
            mana_zone.append(make_mana_card(hand.pop(charge)))

        # 出せる限り実コストを支払ってプレイする(高コスト優先)
        while True:
            playable = [i for i, card in enumerate(hand) if select_mana_payment(mana_zone, card) is not None]
            if not playable:
                break
            # 同コスト帯では効果持ちを優先する(コンボパーツがバニラに埋もれないように)
            index = max(
                playable,
                key=lambda i: (hand[i].cost, 1 if hand[i].card_id in effects else 0, hand[i].power),
            )
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
            if card.is_spell:
                graveyard.append(card)

            def _arrive(summoned, depth: int) -> None:
                # 効果による着地もプレイ列に記録する(コンボ成立検証の観測点)
                nonlocal total_plays
                total_plays += 1
                plays_by_turn[turn] = plays_by_turn.get(turn, 0) + 1
                play_sequence.append(summoned.card_id)
                # 着地したカード自身の効果も連鎖実行する(二段コンボの観測に必要)
                if depth < 5:
                    _apply(summoned, depth + 1)

            def _apply(source, depth: int = 0) -> None:
                for action in _solo_effects(source, effects):
                    count = int(action.get("count", 1))
                    max_cost = action.get("max_cost")
                    if action["op"] == "draw":
                        for _ in range(count):
                            if library:
                                hand.append(library.pop(0))
                    elif action["op"] == "deck_top_to_mana":
                        for _ in range(count):
                            if library:
                                mana_zone.append(make_mana_card(library.pop(0)))
                    elif action["op"] == "deck_top_to_grave":
                        for _ in range(count):
                            if library:
                                graveyard.append(library.pop(0))
                    elif action["op"] == "summon_from_grave":
                        exclude_evo = bool(action.get("exclude_evolution"))
                        civ_filter = action.get("civilizations")
                        for _ in range(count):
                            candidates = [
                                c for c in graveyard
                                if c.is_creature
                                and (max_cost is None or c.cost <= max_cost)
                                and not (exclude_evo and c.is_evolution)
                                and (civ_filter is None or any(cv in civ for civ in c.civilizations for cv in civ_filter))
                            ]
                            if not candidates:
                                break
                            target = max(candidates, key=lambda c: (c.cost, c.power))
                            graveyard.remove(target)
                            _arrive(target, depth)
                    elif action["op"] == "summon_from_mana":
                        if action.get("scope") == "opponent":
                            continue  # 相手依存の効果は一人回しでは実行しない(父なる大地型)
                        exclude_evo = bool(action.get("exclude_evolution"))
                        mana_civ_filter = action.get("civilizations")
                        for _ in range(count):
                            candidates = [
                                m for m in mana_zone
                                if m.card.is_creature
                                and (max_cost is None or m.card.cost <= max_cost)
                                and not (exclude_evo and m.card.is_evolution)
                                and (mana_civ_filter is None or any(cv in civ for civ in m.card.civilizations for cv in mana_civ_filter))
                            ]
                            if not candidates:
                                break
                            target = max(candidates, key=lambda m: (m.card.cost, m.card.power))
                            mana_zone.remove(target)
                            _arrive(target.card, depth)
                    elif action["op"] == "summon_from_hand":
                        for _ in range(count):
                            candidates = [c for c in hand if c.is_creature and (max_cost is None or c.cost <= max_cost)]
                            if not candidates:
                                break
                            target = max(candidates, key=lambda c: (c.cost, c.power))
                            hand.remove(target)
                            _arrive(target, depth)

            _apply(card)

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

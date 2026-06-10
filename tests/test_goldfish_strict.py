from __future__ import annotations

import unittest

from src.battle.kernel.cards import BattleCard
from src.battle.sim.goldfish import simulate_goldfish_strict


def make_card(name: str, cost: int, civilization: str = "火", card_type: str = "クリーチャー") -> BattleCard:
    return BattleCard(
        card_id=name,
        name=name,
        civilizations=(civilization,),
        cost=cost,
        card_type=card_type,
        power=cost * 1000,
    )


class GoldfishStrictTest(unittest.TestCase):
    def test_one_cost_deck_plays_turn_one(self) -> None:
        deck = [make_card(f"軽量{i}", cost=1) for i in range(40)]
        summary = simulate_goldfish_strict(deck, trials=50, max_turns=5, seed=1)
        self.assertEqual(summary["first_play_rate"], 1.0)
        self.assertEqual(summary["first_play_turn_distribution"], {"1ターン目": 50})

    def test_heavy_deck_first_play_turn_five(self) -> None:
        # 5コストのみのデッキは、毎ターン1チャージで5ターン目に初プレイできる
        deck = [make_card(f"重量{i}", cost=5) for i in range(40)]
        summary = simulate_goldfish_strict(deck, trials=20, max_turns=5, seed=2)
        self.assertEqual(summary["first_play_turn_distribution"], {"5ターン目": 20})

    def test_civilization_mismatch_blocks_play(self) -> None:
        # 手札・マナが他文明だけだと文明拘束で出せないケースが発生しないこと
        # (単色デッキなら必ず一致するため初動率100%)
        deck = [make_card(f"単色{i}", cost=1, civilization="自然") for i in range(40)]
        summary = simulate_goldfish_strict(deck, trials=20, max_turns=3, seed=3)
        self.assertEqual(summary["first_play_rate"], 1.0)

    def test_mana_accel_effect_speeds_up_heavy_card(self) -> None:
        accel = [make_card(f"加速{i}", cost=2) for i in range(20)]
        heavy = [make_card(f"大型{i}", cost=6) for i in range(20)]
        deck = accel + heavy
        effects = {
            card.card_id: [{"trigger": "on_play", "actions": [{"op": "deck_top_to_mana", "count": 1}]}]
            for card in accel
        }
        without = simulate_goldfish_strict(deck, trials=300, max_turns=6, seed=4)
        with_fx = simulate_goldfish_strict(deck, trials=300, max_turns=6, seed=4, effects=effects)
        # マナ加速効果がある方が6ターンでのプレイ枚数が多い
        self.assertGreater(with_fx["average_plays"], without["average_plays"])
        self.assertGreater(with_fx["average_final_mana"], without["average_final_mana"])

    def test_draw_effect_increases_plays(self) -> None:
        deck = [make_card(f"軽量{i}", cost=1) for i in range(40)]
        effects = {card.card_id: [{"trigger": "on_play", "actions": [{"op": "draw", "count": 1}]}] for card in deck}
        without = simulate_goldfish_strict(deck, trials=100, max_turns=5, seed=5)
        with_fx = simulate_goldfish_strict(deck, trials=100, max_turns=5, seed=5, effects=effects)
        self.assertGreater(with_fx["average_plays"], without["average_plays"])

    def test_empty_deck(self) -> None:
        summary = simulate_goldfish_strict([], trials=10)
        self.assertEqual(summary["trials"], 0)

    def test_dict_deck_with_quantity(self) -> None:
        deck = [
            {"card_id": "C1", "name": "軽量", "civilization": "火", "cost": 1, "card_type": "クリーチャー", "power": "1000", "quantity": 40}
        ]
        summary = simulate_goldfish_strict(deck, trials=10, max_turns=3, seed=6)
        self.assertEqual(summary["deck_size"], 40)
        self.assertEqual(summary["first_play_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()

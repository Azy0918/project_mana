from __future__ import annotations

import random
import unittest

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.engine import DuelEngine
from src.battle.kernel.lookahead import LookaheadPolicy, evaluate_state
from src.battle.kernel.policy import GreedyPolicy, Policy
from src.battle.kernel.state import CreatureInstance
from src.battle.research import benchmark_policies, run_round_robin


def make_card(
    name: str,
    cost: int = 2,
    civilization: str = "火",
    card_type: str = "クリーチャー",
    power: int = 1000,
    text: str = "",
) -> BattleCard:
    return BattleCard(
        card_id=name,
        name=name,
        civilizations=(civilization,),
        cost=cost,
        card_type=card_type,
        power=power,
        text=text,
    )


def make_deck(size: int = 40, civilization: str = "火", text: str = "") -> list[BattleCard]:
    return [
        make_card(f"{civilization}{i:02d}", cost=(i % 6) + 1, civilization=civilization, power=((i % 6) + 1) * 1000, text=text)
        for i in range(size)
    ]


class StubPolicy(Policy):
    def choose_charge(self, state, player):
        return None

    def choose_main_action(self, state, player, playable):
        return None

    def choose_attack(self, state, player, choices):
        return None

    def choose_blocker(self, state, player, attack, blockers):
        return None


class KeywordTest(unittest.TestCase):
    def test_speed_attacker_ignores_summoning_sickness(self) -> None:
        card = make_card("速攻獣", text="スピードアタッカー")
        creature = CreatureInstance(card=card, summoned_turn=3)
        self.assertTrue(creature.can_attack(3))
        vanilla = CreatureInstance(card=make_card("通常獣"), summoned_turn=3)
        self.assertFalse(vanilla.can_attack(3))

    def test_power_attacker_bonus_in_battle(self) -> None:
        card = make_card("パワアタ獣", power=2000, text="パワーアタッカー+3000")
        self.assertEqual(card.power_attacker_bonus, 3000)
        self.assertEqual(card.attack_power, 5000)

        engine = DuelEngine(make_deck(), make_deck(), StubPolicy(), StubPolicy())
        attacker = CreatureInstance(card=card, summoned_turn=0)
        defender = CreatureInstance(card=make_card("守り獣", power=4000), tapped=True, summoned_turn=0)
        engine.state.players[0].battle_zone.append(attacker)
        engine.state.players[1].battle_zone.append(defender)
        from src.battle.kernel.policy import AttackChoice

        engine._resolve_attack(engine.state.players[0], AttackChoice(attacker_index=0, target_creature_index=0))
        # 攻撃時のみ5000なので4000のブロッカーに勝ち、自身は生き残る
        self.assertIn(attacker, engine.state.players[0].battle_zone)
        self.assertNotIn(defender, engine.state.players[1].battle_zone)


class EvaluateStateTest(unittest.TestCase):
    def test_finished_states(self) -> None:
        engine = DuelEngine(make_deck(), make_deck(), StubPolicy(), StubPolicy())
        engine.state.finished = True
        engine.state.winner = 0
        self.assertEqual(evaluate_state(engine.state, 0), 1000.0)
        self.assertEqual(evaluate_state(engine.state, 1), -1000.0)

    def test_symmetry(self) -> None:
        engine = DuelEngine(make_deck(), make_deck(), StubPolicy(), StubPolicy())
        value_a = evaluate_state(engine.state, 0)
        self.assertAlmostEqual(value_a, -evaluate_state(engine.state, 1))


class LookaheadPolicyTest(unittest.TestCase):
    def test_declines_unfavorable_attack(self) -> None:
        # 攻撃側2000、相手に3000ブロッカーが立っている。攻撃すれば確実に討ち取られる。
        policy = LookaheadPolicy(rng=random.Random(1), rollouts=3)
        engine = DuelEngine(make_deck(), make_deck(), policy, GreedyPolicy(), rng=random.Random(1))
        state = engine.state
        state.turn = 5
        attacker = CreatureInstance(card=make_card("小型", power=2000), summoned_turn=1)
        state.players[0].battle_zone.append(attacker)
        blocker = CreatureInstance(card=make_card("大型ブロッカー", power=3000, text="ブロッカー"), summoned_turn=1)
        state.players[1].battle_zone.append(blocker)
        state.players[1].shields = state.players[1].shields[:1]  # 相手は必ずブロックする状況

        choices = engine._legal_attacks(state.players[0])
        self.assertTrue(choices)
        self.assertIsNone(policy.choose_attack(state, state.players[0], choices))

    def test_takes_winning_direct_attack(self) -> None:
        policy = LookaheadPolicy(rng=random.Random(2), rollouts=2)
        engine = DuelEngine(make_deck(), make_deck(), policy, GreedyPolicy(), rng=random.Random(2))
        state = engine.state
        state.turn = 5
        attacker = CreatureInstance(card=make_card("決め手", power=2000), summoned_turn=1)
        state.players[0].battle_zone.append(attacker)
        state.players[1].shields = []  # ダイレクトアタックで勝てる

        choices = engine._legal_attacks(state.players[0])
        chosen = policy.choose_attack(state, state.players[0], choices)
        self.assertIsNotNone(chosen)
        self.assertIsNone(chosen.target_creature_index)

    def test_determinize_preserves_counts_and_pool(self) -> None:
        policy = LookaheadPolicy(rng=random.Random(3))
        engine = DuelEngine(make_deck(), make_deck(), policy, GreedyPolicy(), rng=random.Random(3))
        state = engine.state
        before_shields = len(state.players[1].shields)
        before_deck = len(state.players[1].deck)
        before_pool = sorted(card.card_id for card in state.players[1].deck + state.players[1].shields)
        policy._determinize(state, 1)
        self.assertEqual(len(state.players[1].shields), before_shields)
        self.assertEqual(len(state.players[1].deck), before_deck)
        after_pool = sorted(card.card_id for card in state.players[1].deck + state.players[1].shields)
        self.assertEqual(before_pool, after_pool)

    def test_full_match_with_lookahead_completes(self) -> None:
        engine = DuelEngine(
            make_deck(),
            make_deck(civilization="自然"),
            LookaheadPolicy(rng=random.Random(4)),
            GreedyPolicy(),
            rng=random.Random(4),
        )
        result = engine.run()
        self.assertIn(result.reason, {"direct_attack", "deckout", "turn_limit"})


class ResearchTest(unittest.TestCase):
    def _deck_dicts(self, prefix: str, civilization: str) -> list[dict]:
        return [
            {
                "card_id": f"{prefix}{i}",
                "name": f"{prefix}カード{i}",
                "civilization": civilization,
                "cost": (i % 5) + 1,
                "card_type": "クリーチャー",
                "power": ((i % 5) + 1) * 1000,
                "quantity": 8,
            }
            for i in range(5)
        ]

    def test_run_round_robin(self) -> None:
        decks = [
            {"deck_name": "火", "cards": self._deck_dicts("F", "火")},
            {"deck_name": "水", "cards": self._deck_dicts("W", "水")},
            {"deck_name": "自然", "cards": self._deck_dicts("N", "自然")},
        ]
        result = run_round_robin(decks, games_per_pair=20, seed=1)
        self.assertEqual(len(result["rankings"]), 3)
        for name in ["火", "水", "自然"]:
            self.assertEqual(len(result["matrix"][name]), 2)
        # 対称性: AのB戦勝率 + BのA戦勝率 <= 1(引き分けぶんだけ下回る)
        total = result["matrix"]["火"]["水"] + result["matrix"]["水"]["火"]
        self.assertLessEqual(total, 1.0 + 1e-9)

    def test_benchmark_policies_runs(self) -> None:
        deck = self._deck_dicts("B", "火")
        result = benchmark_policies(deck, games=10, seed=2)
        self.assertEqual(result["games"], 10)
        self.assertEqual(result["policy_a"], "lookahead")
        self.assertGreaterEqual(result["win_rate_a"], 0.0)


if __name__ == "__main__":
    unittest.main()

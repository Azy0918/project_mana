from __future__ import annotations

import unittest

from src.battle.kernel.cards import BattleCard, battle_card_from_dict
from src.battle.kernel.engine import DuelEngine, select_mana_payment
from src.battle.kernel.policy import AttackChoice, GreedyPolicy, Policy
from src.battle.kernel.state import CreatureInstance, ManaCard
from src.battle.sim.runner import simulate_matches


def make_card(
    name: str,
    cost: int = 2,
    civilization: str = "火",
    card_type: str = "クリーチャー",
    power: int = 1000,
    text: str = "",
    tags: tuple[str, ...] = (),
) -> BattleCard:
    return BattleCard(
        card_id=name,
        name=name,
        civilizations=tuple(civilization.split("/")),
        cost=cost,
        card_type=card_type,
        power=power,
        text=text,
        tags=tags,
    )


def make_deck(size: int = 40, civilization: str = "火") -> list[BattleCard]:
    deck = []
    for index in range(size):
        cost = (index % 6) + 1
        deck.append(make_card(f"{civilization}クリーチャー{index:02d}", cost=cost, civilization=civilization, power=cost * 1000))
    return deck


class StubPolicy(Policy):
    def __init__(self, block_index: int | None = None) -> None:
        self.block_index = block_index

    def choose_charge(self, state, player):
        return None

    def choose_main_action(self, state, player, playable):
        return None

    def choose_attack(self, state, player, choices):
        return None

    def choose_blocker(self, state, player, attack, blockers):
        return self.block_index


def make_engine(policy_a: Policy | None = None, policy_b: Policy | None = None) -> DuelEngine:
    return DuelEngine(make_deck(), make_deck(), policy_a or StubPolicy(), policy_b or StubPolicy())


class ManaPaymentTest(unittest.TestCase):
    def test_civilization_constraint_unmet(self) -> None:
        mana_zone = [ManaCard(make_card("火マナ")), ManaCard(make_card("火マナ2"))]
        card = make_card("水カード", cost=2, civilization="水")
        self.assertIsNone(select_mana_payment(mana_zone, card))

    def test_civilization_constraint_met(self) -> None:
        mana_zone = [ManaCard(make_card("火マナ")), ManaCard(make_card("自然マナ", civilization="自然"))]
        card = make_card("火カード", cost=2, civilization="火")
        payment = select_mana_payment(mana_zone, card)
        self.assertIsNotNone(payment)
        self.assertEqual(len(payment), 2)
        self.assertTrue(any("火" in mana.card.civilizations for mana in payment))

    def test_multicolor_requires_all_civilizations(self) -> None:
        card = make_card("多色カード", cost=2, civilization="火/自然")
        short = [ManaCard(make_card("火マナ")), ManaCard(make_card("火マナ2"))]
        self.assertIsNone(select_mana_payment(short, card))
        enough = [ManaCard(make_card("火マナ")), ManaCard(make_card("自然マナ", civilization="自然"))]
        payment = select_mana_payment(enough, card)
        self.assertIsNotNone(payment)
        civs = {civ for mana in payment for civ in mana.card.civilizations}
        self.assertTrue({"火", "自然"}.issubset(civs))

    def test_insufficient_mana(self) -> None:
        mana_zone = [ManaCard(make_card("火マナ"))]
        self.assertIsNone(select_mana_payment(mana_zone, make_card("重い", cost=3)))

    def test_tapped_mana_excluded(self) -> None:
        mana_zone = [ManaCard(make_card("火マナ"), tapped=True), ManaCard(make_card("火マナ2"))]
        self.assertIsNone(select_mana_payment(mana_zone, make_card("2コスト", cost=2)))


class SummoningSicknessTest(unittest.TestCase):
    def test_cannot_attack_on_summon_turn(self) -> None:
        creature = CreatureInstance(card=make_card("新顔"), summoned_turn=3)
        self.assertFalse(creature.can_attack(3))
        self.assertTrue(creature.can_attack(4))


class AttackResolutionTest(unittest.TestCase):
    def test_shield_break_goes_to_hand(self) -> None:
        engine = make_engine()
        state = engine.state
        attacker = CreatureInstance(card=make_card("アタッカー"), summoned_turn=0)
        state.players[0].battle_zone.append(attacker)
        opponent = state.players[1]
        shields_before = len(opponent.shields)
        hand_before = len(opponent.hand)
        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=None))
        self.assertEqual(len(opponent.shields), shields_before - 1)
        self.assertEqual(len(opponent.hand), hand_before + 1)
        self.assertTrue(attacker.tapped)

    def test_w_breaker_breaks_two(self) -> None:
        engine = make_engine()
        state = engine.state
        attacker = CreatureInstance(card=make_card("Wブレイカー", text="W・ブレイカー"), summoned_turn=0)
        state.players[0].battle_zone.append(attacker)
        opponent = state.players[1]
        shields_before = len(opponent.shields)
        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=None))
        self.assertEqual(len(opponent.shields), shields_before - 2)

    def test_direct_attack_wins(self) -> None:
        engine = make_engine()
        state = engine.state
        state.players[0].battle_zone.append(CreatureInstance(card=make_card("フィニッシャー"), summoned_turn=0))
        state.players[1].shields = []
        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=None))
        self.assertTrue(state.finished)
        self.assertEqual(state.winner, 0)
        self.assertEqual(state.finish_reason, "direct_attack")

    def test_blocker_intercepts_shield_attack(self) -> None:
        engine = make_engine(policy_b=StubPolicy(block_index=0))
        state = engine.state
        attacker = CreatureInstance(card=make_card("アタッカー", power=2000), summoned_turn=0)
        state.players[0].battle_zone.append(attacker)
        opponent = state.players[1]
        blocker = CreatureInstance(card=make_card("ブロッカー", power=3000, tags=("ブロッカー",)), summoned_turn=0)
        opponent.battle_zone.append(blocker)
        shields_before = len(opponent.shields)
        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=None))
        self.assertEqual(len(opponent.shields), shields_before)
        self.assertNotIn(attacker, state.players[0].battle_zone)
        self.assertIn(blocker, opponent.battle_zone)

    def test_battle_power_comparison(self) -> None:
        engine = make_engine()
        state = engine.state
        attacker = CreatureInstance(card=make_card("強い", power=3000), summoned_turn=0)
        target = CreatureInstance(card=make_card("弱い", power=1000), tapped=True, summoned_turn=0)
        state.players[0].battle_zone.append(attacker)
        state.players[1].battle_zone.append(target)
        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=0))
        self.assertIn(attacker, state.players[0].battle_zone)
        self.assertNotIn(target, state.players[1].battle_zone)
        self.assertIn(target.card, state.players[1].graveyard)

    def test_battle_equal_power_trades(self) -> None:
        engine = make_engine()
        state = engine.state
        attacker = CreatureInstance(card=make_card("相打ちA", power=2000), summoned_turn=0)
        target = CreatureInstance(card=make_card("相打ちB", power=2000), tapped=True, summoned_turn=0)
        state.players[0].battle_zone.append(attacker)
        state.players[1].battle_zone.append(target)
        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=0))
        self.assertNotIn(attacker, state.players[0].battle_zone)
        self.assertNotIn(target, state.players[1].battle_zone)


class DeckoutTest(unittest.TestCase):
    def test_draw_from_empty_deck_loses(self) -> None:
        engine = make_engine()
        state = engine.state
        state.players[0].deck = []
        self.assertFalse(engine._draw(state.players[0]))
        self.assertTrue(state.finished)
        self.assertEqual(state.winner, 1)
        self.assertEqual(state.finish_reason, "deckout")


class FullMatchTest(unittest.TestCase):
    def test_vanilla_match_completes(self) -> None:
        import random

        engine = DuelEngine(make_deck(), make_deck(civilization="自然"), GreedyPolicy(), GreedyPolicy(), rng=random.Random(7))
        result = engine.run()
        self.assertIn(result.reason, {"direct_attack", "deckout", "turn_limit"})
        self.assertGreater(result.turns, 0)
        self.assertTrue(result.log)

    def test_same_seed_same_result(self) -> None:
        import random

        results = []
        for _ in range(2):
            engine = DuelEngine(make_deck(), make_deck(civilization="自然"), GreedyPolicy(), GreedyPolicy(), rng=random.Random(11))
            result = engine.run()
            results.append((result.winner, result.turns, result.reason))
        self.assertEqual(results[0], results[1])


class CardInteropTest(unittest.TestCase):
    def test_battle_card_from_dict(self) -> None:
        card = battle_card_from_dict(
            {
                "card_id": "DMPC-0001",
                "name": "テストカード",
                "civilization": "光/水",
                "cost": "3",
                "card_type": "クリーチャー",
                "power": "6000+",
                "text": "W・ブレイカー ブロッカー",
                "tags": "初動;マナ加速",
            }
        )
        self.assertEqual(card.civilizations, ("光", "水"))
        self.assertEqual(card.cost, 3)
        self.assertEqual(card.power, 6000)
        self.assertEqual(card.breaker_count, 2)
        self.assertTrue(card.is_blocker)
        self.assertIn("初動", card.tags)


class SimulationRunnerTest(unittest.TestCase):
    def test_simulate_matches_summary(self) -> None:
        deck_a = [
            {"card_id": f"A{i}", "name": f"火{i}", "civilization": "火", "cost": (i % 5) + 1, "card_type": "クリーチャー", "power": ((i % 5) + 1) * 1000, "text": "", "tags": "", "quantity": 4}
            for i in range(10)
        ]
        deck_b = [
            {"card_id": f"B{i}", "name": f"自然{i}", "civilization": "自然", "cost": (i % 6) + 1, "card_type": "クリーチャー", "power": ((i % 6) + 1) * 1000, "text": "", "tags": "", "quantity": 4}
            for i in range(10)
        ]
        summary = simulate_matches(deck_a, deck_b, games=20, seed=5)
        self.assertEqual(summary.games, 20)
        self.assertEqual(summary.wins_a + summary.wins_b + summary.draws, 20)
        self.assertGreaterEqual(summary.ci95_high_a, summary.win_rate_a)
        self.assertLessEqual(summary.ci95_low_a, summary.win_rate_a)
        self.assertTrue(summary.sample_log)
        self.assertGreater(summary.average_turns, 0)


if __name__ == "__main__":
    unittest.main()

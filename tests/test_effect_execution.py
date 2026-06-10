from __future__ import annotations

import random
import unittest

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.engine import DuelEngine
from src.battle.kernel.policy import AttackChoice, GreedyPolicy, Policy
from src.battle.kernel.state import CreatureInstance
from src.battle.sim.runner import simulate_matches


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
        civilizations=tuple(civilization.split("/")),
        cost=cost,
        card_type=card_type,
        power=power,
        text=text,
    )


def make_deck(size: int = 40, civilization: str = "火") -> list[BattleCard]:
    return [
        make_card(f"{civilization}{index:02d}", cost=(index % 6) + 1, civilization=civilization, power=((index % 6) + 1) * 1000)
        for index in range(size)
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


def make_engine(effects: dict | None = None) -> DuelEngine:
    return DuelEngine(make_deck(), make_deck(), StubPolicy(), StubPolicy(), effects=effects)


class EffectExecutionTest(unittest.TestCase):
    def test_on_play_draw(self) -> None:
        effects = {"ドロー獣": [{"trigger": "on_play", "actions": [{"op": "draw", "count": 2}]}]}
        engine = make_engine(effects)
        state = engine.state
        player = state.players[0]
        card = make_card("ドロー獣")
        hand_before = len(player.hand)
        deck_before = len(player.deck)
        player.battle_zone.append(CreatureInstance(card=card, summoned_turn=1))
        engine.executor.run(engine, 0, "on_play", card)
        self.assertEqual(len(player.hand), hand_before + 2)
        self.assertEqual(len(player.deck), deck_before - 2)

    def test_on_cast_deck_top_to_mana(self) -> None:
        effects = {"加速呪文": [{"trigger": "on_cast", "actions": [{"op": "deck_top_to_mana", "count": 1}]}]}
        engine = make_engine(effects)
        player = engine.state.players[0]
        mana_before = len(player.mana_zone)
        engine.executor.run(engine, 0, "on_cast", make_card("加速呪文", card_type="呪文"))
        self.assertEqual(len(player.mana_zone), mana_before + 1)
        self.assertFalse(player.mana_zone[-1].tapped)

    def test_destroy_creature_respects_max_power(self) -> None:
        effects = {
            "除去呪文": [
                {
                    "trigger": "on_cast",
                    "actions": [{"op": "destroy_creature", "count": 1, "scope": "opponent", "max_power": 3000}],
                }
            ]
        }
        engine = make_engine(effects)
        opponent = engine.state.players[1]
        small = CreatureInstance(card=make_card("小型", power=2000), summoned_turn=0)
        big = CreatureInstance(card=make_card("大型", power=9000), summoned_turn=0)
        opponent.battle_zone.extend([small, big])
        engine.executor.run(engine, 0, "on_cast", make_card("除去呪文", card_type="呪文"))
        self.assertNotIn(small, opponent.battle_zone)
        self.assertIn(big, opponent.battle_zone)
        self.assertIn(small.card, opponent.graveyard)

    def test_bounce_and_tap(self) -> None:
        effects = {
            "バウンス": [{"trigger": "on_cast", "actions": [{"op": "bounce_creature", "count": 1, "scope": "opponent"}]}],
            "タップ": [{"trigger": "on_cast", "actions": [{"op": "tap_creature", "count": 1, "scope": "opponent"}]}],
        }
        engine = make_engine(effects)
        opponent = engine.state.players[1]
        creature_a = CreatureInstance(card=make_card("立ち獣A", power=4000), summoned_turn=0)
        creature_b = CreatureInstance(card=make_card("立ち獣B", power=2000), summoned_turn=0)
        opponent.battle_zone.extend([creature_a, creature_b])

        engine.executor.run(engine, 0, "on_cast", make_card("タップ", card_type="呪文"))
        self.assertTrue(creature_a.tapped)
        self.assertFalse(creature_b.tapped)

        hand_before = len(opponent.hand)
        engine.executor.run(engine, 0, "on_cast", make_card("バウンス", card_type="呪文"))
        self.assertNotIn(creature_a, opponent.battle_zone)
        self.assertEqual(len(opponent.hand), hand_before + 1)

    def test_s_trigger_spell_resolves_on_shield_break(self) -> None:
        effects = {
            "トリガー除去": [
                {"trigger": "s_trigger", "actions": [{"op": "destroy_creature", "count": 1, "scope": "opponent"}]}
            ]
        }
        engine = make_engine(effects)
        state = engine.state
        defender = state.players[1]
        defender.shields = [make_card("トリガー除去", card_type="呪文")]
        attacker = CreatureInstance(card=make_card("アタッカー", power=3000), summoned_turn=0)
        state.players[0].battle_zone.append(attacker)

        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=None))

        # 防御側のS・トリガーで攻撃側クリーチャーが破壊され、呪文は墓地へ置かれる
        self.assertEqual(len(defender.shields), 0)
        self.assertNotIn(attacker, state.players[0].battle_zone)
        self.assertIn(attacker.card, state.players[0].graveyard)
        self.assertTrue(any(card.name == "トリガー除去" for card in defender.graveyard))
        self.assertFalse(any(card.name == "トリガー除去" for card in defender.hand))

    def test_s_trigger_creature_enters_battle_zone(self) -> None:
        effects = {"トリガー獣": [{"trigger": "s_trigger", "actions": [{"op": "draw", "count": 1}]}]}
        engine = make_engine(effects)
        state = engine.state
        defender = state.players[1]
        defender.shields = [make_card("トリガー獣", power=2000)]
        state.players[0].battle_zone.append(CreatureInstance(card=make_card("アタッカー"), summoned_turn=0))

        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=None))

        self.assertTrue(any(creature.card.name == "トリガー獣" for creature in defender.battle_zone))

    def test_on_destroyed_trigger_fires(self) -> None:
        effects = {"道連れ獣": [{"trigger": "on_destroyed", "actions": [{"op": "draw", "count": 1}]}]}
        engine = make_engine(effects)
        owner = engine.state.players[1]
        creature = CreatureInstance(card=make_card("道連れ獣"), summoned_turn=0)
        owner.battle_zone.append(creature)
        hand_before = len(owner.hand)
        engine.destroy_creature(1, creature)
        self.assertEqual(len(owner.hand), hand_before + 1)

    def test_effect_draw_can_cause_deckout(self) -> None:
        effects = {"掘りすぎ": [{"trigger": "on_cast", "actions": [{"op": "draw", "count": 3}]}]}
        engine = make_engine(effects)
        player = engine.state.players[0]
        player.deck = player.deck[:1]
        engine.executor.run(engine, 0, "on_cast", make_card("掘りすぎ", card_type="呪文"))
        self.assertTrue(engine.state.finished)
        self.assertEqual(engine.state.winner, 1)
        self.assertEqual(engine.state.finish_reason, "deckout")

    def test_full_match_with_effects_completes(self) -> None:
        deck_a = make_deck()
        # 全カードにドロー効果を付けても対戦が破綻しないこと
        effects = {card.card_id: [{"trigger": "on_play", "actions": [{"op": "draw", "count": 1}]}] for card in deck_a}
        engine = DuelEngine(deck_a, make_deck(civilization="自然"), GreedyPolicy(), GreedyPolicy(), rng=random.Random(3), effects=effects)
        result = engine.run()
        self.assertIn(result.reason, {"direct_attack", "deckout", "turn_limit"})

    def test_simulate_matches_with_effects(self) -> None:
        deck_a = [
            {"card_id": f"A{i}", "name": f"火{i}", "civilization": "火", "cost": (i % 5) + 1, "card_type": "クリーチャー", "power": ((i % 5) + 1) * 1000, "quantity": 4}
            for i in range(10)
        ]
        deck_b = [
            {"card_id": f"B{i}", "name": f"自然{i}", "civilization": "自然", "cost": (i % 5) + 1, "card_type": "クリーチャー", "power": ((i % 5) + 1) * 1000, "quantity": 4}
            for i in range(10)
        ]
        effects = {f"A{i}": [{"trigger": "on_play", "actions": [{"op": "draw", "count": 1}]}] for i in range(10)}
        summary = simulate_matches(deck_a, deck_b, games=50, seed=9, effects=effects)
        self.assertEqual(summary.wins_a + summary.wins_b + summary.draws, 50)
        self.assertTrue(any(entry["action"] == "effect" for entry in summary.sample_log))


if __name__ == "__main__":
    unittest.main()

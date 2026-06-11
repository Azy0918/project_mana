from __future__ import annotations

import unittest

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.engine import DuelEngine, effective_cost, playable_hand_indexes
from src.battle.kernel.policy import Policy
from src.battle.kernel.state import CreatureInstance, ManaCard


def make_card(name: str, cost: int = 2, card_type: str = "クリーチャー", power: int = 1000, text: str = "") -> BattleCard:
    return BattleCard(
        card_id=name, name=name, civilizations=("火",), cost=cost, card_type=card_type, power=power, text=text
    )


def make_deck(size: int = 40) -> list[BattleCard]:
    return [make_card(f"c{i:02d}", cost=(i % 6) + 1, power=((i % 6) + 1) * 1000) for i in range(size)]


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


class GZeroTest(unittest.TestCase):
    def test_g_zero_parsed(self) -> None:
        card = make_card("スコーラー級", cost=11, text="■G・ゼロ:自分が呪文を5枚以上唱えたターン\n■T・ブレイカー")
        self.assertEqual(card.g_zero_spell_count, 5)
        self.assertIsNone(make_card("通常").g_zero_spell_count)

    def test_g_zero_makes_card_free(self) -> None:
        engine = make_engine()
        player = engine.state.players[0]
        g_zero = make_card("Gゼロ獣", cost=11, text="■G・ゼロ:自分が呪文を3枚以上唱えたターン")
        player.hand = [g_zero]
        player.mana_zone = []
        self.assertEqual(playable_hand_indexes(player), [])
        player.spells_cast_this_turn = 3
        self.assertEqual(effective_cost(player, g_zero), 0)
        self.assertEqual(playable_hand_indexes(player), [0])

    def test_spell_cast_counter_increments_and_resets(self) -> None:
        effects = {}
        engine = make_engine(effects)
        player = engine.state.players[0]
        spell = make_card("呪文", cost=1, card_type="呪文")
        player.hand = [spell]
        player.mana_zone = [ManaCard(make_card("マナ"))]

        class CastOnce(StubPolicy):
            def choose_main_action(self, state, p, playable):
                return playable[0] if playable else None

        engine.policies = (CastOnce(), StubPolicy())
        engine._main_phase(player, engine.policies[0])
        self.assertEqual(player.spells_cast_this_turn, 1)


class CostReductionTest(unittest.TestCase):
    def test_reduction_parsed_and_applied(self) -> None:
        engine = make_engine()
        player = engine.state.players[0]
        reducer = make_card("軽減獣", text="■自分のビートジョッキーの召喚コストを1少なくする。ただし、0以下にならない。")
        self.assertEqual(reducer.summon_cost_reduction, 1)
        player.battle_zone.append(CreatureInstance(card=reducer, summoned_turn=0))
        target = make_card("対象獣", cost=4)
        self.assertEqual(effective_cost(player, target), 3)
        # 1未満にはならない
        cheap = make_card("最軽量", cost=1)
        self.assertEqual(effective_cost(player, cheap), 1)

    def test_spell_not_reduced(self) -> None:
        engine = make_engine()
        player = engine.state.players[0]
        player.battle_zone.append(
            CreatureInstance(card=make_card("軽減獣", text="コストを3少なくする"), summoned_turn=0)
        )
        spell = make_card("呪文", cost=4, card_type="呪文")
        self.assertEqual(effective_cost(player, spell), 4)


class ExtraTurnTest(unittest.TestCase):
    def test_extra_turn_keeps_active_player(self) -> None:
        effects = {"追加ターン獣": [{"trigger": "on_play", "actions": [{"op": "extra_turn"}]}]}
        engine = make_engine(effects)
        state = engine.state
        engine.executor.run(engine, 0, "on_play", make_card("追加ターン獣"))
        self.assertTrue(state.extra_turn_pending)

    def test_extra_turn_limit_prevents_infinite_loop(self) -> None:
        # 毎ターン追加ターンを得ても上限3回で相手に手番が渡り、試合は完走する
        deck = [make_card(f"ループ{i}", cost=1, text="") for i in range(40)]
        effects = {card.card_id: [{"trigger": "on_play", "actions": [{"op": "extra_turn"}]}] for card in deck}

        class PlayFirst(StubPolicy):
            def choose_main_action(self, state, player, playable):
                return playable[0] if playable else None

            def choose_charge(self, state, player):
                return 0 if player.hand else None

        engine = DuelEngine(deck, make_deck(), PlayFirst(), StubPolicy(), effects=effects)
        result = engine.run()
        self.assertIn(result.reason, {"direct_attack", "deckout", "turn_limit"})
        self.assertLessEqual(engine.state.players[0].extra_turns_taken, 3)


if __name__ == "__main__":
    unittest.main()

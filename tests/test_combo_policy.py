from __future__ import annotations

import unittest

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.combo import ComboPolicy
from src.battle.kernel.engine import DuelEngine
from src.battle.kernel.policy import Policy
from src.battle.kernel.state import ManaCard


def make_card(name: str, cost: int = 2, card_type: str = "クリーチャー", power: int = 1000, text: str = "") -> BattleCard:
    return BattleCard(
        card_id=name, name=name, civilizations=("水",), cost=cost, card_type=card_type, power=power, text=text
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


class ComboPolicyTest(unittest.TestCase):
    def _engine(self) -> DuelEngine:
        return DuelEngine(make_deck(), make_deck(), ComboPolicy(), StubPolicy())

    def test_chains_spells_into_g_zero_summon(self) -> None:
        engine = self._engine()
        state = engine.state
        state.turn = 5
        player = state.players[0]
        g_zero = make_card("Gゼロ獣", cost=11, power=12000, text="■G・ゼロ:自分が呪文を3枚以上唱えたターン")
        player.hand = [
            make_card("呪文A", cost=1, card_type="呪文"),
            make_card("呪文B", cost=1, card_type="呪文"),
            make_card("呪文C", cost=2, card_type="呪文"),
            g_zero,
        ]
        player.mana_zone = [ManaCard(make_card(f"マナ{i}", cost=1)) for i in range(4)]
        engine._main_phase(player, engine.policies[0])
        # 呪文3枚を唱えた後、G・ゼロ獣がコスト0で出ている
        self.assertEqual(player.spells_cast_this_turn, 3)
        self.assertTrue(any(creature.card.name == "Gゼロ獣" for creature in player.battle_zone))
        # マナは呪文ぶん(1+1+2=4)しか使っていない
        self.assertEqual(sum(1 for mana in player.mana_zone if mana.tapped), 4)

    def test_does_not_charge_g_zero_card(self) -> None:
        engine = self._engine()
        player = engine.state.players[0]
        g_zero = make_card("Gゼロ獣", cost=11, text="■G・ゼロ:自分が呪文を5枚以上唱えたターン")
        player.hand = [g_zero, make_card("普通", cost=9)]
        choice = engine.policies[0].choose_charge(engine.state, player)
        self.assertEqual(player.hand[choice].name, "普通")

    def test_falls_back_to_greedy_without_g_zero(self) -> None:
        engine = self._engine()
        player = engine.state.players[0]
        player.hand = [make_card("小型", cost=1, power=1000), make_card("大型", cost=3, power=3000)]
        player.mana_zone = [ManaCard(make_card(f"マナ{i}")) for i in range(3)]
        choice = engine.policies[0].choose_main_action(engine.state, player, [0, 1])
        self.assertEqual(player.hand[choice].name, "大型")


if __name__ == "__main__":
    unittest.main()

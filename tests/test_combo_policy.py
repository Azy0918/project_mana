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


MRC_EFFECTS = {
    "ロマノフ": [
        {"trigger": "on_attack", "actions": [{"op": "cast_from_grave", "count": 1, "max_cost": 7}]}
    ],
    "サイン": [
        {"trigger": "on_cast", "actions": [{"op": "summon_from_grave", "count": 1, "max_cost": 7}]}
    ],
}


class ComboPolicyTest(unittest.TestCase):
    def _engine(self, effects: dict | None = None) -> DuelEngine:
        return DuelEngine(make_deck(), make_deck(), ComboPolicy(), StubPolicy(), effects=effects)

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

    def test_discards_grave_good_card_for_engine(self) -> None:
        # エンジン(攻撃時墓地詠唱)が存在する世界では、蘇生呪文を選んで捨てる
        engine = self._engine(effects=MRC_EFFECTS)
        player = engine.state.players[0]
        hand = [
            make_card("普通", cost=9),
            make_card("サイン", cost=5, card_type="呪文"),
            make_card("小型", cost=1),
        ]
        choice = engine.policies[0].choose_discard(engine.state, player, hand)
        self.assertEqual(hand[choice].name, "サイン")

    def test_discard_defaults_to_none_without_engine(self) -> None:
        # エンジン不在ならMRC型の墓地適性は無効(ランダム捨てに任せる)
        effects = {"サイン": MRC_EFFECTS["サイン"]}
        engine = self._engine(effects=effects)
        player = engine.state.players[0]
        hand = [make_card("サイン", cost=5, card_type="呪文"), make_card("普通", cost=9)]
        self.assertIsNone(engine.policies[0].choose_discard(engine.state, player, hand))

    def test_does_not_charge_engine(self) -> None:
        # エンジン本体はマナチャージから保護される(弾の蘇生呪文は保護しない)
        engine = self._engine(effects=MRC_EFFECTS)
        player = engine.state.players[0]
        player.hand = [
            make_card("ロマノフ", cost=6, power=6000),
            make_card("普通", cost=2),
        ]
        choice = engine.policies[0].choose_charge(engine.state, player)
        self.assertEqual(player.hand[choice].name, "普通")

    def test_charges_greedily_when_all_protected(self) -> None:
        # 手札が保護対象だけのときはマナ詰まり回避を優先してチャージする
        engine = self._engine(effects=MRC_EFFECTS)
        player = engine.state.players[0]
        player.hand = [make_card("ロマノフ", cost=6, power=6000)]
        choice = engine.policies[0].choose_charge(engine.state, player)
        self.assertEqual(choice, 0)

    def test_engine_counts_effect_successes(self) -> None:
        # 対象が確定した効果はkeep_logと無関係にop_success_countsへ集計される
        engine = self._engine(effects=MRC_EFFECTS)
        engine.keep_log = False
        player = engine.state.players[0]
        player.graveyard = [make_card("ロマノフ", cost=6, power=6000)]
        source = make_card("サイン", cost=5, card_type="呪文")
        engine.executor._execute_action(engine, 0, "on_cast", source, {"op": "summon_from_grave", "count": 1})
        self.assertEqual(engine.op_success_counts[0]["summon_from_grave"], 1)
        self.assertEqual(engine.op_success_counts[1]["summon_from_grave"], 0)

    def test_executor_routes_discard_to_policy(self) -> None:
        # discard_own_hand実行時に方策のchoose_discardが反映される
        engine = self._engine(effects=MRC_EFFECTS)
        player = engine.state.players[0]
        player.hand = [make_card("普通", cost=9), make_card("サイン", cost=5, card_type="呪文")]
        source = make_card("ソー☆ギョッ", cost=2)
        engine.executor._execute_action(engine, 0, "on_play", source, {"op": "discard_own_hand", "count": 1})
        self.assertEqual([card.name for card in player.hand], ["普通"])
        self.assertEqual(player.graveyard[-1].name, "サイン")

    def test_prefers_revive_spell_when_engine_in_grave(self) -> None:
        # 墓地にエンジンが落ちていれば、蘇生呪文をクリーチャー召喚より先に唱える
        engine = self._engine(effects=MRC_EFFECTS)
        player = engine.state.players[0]
        player.hand = [make_card("大型", cost=5, power=5000), make_card("サイン", cost=5, card_type="呪文")]
        player.graveyard = [make_card("ロマノフ", cost=6, power=6000)]
        choice = engine.policies[0].choose_main_action(engine.state, player, [0, 1])
        self.assertEqual(player.hand[choice].name, "サイン")

    def test_no_revive_priority_without_engine_in_grave(self) -> None:
        # 墓地にエンジンがなければ貪欲どおりクリーチャーを優先する
        engine = self._engine(effects=MRC_EFFECTS)
        player = engine.state.players[0]
        player.hand = [make_card("大型", cost=5, power=5000), make_card("サイン", cost=5, card_type="呪文")]
        player.graveyard = [make_card("普通", cost=3)]
        choice = engine.policies[0].choose_main_action(engine.state, player, [0, 1])
        self.assertEqual(player.hand[choice].name, "大型")

    def test_falls_back_to_greedy_without_g_zero(self) -> None:
        engine = self._engine()
        player = engine.state.players[0]
        player.hand = [make_card("小型", cost=1, power=1000), make_card("大型", cost=3, power=3000)]
        player.mana_zone = [ManaCard(make_card(f"マナ{i}")) for i in range(3)]
        choice = engine.policies[0].choose_main_action(engine.state, player, [0, 1])
        self.assertEqual(player.hand[choice].name, "大型")


if __name__ == "__main__":
    unittest.main()

"""destroy_mana / destroy_creatures_nonciv op(ドルバロム型マナ破壊)の被覆テスト。

「各プレイヤーは闇以外のカードをすべて自身のマナゾーンから墓地に置く。その後、
闇以外のクリーチャーをすべて破壊する」を keep_civ + scope=both で exact に再現する。
"""
from __future__ import annotations

import random
import unittest

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.effect_executor import EffectExecutor
from src.battle.kernel.engine import DuelEngine
from src.battle.kernel.policy import GreedyPolicy
from src.battle.kernel.state import CreatureInstance, make_mana_card


def _mk(name, civ, cost=3, ct="クリーチャー", power=3000):
    return BattleCard(card_id=name, name=name, civilizations=(civ,), cost=cost,
                      card_type=ct, power=power, text="")


class DestroyManaTest(unittest.TestCase):
    def _engine(self):
        a = [_mk("a", "闇") for _ in range(40)]
        b = [_mk("b", "光") for _ in range(40)]
        return DuelEngine(a, b, GreedyPolicy(), GreedyPolicy(), rng=random.Random(0))

    def test_destroy_mana_keep_civ_both(self):
        e = self._engine()
        ex = EffectExecutor(effects={})
        for pidx, civs in ((0, ["闇", "光", "火"]), (1, ["闇", "光", "光"])):
            e.state.players[pidx].mana_zone = [make_mana_card(_mk("m", c)) for c in civs]
        ex._execute_action(e, 0, "on_play", _mk("dorbalom", "闇", 10),
                           {"op": "destroy_mana", "scope": "both", "keep_civ": "闇"})
        # 両者とも闇マナのみ残る
        for pidx in (0, 1):
            mz = e.state.players[pidx].mana_zone
            self.assertTrue(all("闇" in m.card.civilizations for m in mz), pidx)
        self.assertEqual(len(e.state.players[0].mana_zone), 1)  # 闇1枚
        self.assertEqual(len(e.state.players[1].mana_zone), 1)
        self.assertEqual(len(e.state.players[0].graveyard), 2)  # 光火が墓地

    def test_destroy_creatures_nonciv_both(self):
        e = self._engine()
        ex = EffectExecutor(effects={})
        e.state.players[0].battle_zone = [CreatureInstance(card=_mk("d", "闇")),
                                          CreatureInstance(card=_mk("h", "光"))]
        e.state.players[1].battle_zone = [CreatureInstance(card=_mk("h2", "光")),
                                          CreatureInstance(card=_mk("d2", "闇"))]
        ex._execute_action(e, 0, "on_play", _mk("dorbalom", "闇", 10),
                           {"op": "destroy_creatures_nonciv", "scope": "both", "keep_civ": "闇"})
        for pidx in (0, 1):
            bz = e.state.players[pidx].battle_zone
            self.assertTrue(all("闇" in c.card.civilizations for c in bz), pidx)
            self.assertEqual(len(bz), 1)

    def test_no_keep_civ_destroys_all_mana(self):
        e = self._engine()
        ex = EffectExecutor(effects={})
        e.state.players[1].mana_zone = [make_mana_card(_mk("m", "光")) for _ in range(3)]
        ex._execute_action(e, 0, "on_play", _mk("x", "闇"),
                           {"op": "destroy_mana", "scope": "opponent"})
        self.assertEqual(len(e.state.players[1].mana_zone), 0)
        self.assertEqual(len(e.state.players[0].mana_zone), 0)  # 自分は対象外で空のまま


if __name__ == "__main__":
    unittest.main()

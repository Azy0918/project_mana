"""S・トリガーロック(「誰も〜のS・トリガーを使えない」)の被覆テスト。

フ・レイル(闇ロック)/ギガボルバ(光ロック)等の静的ロック能力を、exact-safeに
検出し、シールドブレイク時のS・トリガー発動を抑制することを検証する。
"""
from __future__ import annotations

import random
import unittest

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.engine import DuelEngine
from src.battle.kernel.policy import GreedyPolicy


def _mk(card_id: str, name: str, civ: str, cost: int, ct: str, power: int, text: str = "") -> BattleCard:
    return BattleCard(
        card_id=card_id, name=name, civilizations=(civ,), cost=cost,
        card_type=ct, power=power, text=text,
    )


class StriggerLockDetectionTest(unittest.TestCase):
    def test_unconditional_global_lock_detected(self) -> None:
        furail = _mk("141200", "フ・レイル", "光", 6, "クリーチャー", 5000,
                     "■誰も闇のカードの「S・トリガー」を使えない。")
        giga = _mk("144200", "ギガボルバ", "闇", 4, "クリーチャー", 3000,
                   "■誰も光のカードの「S・トリガー」を使えない。")
        self.assertEqual(furail.strigger_lock_civs, ("闇",))
        self.assertEqual(giga.strigger_lock_civs, ("光",))

    def test_per_break_and_conditional_excluded(self) -> None:
        # per-break型(自分がブレイクしたシールド限定)は範囲を静的確定できないため除外
        dorza = _mk("111700", "ドルザバード", "闇", 6, "進化クリーチャー", 11000,
                    "■相手はこのクリーチャーがブレイクしたシールドの「S・トリガー」を使えない。")
        # 条件付き(5文明なら)も除外
        cond = _mk("y", "ドミティウス", "自然", 9, "クリーチャー", 9000,
                   "■自分の5文明すべてのクリーチャーがあるなら、相手はクリーチャーの「S・トリガー」を使えない。")
        normal = _mk("x", "通常", "火", 3, "クリーチャー", 3000, "■W・ブレイカー")
        self.assertEqual(dorza.strigger_lock_civs, ())
        self.assertEqual(cond.strigger_lock_civs, ())
        self.assertEqual(normal.strigger_lock_civs, ())


class StriggerLockEngineTest(unittest.TestCase):
    def _fires(self, attacker_has_locker: bool, trials: int = 40) -> float:
        strig_text = "◇S・トリガー\n■相手のクリーチャーをすべて破壊する。"
        effects = {"STRIG": [{"trigger": "s_trigger",
                              "actions": [{"op": "destroy_creature", "count": 99, "scope": "opponent"}]}]}
        strig = _mk("STRIG", "闇トリガー", "闇", 3, "呪文", 0, strig_text)
        beater = _mk("BEAT", "殴り", "火", 1, "クリーチャー", 1000)
        locker = _mk("141200", "フ・レイル", "光", 1, "クリーチャー", 5000,
                     "■誰も闇のカードの「S・トリガー」を使えない。")
        total = 0
        for seed in range(trials):
            defender = [strig] * 20 + [beater] * 20
            attacker = ([locker] * 8 + [beater] * 32) if attacker_has_locker else [beater] * 40
            e = DuelEngine(attacker, defender, GreedyPolicy(), GreedyPolicy(),
                           rng=random.Random(seed), effects=effects)
            e.run()
            total += sum(1 for r in e.state.log if r.get("action") == "s_trigger")
        return total / trials

    def test_lock_suppresses_strigger(self) -> None:
        no_lock = self._fires(False)
        with_lock = self._fires(True)
        self.assertGreater(no_lock, 0, "ロックなしでは闇S・トリガーが発火するはず")
        # ロッカー投入で発火が大幅に減少する(完全0ではない=常時場にいるわけではないため)
        self.assertLess(with_lock, no_lock * 0.6,
                        f"ロッカー投入で発火が減少するはず (no={no_lock:.2f} lock={with_lock:.2f})")


if __name__ == "__main__":
    unittest.main()

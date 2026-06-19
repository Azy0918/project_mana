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
        # per-break型は静的civロックではない(別途 disables_broken_strigger で扱う)
        dorza = _mk("111700", "ドルザバード", "闇", 6, "進化クリーチャー", 11000,
                    "■相手はこのクリーチャーがブレイクしたシールドの「S・トリガー」を使えない。")
        # 条件付き(5文明なら)も除外
        cond = _mk("y", "ドミティウス", "自然", 9, "クリーチャー", 9000,
                   "■自分の5文明すべてのクリーチャーがあるなら、相手はクリーチャーの「S・トリガー」を使えない。")
        normal = _mk("x", "通常", "火", 3, "クリーチャー", 3000, "■W・ブレイカー")
        self.assertEqual(dorza.strigger_lock_civs, ())
        self.assertEqual(cond.strigger_lock_civs, ())
        self.assertEqual(normal.strigger_lock_civs, ())

    def test_per_break_disable_detection(self) -> None:
        dorza = _mk("111700", "ドルザバード", "闇", 6, "進化クリーチャー", 11000,
                    "■相手はこのクリーチャーがブレイクしたシールドの「S・トリガー」を使えない。")
        normal = _mk("x", "通常", "火", 3, "クリーチャー", 3000, "■W・ブレイカー")
        furail = _mk("141200", "フ・レイル", "光", 6, "クリーチャー", 5000,
                     "■誰も闇のカードの「S・トリガー」を使えない。")
        self.assertTrue(dorza.disables_broken_strigger)
        self.assertFalse(normal.disables_broken_strigger)
        self.assertFalse(furail.disables_broken_strigger)  # 静的civロックはper-breakではない


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


class SpellLockTest(unittest.TestCase):
    def test_spell_lock_detection(self) -> None:
        chuza = _mk("354900", "お騒がせチューザ", "火", 4, "クリーチャー", 2000,
                    "■可能なら毎ターン攻撃する。\n■このクリーチャーがタップしている時、誰も呪文を唱えられない。")
        arca = _mk("6400", "聖霊王アルカディアス", "光", 6, "進化クリーチャー", 12500,
                   "■T・ブレイカー\n■誰も光以外の呪文を唱えられない。")
        rafu = _mk("700600", "音精 ラフルル", "光", 5, "クリーチャー", 5000,
                   "■バトルゾーンに出た時、そのターン、相手はコスト6以下の呪文を唱えられない。")
        self.assertEqual(chuza.spell_lock, (None, None, True))
        self.assertEqual(arca.spell_lock, ("光", None, False))
        self.assertIsNone(rafu.spell_lock)  # タイミング限定は除外

    def test_tapped_spell_lock_suppresses_spell_strigger(self) -> None:
        effects = {"STRIG": [{"trigger": "s_trigger",
                             "actions": [{"op": "destroy_creature", "count": 99, "scope": "opponent"}]}]}
        strig = _mk("STRIG", "闇除去", "闇", 3, "呪文", 0, "◇S・トリガー\n■相手のクリーチャーをすべて破壊する。")
        chuza = _mk("354900", "お騒がせチューザ", "火", 2, "クリーチャー", 2000,
                    "■このクリーチャーがタップしている時、誰も呪文を唱えられない。")
        filler = _mk("F", "f", "火", 5, "クリーチャー", 1000)
        import random as _r
        def fires(use):
            t = 0
            for s in range(30):
                d = [strig]*20 + [filler]*20
                a = ([chuza]*10 + [filler]*30) if use else [_mk("B","殴","火",2,"クリーチャー",4000,"■W・ブレイカー")]*10+[filler]*30
                e = DuelEngine(a, d, GreedyPolicy(), GreedyPolicy(), rng=_r.Random(s), effects=effects)
                e.run()
                t += sum(1 for x in e.state.log if x.get("action") == "s_trigger")
            return t/30
        self.assertGreater(fires(False), 0.5)
        self.assertLess(fires(True), fires(False) * 0.3)

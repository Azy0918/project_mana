from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.battle.effects.store import upsert_effect_script
from src.battle.loop_finder import find_loop_candidates, mine_loops, verify_loop_candidate


class LoopFinderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "cards.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE cards (card_id TEXT PRIMARY KEY, name TEXT, civilization TEXT,"
                " cost INTEGER, card_type TEXT, power TEXT, race TEXT, text TEXT)"
            )
            rows = [
                ("SAGA", "絶望神もどき", "闇", 5, "クリーチャー", "5000", "", ""),
                ("REAN", "ただの蘇生獣", "闇", 6, "クリーチャー", "6000", "", ""),
                ("VAN", "バニラ", "火", 3, "クリーチャー", "3000", "", ""),
            ]
            conn.executemany("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        # サガ構造: 自壊→蘇生(自身のコストを許容)の順
        upsert_effect_script(
            {
                "card_id": "SAGA",
                "abilities": [
                    {
                        "trigger": "on_play",
                        "actions": [
                            {"op": "destroy_creature", "count": 1, "scope": "self"},
                            {"op": "summon_from_grave", "count": 1, "max_cost": 5},
                        ],
                    }
                ],
            },
            review_status="approved",
            db_path=self.db_path,
            fidelity="exact",
        )
        # 自壊なしの単純蘇生(有限増殖型)
        upsert_effect_script(
            {
                "card_id": "REAN",
                "abilities": [
                    {"trigger": "on_play", "actions": [{"op": "summon_from_grave", "count": 1, "max_cost": 7}]}
                ],
            },
            review_status="approved",
            db_path=self.db_path,
            fidelity="exact",
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_static_screening(self) -> None:
        candidates = find_loop_candidates(self.db_path)
        kinds = {tuple(c["chain"]): c for c in candidates}
        self.assertIn(("SAGA",), kinds)
        self.assertTrue(kinds[("SAGA",)]["infinite_candidate"])
        self.assertIn(("REAN",), kinds)
        self.assertFalse(kinds[("REAN",)]["infinite_candidate"])
        # 相互型: SAGA(上限5)はREAN(コスト6)を釣れないので相互ペアは成立しない
        self.assertNotIn(("REAN", "SAGA"), kinds)

    def test_saga_structure_hits_resolution_cap(self) -> None:
        result = verify_loop_candidate(["SAGA"], db_path=self.db_path)
        self.assertTrue(result["hits_cap"])
        self.assertGreaterEqual(result["revive_count"], 5)

    def test_plain_reanimator_is_finite(self) -> None:
        result = verify_loop_candidate(["REAN"], db_path=self.db_path)
        self.assertFalse(result["hits_cap"])
        # 墓地のコピー3枚を釣り切ったら止まる
        self.assertLessEqual(result["revive_count"], 3)

    def test_mine_loops_ranks_infinite_first(self) -> None:
        result = mine_loops(self.db_path)
        self.assertGreaterEqual(result["static_candidates"], 2)
        self.assertEqual(result["verified"][0]["chain"], ["SAGA"])
        self.assertTrue(result["verified"][0]["hits_cap"])


if __name__ == "__main__":
    unittest.main()


class MRCEngineReproductionTest(unittest.TestCase):
    """歴史上のMRC型ワンショット(攻撃→墓地詠唱→SA蘇生→連続攻撃)の再現回帰テスト。

    合成カードでcast_from_grave + speed_attacker付与の連鎖を検証する。
    """

    def test_attack_cast_revive_chain_one_shots(self) -> None:
        import random

        from src.battle.kernel.cards import BattleCard
        from src.battle.kernel.engine import DuelEngine
        from src.battle.kernel.policy import GreedyPolicy
        from src.battle.kernel.state import CreatureInstance

        def card(cid, name, cost, ctype, power, civ="闇"):
            return BattleCard(card_id=cid, name=name, civilizations=(civ,), cost=cost,
                              card_type=ctype, power=power, text="W・ブレイカー" if ctype == "クリーチャー" else "")

        romanov = card("ROM", "ロマノフ風", 7, "クリーチャー", 7000)
        sign = card("SIGN", "魔弾風", 6, "呪文", 0)
        effects = {
            "ROM": [{"trigger": "on_attack", "actions": [{"op": "cast_from_grave", "count": 1, "max_cost": 7}]}],
            "SIGN": [{"trigger": "on_cast", "actions": [
                {"op": "summon_from_grave", "count": 1, "max_cost": 7, "speed_attacker": True}]}],
        }
        filler = [card(f"F{i}", f"埋め{i}", 2, "クリーチャー", 2000) for i in range(40)]
        engine = DuelEngine(filler, filler, GreedyPolicy(), GreedyPolicy(),
                            rng=random.Random(1), effects=effects)
        state = engine.state
        state.turn = 8
        player = state.players[0]
        player.battle_zone.append(CreatureInstance(card=romanov, summoned_turn=7))
        player.graveyard.extend([sign] * 4 + [romanov] * 3)

        engine._attack_phase(player, engine.policies[0])

        casts = [e for e in state.log if e.get("op") == "cast_from_grave" and "target" in e]
        revives = [e for e in state.log if e.get("op") == "summon_from_grave" and "target" in e]
        self.assertGreaterEqual(len(casts), 2)
        self.assertGreaterEqual(len(revives), 2)
        # 連続攻撃でシールドを削り切りダイレクトアタックに到達する
        self.assertTrue(state.finished)
        self.assertEqual(state.finish_reason, "direct_attack")

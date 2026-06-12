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

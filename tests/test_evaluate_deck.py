from __future__ import annotations

import unittest

from src.evaluate_deck import _count_defense, evaluate_deck


class DefenseCountTest(unittest.TestCase):
    def test_blockers_counted_as_defense(self) -> None:
        # ブロッカー(テキスト由来)が受け札として数えられる(探索のブロッカー盲点対策)
        cards = [{"text": "◇ブロッカー", "tags": ""} for _ in range(6)]
        self.assertEqual(_count_defense(cards), 6)

    def test_defense_tag_not_double_counted_with_blocker(self) -> None:
        # 受け札タグとブロッカーテキストの両方を持つカードは1回だけ数える
        cards = [{"text": "◇ブロッカー S・トリガー", "tags": "受け札"}]
        self.assertEqual(_count_defense(cards), 1)

    def test_blocker_wall_reported_in_role_counts(self) -> None:
        # ブロッカー壁の受け札枚数が評価サマリに反映される
        deck = [{"name": f"c{i}", "cost": 2, "civilization": "光", "text": "◇ブロッカー", "tags": ""} for i in range(12)]
        summary = evaluate_deck(deck)
        self.assertEqual(summary["role_counts"]["受け札"], 12)


if __name__ == "__main__":
    unittest.main()

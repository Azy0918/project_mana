from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.battle.rating.meta_rating import load_meta_battle_decks, rate_deck_against_meta
from src.battle.rating.store import ensure_rating_tables, list_sim_ratings
from src.battle.sim.chain_validator import validate_chain_playable
from src.deck_candidate_scorer import apply_sim_strength


def card_row(card_id: str, name: str, cost: int, power: int, civilization: str = "火") -> tuple:
    return (card_id, name, civilization, cost, "クリーチャー", str(power), "", "")


def deck_dicts(prefix: str, civilization: str = "火", costs: list[int] | None = None) -> list[dict]:
    costs = costs or [1, 2, 3, 4, 5]
    return [
        {
            "card_id": f"{prefix}{i}",
            "name": f"{prefix}カード{i}",
            "civilization": civilization,
            "cost": cost,
            "card_type": "クリーチャー",
            "power": cost * 1000,
            "quantity": 8,
        }
        for i, cost in enumerate(costs)
    ]


class MetaRatingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "cards.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE cards (card_id TEXT PRIMARY KEY, name TEXT, civilization TEXT,"
                " cost INTEGER, card_type TEXT, power TEXT, race TEXT, text TEXT)"
            )
            conn.execute(
                "CREATE TABLE meta_deck_cards (id INTEGER PRIMARY KEY AUTOINCREMENT,"
                " deck_name TEXT, format TEXT, source_url TEXT, card_name TEXT, count INTEGER,"
                " raw_line TEXT, imported_at TEXT)"
            )
            # メタデッキ「火速攻」: DB一致カード10種x4枚
            for i in range(10):
                cost = (i % 3) + 1
                conn.execute(
                    "INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    card_row(f"M{i}", f"メタカード{i}", cost, cost * 1000),
                )
                conn.execute(
                    "INSERT INTO meta_deck_cards (deck_name, format, source_url, card_name, count, raw_line, imported_at)"
                    " VALUES ('火速攻', 'ND', '', ?, 4, '', '')",
                    (f"メタカード{i}",),
                )
            # メタデッキ「未収録デッキ」: DBに存在しないカードのみ(除外されるべき)
            conn.execute(
                "INSERT INTO meta_deck_cards (deck_name, format, source_url, card_name, count, raw_line, imported_at)"
                " VALUES ('未収録デッキ', 'ND', '', '存在しないカード', 40, '', '')"
            )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_load_meta_battle_decks(self) -> None:
        decks, warnings = load_meta_battle_decks(self.db_path)
        self.assertEqual(len(decks), 1)
        self.assertEqual(decks[0]["deck_name"], "火速攻")
        self.assertEqual(decks[0]["coverage"], 1.0)
        self.assertEqual(decks[0]["total_cards"], 40)
        self.assertEqual(len(warnings), 1)
        self.assertIn("未収録デッキ", warnings[0])

    def test_rate_deck_against_meta(self) -> None:
        deck = deck_dicts("A")
        result = rate_deck_against_meta(deck, "テストデッキ", db_path=self.db_path, games_per_pair=50, seed=1)
        self.assertIsNotNone(result["strength_score"])
        self.assertEqual(result["games_total"], 50)
        self.assertEqual(len(result["details"]), 1)
        self.assertEqual(result["details"][0]["opponent"], "火速攻")
        ratings = list_sim_ratings(self.db_path)
        self.assertEqual(len(ratings), 1)
        self.assertEqual(ratings[0]["deck_name"], "テストデッキ")
        self.assertEqual(ratings[0]["games_total"], 50)
        with sqlite3.connect(self.db_path) as conn:
            log_count = conn.execute("SELECT COUNT(*) FROM sim_battle_logs").fetchone()[0]
        self.assertEqual(log_count, 1)

    def test_rate_with_no_meta_decks(self) -> None:
        empty_db = Path(self._tmpdir.name) / "empty.db"
        with sqlite3.connect(empty_db) as conn:
            conn.execute("CREATE TABLE cards (card_id TEXT, name TEXT, civilization TEXT, cost INTEGER, card_type TEXT, power TEXT, race TEXT, text TEXT)")
            conn.execute("CREATE TABLE meta_deck_cards (id INTEGER PRIMARY KEY, deck_name TEXT, format TEXT, source_url TEXT, card_name TEXT, count INTEGER, raw_line TEXT, imported_at TEXT)")
        result = rate_deck_against_meta(deck_dicts("A"), "テスト", db_path=empty_db)
        self.assertIsNone(result["strength_score"])
        self.assertTrue(result["warnings"])

    def test_ensure_rating_tables_idempotent(self) -> None:
        ensure_rating_tables(self.db_path)
        ensure_rating_tables(self.db_path)


class ChainValidatorTest(unittest.TestCase):
    def test_cheap_chain_succeeds(self) -> None:
        deck = deck_dicts("C", costs=[1, 2])  # 1コストと2コストのみ各8種…ではなく2種x8枚
        result = validate_chain_playable(["C0", "C1"], deck, trials=100, max_turns=5, seed=1)
        self.assertGreater(result["success_rate"], 0.5)
        self.assertTrue(result["completion_turn_distribution"])

    def test_impossible_chain_fails(self) -> None:
        deck = deck_dicts("C", costs=[9, 9, 9, 9, 9])
        result = validate_chain_playable(["C0", "C1"], deck, trials=50, max_turns=3, seed=2)
        self.assertEqual(result["success_rate"], 0.0)

    def test_missing_chain_card_warns(self) -> None:
        deck = deck_dicts("C")
        result = validate_chain_playable(["C0", "Z9"], deck, trials=50)
        self.assertEqual(result["trials"], 0)
        self.assertTrue(result["warnings"])

    def test_partial_rates_monotonic(self) -> None:
        deck = deck_dicts("C", costs=[1, 3, 5])
        result = validate_chain_playable(["C0", "C1", "C2"], deck, trials=200, max_turns=6, seed=3)
        rates = [result["partial_rates"][card_id] for card_id in ["C0", "C1", "C2"]]
        self.assertTrue(rates[0] >= rates[1] >= rates[2])


class MetaPoolExpansionTest(MetaRatingTest):
    def test_add_deck_to_meta_pool(self) -> None:
        from src.battle.rating.meta_rating import add_deck_to_meta_pool

        deck = deck_dicts("M", "火")
        # カード名がcardsテーブルと一致するように既存メタカード名を使う
        deck = [
            {"card_id": f"M{i}", "name": f"メタカード{i}", "civilization": "火", "cost": 2,
             "card_type": "クリーチャー", "power": 2000, "quantity": 4}
            for i in range(10)
        ]
        added = add_deck_to_meta_pool(deck, "自己対戦テスト", db_path=self.db_path)
        self.assertEqual(added, 10)
        # 同名は再登録しない
        self.assertEqual(add_deck_to_meta_pool(deck, "自己対戦テスト", db_path=self.db_path), 0)
        decks, warnings = load_meta_battle_decks(self.db_path)
        names = {d["deck_name"] for d in decks}
        self.assertIn("自己対戦テスト", names)
        self.assertIn("火速攻", names)
        promoted = next(d for d in decks if d["deck_name"] == "自己対戦テスト")
        self.assertEqual(promoted["coverage"], 1.0)
        self.assertEqual(promoted["total_cards"], 40)


class OpponentRotationTest(unittest.TestCase):
    def test_sliding_window_covers_all_decks(self) -> None:
        from src.battle.hybrid_search import _opponents_for_generation

        meta = [{"deck_name": f"D{i}"} for i in range(5)]
        seen = set()
        windows = []
        for generation in range(1, 6):
            opponents = _opponents_for_generation(meta, generation, 2)
            self.assertEqual(len(opponents), 2)
            windows.append(tuple(d["deck_name"] for d in opponents))
            seen.update(d["deck_name"] for d in opponents)
        # 5世代で全デッキが選別相手に登場し、ウィンドウは世代ごとに変わる
        self.assertEqual(seen, {f"D{i}" for i in range(5)})
        self.assertGreater(len(set(windows)), 1)

    def test_small_meta_returns_all(self) -> None:
        from src.battle.hybrid_search import _opponents_for_generation

        meta = [{"deck_name": "D0"}, {"deck_name": "D1"}]
        self.assertEqual(_opponents_for_generation(meta, 3, 3), meta)


class HybridSearchTest(MetaRatingTest):
    def test_run_hybrid_search(self) -> None:
        import sqlite3 as sq

        with sq.connect(self.db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS card_tags (card_id TEXT, tag TEXT)")
        from src.battle.hybrid_search import run_hybrid_search

        result = run_hybrid_search(
            db_path=self.db_path,
            generations=2,
            population_size=4,
            seed=1,
            sim_games=4,
            sim_opponents=1,
            sim_weight=0.7,
        )
        best = result["best"]
        self.assertIsNotNone(best)
        self.assertEqual(sum(int(c.get("quantity", 1)) for c in best["deck"]), 40)
        self.assertEqual(len(result["history"]), 2)
        self.assertGreaterEqual(best["combined_score"], 0)
        self.assertEqual(result["opponents"], ["火速攻"])

    def test_save_to_generated_decks(self) -> None:
        import json as json_module
        import sqlite3 as sq

        from src.battle.hybrid_search import save_to_generated_decks

        deck = deck_dicts("S", "火")
        deck_id = save_to_generated_decks(deck, "保存テスト", "メモ", db_path=self.db_path)
        with sq.connect(self.db_path) as conn:
            conn.row_factory = sq.Row
            row = conn.execute("SELECT * FROM generated_decks WHERE id = ?", (deck_id,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["deck_name"], "保存テスト")
        self.assertEqual(row["candidate_origin"], "hybrid_search")
        saved_deck = json_module.loads(row["deck_cards_json"])
        self.assertEqual(sum(int(c.get("quantity", 1)) for c in saved_deck), 40)
        self.assertGreater(row["average_cost"], 0)

    def test_hybrid_search_without_meta_decks(self) -> None:
        import sqlite3 as sq

        empty_db = Path(self._tmpdir.name) / "empty2.db"
        with sq.connect(empty_db) as conn:
            conn.execute("CREATE TABLE cards (card_id TEXT, name TEXT, civilization TEXT, cost INTEGER, card_type TEXT, power TEXT, race TEXT, text TEXT)")
            conn.execute("CREATE TABLE card_tags (card_id TEXT, tag TEXT)")
            conn.execute("CREATE TABLE meta_deck_cards (id INTEGER PRIMARY KEY, deck_name TEXT, format TEXT, source_url TEXT, card_name TEXT, count INTEGER, raw_line TEXT, imported_at TEXT)")
            conn.execute("INSERT INTO cards VALUES ('C1','カード','火',1,'クリーチャー','1000','','')")
        from src.battle.hybrid_search import run_hybrid_search

        result = run_hybrid_search(db_path=empty_db, generations=1, population_size=2, seed=1)
        self.assertIsNone(result["best"])
        self.assertTrue(result["warnings"])



    def test_blend(self) -> None:
        base = {"candidate_score": 80.0}
        result = apply_sim_strength(base, sim_win_rate=0.5, weight=0.3)
        self.assertEqual(result["sim_strength_score"], 50.0)
        self.assertEqual(result["candidate_score_with_sim"], round(80 * 0.7 + 60 * 0.3, 1))
        self.assertEqual(base, {"candidate_score": 80.0})  # 元のdictは変更しない

    def test_weight_clamped(self) -> None:
        result = apply_sim_strength({"candidate_score": 100.0}, sim_win_rate=1.0, weight=2.0)
        self.assertEqual(result["sim_weight"], 1.0)
        self.assertEqual(result["candidate_score_with_sim"], 120.0)


if __name__ == "__main__":
    unittest.main()

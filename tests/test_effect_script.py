from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.battle.effects.draft_generator import generate_draft_effect_script
from src.battle.effects.schema import validate_effect_script
from src.battle.effects.store import (
    apply_curated_scripts,
    approve_clean_drafts,
    coverage_summary,
    generate_drafts_for_missing_cards,
    get_effect_script,
    load_approved_effects_map,
    upsert_effect_script,
)


class SchemaValidationTest(unittest.TestCase):
    def test_valid_script(self) -> None:
        script = {
            "card_id": "DMPC-0001",
            "abilities": [{"trigger": "on_cast", "actions": [{"op": "deck_top_to_mana", "count": 1}]}],
        }
        self.assertEqual(validate_effect_script(script), [])

    def test_vanilla_script_is_valid(self) -> None:
        self.assertEqual(validate_effect_script({"card_id": "X", "abilities": []}), [])

    def test_unknown_trigger_and_op(self) -> None:
        script = {
            "card_id": "X",
            "abilities": [{"trigger": "when_happy", "actions": [{"op": "win_game"}]}],
        }
        errors = validate_effect_script(script)
        self.assertEqual(len(errors), 2)

    def test_invalid_count_and_scope(self) -> None:
        script = {
            "card_id": "X",
            "abilities": [
                {"trigger": "on_play", "actions": [{"op": "draw", "count": 0}]},
                {"trigger": "on_play", "actions": [{"op": "destroy_creature", "scope": "everyone"}]},
            ],
        }
        errors = validate_effect_script(script)
        self.assertEqual(len(errors), 2)

    def test_unexpected_parameter(self) -> None:
        script = {
            "card_id": "X",
            "abilities": [{"trigger": "on_play", "actions": [{"op": "draw", "count": 1, "target": "self"}]}],
        }
        self.assertEqual(len(validate_effect_script(script)), 1)


class DraftGeneratorTest(unittest.TestCase):
    def test_mana_acceleration_spell(self) -> None:
        card = {
            "card_id": "DMPC-0001",
            "name": "マナ加速呪文",
            "card_type": "呪文",
            "text": "山札の上から1枚目をマナゾーンに置く。",
        }
        script = generate_draft_effect_script(card)
        self.assertEqual(validate_effect_script(script), [])
        self.assertEqual(script["abilities"][0]["trigger"], "on_cast")
        self.assertEqual(script["abilities"][0]["actions"], [{"op": "deck_top_to_mana", "count": 1}])

    def test_draw_creature_with_count(self) -> None:
        card = {
            "card_id": "DMPC-0002",
            "name": "ドロークリーチャー",
            "card_type": "クリーチャー",
            "text": "このクリーチャーが出た時、カードを2枚引く。",
        }
        script = generate_draft_effect_script(card)
        self.assertEqual(script["abilities"][0]["trigger"], "on_play")
        self.assertEqual(script["abilities"][0]["actions"], [{"op": "draw", "count": 2}])

    def test_trigger_clause_not_misread_as_summon(self) -> None:
        # 「バトルゾーンに出た時」はトリガー句であり、マナ回収をsummon_from_manaと
        # 誤読してはいけない(ストーム・クロウラー事件の回帰テスト)
        card = {
            "card_id": "DMPC-0010",
            "name": "マナ回収獣",
            "card_type": "クリーチャー",
            "text": "バトルゾーンに出た時、自分のマナゾーンからカードを探索し、1枚を手札に戻す。",
        }
        script = generate_draft_effect_script(card)
        ops = {action["op"] for ability in script["abilities"] for action in ability["actions"]}
        self.assertNotIn("summon_from_mana", ops)
        self.assertIn("mana_to_hand", ops)

    def test_transitive_summon_from_mana_still_detected(self) -> None:
        card = {
            "card_id": "DMPC-0011",
            "name": "マナ展開獣",
            "card_type": "クリーチャー",
            "text": "バトルゾーンに出た時、自分のマナゾーンからコスト3以下のクリーチャーを1体バトルゾーンに出す。",
        }
        script = generate_draft_effect_script(card)
        ops = {action["op"] for ability in script["abilities"] for action in ability["actions"]}
        self.assertIn("summon_from_mana", ops)

    def test_removal_with_power_limit_and_s_trigger(self) -> None:
        card = {
            "card_id": "DMPC-0003",
            "name": "除去呪文",
            "card_type": "呪文",
            "text": "S・トリガー\n相手のパワー3000以下のクリーチャーを1体破壊する。",
        }
        script = generate_draft_effect_script(card)
        self.assertEqual(validate_effect_script(script), [])
        triggers = [ability["trigger"] for ability in script["abilities"]]
        self.assertIn("on_cast", triggers)
        self.assertIn("s_trigger", triggers)
        action = script["abilities"][0]["actions"][0]
        self.assertEqual(action["op"], "destroy_creature")
        self.assertEqual(action["max_power"], 3000)

    def test_vanilla_card(self) -> None:
        card = {"card_id": "DMPC-0004", "name": "バニラ", "card_type": "クリーチャー", "text": ""}
        script = generate_draft_effect_script(card)
        self.assertEqual(script["abilities"], [])
        self.assertTrue(script["notes"])


class StoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "cards.db"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE cards (card_id TEXT PRIMARY KEY, name TEXT, civilization TEXT,"
                " cost INTEGER, card_type TEXT, power TEXT, race TEXT, text TEXT)"
            )
            conn.execute(
                "INSERT INTO cards VALUES ('C1', 'マナ加速', '自然', 2, '呪文', '', '',"
                " '山札の上から1枚目をマナゾーンに置く。')"
            )
            conn.execute("INSERT INTO cards VALUES ('C2', 'バニラ', '火', 1, 'クリーチャー', '1000', '', '')")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_upsert_and_get_roundtrip(self) -> None:
        script = {
            "card_id": "C1",
            "name": "マナ加速",
            "abilities": [{"trigger": "on_cast", "actions": [{"op": "deck_top_to_mana", "count": 1}]}],
        }
        self.assertEqual(upsert_effect_script(script, db_path=self.db_path), [])
        loaded = get_effect_script("C1", db_path=self.db_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["abilities"], script["abilities"])
        self.assertEqual(loaded["review_status"], "draft")

    def test_invalid_script_not_saved(self) -> None:
        errors = upsert_effect_script({"card_id": "C1", "abilities": [{"trigger": "bad", "actions": []}]}, db_path=self.db_path)
        self.assertTrue(errors)
        self.assertIsNone(get_effect_script("C1", db_path=self.db_path))

    def test_approved_only_filter(self) -> None:
        script = {"card_id": "C1", "abilities": []}
        upsert_effect_script(script, db_path=self.db_path)
        self.assertIsNone(get_effect_script("C1", db_path=self.db_path, approved_only=True))
        upsert_effect_script(script, review_status="approved", db_path=self.db_path)
        self.assertIsNotNone(get_effect_script("C1", db_path=self.db_path, approved_only=True))

    def test_approve_clean_drafts(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO cards VALUES ('C3', '部分変換', '水', 3, '呪文', '', '',"
                " 'カードを1枚引く。その後、複雑な効果を解決する。')"
            )
        generate_drafts_for_missing_cards(db_path=self.db_path)
        approved = approve_clean_drafts(db_path=self.db_path)
        # C1(完全変換)とC2(バニラ)は承認、C3(部分変換の警告付き)はdraftのまま
        self.assertEqual(approved, 2)
        effects_map = load_approved_effects_map(db_path=self.db_path)
        self.assertIn("C1", effects_map)
        self.assertNotIn("C3", effects_map)
        self.assertIsNone(get_effect_script("C3", db_path=self.db_path, approved_only=True))
        # 再実行しても追加承認なし
        self.assertEqual(approve_clean_drafts(db_path=self.db_path), 0)

    def test_apply_curated_scripts(self) -> None:
        import json as json_module

        curated_dir = Path(self._tmpdir.name) / "effect_scripts"
        curated_dir.mkdir()
        (curated_dir / "test.json").write_text(
            json_module.dumps(
                [
                    {
                        "name": "マナ加速",
                        "abilities": [{"trigger": "on_cast", "actions": [{"op": "draw", "count": 1}]}],
                        "note": "テスト用近似",
                    },
                    {"name": "存在しない名前", "abilities": []},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        applied, missing = apply_curated_scripts(curated_dir, db_path=self.db_path)
        self.assertEqual(applied, 1)
        self.assertEqual(missing, ["存在しない名前"])
        # キュレーションは承認済みとして適用され、再生成でも上書きされない
        script = get_effect_script("C1", db_path=self.db_path, approved_only=True)
        self.assertIsNotNone(script)
        self.assertEqual(script["abilities"][0]["actions"][0]["op"], "draw")
        self.assertEqual(generate_drafts_for_missing_cards(db_path=self.db_path), 1)  # C2のみ
        script_after = get_effect_script("C1", db_path=self.db_path, approved_only=True)
        self.assertEqual(script_after["abilities"], script["abilities"])

    def test_generate_drafts_and_coverage(self) -> None:
        created = generate_drafts_for_missing_cards(db_path=self.db_path)
        self.assertEqual(created, 2)
        # 2回目は既存登録をスキップする
        self.assertEqual(generate_drafts_for_missing_cards(db_path=self.db_path), 0)
        summary = coverage_summary(db_path=self.db_path)
        self.assertEqual(summary["total_cards"], 2)
        self.assertEqual(summary["registered"], 2)
        self.assertEqual(summary["registered_rate"], 1.0)
        self.assertEqual(summary["approved_rate"], 0.0)
        draft = get_effect_script("C1", db_path=self.db_path)
        self.assertEqual(draft["abilities"][0]["actions"][0]["op"], "deck_top_to_mana")


if __name__ == "__main__":
    unittest.main()

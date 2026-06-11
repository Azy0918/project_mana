from __future__ import annotations

import sqlite3
import unittest

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.engine import DuelEngine
from src.battle.kernel.policy import AttackChoice, Policy
from src.battle.kernel.state import CreatureInstance, make_mana_card
from src.battle.effects.draft_generator import generate_draft_effect_script
from src.battle.effects.schema import validate_effect_script


def make_card(
    name: str,
    cost: int = 2,
    civilization: str = "火",
    card_type: str = "クリーチャー",
    power: int = 1000,
    text: str = "",
) -> BattleCard:
    return BattleCard(
        card_id=name,
        name=name,
        civilizations=tuple(civilization.split("/")),
        cost=cost,
        card_type=card_type,
        power=power,
        text=text,
    )


def make_deck(size: int = 40, civilization: str = "火") -> list[BattleCard]:
    return [
        make_card(f"{civilization}{i:02d}", cost=(i % 6) + 1, civilization=civilization, power=((i % 6) + 1) * 1000)
        for i in range(size)
    ]


class StubPolicy(Policy):
    def choose_charge(self, state, player):
        return None

    def choose_main_action(self, state, player, playable):
        return None

    def choose_attack(self, state, player, choices):
        return None

    def choose_blocker(self, state, player, attack, blockers):
        return 0


def make_engine(effects: dict | None = None, policy_b: Policy | None = None) -> DuelEngine:
    return DuelEngine(make_deck(), make_deck(), StubPolicy(), policy_b or StubPolicy(), effects=effects)


class FidelityTest(unittest.TestCase):
    def test_multicolor_card_enters_mana_tapped(self) -> None:
        multicolor = make_card("多色", civilization="火/自然")
        self.assertTrue(make_mana_card(multicolor).tapped)
        single = make_card("単色")
        self.assertFalse(make_mana_card(single).tapped)

    def test_cannot_attack_excluded_from_legal_attacks(self) -> None:
        engine = make_engine()
        state = engine.state
        state.turn = 5
        state.players[0].battle_zone.append(
            CreatureInstance(card=make_card("守り专", text="ブロッカー このクリーチャーは攻撃できない。"), summoned_turn=1)
        )
        self.assertEqual(engine._legal_attacks(state.players[0]), [])

    def test_cannot_attack_player_allows_creature_attacks_only(self) -> None:
        engine = make_engine()
        state = engine.state
        state.turn = 5
        state.players[0].battle_zone.append(
            CreatureInstance(card=make_card("間接攻撃", text="このクリーチャーは相手プレイヤーを攻撃できない。"), summoned_turn=1)
        )
        state.players[1].battle_zone.append(CreatureInstance(card=make_card("寝た敵"), tapped=True, summoned_turn=1))
        choices = engine._legal_attacks(state.players[0])
        self.assertEqual(len(choices), 1)
        self.assertIsNotNone(choices[0].target_creature_index)

    def test_unblockable_skips_blockers(self) -> None:
        engine = make_engine(policy_b=StubPolicy())  # StubPolicyは必ずブロックする
        state = engine.state
        attacker = CreatureInstance(
            card=make_card("すり抜け", power=1000, text="このクリーチャーはブロックされない。"), summoned_turn=0
        )
        state.players[0].battle_zone.append(attacker)
        opponent = state.players[1]
        opponent.battle_zone.append(
            CreatureInstance(card=make_card("巨大ブロッカー", power=9000, text="ブロッカー"), summoned_turn=0)
        )
        shields_before = len(opponent.shields)
        engine._resolve_attack(state.players[0], AttackChoice(attacker_index=0, target_creature_index=None))
        self.assertEqual(len(opponent.shields), shields_before - 1)
        self.assertIn(attacker, state.players[0].battle_zone)


class NewOpsTest(unittest.TestCase):
    def test_add_shield(self) -> None:
        effects = {"要塞": [{"trigger": "on_cast", "actions": [{"op": "add_shield", "count": 2}]}]}
        engine = make_engine(effects)
        player = engine.state.players[0]
        shields_before = len(player.shields)
        deck_before = len(player.deck)
        engine.executor.run(engine, 0, "on_cast", make_card("要塞", card_type="呪文"))
        self.assertEqual(len(player.shields), shields_before + 2)
        self.assertEqual(len(player.deck), deck_before - 2)

    def test_discard_opponent_hand(self) -> None:
        effects = {"ハンデス": [{"trigger": "on_cast", "actions": [{"op": "discard_opponent_hand", "count": 2}]}]}
        engine = make_engine(effects)
        opponent = engine.state.players[1]
        hand_before = len(opponent.hand)
        grave_before = len(opponent.graveyard)
        engine.executor.run(engine, 0, "on_cast", make_card("ハンデス", card_type="呪文"))
        self.assertEqual(len(opponent.hand), hand_before - 2)
        self.assertEqual(len(opponent.graveyard), grave_before + 2)

    def test_deck_top_to_grave_and_recover(self) -> None:
        effects = {
            "墓地肥やし": [{"trigger": "on_cast", "actions": [{"op": "deck_top_to_grave", "count": 3}]}],
            "回収": [{"trigger": "on_cast", "actions": [{"op": "grave_to_hand", "count": 1}]}],
        }
        engine = make_engine(effects)
        player = engine.state.players[0]
        engine.executor.run(engine, 0, "on_cast", make_card("墓地肥やし", card_type="呪文"))
        self.assertEqual(len(player.graveyard), 3)
        highest = max(player.graveyard, key=lambda card: card.cost)
        hand_before = len(player.hand)
        engine.executor.run(engine, 0, "on_cast", make_card("回収", card_type="呪文"))
        self.assertIn(highest, player.hand)
        self.assertEqual(len(player.hand), hand_before + 1)

    def test_summon_from_hand_respects_max_cost_and_triggers_on_play(self) -> None:
        effects = {
            "踏み倒し": [
                {"trigger": "on_cast", "actions": [{"op": "summon_from_hand", "count": 1, "max_cost": 4}]}
            ],
            "出た時ドロー": [{"trigger": "on_play", "actions": [{"op": "draw", "count": 1}]}],
        }
        engine = make_engine(effects)
        player = engine.state.players[0]
        cheap = make_card("出た時ドロー", cost=4, power=4000)
        heavy = make_card("重量級", cost=9, power=9000)
        player.hand = [cheap, heavy]
        deck_before = len(player.deck)
        engine.executor.run(engine, 0, "on_cast", make_card("踏み倒し", card_type="呪文"))
        # コスト4以下のみ踏み倒され、出た時効果(ドロー)も連鎖する
        self.assertTrue(any(creature.card.name == "出た時ドロー" for creature in player.battle_zone))
        self.assertIn(heavy, player.hand)
        self.assertEqual(len(player.deck), deck_before - 1)

    def test_send_creature_to_mana(self) -> None:
        effects = {"マナ送り": [{"trigger": "on_cast", "actions": [{"op": "send_creature_to_mana", "count": 1, "scope": "opponent"}]}]}
        engine = make_engine(effects)
        opponent = engine.state.players[1]
        creature = CreatureInstance(card=make_card("大型", power=9000), summoned_turn=0)
        opponent.battle_zone.append(creature)
        mana_before = len(opponent.mana_zone)
        engine.executor.run(engine, 0, "on_cast", make_card("マナ送り", card_type="呪文"))
        self.assertNotIn(creature, opponent.battle_zone)
        self.assertEqual(len(opponent.mana_zone), mana_before + 1)

    def test_summon_from_mana(self) -> None:
        effects = {"マナ展開": [{"trigger": "on_cast", "actions": [{"op": "summon_from_mana", "count": 1, "max_cost": 6}]}]}
        engine = make_engine(effects)
        player = engine.state.players[0]
        cheap = make_card("出せる獣", cost=6, power=6000)
        heavy = make_card("出せない獣", cost=8, power=8000)
        player.mana_zone.extend([make_mana_card(cheap), make_mana_card(heavy)])
        mana_before = len(player.mana_zone)
        engine.executor.run(engine, 0, "on_cast", make_card("マナ展開", card_type="呪文"))
        self.assertTrue(any(creature.card.name == "出せる獣" for creature in player.battle_zone))
        self.assertFalse(any(creature.card.name == "出せない獣" for creature in player.battle_zone))
        self.assertEqual(len(player.mana_zone), mana_before - 1)

    def test_burn_opponent_shield_skips_trigger(self) -> None:
        effects = {
            "焼却": [{"trigger": "on_play", "actions": [{"op": "burn_opponent_shield", "count": 1}]}],
            "トリガー獣": [{"trigger": "s_trigger", "actions": [{"op": "draw", "count": 1}]}],
        }
        engine = make_engine(effects)
        opponent = engine.state.players[1]
        opponent.shields = [make_card("トリガー獣")]
        hand_before = len(opponent.hand)
        engine.executor.run(engine, 0, "on_play", make_card("焼却"))
        # シールドは墓地へ。手札にもバトルゾーンにも行かず、S・トリガーも発動しない
        self.assertEqual(len(opponent.shields), 0)
        self.assertEqual(len(opponent.hand), hand_before)
        self.assertTrue(any(card.name == "トリガー獣" for card in opponent.graveyard))
        self.assertFalse(opponent.battle_zone)

    def test_policy_chooses_effect_target(self) -> None:
        # 方策が最弱対象を指定すれば、既定の最大パワー優先を上書きできる
        class WeakestTarget(StubPolicy):
            def choose_effect_target(self, state, player, op, candidates):
                return min(range(len(candidates)), key=lambda i: candidates[i].card.power)

        effects = {"除去": [{"trigger": "on_cast", "actions": [{"op": "destroy_creature", "count": 1, "scope": "opponent"}]}]}
        engine = DuelEngine(make_deck(), make_deck(), WeakestTarget(), StubPolicy(), effects=effects)
        opponent = engine.state.players[1]
        weak = CreatureInstance(card=make_card("弱い", power=1000), summoned_turn=0)
        strong = CreatureInstance(card=make_card("強い", power=9000), summoned_turn=0)
        opponent.battle_zone.extend([weak, strong])
        engine.executor.run(engine, 0, "on_cast", make_card("除去", card_type="呪文"))
        self.assertNotIn(weak, opponent.battle_zone)
        self.assertIn(strong, opponent.battle_zone)

    def test_zero_cost_twinpact_gets_estimated_cost(self) -> None:
        from src.battle.kernel.cards import battle_card_from_dict

        card = battle_card_from_dict(
            {"card_id": "T0", "name": "罠", "civilization": "自然", "cost": 0, "card_type": "ツインパクト", "power": "7000"}
        )
        self.assertEqual(card.cost, 7)
        spell_side = battle_card_from_dict(
            {"card_id": "T1", "name": "罠2", "civilization": "自然", "cost": 0, "card_type": "ツインパクト", "power": ""}
        )
        self.assertEqual(spell_side.cost, 2)

    def test_twinpact_with_power_is_creature(self) -> None:
        twinpact = make_card("両面", card_type="ツインパクト", power=4000)
        self.assertTrue(twinpact.is_creature)
        spell_side_only = make_card("呪文寄り", card_type="ツインパクト", power=0)
        self.assertFalse(spell_side_only.is_creature)

    def test_discard_own_and_shield_to_hand_and_hand_to_mana(self) -> None:
        effects = {
            "代償": [{"trigger": "on_cast", "actions": [{"op": "discard_own_hand", "count": 1}]}],
            "回収": [{"trigger": "on_cast", "actions": [{"op": "own_shield_to_hand", "count": 1}]}],
            "埋め": [{"trigger": "on_cast", "actions": [{"op": "hand_to_mana", "count": 1}]}],
        }
        engine = make_engine(effects)
        player = engine.state.players[0]
        hand_before = len(player.hand)
        engine.executor.run(engine, 0, "on_cast", make_card("代償", card_type="呪文"))
        self.assertEqual(len(player.hand), hand_before - 1)

        shields_before = len(player.shields)
        engine.executor.run(engine, 0, "on_cast", make_card("回収", card_type="呪文"))
        self.assertEqual(len(player.shields), shields_before - 1)

        mana_before = len(player.mana_zone)
        engine.executor.run(engine, 0, "on_cast", make_card("埋め", card_type="呪文"))
        self.assertEqual(len(player.mana_zone), mana_before + 1)

    def test_untap_creature_self(self) -> None:
        effects = {"再起": [{"trigger": "on_cast", "actions": [{"op": "untap_creature", "count": 1, "scope": "self"}]}]}
        engine = make_engine(effects)
        player = engine.state.players[0]
        creature = CreatureInstance(card=make_card("疲れた獣"), tapped=True, summoned_turn=0)
        player.battle_zone.append(creature)
        engine.executor.run(engine, 0, "on_cast", make_card("再起", card_type="呪文"))
        self.assertFalse(creature.tapped)


class NewDraftPatternsTest(unittest.TestCase):
    def _draft(self, text: str, card_type: str = "呪文") -> dict:
        script = generate_draft_effect_script(
            {"card_id": "T1", "name": "テスト", "card_type": card_type, "text": text}
        )
        self.assertEqual(validate_effect_script(script), [])
        return script

    def _ops(self, script: dict) -> list[str]:
        return [action["op"] for ability in script["abilities"] for action in ability["actions"]]

    def test_add_shield_pattern(self) -> None:
        script = self._draft("山札の上から1枚目を裏向きのままシールドゾーンに置く。")
        self.assertIn("add_shield", self._ops(script))

    def test_discard_pattern(self) -> None:
        script = self._draft("相手の手札を1枚見ないで選び、捨てさせる。")
        self.assertIn("discard_opponent_hand", self._ops(script))

    def test_mill_pattern(self) -> None:
        script = self._draft("自分の山札の上から3枚を墓地に置く。")
        ops = self._ops(script)
        self.assertIn("deck_top_to_grave", ops)
        action = script["abilities"][0]["actions"][0]
        self.assertEqual(action["count"], 3)

    def test_recover_pattern(self) -> None:
        script = self._draft("自分の墓地からクリーチャーを1体選び、手札に戻す。")
        self.assertIn("grave_to_hand", self._ops(script))

    def test_cheat_summon_pattern(self) -> None:
        script = self._draft("コスト4以下のクリーチャーを1体、手札からコストを支払わずに出す。")
        ops = self._ops(script)
        self.assertIn("summon_from_hand", ops)
        action = next(
            action
            for ability in script["abilities"]
            for action in ability["actions"]
            if action["op"] == "summon_from_hand"
        )
        self.assertEqual(action["max_cost"], 4)

    def test_keyword_only_text_is_fully_converted(self) -> None:
        # カーネルが直接処理するキーワード行のみのカードは「変換済み」扱い(notesなし)
        script = generate_draft_effect_script(
            {
                "card_id": "K1",
                "name": "キーワード持ち",
                "card_type": "クリーチャー",
                "text": "◇S・トリガー\n◇ブロッカー\n■W・ブレイカー(このクリーチャーはシールドを2枚ブレイクする)",
            }
        )
        self.assertEqual(script["notes"], [])
        self.assertEqual(script["abilities"], [])

    def test_real_card_text_fully_converts(self) -> None:
        # 実在カード相当: キーワード行 + 全体タップ効果
        script = generate_draft_effect_script(
            {
                "card_id": "R1",
                "name": "閃光の守護者ホーリー",
                "card_type": "クリーチャー",
                "text": "◇S・トリガー\n◇ブロッカー\n■バトルゾーンに出た時、相手のクリーチャーをすべてタップする。",
            }
        )
        self.assertEqual(validate_effect_script(script), [])
        self.assertEqual(script["notes"], [])
        triggers = [ability["trigger"] for ability in script["abilities"]]
        self.assertIn("on_play", triggers)
        self.assertIn("s_trigger", triggers)
        action = script["abilities"][0]["actions"][0]
        self.assertEqual(action["op"], "tap_creature")
        self.assertEqual(action["count"], 99)

    def test_reminder_text_stripped(self) -> None:
        script = generate_draft_effect_script(
            {
                "card_id": "R2",
                "name": "注釈持ち",
                "card_type": "呪文",
                "text": "カードを1枚引く。(引けない場合は何もしない)",
            }
        )
        self.assertEqual(script["notes"], [])
        self.assertEqual(self._ops(script), ["draw"])

    def test_mana_send_removal_not_confused_with_ramp(self) -> None:
        # 「相手のクリーチャーをマナゾーンに置く」は除去であり、自分のマナ加速に誤変換しない
        script = self._draft("相手のクリーチャー1体をマナゾーンに置く。")
        ops = self._ops(script)
        self.assertIn("send_creature_to_mana", ops)
        self.assertNotIn("deck_top_to_mana", ops)

    def test_summon_from_mana_pattern(self) -> None:
        script = self._draft("自分のマナゾーンからコスト6以下のクリーチャー1枚をバトルゾーンに出す。")
        ops = self._ops(script)
        self.assertIn("summon_from_mana", ops)
        action = next(
            action
            for ability in script["abilities"]
            for action in ability["actions"]
            if action["op"] == "summon_from_mana"
        )
        self.assertEqual(action["max_cost"], 6)

    def test_mach_fighter_attacks_creature_on_summon_turn(self) -> None:
        creature = CreatureInstance(card=make_card("マッハ獣", text="マッハファイター"), summoned_turn=3)
        self.assertFalse(creature.can_attack(3))
        self.assertTrue(creature.can_attack_creature(3))
        engine = make_engine()
        state = engine.state
        state.turn = 3
        state.players[0].battle_zone.append(creature)
        state.players[1].battle_zone.append(CreatureInstance(card=make_card("寝た敵"), tapped=True, summoned_turn=1))
        choices = engine._legal_attacks(state.players[0])
        # プレイヤー攻撃は不可、クリーチャー攻撃のみ可能
        self.assertEqual(len(choices), 1)
        self.assertIsNotNone(choices[0].target_creature_index)

    def test_look_and_mill_pattern(self) -> None:
        script = self._draft(
            "バトルゾーンに出た時、自分の山札の上から2枚を見る。その中から1枚墓地に置き、残りを山札の一番上に置く。",
            card_type="クリーチャー",
        )
        self.assertEqual(script["notes"], [])
        self.assertIn("deck_top_to_grave", self._ops(script))

    def test_evolution_hyphen_and_invasion_covered(self) -> None:
        script = self._draft("■進化-自然のクリーチャー\n■侵略:光のクリーチャー\n■W・ブレイカー", card_type="進化クリーチャー")
        self.assertEqual(script["notes"], [])

    def test_mana_to_hand_pattern(self) -> None:
        script = self._draft("自分のマナゾーンからクリーチャーを探索し、2枚を手札に戻す。")
        self.assertIn("mana_to_hand", self._ops(script))

    def test_power_down_approximated_as_capped_destroy(self) -> None:
        script = self._draft("バトルゾーンに出た時、そのターン、相手のクリーチャー1体のパワーを-3000する。", card_type="クリーチャー")
        action = script["abilities"][0]["actions"][0]
        self.assertEqual(action["op"], "destroy_creature")
        self.assertEqual(action["max_power"], 3000)

    def test_self_sacrifice_converted(self) -> None:
        script = self._draft("バトルゾーンに出た時、自分のクリーチャー1体を破壊する。", card_type="クリーチャー")
        action = script["abilities"][0]["actions"][0]
        self.assertEqual(action["op"], "destroy_creature")
        self.assertEqual(action["scope"], "self")

    def test_search_to_hand_approximated_as_draw(self) -> None:
        script = self._draft(
            "自分の山札の上から3枚を見る。その中から呪文1枚を公開してから手札に加えてもよい。"
            "残りをランダムな順番で山札の一番下に置く。"
        )
        self.assertEqual(script["notes"], [])
        self.assertEqual(self._ops(script), ["draw"])

    def test_noop_riders_count_as_converted(self) -> None:
        script = self._draft("山札の上から1枚目をマナゾーンに置く。その後、山札をシャッフルする。")
        self.assertEqual(script["notes"], [])
        self.assertEqual(self._ops(script), ["deck_top_to_mana"])

    def test_keyword_lines_charger_slayer_powered(self) -> None:
        script = generate_draft_effect_script(
            {
                "card_id": "K2",
                "name": "キーワード盛り",
                "card_type": "クリーチャー",
                "text": "◇スレイヤー\n■パワード・ブレイカー\n■進化:火のクリーチャー",
            }
        )
        self.assertEqual(script["notes"], [])

    def test_untap_pattern_excludes_opponent(self) -> None:
        script = self._draft("このクリーチャーをアンタップする。", card_type="クリーチャー")
        self.assertIn("untap_creature", self._ops(script))
        opponent_tap = self._draft("相手のクリーチャーを1体タップする。")
        self.assertIn("tap_creature", self._ops(opponent_tap))
        self.assertNotIn("untap_creature", self._ops(opponent_tap))


if __name__ == "__main__":
    unittest.main()

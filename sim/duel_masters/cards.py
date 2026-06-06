"""
duel_masters.cards
==================
カードプール。各カードは「定義(CardDef) + 能力(Ability)」で表現する。
新カードを足すときは、効果関数を書いて CardDef に Ability として渡すだけ。

ここでは初期デュエマの代表的カードを10枚モデル化(全5文明をカバー):
 - バニラ / ETBドロー / ETBマナ加速 / 加速呪文 / 除去呪文(ST) /
   全タップ呪文(ST) / スピードアタッカー / ブロッカー / 小型除去(ST)
"""

from __future__ import annotations
from .engine import (
    CardDef, Ability, Card,
    LIGHT, WATER, DARKNESS, FIRE, NATURE,
    CREATURE, SPELL,
    ON_SUMMON, CAST,
)


# ---- 効果関数 --------------------------------------------------------------

def eff_draw(n):
    def f(game, controller, source):
        game.log(f"    効果: {controller} が{n}枚ドロー")
        game.draw(controller, n)
    return Ability(ON_SUMMON, f, desc=f"出たとき{n}ドロー")


def eff_ramp_on_summon(n):
    def f(game, controller, source):
        game.mana_from_deck(controller, n)
    return Ability(ON_SUMMON, f, desc=f"出たときマナ加速{n}")


def eff_ramp_spell(n):
    def f(game, controller, source):
        game.mana_from_deck(controller, n)
    return Ability(CAST, f, desc=f"マナ加速{n}")


def eff_destroy_one():
    """相手クリーチャー1体を破壊(パワー最大を狙うのは agent 側)。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        if not opp.battle:
            game.log("    効果: 対象なし")
            return
        t = controller.agent.choose_card(game, "破壊するクリーチャー", opp.battle)
        if t is not None:
            game.log(f"    効果: {t} を破壊")
            game.destroy(t)
    return Ability(CAST, f, desc="相手クリーチャー1体破壊")


def eff_destroy_power_le(maxpow):
    def f(game, controller, source):
        opp = game.opponent(controller)
        cands = [c for c in opp.battle if c.power is not None and c.power <= maxpow]
        if not cands:
            game.log("    効果: 対象なし")
            return
        t = controller.agent.choose_card(
            game, f"破壊(パワー{maxpow}以下)", cands)
        if t is not None:
            game.log(f"    効果: {t} を破壊")
            game.destroy(t)
    return Ability(CAST, f, desc=f"パワー{maxpow}以下を1体破壊")


def eff_tap_all_enemy():
    def f(game, controller, source):
        opp = game.opponent(controller)
        for c in opp.battle:
            c.tapped = True
        game.log(f"    効果: {opp} のクリーチャーを全てタップ")
    return Ability(CAST, f, desc="相手クリーチャーを全タップ")


# ---- カード定義 ------------------------------------------------------------

POOL = {
    "aqua_hulcus": CardDef(
        "aqua_hulcus", "アクア・ハルカス", 3, frozenset({WATER}), CREATURE,
        power=2000, races=("リキッド・ピープル",),
        abilities=(eff_draw(1),)),

    "bronze_arm": CardDef(
        "bronze_arm", "青銅の鎧", 3, frozenset({NATURE}), CREATURE,
        power=1000, races=("ビーストフォーク",),
        abilities=(eff_ramp_on_summon(1),)),

    "faerie_life": CardDef(
        "faerie_life", "フェアリー・ライフ", 3, frozenset({NATURE}), SPELL,
        keywords=frozenset({"shield_trigger"}),
        abilities=(eff_ramp_spell(1),)),

    "demon_hand": CardDef(
        "demon_hand", "デーモン・ハンド", 5, frozenset({DARKNESS}), SPELL,
        keywords=frozenset({"shield_trigger"}),
        abilities=(eff_destroy_one(),)),

    "holy_awe": CardDef(
        "holy_awe", "ホーリー・スパーク", 6, frozenset({LIGHT}), SPELL,
        keywords=frozenset({"shield_trigger"}),
        abilities=(eff_tap_all_enemy(),)),

    "crimson_hammer": CardDef(
        "crimson_hammer", "クリムゾン・ハンマー", 2, frozenset({FIRE}), SPELL,
        keywords=frozenset({"shield_trigger"}),
        abilities=(eff_destroy_power_le(2000),)),

    "blaze_claw": CardDef(
        "blaze_claw", "凶戦士ブレイズ・クロー", 1, frozenset({FIRE}), CREATURE,
        power=1000, races=("ヒューマノイド",),
        keywords=frozenset({"speed_attacker"})),

    "aqua_guard": CardDef(
        "aqua_guard", "アクア・ガード", 1, frozenset({WATER}), CREATURE,
        power=1000, races=("リキッド・ピープル",),
        keywords=frozenset({"blocker"})),

    "bolshack": CardDef(
        "bolshack", "ボルシャック・ドラゴン", 6, frozenset({FIRE}), CREATURE,
        power=6000, races=("アーマード・ドラゴン",)),  # MVPはバニラ扱い

    "gaia": CardDef(
        "gaia", "大勇者「鎧亜の剣」", 5, frozenset({NATURE}), CREATURE,
        power=5000, races=("ジャイアント",)),       # バニラの中型
}


def make(cid: str, owner) -> Card:
    return Card(POOL[cid], owner)


def sample_decklist():
    """各カード4枚=40枚の汎用デッキ(MVP検証用)。"""
    return [cid for cid in POOL for _ in range(4)]   # 10種 × 4 = 40


def build_deck(owner, decklist=None):
    decklist = decklist or sample_decklist()
    return [make(cid, owner) for cid in decklist]

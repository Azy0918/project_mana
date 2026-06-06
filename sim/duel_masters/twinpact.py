"""
duel_masters.twinpact
=====================
ツインパクト(クリーチャー／呪文の二面カード)の**呪文面**を CardDef に差す層。

背景: DB はツインパクトを1行(クリーチャー面のコスト/パワー)で持ち、呪文面のコスト
が無い。本文は【LINE】で2面に分かれるが効果のみ。よって呪文面のコスト/効果は
kamigame デュエプレで確認して手登録する(覚醒後フォームと同じ運用)。

engine 側はクリーチャー面で召喚も、呪文面(CardDef.twin_spell)で詠唱も可能。
S・トリガーが呪文面にあるトラップは、シールドから呪文として撃てる。
"""
from __future__ import annotations
import dataclasses

from .engine import (CardDef, Ability, SPELL, CAST,
                     DARKNESS, WATER, FIRE, NATURE, LIGHT)


# ---- 呪文面の効果ファクトリ -------------------------------------------------

def _to_mana(game, card):
    ctrl = card.controller
    if card in ctrl.battle:
        ctrl.battle.remove(card)
    elif card in ctrl.shields:
        ctrl.shields.remove(card)
    card.zone = "mana"
    card.tapped = False
    card.controller = card.owner
    card.owner.mana.append(card)


def cast_destroy_one() -> Ability:
    """デーモン・ハンド: 相手のクリーチャー1体を破壊。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        cands = [c for c in opp.battle
                 if not game.is_restricted(controller, "untargetable", c)]
        if cands:
            t = controller.agent.choose_card(game, "破壊", cands)
            if t is not None:
                game.destroy(t)
    return Ability(CAST, f, "相手クリーチャー1体を破壊")


def cast_mana_send_and_cheat(maxcheat: int) -> Ability:
    """マクスカルゴ・トラップ: 相手1体をマナ送り→自分のマナからコスト以下を踏み倒し。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        if opp.battle:
            t = max(opp.battle, key=lambda c: c.power or 0)
            game.log(f"    効果: {t} をマナゾーンへ")
            _to_mana(game, t)
        cheat = [c for c in controller.mana
                 if c.ctype == "creature" and c.cost <= maxcheat]
        if cheat:
            pick = max(cheat, key=lambda c: c.power or 0)
            controller.mana.remove(pick)
            game._enter_battle(controller, pick, free=True)
            game.log(f"    効果: マナから {pick} を踏み倒し")
    return Ability(CAST, f, f"相手1体をマナ送り+マナからコスト{maxcheat}以下を踏み倒し")


def cast_mana_send_creature() -> Ability:
    """ナチュラル・トラップ: 相手のクリーチャー1体をマナゾーンに置く。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        if opp.battle:
            t = max(opp.battle, key=lambda c: c.power or 0)
            game.log(f"    効果: {t} をマナゾーンへ")
            _to_mana(game, t)
    return Ability(CAST, f, "相手クリーチャー1体をマナ送り")


def cast_draw(n: int) -> Ability:
    def f(game, controller, source):
        game.draw(controller, n)
    return Ability(CAST, f, f"カードを{n}枚引く")


def cast_ramp(twin_bonus: bool = False) -> Ability:
    """レッツ・ゴイチゴ/魂フエミドロ: 山札の上をマナへ(ツインパクトならもう1枚)。G・ゼロの燃料。"""
    def f(game, controller, source):
        if controller.deck:
            c = controller.deck.pop(0)
            c.zone = "mana"
            c.tapped = False
            controller.mana.append(c)
            if twin_bonus and "/" in c.name and controller.deck:
                c2 = controller.deck.pop(0)
                c2.zone = "mana"
                c2.tapped = False
                controller.mana.append(c2)
    return Ability(CAST, f, "山札からマナ加速")


def cast_search_twinpact() -> Ability:
    """ツインパクト・マップ: 山札の上3枚からツインパクト1枚を手札に、残りを山札の下へ。"""
    def f(game, controller, source):
        top = controller.deck[:3]
        del controller.deck[:3]
        found = next((c for c in top if "/" in c.name), None)
        if found is not None:
            found.zone = "hand"
            controller.hand.append(found)
            top.remove(found)
        for c in top:
            c.zone = "deck"
            controller.deck.append(c)
    return Ability(CAST, f, "山札上3枚からツインパクト1枚回収")


def _discard_random(game, opp, n):
    for _ in range(n):
        if opp.hand:
            d = game.rng.choice(opp.hand)
            opp.hand.remove(d)
            d.zone = "graveyard"
            opp.graveyard.append(d)


def cast_discard_opp(n: int) -> Ability:
    """ジェニコの知らない世界等: 相手の手札をランダムに n 枚捨てさせる。"""
    def f(game, controller, source):
        _discard_random(game, game.opponent(controller), n)
    return Ability(CAST, f, f"相手の手札を{n}枚捨てさせる")


def cast_discard_and_destroy(nd: int, nk: int) -> Ability:
    """真血染める闇牙: 相手手札を nd 枚捨て→相手クリーチャー nk 体を破壊。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        _discard_random(game, opp, nd)
        for t in sorted(opp.battle, key=lambda c: -(c.power or 0))[:nk]:
            game.destroy(t)
    return Ability(CAST, f, f"相手手札{nd}枚捨て+{nk}体破壊")


def cast_destroy_total(maxtotal: int) -> Ability:
    """ダイナマウス・スクラッパー: パワーの合計が maxtotal 以下になるよう相手を破壊。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        chosen, total = [], 0
        for c in sorted(opp.battle, key=lambda c: (c.power or 0)):
            if total + (c.power or 0) <= maxtotal:
                chosen.append(c)
                total += c.power or 0
        for c in chosen:
            game.destroy(c)
    return Ability(CAST, f, f"パワー合計{maxtotal}以下になるよう破壊")


def cast_jokers_search() -> Ability:
    """一筆奏上！: 山札の上2枚から、ジョーカーズを手札に・残りをマナへ。"""
    def f(game, controller, source):
        top = controller.deck[:2]
        del controller.deck[:2]
        for c in top:
            if any("ジョーカーズ" in r for r in c.d.races):
                c.zone = "hand"
                controller.hand.append(c)
            else:
                c.zone = "mana"
                c.tapped = False
                controller.mana.append(c)
    return Ability(CAST, f, "山札上2枚:ジョーカーズ回収+残りマナ")


def cast_spell_lock_draw() -> Ability:
    """ジャミング・チャフ: 次の自分のターンまで相手は呪文を唱えられない+1ドロー。"""
    def f(game, controller, source):
        game.draw(controller, 1)
        game.opponent(controller).no_spell_until = game.turn_count + 2
        game.log("    効果: 相手の呪文を次の自ターンまでロック")
    return Ability(CAST, f, "相手の呪文ロック+1ドロー")


def cast_number_lock() -> Ability:
    """「本日のラッキーナンバー！」: 数字を1つ選び、次の自分のターン開始時まで、相手は
    その(印刷)コストのクリーチャーと呪文を実行できない。相手の手札+盤面で最頻のコストを潰す。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        counts = {}
        for c in opp.hand:
            counts[c.cost] = counts.get(c.cost, 0) + 1
        for c in opp.battle:
            counts[c.cost] = counts.get(c.cost, 0) + 1
        num = max(counts, key=counts.get) if counts else 5
        opp.locked_costs[num] = game.turn_count + 2   # 次の自分のターン開始まで
        game.log(f"    効果: 数字{num}ロック(相手はそのコストを実行不可)")
    return Ability(CAST, f, "数字ロック:指定コストのクリーチャー/呪文を実行不可")


def cast_doom_stick() -> Ability:
    """終葬 5.S.D.: 相手クリーチャー1体を山札の4枚目に刺し(引いたら敗北)、このカードを場に出す。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        if opp.battle:
            t = max(opp.battle, key=lambda c: c.power or 0)
            game.stick_into_deck(opp, t, pos=3, doom=True)
        # このツインパクト(Q.Q.QX.のクリーチャー面)をバトルゾーンに出す(墓地送りされない)。
        game._enter_battle(controller, source, free=True)
    return Ability(CAST, f, "相手1体を山札に刺す(引いたら敗北)+自身を場に")


def cast_creature_or_shield_to_mana() -> Ability:
    """地獄極楽トラップ黙示録: 相手のクリーチャー1体、または無ければシールド1つをマナ送り。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        if opp.battle:
            t = max(opp.battle, key=lambda c: c.power or 0)
            game.log(f"    効果: {t} をマナゾーンへ")
            _to_mana(game, t)
        elif opp.shields:
            s = game.rng.choice(opp.shields)
            game.log("    効果: 相手シールド1つをマナゾーンへ")
            _to_mana(game, s)
    return Ability(CAST, f, "相手1体orシールドをマナ送り")


# ---- 呪文面データ(kamigame デュエプレで確認) -------------------------------
# キーは DB のカード名(半角スラッシュ)。cost/civs/st/ability を持つ。
_CIV = {"闇": DARKNESS, "水": WATER, "火": FIRE, "自然": NATURE, "光": LIGHT}

TWIN_SPELLS = {
    "凶鬼悪号 デモンスパイン/デーモン・ハンド": dict(
        spell="デーモン・ハンド", cost=6, civs={DARKNESS}, st=True,
        ability=cast_destroy_one()),
    "龍罠 エスカルデン/マクスカルゴ・トラップ": dict(
        spell="マクスカルゴ・トラップ", cost=7, civs={NATURE}, st=False,
        ability=cast_mana_send_and_cheat(6)),
    "超機動罠 デンジャデオン/地獄極楽トラップ黙示録": dict(
        spell="地獄極楽トラップ黙示録", cost=6, civs={NATURE}, st=True,
        ability=cast_creature_or_shield_to_mana()),
    "ナ・チュラルゴ・デンジャー/ナチュラル・トラップ": dict(
        spell="ナチュラル・トラップ", cost=6, civs={NATURE}, st=True,
        ability=cast_mana_send_creature()),
    "龍装者 ヴィヌフィース/究めし優美のブレイン": dict(
        spell="究めし優美のブレイン", cost=3, civs={WATER}, st=True,
        ability=cast_draw(2)),
    # 以下3枚は kamigame に呪文面コスト記載が無く、明確に安いランプ/サーチのため推定。
    "イチゴッチ・タンク/レッツ・ゴイチゴ": dict(
        spell="レッツ・ゴイチゴ", cost=1, civs={NATURE}, st=False,   # コスト推定
        ability=cast_ramp()),
    "コンダマ/魂フエミドロ": dict(
        spell="魂フエミドロ", cost=1, civs={NATURE}, st=False,        # コスト推定
        ability=cast_ramp(twin_bonus=True)),
    "レレディ・バ・グーバ/ツインパクト・マップ": dict(
        spell="ツインパクト・マップ", cost=3, civs={WATER}, st=False,  # コスト推定
        ability=cast_search_twinpact()),
    # --- 第3弾(2026-06-05) ---
    "奇石 ミクセル/ジャミング・チャフ": dict(
        spell="ジャミング・チャフ", cost=5, civs={LIGHT}, st=False,
        ability=cast_spell_lock_draw()),
    "牙修羅バット/真血染める闇牙": dict(
        spell="真血染める闇牙", cost=8, civs={DARKNESS}, st=False,
        ability=cast_discard_and_destroy(2, 2)),
    "傀儡将ボルギーズ/ジェニコの知らない世界": dict(
        spell="ジェニコの知らない世界", cost=3, civs={DARKNESS}, st=False,  # コスト推定
        ability=cast_discard_opp(1)),
    "ゴリガン砕車 ゴルドーザ/ダイナマウス・スクラッパー": dict(
        spell="ダイナマウス・スクラッパー", cost=6, civs={FIRE}, st=False,  # コスト推定
        ability=cast_destroy_total(6000)),
    "ふでがき師匠/一筆奏上！": dict(
        spell="一筆奏上！", cost=2, civs={NATURE}, st=False,            # コスト推定
        ability=cast_jokers_search()),
    # --- 未実装解決(2026-06): 数字ロック / 特殊敗北 ---
    "機術士ディール/「本日のラッキーナンバー！」": dict(
        spell="「本日のラッキーナンバー！」", cost=4, civs={WATER}, st=False,  # コスト推定
        ability=cast_number_lock()),
    # 終葬 5.S.D.: 条件付きS・トリガー(マナにツインパクト5枚以上)は簡略し非ST。
    "Q.Q.QX./終葬 5.S.D.": dict(
        spell="終葬 5.S.D.", cost=5, civs={NATURE}, st=False,
        ability=cast_doom_stick()),
}


def attach_twin_spells(pool) -> list:
    """pool のツインパクトに呪文面(twin_spell)を差す。戻り値=差せた名前。"""
    attached = []
    index = {n.replace("／", "/"): n for n in pool}      # 全角→半角で索引
    for key, d in TWIN_SPELLS.items():
        real = key if key in pool else index.get(key)
        if real is None:
            continue
        spell_def = CardDef(
            cid="TS-" + d["spell"], name=d["spell"], cost=d["cost"],
            civs=frozenset(d["civs"]), ctype=SPELL,
            keywords=frozenset({"shield_trigger"}) if d["st"] else frozenset(),
            abilities=(d["ability"],))
        pool[real] = dataclasses.replace(pool[real], twin_spell=spell_def)
        attached.append(real)
    return attached

"""
duel_masters.effects
====================
carddb が作る CardDef 骨格(効果なし)に、手書きの効果(Ability/Static)を
**カード名で**紐づける登録レイヤー。まずはビートジョッキー敗北拒否軸の MVP。

効果テキストは自然言語なので自動実行できない。ここが「ルールエンジンの本質的
コスト」= 人力モデリングの場所。よく出るパターンはファクトリ関数にして、
新カードは register() 1行で足せるようにしてある。

カード名は公式表記の全角クォート/スペースで揺れるため _norm() で正規化マッチ。
マッチ漏れは apply_effects() が missing として返す(登録ミスの取りこぼし防止)。
"""
from __future__ import annotations
import dataclasses

from .engine import Static, Ability, CAST, ON_ATTACK, ON_SUMMON

_REG = {}  # normalized name -> (abilities tuple, statics tuple)


# 正規化で除去する文字: 空白・各種クォート・各種ダッシュ(コードネームの "S-駆" 等は
# ハイフン/全角長音/半角長音ｰ が混在するため、ダッシュ類は全部落として一致させる)。
_STRIP_CHARS = (" ", "　", "“", "”", "\"", "「", "」",
                "-", "ー", "ｰ", "−", "–", "—", "‐", "―")


def _norm(s: str) -> str:
    for ch in _STRIP_CHARS:
        s = s.replace(ch, "")
    return s


def register(name, *, abilities=(), statics=()):
    _REG[_norm(name)] = (tuple(abilities), tuple(statics))


def _is_bj(card) -> bool:
    return any("ビートジョッキー" in r for r in card.d.races)


def _hand_le1(p) -> bool:
    """G・G・G の共通条件: 手札が1枚以下。"""
    return len(p.hand) <= 1


# ---- 効果ファクトリ(よく出るパターン) -------------------------------------

def ggg_grant(keyword: str) -> Static:
    """G・G・G: 自分の手札が1枚以下なら自身に keyword を付与。"""
    def fn(game, src, target):
        if target is src and _hand_le1(src.controller):
            return {keyword}
        return set()
    return Static("keywords", fn, f"G・G・G:手札1枚以下で自身に{keyword}")


def bj_cost_reducer(amount: int, *, ggg: bool = False) -> Static:
    """自分のビートジョッキーの召喚コストを amount 軽減(ggg=手札1枚以下が条件)。"""
    def fn(game, src, player, card):
        if src.controller is not player:
            return 0
        if ggg and not _hand_le1(src.controller):
            return 0
        if card.ctype == "creature" and _is_bj(card):
            return amount
        return 0
    cond = "(G・G・G)" if ggg else ""
    return Static("cost", fn, f"自分のビートジョッキー召喚コスト-{amount}{cond}")


def loss_refusal(*, own_turn_only: bool, desc: str) -> Static:
    def fn(game, src, player):
        return (game.active() is player) if own_turn_only else True
    return Static("loss_refusal", fn, desc)


def cast_destroy_le(maxpow: int) -> Ability:
    """呪文: 相手のパワー maxpow 以下を1体破壊(対象は agent が選択)。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        cands = [c for c in opp.battle
                 if c.power is not None and c.power <= maxpow
                 and not game.is_restricted(controller, "untargetable", c)]
        if not cands:
            game.log("    効果: 対象なし")
            return
        t = controller.agent.choose_card(game, f"破壊(パワー{maxpow}以下)", cands)
        if t is not None:
            game.log(f"    効果: {t} を破壊")
            game.destroy(t)
    return Ability(CAST, f, f"パワー{maxpow}以下を1体破壊")


def cast_destroy_all_le(maxpow: int) -> Ability:
    """呪文: 相手のパワー maxpow 以下をすべて破壊。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        targets = [c for c in opp.battle if c.power is not None and c.power <= maxpow]
        for c in list(targets):
            game.destroy(c)
        game.log(f"    効果: 相手パワー{maxpow}以下を{len(targets)}体破壊")
    return Ability(CAST, f, f"パワー{maxpow}以下を全破壊")


def on_attack_kill_blocker_if_empty() -> Ability:
    """G・G・G: 攻撃時、手札1枚以下なら相手のブロッカー1体を破壊。"""
    def f(game, controller, source):
        if not _hand_le1(controller):
            return
        opp = game.opponent(controller)
        blk = [c for c in opp.battle if "blocker" in game.keywords_of(c)]
        if blk:
            t = controller.agent.choose_card(game, "ブロッカーを破壊", blk)
            if t is not None:
                game.log(f"    効果: ブロッカー {t} を破壊")
                game.destroy(t)
    return Ability(ON_ATTACK, f, "G・G・G:攻撃時 手札1枚以下で相手ブロッカー1体破壊")


# ---- カード登録(ビートジョッキー敗北拒否 MVP) -----------------------------

# G・G・G 条件付きキーワード
register("グレイト“S-駆”", statics=[ggg_grant("speed_attacker")])
register("ミサイル“J-飛”", statics=[ggg_grant("speed_attacker")])
register("“E-闘”ララッタ", statics=[ggg_grant("w_breaker")])

# コスト軽減
register("一番隊 チュチュリス", statics=[bj_cost_reducer(1)])
register("“R-夢”ララッタ", statics=[bj_cost_reducer(2, ggg=True)])

# 攻撃時の盤面干渉
register("“K-殴”ララッタ", abilities=[on_attack_kill_blocker_if_empty()])

# フィニッシャー(敗北拒否)
register("グッド“MSL”バウンサー",
         statics=[loss_refusal(own_turn_only=True, desc="自分のターン中は負けない")])
register("“血煙” マキシマム",
         statics=[loss_refusal(own_turn_only=False,
                               desc="敗北拒否(簡易: 一度きり自己シャッフルは未実装)")])

# 火の除去/バーン呪文(S・トリガーはキーワードとして carddb が自動付与)
register("スチーム・ハエタタキ", abilities=[cast_destroy_le(4000)])
register("ツリンボー・ファイアー", abilities=[cast_destroy_le(4000)])
register("ゼンメツー・スクラッパー", abilities=[cast_destroy_all_le(2000)])


# ---- Tier S 実メタの核効果(公式body_textに基づく手実装) -------------------
# 多くの実メタ効果は engine の既存プリミティブで表現できる。複雑な部分
# (G・ゼロの呪文カウント, NEO進化, 追加ターン等)は簡略 or 未実装(下記コメント)。

def _tap_all_enemies(game, controller):
    for c in game.opponent(controller).battle:
        c.tapped = True


def cast_tap_all(shield_if_le=None) -> Ability:
    """DNA・スパーク: 相手全タップ + 自分のシールドが少なければ山札上をシールド化。"""
    def f(game, controller, source):
        _tap_all_enemies(game, controller)
        if shield_if_le is not None and len(controller.shields) <= shield_if_le \
                and controller.deck:
            s = controller.deck.pop(0)
            s.zone = "shield"
            controller.shields.append(s)
    return Ability(CAST, f, "相手全タップ+条件シールド化")


def on_summon_tap_all() -> Ability:
    """閃光の守護者ホーリー等: 出た時、相手のクリーチャーをすべてタップ。"""
    def f(game, controller, source):
        _tap_all_enemies(game, controller)
    return Ability(ON_SUMMON, f, "出た時:相手全タップ")


def cast_oriotis_judge() -> Ability:
    """オリオティス・ジャッジ: 各PL、自身の最大マナ以上のコストのクリーチャーを山札の下へ。"""
    def f(game, controller, source):
        for p in game.players:
            maxmana = len(p.mana)
            if maxmana <= 0:
                continue
            for c in list(p.battle):
                if c.cost >= maxmana:
                    p.battle.remove(c)
                    c.zone = "deck"
                    c.controller = c.owner
                    c.tapped = False
                    p.deck.append(c)        # 山札の一番下
        game.log("    効果: 最大マナ以上のクリーチャーを山札の下へ")
    return Ability(CAST, f, "各PL:最大マナ以上コストのクリーチャーを山札下へ")


def on_summon_draw(n: int) -> Ability:
    def f(game, controller, source):
        game.draw(controller, n)
    return Ability(ON_SUMMON, f, f"出た時:カードを{n}枚引く")


def on_summon_battle_enemy() -> Ability:
    """“乱振”舞神 G・W・D: 出た時、相手1体とバトル。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        if opp.battle:
            t = controller.agent.choose_card(game, "バトルさせる相手", opp.battle)
            if t is not None:
                game.battle(source, t)
    return Ability(ON_SUMMON, f, "出た時:相手1体とバトル")


def on_summon_shield_burn(n: int) -> Ability:
    """“B-零朱”レイド: 出た時、相手のシールドを n 枚墓地に置く。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        for _ in range(n):
            if opp.shields:
                s = game.rng.choice(opp.shields)
                opp.shields.remove(s)
                s.zone = "graveyard"
                opp.graveyard.append(s)
        game.log(f"    効果: 相手シールドを{n}枚墓地へ")
    return Ability(ON_SUMMON, f, f"出た時:相手シールド{n}枚を墓地へ")


def on_summon_brand_destroy() -> Ability:
    """“轟轟轟”ブランド: 出た時1ドロー、手札を捨てた枚数だけ相手のパワー6000以下を破壊。"""
    def f(game, controller, source):
        game.draw(controller, 1)
        opp = game.opponent(controller)
        killable = sorted([c for c in opp.battle if (c.power or 0) <= 6000],
                          key=lambda c: -(c.power or 0))
        n = min(len(controller.hand), len(killable))
        for _ in range(n):                      # 安いカードから捨てる
            d = min(controller.hand, key=lambda c: c.cost)
            controller.hand.remove(d)
            d.zone = "graveyard"
            controller.graveyard.append(d)
        for t in killable[:n]:
            game.destroy(t)
    return Ability(ON_SUMMON, f, "出た時:手札を捨てて6000以下を破壊")


def on_summon_discard_opp(n: int) -> Ability:
    """刻解人形ジェニー・ジェーン等: 出た時、相手の手札を n 枚(高コスト)捨てさせる。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        for _ in range(n):
            if opp.hand:
                d = max(opp.hand, key=lambda c: c.cost)
                opp.hand.remove(d)
                d.zone = "graveyard"
                opp.graveyard.append(d)
        game.log(f"    効果: 相手手札を{n}枚捨て")
    return Ability(ON_SUMMON, f, f"出た時:相手手札{n}枚を捨てさせる")


def g_zero(threshold: int) -> Static:
    """G・ゼロ: このターンに唱えた呪文が threshold 枚以上ならコスト0で召喚可。"""
    def fn(game, src, player):
        return player.spells_this_turn >= threshold
    return Static("g_zero", fn, f"G・ゼロ:呪文{threshold}枚以上で無料召喚")


def on_summon_extra_turn() -> Ability:
    """次元の嵐 スコーラー: 召喚で出た時、追加ターンを得る(ゲーム中1回)。"""
    def f(game, controller, source):
        if not getattr(controller, "_extra_turn_used", False):
            controller._extra_turn_used = True
            game.request_extra_turn(controller)
            game.log("    効果: 追加ターンを獲得")
    return Ability(ON_SUMMON, f, "召喚時:追加ターン(ゲーム中1回)")


# 登録(Tier S 実メタの核カード)
register("DNA・スパーク", abilities=[cast_tap_all(shield_if_le=2)])
register("閃光の守護者ホーリー", abilities=[on_summon_tap_all()])
register("オリオティス・ジャッジ", abilities=[cast_oriotis_judge()])
register("超宮兵 マノミ", abilities=[on_summon_draw(2)], statics=[g_zero(3)])
register("超宮城 コーラリアン", abilities=[on_summon_draw(1)], statics=[g_zero(4)])
register("次元の嵐 スコーラー",
         abilities=[on_summon_extra_turn()], statics=[g_zero(5)])
register("“乱振”舞神 G・W・D", abilities=[on_summon_battle_enemy()])
register("“B-零朱”レイド", abilities=[on_summon_shield_burn(1)])
register("“轟轟轟”ブランド", abilities=[on_summon_brand_destroy()])
register("刻解人形ジェニー・ジェーン", abilities=[on_summon_discard_opp(1)])


def apply_effects(pool):
    """pool(name->CardDef骨格) に効果を差し込む。

    戻り値 (applied, missing): applied=効果を付与できたカード名、
    missing=登録したが pool に見つからなかった正規化名(=登録ミス検出用)。
    """
    index = {_norm(name): name for name in pool}
    applied, missing = [], []
    for nkey, (abi, sta) in _REG.items():
        real = index.get(nkey)
        if real is None:
            missing.append(nkey)
            continue
        cd = pool[real]
        pool[real] = dataclasses.replace(
            cd, abilities=cd.abilities + abi, statics=cd.statics + sta)
        applied.append(real)
    return applied, missing

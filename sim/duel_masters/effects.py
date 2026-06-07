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

from .engine import Static, Ability, CAST, ON_ATTACK, ON_SUMMON, ON_TURN_END

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


def on_summon_skip_turn() -> Ability:
    """終末の時計 ザ・クロック: 出た時(相手の攻撃中等)、このターンの残りをとばす。"""
    def f(game, controller, source):
        game.skip_rest_of_turn = True
        game.log("    効果: このターンの残りをとばす")
    return Ability(ON_SUMMON, f, "出た時:このターンの残りをとばす")


def on_summon_refresh_shields(n: int) -> Ability:
    """煌メク聖壁 灰瞳: 出た時、自分のシールドを手札に加え(ST不可)、山札上 n 枚をシールド化。"""
    def f(game, controller, source):
        for s in list(controller.shields):
            controller.shields.remove(s)
            s.zone = "hand"
            controller.hand.append(s)
        for _ in range(n):
            if controller.deck:
                c = controller.deck.pop(0)
                c.zone = "shield"
                controller.shields.append(c)
        game.log(f"    効果: シールドを{n}枚に張り替え")
    return Ability(ON_SUMMON, f, f"出た時:シールドを{n}枚に張り替え")


def on_summon_grave_to_deck() -> Ability:
    """水上第九院 シャコガイル(着地): 墓地を山札に加えシャッフル。"""
    def f(game, controller, source):
        for c in list(controller.graveyard):
            controller.graveyard.remove(c)
            c.zone = "deck"
            controller.deck.append(c)
        game.rng.shuffle(controller.deck)
    return Ability(ON_SUMMON, f, "出た時:墓地を山札に加えシャッフル")


def win_on_deckout() -> Static:
    """山札を引き切る時、代わりにゲームに勝つ(シャコガイル)。"""
    return Static("win_on_deckout", lambda g, s, p: True, "山札を引き切る時に勝利")


def on_turn_end_mill_self(draw_n: int, discard_n: int) -> Ability:
    """シャコガイル: ターン終了時に draw_n 引き discard_n 捨て(自山札を掘り引き切り勝利へ)。"""
    def f(game, controller, source):
        game.draw(controller, draw_n)
        for _ in range(discard_n):
            if controller.hand and game.winner is None:
                d = controller.hand.pop()
                d.zone = "graveyard"
                controller.graveyard.append(d)
    return Ability(ON_TURN_END, f, f"ターン終了時:{draw_n}引き{discard_n}捨て")


def cast_mana_refund(n: int = 1) -> Ability:
    """セイレーン・コンチェルト/シンクロ・スパイラル等の『実質0コスト』: 唱えると
    タップ済みマナを n 回復(コスト分を実質返す)。安い呪文の連打=G・ゼロの燃料になる。"""
    def f(game, controller, source):
        tapped = [m for m in controller.mana if m.tapped]
        for m in tapped[:n]:
            m.tapped = False
    return Ability(CAST, f, f"実質0コスト(マナ{n}回復)")


def cast_tap_all_draw() -> Ability:
    """ノヴァルティ・アメイズ(本体): 相手全タップ+1ドロー。"""
    def f(game, controller, source):
        _tap_all_enemies(game, controller)
        game.draw(controller, 1)
    return Ability(CAST, f, "相手全タップ+1ドロー")


def on_summon_number_bounce() -> Ability:
    """機術士ディール: 出た時、数字を1つ選び、その(印刷)コストの相手クリーチャーを全て手札へ。
    選ぶ数字は『戻して一番得なコスト帯(パワー総和最大)』を貪欲に選択する。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        if not opp.battle:
            game.log("    効果: 対象なし(数字選択)")
            return
        by_cost = {}
        for c in opp.battle:
            by_cost.setdefault(c.cost, []).append(c)
        num = max(by_cost,
                  key=lambda k: sum((c.power or 0) for c in by_cost[k]))
        for c in list(by_cost[num]):
            game.bounce(c)
        game.log(f"    効果: 数字{num}を選び同コストの相手を全て手札へ")
    return Ability(ON_SUMMON, f, "出た時:数字を選びその同コストの相手を全バウンス")


def doom_break() -> Static:
    """Q.Q.QX: シールドをブレイクする時、相手はそれを手札に加えるかわりに山札に刺す。
    刺さったカードを相手が引くと敗北する(engine.break_shield/_move_top_to_hand が解決)。"""
    return Static("doom_break", lambda g, s, leaving: True,
                  "ブレイクしたシールドを山札に刺す(引いたら敗北)")


# ---- ジョーカーズ・ロック / 盤面空勝利(未開拓軸) ---------------------------

def _jokers(game, p) -> int:
    return game.count_race(p, "ジョーカーズ")     # バトル＋マナのジョーカーズ枚数


def joker_unblockable(threshold: int = 5) -> Static:
    """ジョリー: 自分のジョーカーズが threshold 枚以上なら自身はブロックされない。"""
    def fn(game, src, target):
        if target is src and _jokers(game, src.controller) >= threshold:
            return {"unblockable"}
        return set()
    return Static("keywords", fn, f"ジョーカーズ{threshold}枚で自身アンブロッカブル")


def joker_attack_win(threshold: int = 5) -> Static:
    """ジョリー・ザ・ジョニー: ジョーカーズ threshold 枚以上で、攻撃の後に相手の
    シールドもクリーチャーも無ければゲームに勝つ(engine._check_attack_win が解決)。"""
    def fn(game, src):
        opp = game.opponent(src.controller)
        return (_jokers(game, src.controller) >= threshold
                and not opp.shields and not opp.battle)
    return Static("attack_win", fn,
                  f"ジョーカーズ{threshold}枚&相手の盤面/シールド空で攻撃後に勝利")


def senno_no_cheat() -> Static:
    """洗脳センノー: 相手は自分のターン中、召喚以外の方法でクリーチャーを出せない。"""
    def fn(game, src, player, kind, card):
        if kind != "no_free_play" or player is src.controller:
            return False
        return game.active() is player
    return Static("restrict", fn, "相手は自分のターン中、踏み倒しでクリーチャーを出せない")


def golden_spell_cap(cap: int = 1) -> Static:
    """ゴールデン・ザ・ジョニー: 相手は各ターンに cap 回しか呪文を唱えられない。"""
    def fn(game, src, player):
        return cap if player is not src.controller else None
    return Static("spell_cap", fn, f"相手は各ターン呪文{cap}回まで")


def cast_joker_search() -> Ability:
    """ジョジョジョ・ジョーカーズ: 山札上4枚からジョーカーズ・クリーチャー1枚を手札へ。"""
    def f(game, controller, source):
        top = controller.deck[:4]
        del controller.deck[:4]
        found = next((c for c in top
                      if c.ctype == "creature"
                      and any("ジョーカーズ" in r for r in c.d.races)), None)
        if found is not None:
            found.zone = "hand"
            controller.hand.append(found)
            top.remove(found)
        for c in top:
            c.zone = "deck"
            controller.deck.append(c)
    return Ability(CAST, f, "山札上4枚からジョーカーズ1枚回収")


def cast_meramera() -> Ability:
    """メラメラ・ジョーカーズ: ジョーカーズ1枚を捨て、2枚引く。"""
    def f(game, controller, source):
        jk = next((c for c in controller.hand
                   if any("ジョーカーズ" in r for r in c.d.races)), None)
        if jk is not None:
            controller.hand.remove(jk)
            jk.zone = "graveyard"
            controller.graveyard.append(jk)
            game.draw(controller, 2)
    return Ability(CAST, f, "ジョーカーズ1捨て2ドロー")


def on_summon_gayou() -> Ability:
    """ガヨウ神: 出た時、ジョーカーズが5枚以上なら2枚引く(簡略)。"""
    def f(game, controller, source):
        if _jokers(game, controller) >= 5:
            game.draw(controller, 2)
    return Ability(ON_SUMMON, f, "出た時ジョーカーズ5枚以上で2ドロー")


# ---- 公平化: メタ4デッキのカバレッジ補完(2026-06) ----------------------------

def cast_draw_discard(nd: int, ndi: int) -> Ability:
    """エマージェンシー・タイフーン/サイバー・チューン: nd枚引きndi枚捨てる。"""
    def f(game, controller, source):
        game.draw(controller, nd)
        for _ in range(ndi):
            if controller.hand:
                d = min(controller.hand, key=lambda c: c.cost)   # 安いカードを捨てる
                controller.hand.remove(d)
                d.zone = "graveyard"
                controller.graveyard.append(d)
    return Ability(CAST, f, f"{nd}枚引き{ndi}枚捨て")


def cast_ramp_draw(draw_if_le: int = 0) -> Ability:
    """豊潤フォージュン/トライガード・チャージャー等: 山札上1枚をマナへ。最大マナが
    draw_if_le 以下なら1ドロー。"""
    def f(game, controller, source):
        if controller.deck:
            c = controller.deck.pop(0)
            c.zone = "mana"; c.tapped = False
            controller.mana.append(c)
        if draw_if_le and len(controller.mana) <= draw_if_le:
            game.draw(controller, 1)
    return Ability(CAST, f, "山札上1枚をマナ加速(条件で1ドロー)")


def on_summon_destroy_all_others() -> Ability:
    """悪魔神王ディス・バルカミラ: 出た時、自身以外のクリーチャーをすべて破壊(全体除去)。"""
    def f(game, controller, source):
        for p in game.players:
            for c in list(p.battle):
                if c is not source:
                    game.destroy(c)
        game.log("    効果: 他のクリーチャーをすべて破壊")
    return Ability(ON_SUMMON, f, "出た時:自身以外を全破壊")


def on_summon_discard_all_opp() -> Ability:
    """「黒幕」: 出た時、相手は手札をすべて捨てる(全ハンデス)。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        n = len(opp.hand)
        for c in list(opp.hand):
            opp.hand.remove(c)
            c.zone = "graveyard"
            opp.graveyard.append(c)
        game.log(f"    効果: 相手の手札{n}枚を全て捨てさせる")
    return Ability(ON_SUMMON, f, "出た時:相手の手札を全て捨てさせる")


def spell_cost_tax(amount: int = 2) -> Static:
    """奇石 タスリク: 相手の呪文を唱えるコストが amount 多くなる(cost静的で負の軽減)。"""
    def fn(game, src, player, card):
        if player is not src.controller and card.ctype == "spell":
            return -amount
        return 0
    return Static("cost", fn, f"相手の呪文コスト+{amount}")


def cast_mana_to_hand_fix() -> Ability:
    """ローラー雪だるま: マナのクリーチャー1枚を手札へ→山札上1枚をマナへ(色/事故修正)。"""
    def f(game, controller, source):
        creatures = [c for c in controller.mana if c.ctype == "creature"]
        if creatures and controller.deck:
            pick = max(creatures, key=lambda c: c.cost)
            controller.mana.remove(pick)
            pick.zone = "hand"; pick.tapped = False
            controller.hand.append(pick)
            c = controller.deck.pop(0)
            c.zone = "mana"; c.tapped = False
            controller.mana.append(c)
    return Ability(CAST, f, "マナのクリーチャー1枚を手札へ+山札上1枚をマナへ")


def field_protect_multicolor(min_cost: int = 5) -> Static:
    """Dの妖艶 マッド・デッド・ウッド: 自分のコスト min_cost 以上の多色クリーチャーが
    離場する時、パワーが0より大きければ、かわりにとどまる(離場の置換・フィールド由来)。"""
    def fn(game, src, leaving):
        if leaving.controller is not src.controller:
            return False
        if leaving.cost < min_cost or len(leaving.civs) < 2:
            return False
        return (game.power_of(leaving) or 0) > 0
    return Static("replace_leave_field", fn,
                  f"自分のコスト{min_cost}以上の多色は破壊されず残る(パワー>0)")


# 登録(Tier S 実メタの核カード)
register("DNA・スパーク", abilities=[cast_tap_all(shield_if_le=2)])
register("終末の時計 ザ・クロック", abilities=[on_summon_skip_turn()])
register("煌メク聖壁 灰瞳", abilities=[on_summon_refresh_shields(5)])
register("水上第九院 シャコガイル",
         abilities=[on_summon_grave_to_deck(), on_turn_end_mill_self(5, 3)],
         statics=[win_on_deckout()])
register("ノヴァルティ・アメイズ", abilities=[cast_tap_all_draw()])
register("セイレーン・コンチェルト", abilities=[cast_mana_refund(1)])
register("シンクロ・スパイラル", abilities=[cast_mana_refund(1)])
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

# --- 未実装解決(2026-06): 数字ロック / 特殊敗北 / D2フィールド ---
# 機術士ディール(ツインパクトのクリーチャー面): 出た時、数字を選び同コストの相手を全戻し。
# 呪文面「本日のラッキーナンバー！」(数字ロック)は twinpact.py 側で付与。
register("機術士ディール/「本日のラッキーナンバー！」",
         abilities=[on_summon_number_bounce()])
# Q.Q.QX.(クリーチャー面): ブレイクしたシールドを山札に刺す(引いたら敗北)。
# 呪文面「終葬 5.S.D.」(相手を山札に刺す+自身を場に)は twinpact.py 側で付与。
register("Q.Q.QX./終葬 5.S.D.", statics=[doom_break()])
# Dの妖艶 マッド・デッド・ウッド(D2フィールド): 自分のコスト5以上多色を離場から守る。
# Dスイッチ(全墓地進化蘇生)は複雑なため未実装。
register("Dの妖艶 マッド・デッド・ウッド",
         statics=[field_protect_multicolor(5)])

# --- 未開拓軸: ジョーカーズ・ロック / 盤面空勝利(2026-06) ---
# ジョリー・ザ・ジョニー: ジョーカーズ5枚でアンブロッカブル＋攻撃後の盤面空勝利。
# SA/マスター・W・ブレイカーはテキストから自動付与。ゲーム外フェッチは未実装。
register("ジョリー・ザ・ジョニー",
         statics=[joker_unblockable(5), joker_attack_win(5)])
register("洗脳センノー", statics=[senno_no_cheat()])
register("ゴールデン・ザ・ジョニー", statics=[golden_spell_cap(1)])
register("ジョジョジョ・ジョーカーズ", abilities=[cast_joker_search()])
register("メラメラ・ジョーカーズ", abilities=[cast_meramera()])
register("ガヨウ神", abilities=[on_summon_gayou()])

# --- 公平化: メタ4デッキのカバレッジ補完(2026-06) ---
# 青白コントロール(5→13/14): ドロー呪文/全体除去/全ハンデス/ランプ。ブロッカー群
# (エメラルーダ/ミタラシオ/ラ・ウラ・ギガ)はキーワードで既に受けが機能。
register("エマージェンシー・タイフーン", abilities=[cast_draw_discard(2, 1)])
register("サイバー・チューン", abilities=[cast_draw_discard(3, 2)])
register("トライガード・チャージャー", abilities=[cast_ramp_draw()])
register("悪魔神王ディス・バルカミラ", abilities=[on_summon_destroy_all_others()])
register("「黒幕」", abilities=[on_summon_discard_all_opp()])
# 火光レイド(9→11/13): タスリク=相手呪文増税、ダチッコ=自分のBJ軽減。
register("奇石 タスリク", statics=[spell_cost_tax(2)])
register("ダチッコ・チュリス", statics=[bj_cost_reducer(3)])
# 水自然スコーラー(10→12/14): ランプ系。
register("豊潤フォージュン", abilities=[cast_ramp_draw(draw_if_le=5)])
register("ローラー雪だるま", abilities=[cast_mana_to_hand_fix()])


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

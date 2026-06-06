"""覚醒リンクの複雑能力の検証。
常在パワー修整 / 種族キーワード付与 / 踏み倒しメタ / サイキック攻撃不可 /
バトル勝利時アンタップ / 攻撃時 全体-9000 / 攻撃時ドロー を個別に確認する。"""
import random

from duel_masters import carddb, superdim, effects
from duel_masters.engine import (Game, Player, Card, CardDef, CREATURE,
                                  ON_ATTACK, ON_TURN_END, ON_LINK, FIRE,
                                  LIGHT, WATER)
from duel_masters.agents import HeuristicAgent

PASS = FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {label}")
    else:
        FAIL += 1
        print(f"  NG  {label}")


def mk(owner, name, power, races=(), keywords=frozenset(), psychic=False,
       ctype=CREATURE, civs=frozenset({FIRE})):
    c = Card(CardDef(cid=name, name=name, cost=2, civs=civs, ctype=ctype,
                     power=power, races=tuple(races), keywords=keywords,
                     psychic=psychic), owner)
    c.zone = "battle"
    return c


def trigger_attack(game, src):
    for ab in src.d.abilities:
        if ab.event == ON_ATTACK:
            ab.resolve(game, src.controller, src)


def main():
    reg = {n: d for n, d in
           [(n, superdim.LINK_REGISTRY[n][1]) for n in superdim.register_builtin_links()]}
    rng = random.Random(5)
    A = Player("A", HeuristicAgent("A", rng))
    B = Player("B", HeuristicAgent("B", rng))
    g = Game(A, B, rng=rng)

    # 1) 常在パワー修整: 雲龍(他のエイリアン+5000)
    unryu = Card(reg["雲龍 ディス・イズ・大横綱"], A); unryu.zone = "battle"
    ally = mk(A, "味方エイリアン", 3000, races=("エイリアン",))
    A.battle = [unryu, ally]
    check(g.power_of(ally) == 8000, f"エイリアン+5000 反映(={g.power_of(ally)})")
    check(g.power_of(unryu) == 20000, "自身は+5000しない(他の～)")

    # 2) 種族キーワード付与: 星龍王(自分のハンターにSA)
    star = Card(reg["星龍王ガイアール・リュウセイドラゴン"], A); star.zone = "battle"
    hunter = mk(A, "味方ハンター", 2000, races=("ハンター",))
    A.battle = [star, hunter]
    check("speed_attacker" in g.keywords_of(hunter), "ハンターにSA付与")

    # 3) 相手サイキック攻撃不可(星龍王)
    enemy_psy = mk(B, "敵サイキック", 4000, psychic=True)
    enemy_psy.summoning_sick = False
    B.battle = [enemy_psy]
    atks = [a for a in g.legal_attacks(B) if a.card is enemy_psy]
    check(not atks, "相手サイキックは攻撃候補から除外")

    # 4) バトル勝利時アンタップ(雲龍)
    A.battle = [unryu]; B.battle = []
    unryu.tapped = True
    weak = mk(B, "弱者", 1000); B.battle = [weak]
    g.battle(unryu, weak)
    check(weak not in B.battle, "雲龍がバトルに勝ち相手破壊")
    check(unryu.tapped is False, "バトル勝利時にアンタップ")

    # 5) 攻撃時 全体-9000(シャチホコGOLDEN)
    golden = Card(reg["シャチホコ・GOLDEN・ドラゴン"], A); golden.zone = "battle"
    A.battle = [golden]
    small = mk(B, "小型", 8000)
    big = mk(B, "大型", 12000)
    B.battle = [small, big]
    trigger_attack(g, golden)
    check(small not in B.battle, "全体-9000で8000以下は破壊")
    check(big in B.battle and g.power_of(big) == 3000, "12000は生存しP3000に低下")

    # 6) 踏み倒しメタ(ガロウズ): 攻撃中は相手のS・トリガー不可
    garowz = Card(reg["死海竜ガロウズ・デビルドラゴン"], A); garowz.zone = "battle"
    A.battle = [garowz]; B.battle = []
    st_card = mk(B, "STクリーチャー", 3000, keywords=frozenset({"shield_trigger"}))
    st_card.zone = "shield"; B.shields = [st_card]
    g.attacking = garowz                      # ガロウズの攻撃中
    g.break_shield(B, A)
    check(st_card in B.hand and st_card not in B.battle,
          "踏み倒しメタでS・トリガー不発(手札へ)")
    g.attacking = None

    # 同条件で メタが無ければ発動すること(対照)
    A.battle = []                             # ガロウズ退場
    st2 = mk(B, "ST2", 3000, keywords=frozenset({"shield_trigger"}))
    st2.zone = "shield"; B.shields = [st2]; B.hand = []
    g.break_shield(B, A)
    check(st2 in B.battle, "メタ無しならS・トリガー発動(場に出る)")

    # 7) 攻撃時ドロー(ジェット・カスケード)
    jet = Card(reg["弩級合身！ジェット・カスケード・アタック"], A); jet.zone = "battle"
    A.battle = [jet]; B.battle = []
    A.deck = [mk(A, f"山札{i}", 1000) for i in range(5)]
    h0 = len(A.hand)
    trigger_attack(g, jet)
    check(len(A.hand) == h0 + 3, f"攻撃時3ドロー(手札+{len(A.hand)-h0})")

    # 8) 選択不可(シャチホコGOLDEN): 相手の除去で対象にならない
    golden2 = Card(reg["シャチホコ・GOLDEN・ドラゴン"], B); golden2.zone = "battle"
    normal = mk(B, "通常クリーチャー", 2000)
    B.battle = [golden2, normal]; A.battle = []
    rm = effects.cast_destroy_le(99999)
    rm.resolve(g, A, None)            # A が B のクリーチャーを破壊しようとする
    check(golden2 in B.battle, "選択不可:シャチホコは除去対象にならない")
    check(normal not in B.battle, "選択可の通常クリーチャーは破壊された")

    # 9) 強制ブロック(雲龍): 相手はブロックを省略できない
    unryu2 = Card(reg["雲龍 ディス・イズ・大横綱"], A); unryu2.zone = "battle"
    A.battle = [unryu2]
    blocker = mk(B, "渋いブロッカー", 3000, keywords=frozenset({"blocker"}))
    B.battle = [blocker]
    B.shields = [mk(B, "s", 1000) for _ in range(3)]  # シールド有→通常はブロック回避
    for s in B.shields:
        s.zone = "shield"
    g.resolve_attack(unryu2, "player")
    check(blocker not in B.battle, "強制ブロックでブロッカーが受けて破壊された")
    check(len(B.shields) == 3, "ブロック成立によりシールドは割れていない")

    # 10) ハンティング(オレドラゴン): アンタップの相手クリーチャーも攻撃できる
    ore = Card(reg["唯我独尊ガイアール・オレドラゴン"], A); ore.zone = "battle"
    ore.summoning_sick = False
    A.battle = [ore]
    untapped = mk(B, "未タップ", 2000); untapped.tapped = False
    B.battle = [untapped]
    has = [a for a in g.legal_attacks(A)
           if a.card is ore and a.target is untapped]
    check(bool(has), "ハンティング:アンタップの相手も攻撃対象にできる")

    # 11) 離脱時生存(シャンメリー): 破壊されても手札を捨てて残る
    shan = Card(reg["豪遊！セイント・シャン・メリー"], A); shan.zone = "battle"
    A.battle = [shan]
    A.hand = [mk(A, "手札1", 1000), mk(A, "手札2", 1000)]
    hbefore = len(A.hand)
    g.destroy(shan)
    check(shan in A.battle, "離脱時生存:破壊されてもバトルゾーンに残る")
    check(len(A.hand) == hbefore - 1, "生存コストとして手札1枚を捨てた")

    # 12) リンク時展開(メンチ斬ルゾウ): 超次元のハンターを召喚
    menchi = Card(reg["バンカラ大親分 メンチ斬ルゾウ"], A); menchi.zone = "battle"
    A.battle = [menchi]
    hunter_psy = mk(A, "ハンターサイキック", 3000, races=("ハンター",), psychic=True)
    hunter_psy.zone = "super_zone"
    A.super_zone = [hunter_psy]
    for ab in menchi.d.abilities:
        if ab.event == ON_LINK:
            ab.resolve(g, A, menchi)
    check(hunter_psy in A.battle, "リンク時:超次元のハンターを召喚")

    # 13) ターン終了能力(シャンメリー): 自分アンタップ+ハンター数シールド化
    shan.tapped = True
    A.battle = [shan]               # シャンメリーはハンター種族
    A.deck = [mk(A, f"d{i}", 1000) for i in range(3)]
    s0 = len(A.shields)
    for ab in shan.d.abilities:
        if ab.event == ON_TURN_END:
            ab.resolve(g, A, shan)
    check(shan.tapped is False, "ターン終了時に自分をアンタップ")
    check(len(A.shields) == s0 + 1, "ハンター1体分シールドを追加")

    print(f"\n{'ALL PASS' if FAIL == 0 else 'FAILED'} ({PASS} ok / {FAIL} ng)")
    return FAIL == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)

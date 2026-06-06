"""覚醒リンク(P'S覚醒リンク)の実データ検証。
データ表 _LINK_DATA の各家系について 3体集結→リンク→ブレイカー→攻撃時効果→
リンク解除 の一連を確認する。覚醒後スタッツは kamigame デュエプレで確認した値。"""
import random

from duel_masters import carddb, superdim
from duel_masters.engine import Game, Player
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


# (覚醒後名, 構成3体, 期待パワー, 期待break_count, 超次元へ戻る構成, 攻撃時効果タグ)
FAMILIES = [
    ("死海竜ガロウズ・デビルドラゴン",
     ["ガロウズ・セブ・カイザー", "竜骨なる者ザビ・リゲル", "ハイドラ・ギルザウルス"],
     15000, 3, "ガロウズ・セブ・カイザー", "bounce"),
    ("激竜王ガイアール・オウドラゴン",
     ["ガイアール・カイザー", "ブーストグレンオー", "ドラゴニック・ピッピー"],
     25000, 99, "ガイアール・カイザー", "destroy_weaker"),
    ("雲龍 ディス・イズ・大横綱",
     ["横綱 義留の富士", "小結 座美の花", "大関 地男の里"],
     20000, 4, "横綱 義留の富士", None),
    ("唯我独尊ガイアール・オレドラゴン",
     ["勝利のプリンプリン", "勝利のガイアール・カイザー", "勝利のリュウセイ・カイザー"],
     26000, 99, "勝利のガイアール・カイザー", None),
    ("弩級合身！ジェット・カスケード・アタック",
     ["アクア・ジェット＜BOOON・スカイ＞", "アクア・アタック＜BAGOOON・パンツァー＞",
      "アクア・カスケード＜ZABUUUN・クルーザー＞"],
     17000, 3, "アクア・カスケード＜ZABUUUN・クルーザー＞", "bounce"),
    ("バンカラ大親分 メンチ斬ルゾウ",
     ["紅蓮の怒 鬼流院 刃", "魂の大番長「四つ牙」", "カチコミの哲"],
     17000, 3, "紅蓮の怒 鬼流院 刃", None),
    ("シャチホコ・GOLDEN・ドラゴン",
     ["ホワイト・TENMTH・カイザー", "ブラック・WILLOW・カイザー",
      "レッド・ABYTHEN・カイザー"],
     39000, 99, "レッド・ABYTHEN・カイザー", None),
    ("星龍王ガイアール・リュウセイドラゴン",
     ["流星のフォーエバー・カイザー", "ウコン・ピッピー", "サコン・ピッピー"],
     17000, 3, "流星のフォーエバー・カイザー", None),
    ("豪遊！セイント・シャン・メリー",
     ["光器セイント・アヴェ・マリア", "光器シャンデリア", "アルプスの使徒メリーアン"],
     19500, 4, "光器セイント・アヴェ・マリア", None),
    ("絶対絶命 ガロウズ・ゴクドラゴン",
     ["激沸騰！オンセン・ガロウズ", "激天下！シャチホコ・カイザー", "激相撲！ツッパリキシ"],
     17000, 3, "激沸騰！オンセン・ガロウズ", "mill_to"),
]


def vanilla_opp_creatures(pool, opp, n, power_cap):
    """相手にパワー power_cap 未満のクリーチャーを n 体置く(攻撃時効果の検証用)。"""
    made = []
    for name, cd in pool.items():
        if cd.ctype == "creature" and (cd.power or 0) < power_cap:
            c = carddb.make(pool, name, opp)
            c.zone = "battle"
            opp.battle.append(c)
            made.append(c)
            if len(made) >= n:
                break
    return made


def test_family(pool, spool, after, comps, power, brk, super_ret, atk):
    print(f"\n--- {after} ---")
    missing = [n for n in comps if n not in spool]
    check(not missing, f"構成3体が超次元プールに在る(欠け={missing})")
    if missing:
        return
    rng = random.Random(7)
    me = Player("A", HeuristicAgent("A", rng))
    opp = Player("B", HeuristicAgent("B", rng))
    me.super_zone = carddb.build_super_zone(spool, me, comps)
    g = Game(me, opp, rng=rng)
    superdim.install_awaken_hook(g)

    g.summon_from_super_zone(me, count=3, max_cost=99)
    check(len(me.battle) == 3, "構成3体がバトルに揃った")
    superdim.turn_end_link(g, me)
    devil = [c for c in me.battle if c.name == after]
    check(len(devil) == 1 and len(me.battle) == 1, "リンク体のみがバトルに残った")
    if not devil:
        return
    d = devil[0]
    check(d.power == power, f"パワー{power}(={d.power})")
    check(g.break_count(d) == brk, f"ブレイク数{brk}(={g.break_count(d)})")

    # 攻撃時効果(タグ別)。リーサル誤爆を防ぐため相手シールドは多めに積む。
    # 攻撃時ドロー持ち(ジェット等)のデッキ切れ敗北を避けるため自分の山札も用意。
    me.deck = [carddb.make(pool, list(pool)[0], me) for _ in range(6)]
    for _ in range(6):
        opp.shields.append(carddb.make(pool, list(pool)[0], opp))
    if atk == "mill_to":
        opp.deck = [carddb.make(pool, list(pool)[0], opp) for _ in range(12)]
        g.resolve_attack(d, "player")
        check(len(opp.deck) <= 2, f"攻撃時:相手山札を2枚まで墓地(残{len(opp.deck)})")
    elif atk in ("bounce", "destroy_weaker"):
        targets = vanilla_opp_creatures(pool, opp, 2, power)
        n_before = len(opp.battle)
        g.resolve_attack(d, "player")
        if atk == "bounce":
            check(len(opp.battle) <= n_before - 2, "攻撃時:相手2体バウンス")
        else:
            check(all(t not in opp.battle for t in targets),
                  "攻撃時:自身より小さい相手を全破壊")
    else:
        g.resolve_attack(d, "player")  # 攻撃時効果なし(ブレイカーのみ)

    if d not in me.battle:
        me.battle.append(d)
    g.destroy(d)
    nb = {c.name for c in me.battle}
    ns = {c.name for c in me.super_zone}
    check(super_ret in ns, f"解除: {super_ret} は超次元ゾーンへ")
    others = [n for n in comps if n != super_ret]
    check(all(o in nb for o in others), "解除: 残り構成はバトルに残る")
    check(after not in nb, "リンク体はバトルから消えた")


def main():
    keys = superdim.register_builtin_links()
    print(f"登録された覚醒リンク家系: {len(keys)} ({', '.join(keys)})")
    pool = carddb.load_pool()
    spool = carddb.load_super_pool()
    check(len(keys) >= 2, "データ表から2家系以上を登録")
    for fam in FAMILIES:
        test_family(pool, spool, *fam)
    print(f"\n{'ALL PASS' if FAIL == 0 else 'FAILED'} ({PASS} ok / {FAIL} ng)")
    return FAIL == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)

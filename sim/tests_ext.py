"""
tests_ext.py — エンジン拡張(常在効果フレーム + W・ブレイカー)の回帰テスト。
実DB(carddb)+ effects を読み込み、各 hook を直接検証する。

    python tests_ext.py    # 全 assert 成功で "ALL PASS"
"""
import random
from duel_masters import carddb, effects, Game, Player, GreedyAgent
from duel_masters.engine import Card


def _mkgame():
    p0, p1 = Player("P1", GreedyAgent("P1")), Player("P2", GreedyAgent("P2"))
    return Game(p0, p1, rng=random.Random(0)), p0, p1


def _put(pool, p, name):
    c = Card(pool[name], p)
    c.zone = "battle"
    c.controller = p
    p.battle.append(c)
    return c


def _is_bj(cd):
    return any("ビートジョッキー" in r for r in cd.races)


def main():
    pool = carddb.load_pool()
    applied, missing = effects.apply_effects(pool)
    assert not missing, ("効果登録の名前不一致:", missing)
    assert set(applied) >= {"グレイト“S-駆”", "一番隊 チュチュリス",
                            "グッド“MSL”バウンサー", "“血煙” マキシマム"}

    # 1) コスト軽減: チュチュリスは自分のビートジョッキーを -1、非BJは不変
    g, p0, _ = _mkgame()
    _put(pool, p0, "一番隊 チュチュリス")
    bj = next(cd for cd in pool.values()
              if cd.ctype == "creature" and _is_bj(cd) and cd.cost >= 3)
    non = next(cd for cd in pool.values()
               if cd.ctype == "creature" and not _is_bj(cd) and cd.cost >= 3)
    assert g.cost_of(p0, Card(bj, p0)) == bj.cost - 1
    assert g.cost_of(p0, Card(non, p0)) == non.cost

    # 2) G・G・G: 手札1枚以下のときだけ自身にSA
    g, p0, _ = _mkgame()
    s = _put(pool, p0, "グレイト“S-駆”")
    p0.hand = []
    assert "speed_attacker" in g.keywords_of(s)
    p0.hand = [Card(pool["グレイト“S-駆”"], p0) for _ in range(2)]
    assert "speed_attacker" not in g.keywords_of(s)

    # 3) ブレイク枚数: W・ブレイカー=2、通常=1
    g, p0, _ = _mkgame()
    assert g.break_count(_put(pool, p0, "グッド“MSL”バウンサー")) == 2
    assert g.break_count(_put(pool, p0, "グレイト“S-駆”")) == 1

    # 4) 敗北拒否: MSLは自分のターン中のみ、血煙は常時(簡易)
    g, p0, p1 = _mkgame()                 # active = p0
    _put(pool, p0, "グッド“MSL”バウンサー")
    assert g.loss_is_prevented(p0) is True
    g.active_index = 1
    assert g.loss_is_prevented(p0) is False
    _put(pool, p1, "“血煙” マキシマム")
    assert g.loss_is_prevented(p1) is True

    # 5) 実戦: W・ブレイカーはシールドを2枚割る
    g, p0, p1 = _mkgame()
    for _ in range(5):
        c = Card(pool["グレイト“S-駆”"], p1)
        c.zone = "shield"
        p1.shields.append(c)
    msl = _put(pool, p0, "グッド“MSL”バウンサー")
    msl.summoning_sick = False
    before = len(p1.shields)
    g.resolve_attack(msl, "player")
    assert len(p1.shields) == before - 2

    print("ALL PASS (9 checks)")


if __name__ == "__main__":
    main()

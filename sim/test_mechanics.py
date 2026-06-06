"""未実装メカニクスの検証(2026-06実装分)。
進化/NEO進化 / 数字ロック(本日のラッキーナンバー) / 特殊敗北(Q.Q.QX) /
D2フィールド(マッド・デッド・ウッド) を、エンジンのプリミティブと実カード登録の
両面から個別に確認する。test_complex.py と同じ check/PASS スタイル。"""
import random

from duel_masters import decks, carddb
from duel_masters.engine import (Game, Player, Card, CardDef, CREATURE, FIELD,
                                  FIRE, WATER, LIGHT, NATURE, Action)
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


def mk(owner, name, power=2000, cost=2, races=(), keywords=frozenset(),
       civs=frozenset({FIRE}), ctype=CREATURE, evolution=False, neo=False,
       field=False):
    c = Card(CardDef(cid=name, name=name, cost=cost, civs=civs, ctype=ctype,
                     power=power, races=tuple(races), keywords=keywords,
                     evolution=evolution, neo=neo, field=field), owner)
    c.zone = "battle"
    return c


def fresh_game():
    rng = random.Random(7)
    A = Player("A", HeuristicAgent("A", rng))
    B = Player("B", HeuristicAgent("B", rng))
    return Game(A, B, rng=rng), A, B


def test_evolution():
    print("[進化/NEO進化]")
    g, A, B = fresh_game()
    base = mk(A, "基盤", 3000); base.summoning_sick = True
    A.battle = [base]
    evo = mk(A, "進化体", 7000, cost=5, evolution=True); evo.zone = "hand"
    A.hand = [evo]
    # 進化召喚: 基盤の上に重ねる → 召喚酔いなし、基盤は場から外れて下に格納
    g._enter_battle(A, evo, free=True, evolve_on=g.evolution_base(A, evo))
    check(evo in A.battle and base not in A.battle, "進化体が場に出て基盤は下に格納")
    check(evo.summoning_sick is False, "進化体は召喚酔いなし(出たターンに攻撃可)")
    check(getattr(evo, "_evo_under", []) == [base], "下に基盤を1枚保持")
    # 破壊で進化の下の基盤も一緒に墓地へ
    g.destroy(evo)
    check(evo not in A.battle and base in A.graveyard and evo in A.graveyard,
          "進化体破壊で下の基盤も墓地へ")

    # 純粋進化は基盤が無いと出せない / NEO進化は基盤無しでも出せる
    g2, A2, B2 = fresh_game()
    pure = mk(A2, "純進化", 6000, cost=5, evolution=True, neo=False); pure.zone = "hand"
    neo = mk(A2, "NEO進化", 4000, cost=4, evolution=True, neo=True); neo.zone = "hand"
    A2.hand = [pure, neo]
    A2.mana = [mk(A2, f"m{i}", 1000) for i in range(6)]
    for m in A2.mana:
        m.zone = "mana"; m.tapped = False
    check(g2._can_play_now(A2, pure, True) is False, "純粋進化:基盤無しでは出せない")
    check(g2._can_play_now(A2, neo, True) is True, "NEO進化:基盤無しでも出せる")
    A2.battle = [mk(A2, "下", 2000)]
    check(g2._can_play_now(A2, pure, True) is True, "純粋進化:基盤があれば出せる")


def test_number_lock():
    print("[数字ロック(本日のラッキーナンバー)]")
    g, A, B = fresh_game()
    g.turn_count = 5
    locked = mk(B, "5コスト", 6000, cost=5); locked.zone = "hand"
    other = mk(B, "3コスト", 4000, cost=3); other.zone = "hand"
    B.hand = [locked, other]
    B.mana = [mk(B, f"m{i}", 1000) for i in range(7)]
    for m in B.mana:
        m.zone = "mana"; m.tapped = False
    B.locked_costs = {5: g.turn_count + 2}     # コスト5を次の自ターンまでロック
    check(g.is_cost_locked(B, locked) is True, "ロック中: コスト5は実行不可")
    check(g.is_cost_locked(B, other) is False, "非ロック: コスト3は実行可")
    check(g._can_play_now(B, locked, True) is False, "メインの候補手からコスト5が外れる")
    g.turn_count = 7                            # 次の自ターン開始時に解除
    check(g.is_cost_locked(B, locked) is False, "次の自ターンでロック解除")


def test_number_bounce():
    print("[機術士ディール: 数字バウンス(ON_SUMMON)]")
    pool, super_pool = decks.build_full_pool(nd_only=False)
    name = decks.resolve_name(pool, "機術士ディール／「本日のラッキーナンバー！」")
    g, A, B = fresh_game()
    deal = Card(pool[name], A)
    # 相手盤面: コスト5が2体(パワー総和大)、コスト3が1体 → 5を選んで2体戻すはず
    c5a = mk(B, "敵5a", 5000, cost=5); c5b = mk(B, "敵5b", 4000, cost=5)
    c3 = mk(B, "敵3", 8000, cost=3)
    B.battle = [c5a, c5b, c3]
    g._enter_battle(A, deal, free=True)         # 出た時効果が発火
    check(c5a in B.hand and c5b in B.hand, "コスト5の相手2体を手札へ戻した")
    check(c3 in B.battle, "コスト3の相手は盤面に残る")


def test_qqqx_doom():
    print("[Q.Q.QX: 特殊敗北(山札に刺す)]")
    pool, super_pool = decks.build_full_pool(nd_only=False)
    name = decks.resolve_name(pool, "Q.Q.QX.／終葬 5.S.D.")
    g, A, B = fresh_game()
    qx = Card(pool[name], A); qx.zone = "battle"; A.battle = [qx]
    B.deck = [mk(B, f"d{i}", 1000) for i in range(10)]
    for d in B.deck:
        d.zone = "deck"
    shield = mk(B, "盾", 3000); shield.zone = "shield"; B.shields = [shield]
    g.attacking = qx                            # Q.Q.QX の攻撃(ブレイク)中
    g.break_shield(B, A)
    check(shield not in B.hand and shield in B.deck, "ブレイク盾は手札でなく山札へ")
    check(B.deck.index(shield) == 3, "山札の上から4枚目に刺さる")
    check(shield.uid in B.doomed_uids, "刺さったカードは『引いたら敗北』マーク")
    # 刺さったカードを引くと敗北
    for _ in range(4):
        if g.winner is None:
            g.draw(B, 1)
    check(g.winner is A, "刺さったカードを引いて B が敗北")

    # 敗北拒否があれば刺さりカードを引いても負けない
    g2, A2, B2 = fresh_game()
    refuser = mk(B2, "拒否者", 5000)
    from duel_masters import effects
    refuser.d = effects.dataclasses.replace(
        refuser.d, statics=(effects.loss_refusal(own_turn_only=False, desc="t"),))
    B2.battle = [refuser]
    doomed = mk(B2, "刺さり", 1000); doomed.zone = "deck"
    B2.deck = [doomed]; B2.doomed_uids = {doomed.uid}
    g2.draw(B2, 1)
    check(g2.winner is None and doomed in B2.hand, "敗北拒否中は刺さりカードでも負けない")


def test_doom_stick_spell():
    print("[終葬 5.S.D.: 相手を刺す+自身を場に]")
    pool, super_pool = decks.build_full_pool(nd_only=False)
    name = decks.resolve_name(pool, "Q.Q.QX.／終葬 5.S.D.")
    g, A, B = fresh_game()
    card = Card(pool[name], A); card.zone = "hand"; A.hand = [card]
    A.mana = [mk(A, f"m{i}", 1000, civs=frozenset({NATURE})) for i in range(6)]
    for m in A.mana:
        m.zone = "mana"; m.tapped = False
    victim = mk(B, "犠牲", 6000, cost=4); B.battle = [victim]
    B.deck = [mk(B, f"d{i}", 1000) for i in range(8)]
    for d in B.deck:
        d.zone = "deck"
    g.play_twin_spell(A, card)                  # 呪文面で唱える
    check(victim in B.deck and victim.uid in B.doomed_uids, "相手1体を山札に刺した")
    check(card in A.battle, "唱えたカード自身がバトルゾーンに出る(墓地に行かない)")
    check(card not in A.graveyard, "墓地には送られていない")


def test_d2field():
    print("[D2フィールド: マッド・デッド・ウッド]")
    pool, super_pool = decks.build_full_pool(nd_only=False)
    name = decks.resolve_name(pool, "Dの妖艶 マッド・デッド・ウッド")
    g, A, B = fresh_game()
    mdw = Card(pool[name], A); mdw.zone = "field"; A.field = [mdw]
    # 自分のコスト5以上の多色クリーチャーは破壊されず残る
    multi = mk(A, "多色5", 6000, cost=5, civs=frozenset({FIRE, WATER}))
    A.battle = [multi]
    g.destroy(multi)
    check(multi in A.battle, "コスト5以上の多色は破壊されず残る(置換)")
    # コスト4(条件外)は普通に破壊される
    cheap = mk(A, "多色4", 3000, cost=4, civs=frozenset({FIRE, WATER}))
    A.battle = [multi, cheap]
    g.destroy(cheap)
    check(cheap not in A.battle, "コスト4の多色は守られず破壊")
    # 単色5コスト(多色でない)は守られない
    mono = mk(A, "単色5", 6000, cost=5, civs=frozenset({FIRE}))
    A.battle = [mono]
    g.destroy(mono)
    check(mono not in A.battle, "単色は守られず破壊")
    # 新しいD2フィールドが出ると古いものは破壊される(1枚保持)
    mdw2 = Card(pool[name], A); mdw2.zone = "hand"; A.hand = [mdw2]
    g._enter_field(A, mdw2)
    check(mdw not in A.field and mdw2 in A.field, "新フィールドで旧フィールドを破壊(1枚保持)")
    check(mdw in A.graveyard, "旧フィールドは墓地へ")


def test_dragheart():
    print("[龍解/ドラグハート]")
    from duel_masters import superdim
    g, A, B = fresh_game()
    # 合成のドラグハート・フォートレス(超次元ゾーン)と龍解後クリーチャー定義
    fortress = mk(A, "テスト城", None, cost=4, ctype=FIELD, civs=frozenset({FIRE}))
    fortress.d = CardDef(cid="DH", name="テスト城", cost=4,
                         civs=frozenset({FIRE}), ctype=FIELD, power=None,
                         psychic=True, field=True)
    fortress.zone = "super_zone"; A.super_zone = [fortress]
    solved = CardDef(cid="DH2", name="テスト龍", cost=4, civs=frozenset({FIRE}),
                     ctype=CREATURE, power=12000, keywords=frozenset({"t_breaker"}),
                     psychic=True)
    # ドラグナーが展開 → フィールドゾーンへ
    g.deploy_dragheart(A, fortress)
    check(fortress in A.field and fortress not in A.super_zone,
          "ドラグハートをフィールドへ展開")
    # 龍解条件(ここでは常に真)を登録し、ターン終了フックで龍解
    superdim.register_dragsolve("テスト城", lambda gm, c: True, solved)
    superdim.install_awaken_hook(g)
    for hook in g.turn_end_hooks:
        hook(g, A)
    check(fortress in A.battle and fortress not in A.field, "龍解でバトルゾーンへ")
    check(fortress.d.name == "テスト龍" and fortress.power == 12000,
          "龍解後フォームに反転(P12000/T・ブレイカー)")
    check(fortress.summoning_sick is False, "龍解後は召喚酔いなし")
    # 龍解後(psychic)は破壊されると超次元ゾーンへ戻る
    g.destroy(fortress)
    check(fortress in A.super_zone, "龍解後クリーチャーは離場で超次元へ戻る")
    superdim.DRAGSOLVE_REGISTRY.clear()

    # ドラグハートがDBから読めること(機構の実在確認)
    dh = carddb.load_dragheart_pool()
    check(len(dh) > 0, f"ドラグハートをDBから{len(dh)}枚ロード")
    fort = [c for c in dh.values() if c.field]
    check(len(fort) > 0, "フォートレスは field=True で読み込まれる")


def test_clone_integrity():
    print("[clone: 新状態の複製整合]")
    g, A, B = fresh_game()
    base = mk(A, "基盤", 3000); A.battle = [base]
    evo = mk(A, "進化体", 7000, evolution=True)
    g._enter_battle(A, evo, free=True, evolve_on=base)
    A.locked_costs = {4: 99}
    B.doomed_uids = {12345}
    mdw = mk(A, "D2", None, ctype=FIELD, field=True); mdw.zone = "field"
    A.field = [mdw]
    g2 = g.clone()
    A2 = g2.players[0]; B2 = g2.players[1]
    evo2 = next(c for c in A2.battle if c.name == "進化体")
    check(getattr(evo2, "_evo_under", []) and evo2._evo_under[0].name == "基盤",
          "進化スタックが複製される")
    check(A2.locked_costs == {4: 99}, "locked_costs が複製される")
    check(B2.doomed_uids == {12345}, "doomed_uids が複製される")
    check(len(A2.field) == 1 and A2.field[0].name == "D2", "フィールドゾーンが複製される")


def main():
    test_evolution()
    test_number_lock()
    test_number_bounce()
    test_qqqx_doom()
    test_doom_stick_spell()
    test_d2field()
    test_dragheart()
    test_clone_integrity()
    print(f"\n{'ALL PASS' if FAIL == 0 else 'FAILED'} ({PASS} ok / {FAIL} ng)")
    return FAIL == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)

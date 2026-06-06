"""ツインパクト両面プレイのエンジン検証。
クリーチャー面で召喚 / 呪文面で詠唱(コスト支払い・効果解決・墓地へ) / 呪文面S・トリガー。"""
import random

from duel_masters.engine import (Game, Player, Card, CardDef, Ability,
                                  CREATURE, SPELL, CAST, WATER, FIRE)
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


def destroy_strongest():
    def f(game, controller, source):
        opp = game.opponent(controller)
        if opp.battle:
            t = max(opp.battle, key=lambda c: c.power or 0)
            game.destroy(t)
    return Ability(CAST, f, "破壊:相手最大パワー1体")


def mana(owner, n):
    out = []
    for _ in range(n):
        c = Card(CardDef("m", "マナ", 1, frozenset({WATER, FIRE}), CREATURE, 1), owner)
        c.zone = "mana"
        out.append(c)
    return out


def make_twin(owner, st_on_spell=False):
    # 呪文面: コスト2・水・相手1体破壊(任意でST)
    spell = CardDef(cid="trap", name="トラップ呪文面", cost=2,
                    civs=frozenset({WATER}), ctype=SPELL,
                    keywords=frozenset({"shield_trigger"}) if st_on_spell else frozenset(),
                    abilities=(destroy_strongest(),))
    # クリーチャー面: コスト4・水火・P3000
    cdef = CardDef(cid="twin", name="二面クリーチャー", cost=4,
                   civs=frozenset({WATER}), ctype=CREATURE, power=3000,
                   twin_spell=spell)
    return Card(cdef, owner)


def main():
    rng = random.Random(1)
    A = Player("A", HeuristicAgent("A", rng))
    B = Player("B", HeuristicAgent("B", rng))
    g = Game(A, B, rng=rng)

    # 呪文面の支払い判定: マナ2でクリーチャー面(4)は不可、呪文面(2)は可
    t = make_twin(A)
    t.zone = "hand"
    A.hand = [t]
    A.mana = mana(A, 2)
    check(not g.can_pay(A, t), "マナ2ではクリーチャー面(コスト4)は出せない")
    check(g.can_pay_twin_spell(A, t), "マナ2で呪文面(コスト2)は唱えられる")

    # 呪文面で詠唱 → 相手を破壊、自身は墓地へ、呪文カウント+1
    enemy = Card(CardDef("e", "敵", 2, frozenset({FIRE}), CREATURE, 4000), B)
    enemy.zone = "battle"
    B.battle = [enemy]
    sp0 = A.spells_this_turn
    g.play_twin_spell(A, t)
    check(enemy not in B.battle, "呪文面の効果で相手を破壊")
    check(t in A.graveyard and t not in A.hand, "ツインパクトは墓地へ")
    check(A.spells_this_turn == sp0 + 1, "呪文カウントが増えた(G・ゼロ連動)")

    # クリーチャー面: マナ4で召喚できる
    t2 = make_twin(A)
    t2.zone = "hand"
    A.hand = [t2]
    A.mana = mana(A, 4)
    check(g.can_pay(A, t2), "マナ4でクリーチャー面を召喚できる")
    g.play(A, t2)
    check(t2 in A.battle, "クリーチャー面はバトルゾーンへ")

    # 呪文面S・トリガー: シールドから破壊呪文が撃てる
    t3 = make_twin(B, st_on_spell=True)
    t3.zone = "shield"
    B.shields = [t3]
    atkr = Card(CardDef("a", "攻撃役", 1, frozenset({FIRE}), CREATURE, 5000), A)
    atkr.zone = "battle"
    A.battle = [atkr]                       # Aの盤面(STの破壊対象)
    g.break_shield(B, A)
    check(t3 in B.graveyard, "呪文面S・トリガーが発動し墓地へ")
    check(atkr not in A.battle, "S・トリガーの破壊が解決(攻撃役を破壊)")

    print(f"\n{'ALL PASS' if FAIL == 0 else 'FAILED'} ({PASS} ok / {FAIL} ng)")
    return FAIL == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)

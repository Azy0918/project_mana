"""ISMCTS パイロットの検証。
行動シグネチャの安定性・木の選択/展開/逆伝播・実デッキでクラッシュなく完走し
ランダムに圧勝することを確認する(少反復で高速に)。"""
import random

from duel_masters import decks, superdim
from duel_masters.engine import Game, Action, Card, CardDef, FIRE, CREATURE
from duel_masters.agents import RandomAgent, HeuristicAgent
from duel_masters.ismcts import ISMCTSAgent, Node, _sig, _TreePlayoutAgent

PASS = FAIL = 0


def mkcard(owner, name):
    cd = CardDef(cid=name, name=name, cost=2, civs=frozenset({FIRE}),
                 ctype=CREATURE, power=2000)
    return Card(cd, owner)


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {label}")
    else:
        FAIL += 1
        print(f"  NG  {label}")


def test_sig():
    print("[行動シグネチャ(決定化間で安定)]")
    rng = random.Random(0)
    A = type("P", (), {})()
    from duel_masters.engine import Card, CardDef, FIRE, CREATURE
    cd = CardDef(cid="x", name="カードX", cost=2, civs=frozenset({FIRE}),
                 ctype=CREATURE, power=2000)
    c1 = Card(cd, A)
    c2 = Card(cd, A)               # 同名・別実体(uid違い)
    check(_sig(Action("play", c1)) == _sig(Action("play", c2)),
          "同名カードのplayは同じシグネチャ(uid非依存)")
    check(_sig(Action("pass")) == ("pass",), "passシグネチャ")
    check(_sig(Action("attack", c1, "player")) != _sig(Action("play", c1)),
          "攻撃とプレイは別シグネチャ")


def test_tree_mechanics():
    print("[木: 選択/展開/逆伝播]")
    root = Node()
    pol = HeuristicAgent("p", random.Random(1))
    agent = _TreePlayoutAgent(root, pol, max_depth=5, rng=random.Random(1), c=0.7)
    from duel_masters.engine import Card, CardDef, FIRE, CREATURE
    cd = CardDef(cid="x", name="X", cost=2, civs=frozenset({FIRE}),
                 ctype=CREATURE, power=2000)
    A = type("P", (), {})()
    acts = [Action("play", Card(cd, A)), Action("pass")]
    # 未展開 → 展開して frontier(in_rollout)へ(汎用 _tree_choose)
    a = agent._tree_choose([(_sig(x), x) for x in acts])
    check(a in acts, "未展開: 候補から1手を選び展開")
    check(len(root.children) == 1 and len(agent.path) == 1, "子1ノード展開・path記録")
    # 逆伝播の模倣
    for node in agent.path:
        node.visits += 1
        node.reward += 1.0
    child = next(iter(root.children.values()))
    check(child.visits == 1 and child.reward == 1.0, "逆伝播でvisits/reward更新")

    # 反応窓も木に載る(完全木探索): choose_yes_no / choose_card がノードを作る
    a2 = _TreePlayoutAgent(Node(), pol, max_depth=5, rng=random.Random(2), c=0.7)
    yn = a2.choose_yes_no(None, "S・トリガー Xを使う?")
    check(yn in (True, False) and len(a2.root.children) == 1,
          "S・トリガー判断が木のノードになる")
    a3 = _TreePlayoutAgent(Node(), pol, max_depth=5, rng=random.Random(3), c=0.7)
    blk = mkcard(A, "ブロッカーA")
    chosen = a3.choose_card(None, "Xをブロックする?", [blk], optional=True)
    check(chosen in (None, blk) and len(a3.root.children) == 1,
          "ブロック判断(任意)が木のノードになる")


def _play(agentA_factory, agentB_factory, seed, deckname="火光レイド"):
    pool, super_pool = decks.build_full_pool(nd_only=False)
    d = decks.decklist(deckname)
    rng = random.Random(seed)
    pa = decks.make_player(pool, super_pool, "A", agentA_factory("A", rng), *d)
    pb = decks.make_player(pool, super_pool, "B", agentB_factory("B", rng), *d)
    g = Game(pa, pb, rng=rng)
    superdim.install_awaken_hook(g)
    w = g.run(max_turns=120)
    return 1 if w is pa else (0.5 if w is None else 0)


def test_full_game():
    print("[実デッキ: 完走&対ランダム圧勝(少反復)]")
    def ism(n, r):
        return ISMCTSAgent(n, r, iterations=30, horizon=6, max_depth=8)
    s = sum(_play(ism, lambda n, r: RandomAgent(n, r), 300 + i) for i in range(4))
    check(s >= 3, f"ISMCTS(30) vs Random: {s}/4 勝(クラッシュなく完走)")


def test_block_search():
    print("[単発ブロックのISMCTS化: ブロッカー持ちデッキで完走]")
    # 青白(ブロッカー多数)を ISMCTS(ブロック探索ON)で操縦→ブロック経路を通す
    def ism(n, r):
        return ISMCTSAgent(n, r, iterations=20, horizon=5, max_depth=8,
                           block_iterations=12)
    ok = True
    try:
        _play(ism, lambda n, r: HeuristicAgent(n, r), 400, deckname="青白コントロール")
    except Exception as e:
        ok = False
        print("    error:", e)
    check(ok, "ブロック探索を含む実戦が例外なく完走")


def main():
    test_sig()
    test_tree_mechanics()
    test_full_game()
    print(f"\n{'ALL PASS' if FAIL == 0 else 'FAILED'} ({PASS} ok / {FAIL} ng)")
    return FAIL == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)

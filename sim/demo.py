"""
demo.py — エンジンの動作確認。
1) 詳細ログ付きの1ゲーム(Greedy同士)
2) Greedy vs Random を多数試行 → 勝率を測定
   (この「勝率を測る関数」こそ、遺伝的アルゴリズムが必要とする適応度の素)
"""

import random
from duel_masters import Game, Player, RandomAgent, GreedyAgent, cards


def new_game(agent0, agent1, seed, verbose=False):
    rng = random.Random(seed)
    p0 = Player("P1", agent0)
    p1 = Player("P2", agent1)
    p0.deck = cards.build_deck(p0)
    p1.deck = cards.build_deck(p1)
    return Game(p0, p1, verbose=verbose, rng=rng)


def play_one_verbose():
    print("=" * 60)
    print(" 詳細ログ: GreedyAgent 同士のミラー戦")
    print("=" * 60)
    g = new_game(GreedyAgent("P1"), GreedyAgent("P2"), seed=7, verbose=True)
    w = g.run(max_turns=100)
    print(f"\n勝者: {w}  (総ターン {g.turn_count})")


def measure_winrate(agent_factory0, agent_factory1, n=500):
    wins0 = wins1 = draws = 0
    total_turns = 0
    for i in range(n):
        g = new_game(agent_factory0(i), agent_factory1(i), seed=1000 + i)
        w = g.run(max_turns=200)
        total_turns += g.turn_count
        if w is None:
            draws += 1
        elif w.name == "P1":
            wins0 += 1
        else:
            wins1 += 1
    return wins0, wins1, draws, total_turns / n


def main():
    play_one_verbose()

    print("\n" + "=" * 60)
    print(" 勝率測定 = 適応度の素 (各 N=500 戦)")
    print("=" * 60)

    # サニティチェック: 同型ミラーは ~50%
    w0, w1, d, avg = measure_winrate(
        lambda i: GreedyAgent("P1", random.Random(i)),
        lambda i: GreedyAgent("P2", random.Random(i + 99)), n=500)
    print(f"Greedy vs Greedy : P1 {w0}  P2 {w1}  draw {d}  "
          f"(P1勝率 {w0 / 500:.1%}, 平均{avg:.1f}ターン)")

    # スキル差の検出: Greedy は Random に明確に勝つはず
    w0, w1, d, avg = measure_winrate(
        lambda i: GreedyAgent("P1", random.Random(i)),
        lambda i: RandomAgent("P2", random.Random(i + 99)), n=500)
    print(f"Greedy vs Random : P1 {w0}  P2 {w1}  draw {d}  "
          f"(Greedy勝率 {w0 / 500:.1%}, 平均{avg:.1f}ターン)")


if __name__ == "__main__":
    main()

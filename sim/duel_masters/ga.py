"""
duel_masters.ga
===============
デッキ進化(遺伝的アルゴリズム)。前回話した「進化ループ」の最小実装。
  個体   = 40枚デッキ(同名4枚まで)。Counter(name->count) で表現。
  適応度 = 固定ガントレットへの**着席公平**な勝率(先攻/後攻を半々で測る)。
  操作   = エリート保存 + トーナメント選択 + 交叉(カード混合) + 突然変異。

パイロットは GreedyAgent 同士(決定論的)。同一シードで再現可能、個体間比較も公平。
適応度はキャッシュ(同じデッキは再計算しない)。

既知の限界(設計メモ):
- Greedy は弱く、コンボ系デッキを過小評価しうる → 本番は ISMCTS へ。
- 固定ガントレットへの過学習(じゃんけん)が起きうる → 見えたら共進化へ昇格。
- 「ルールエンジンのバグでだけ勝つ」デッキを拾う可能性 → 発見後は人間が再生検証。
"""
from __future__ import annotations
import random
from collections import Counter

from . import carddb, effects
from .engine import Game, Player, FIRE
from .agents import GreedyAgent, HeuristicAgent

# 評価パイロット。MetaStone の知見「AIがちゃんと回せると進化デッキが強い」に倣い、
# 既定を盤面評価ヒューリスティックにする(GreedyAgent はミラーで A/B 比較用に温存)。
PILOT = HeuristicAgent

DECK_SIZE = 40
MAX_COPIES = 4


def build_pools(civ=FIRE, max_cost=8):
    """(効果適用済み pool, 候補名リスト)。候補 = 火クリーチャー + 効果実装済みの火呪文。"""
    pool = carddb.load_pool()
    effects.apply_effects(pool)
    cand = []
    for name, cd in pool.items():
        if civ not in cd.civs or cd.cost > max_cost:
            continue
        if cd.ctype == "creature" or (cd.ctype == "spell" and cd.abilities):
            cand.append(name)
    return pool, cand


# ---- 個体(デッキ)操作 -----------------------------------------------------

def deck_to_list(deck):
    return [n for n, c in deck.items() for _ in range(c)]


def deck_key(deck):
    return frozenset(deck.items())


def repair(deck, cand, rng):
    """同名4枚まで・合計ちょうど40枚に整える。"""
    for n in list(deck):
        if deck[n] > MAX_COPIES:
            deck[n] = MAX_COPIES
        if deck[n] <= 0:
            del deck[n]
    total = sum(deck.values())
    while total < DECK_SIZE:
        n = rng.choice(cand)
        if deck[n] < MAX_COPIES:
            deck[n] += 1
            total += 1
    while total > DECK_SIZE:
        n = rng.choice(list(deck))
        deck[n] -= 1
        total -= 1
        if deck[n] <= 0:
            del deck[n]
    return deck


def random_deck(cand, rng):
    return repair(Counter(), cand, rng)


def crossover(a, b, cand, rng):
    child = Counter()
    for n in set(a) | set(b):
        child[n] = min(MAX_COPIES, max(a.get(n, 0), b.get(n, 0)))
    return repair(child, cand, rng)


def mutate(deck, cand, rng, n_swaps=3):
    for _ in range(n_swaps):
        if deck:
            n = rng.choice(deck_to_list(deck))
            deck[n] -= 1
            if deck[n] <= 0:
                del deck[n]
    for _ in range(n_swaps):
        m = rng.choice(cand)
        if deck[m] < MAX_COPIES:
            deck[m] += 1
    return repair(deck, cand, rng)


# ---- 評価(着席公平な勝率) -------------------------------------------------

def _play(pool, deckA, deckB, seed):
    rng = random.Random(seed)
    p0 = Player("A", PILOT("A", rng))
    p1 = Player("B", PILOT("B", rng))
    p0.deck = carddb.build_deck(pool, p0, deck_to_list(deckA))
    p1.deck = carddb.build_deck(pool, p1, deck_to_list(deckB))
    w = Game(p0, p1, rng=rng).run(max_turns=100)
    if w is None:
        return 0.5
    return 1.0 if w.name == "A" else 0.0


def winrate_vs(pool, deck, opp, games=10, seed0=777):
    """deck の opp に対する勝率(先攻/後攻 半々)。"""
    s = 0.0
    for k in range(games):
        s += _play(pool, deck, opp, seed0 + k)            # deck 先攻
        s += 1.0 - _play(pool, opp, deck, seed0 + 500 + k)  # deck 後攻
    return s / (2 * games)


def fitness(pool, deck, gauntlet, games=10):
    return sum(winrate_vs(pool, deck, opp, games, seed0=777 + 1000 * gi)
               for gi, opp in enumerate(gauntlet)) / len(gauntlet)


# ---- ガントレット(評価相手) ----------------------------------------------

def _deck_from_top(sorted_cards, cand, rng):
    deck = Counter()
    for name, _ in sorted_cards:
        deck[name] = MAX_COPIES
        if sum(deck.values()) >= DECK_SIZE:
            break
    return repair(deck, cand, rng)


def build_gauntlet(pool, cand, rng):
    """自動生成の2デッキ: 低コストアグロ / 高パワー・ミッドレンジ。"""
    creatures = [(n, pool[n]) for n in cand if pool[n].ctype == "creature"]
    aggro = sorted(creatures, key=lambda x: (x[1].cost, -(x[1].power or 0)))
    mids = [c for c in creatures if c[1].cost <= 6]
    midrange = sorted(mids, key=lambda x: -(x[1].power or 0))
    return [_deck_from_top(aggro, cand, rng),
            _deck_from_top(midrange, cand, rng)]


# ---- 進化ループ ------------------------------------------------------------

def _tournament(scored, fit, rng, k=3):
    return max((rng.choice(scored) for _ in range(k)), key=fit)


def evolve(generations=15, pop=24, elite_frac=0.25, games=10, seed=42,
           verbose=True):
    rng = random.Random(seed)
    pool, cand = build_pools()
    gauntlet = build_gauntlet(pool, cand, rng)
    cache = {}

    def fit(ind):
        k = deck_key(ind)
        if k not in cache:
            cache[k] = fitness(pool, ind, gauntlet, games=games)
        return cache[k]

    population = [random_deck(cand, rng) for _ in range(pop)]
    n_elite = max(1, int(pop * elite_frac))
    best = None
    for gen in range(generations):
        scored = sorted(population, key=fit, reverse=True)
        best = scored[0]
        if verbose:
            med = fit(scored[len(scored) // 2])
            print(f"gen {gen:2d}: best {fit(best):.3f}  median {med:.3f}  "
                  f"(評価デッキ数 {len(cache)})")
        newpop = list(scored[:n_elite])              # エリート保存
        while len(newpop) < pop:
            a = _tournament(scored, fit, rng)
            b = _tournament(scored, fit, rng)
            child = mutate(crossover(a, b, cand, rng), cand, rng)
            newpop.append(child)
        population = newpop
    return pool, best, fit(best), gauntlet


def describe(pool, deck):
    out = []
    for name, c in sorted(deck.items(),
                          key=lambda kv: (pool[kv[0]].cost, kv[0])):
        cd = pool[name]
        star = " ★効果" if (cd.abilities or cd.statics) else ""
        kw = "".join(sorted(cd.keywords))
        out.append(f"  {c}x c{cd.cost} {name} (P{cd.power}{' '+kw if kw else ''}){star}")
    return "\n".join(out)


def main(**kw):
    pool, best, score, gauntlet = evolve(**kw)
    print(f"\n=== 発見デッキ 適応度(平均勝率) {score:.3f} ===")
    print(describe(pool, best))
    for gi, opp in enumerate(gauntlet):
        wr = winrate_vs(pool, best, opp, games=50, seed0=99 + 1000 * gi)
        print(f"  vs ガントレット#{gi} 勝率 {wr:.1%} (着席公平・50x2戦)")


if __name__ == "__main__":
    main()

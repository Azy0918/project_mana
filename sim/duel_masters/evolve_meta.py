"""
duel_masters.evolve_meta
========================
GA で「実メタ(Tier S 3デッキ)に勝つ火単NDデッキ」を進化させる。

ga.py の遺伝操作(個体=40枚, 交叉/変異/トーナメント)を流用しつつ、適応度を
**decks.META の実メタ3デッキへの着席公平な勝率**にする。個体は火単(build_pools
の候補)。対戦は全NDプール+超次元(覚醒フック)で行うので、相手のホール召喚・覚醒
リンク・ツインパクト(クリーチャー面)も機能する。

注意: 実メタ側はカード効果のカバレッジが低く(多くがバニラ/キーワード稼働)、
本来のTier S性能より弱い。ここで得られる勝率は「現エンジン上で」のもの。
"""
from __future__ import annotations
import os
import random
import time
from collections import Counter

from . import ga, decks, carddb, superdim
from .endurance import _now_jst, _fmt_dur, _atomic_write
from .engine import Game, Player
from .agents import HeuristicAgent


def _play_vs(pool, super_pool, ga_names, meta_main, meta_super, seed, ga_first,
             ga_super=(), pilot=None):
    rng = random.Random(seed)
    pilot = pilot or (lambda n, r: HeuristicAgent(n, r))
    ga_p = Player("GA", pilot("GA", rng))
    ga_p.deck = carddb.build_deck(pool, ga_p, ga_names)
    if ga_super:
        ga_p.super_zone = carddb.build_super_zone(super_pool, ga_p, ga_super)
    meta_p = decks.make_player(pool, super_pool, "META",
                               pilot("META", rng), meta_main, meta_super)
    p0, p1 = (ga_p, meta_p) if ga_first else (meta_p, ga_p)
    g = Game(p0, p1, rng=rng)
    superdim.install_awaken_hook(g)
    w = g.run(max_turns=120)
    if w is None:
        return 0.5
    return 1.0 if w is ga_p else 0.0


def fitness_vs_meta(pool, super_pool, deck, gauntlet, games=6, ga_super=(),
                    pilot=None):
    """deck の対メタ平均勝率。pilot を渡すと両席をそのパイロットで操縦(忠実評価)。"""
    names = ga.deck_to_list(deck)
    s = 0.0
    for gi, (mm, ms) in enumerate(gauntlet):
        for k in range(games):
            s += _play_vs(pool, super_pool, names, mm, ms, 100 + gi * 50 + k,
                          True, ga_super, pilot)
            s += _play_vs(pool, super_pool, names, mm, ms, 600 + gi * 50 + k,
                          False, ga_super, pilot)
    return s / (len(gauntlet) * games * 2)


def winrates_vs_each(pool, super_pool, deck, gauntlet_named, games=20, ga_super=()):
    names = ga.deck_to_list(deck)
    out = {}
    for dname, (mm, ms) in gauntlet_named.items():
        s = 0.0
        for k in range(games):
            s += _play_vs(pool, super_pool, names, mm, ms, 7 + k, True, ga_super)
            s += _play_vs(pool, super_pool, names, mm, ms, 700 + k, False, ga_super)
        out[dname] = s / (games * 2)
    return out


def evolve_vs_meta(generations=10, pop=18, games=5, elite_frac=0.25, seed=42,
                   verbose=True):
    pool, super_pool = decks.build_full_pool()
    _, cand = ga.build_pools()                      # 火単候補(個体の素材)
    gauntlet = [decks.decklist(n) for n in decks.META]
    rng = random.Random(seed)
    cache = {}

    def fit(ind):
        k = ga.deck_key(ind)
        if k not in cache:
            cache[k] = fitness_vs_meta(pool, super_pool, ind, gauntlet, games=games)
        return cache[k]

    population = [ga.random_deck(cand, rng) for _ in range(pop)]
    n_elite = max(1, int(pop * elite_frac))
    best = None
    for gen in range(generations):
        scored = sorted(population, key=fit, reverse=True)
        best = scored[0]
        if verbose:
            med = fit(scored[len(scored) // 2])
            print(f"gen {gen:2d}: best {fit(best):.3f}  median {med:.3f}  "
                  f"(評価 {len(cache)})", flush=True)
        newpop = list(scored[:n_elite])
        while len(newpop) < pop:
            a = ga._tournament(scored, fit, rng)
            b = ga._tournament(scored, fit, rng)
            child = ga.mutate(ga.crossover(a, b, cand, rng), cand, rng)
            newpop.append(child)
        population = newpop
    return pool, super_pool, best, fit(best)


def fast_ismcts_pilot(name, rng):
    """GAの精評価用 ISMCTS(40反復/horizon6/反応窓は木/ブロック探索off)。
    フル(ISMCTS80/blk40)の約2倍速で較正を維持しつつ、フル評価への**予測力**を確保する
    (24反復より弱いとメタの操縦が甘くアグロを過大評価し、GAが幻のデッキを選ぶ)。"""
    from .ismcts import ISMCTSAgent
    return ISMCTSAgent(name, rng, iterations=40, horizon=6, max_depth=10,
                       block_iterations=0, reactions_in_tree=True)


def ad_candidates(pool, civs, max_cost=9):
    """AD全体から、指定文明(＋無色)で払える効果ありorクリーチャーの候補名を作る。
    多色シナジー核(アイニー=火自然等)を最適化する二段GAの素材プール。"""
    civset = set(civs)
    cand = []
    for n, cd in pool.items():
        if cd.cost > max_cost or cd.field or "kindan" in {s.kind for s in cd.statics}:
            continue
        if not (cd.civs <= civset):
            continue
        if cd.ctype == "creature" or cd.abilities or cd.statics or cd.twin_spell:
            cand.append(n)
    return cand


def evolve_two_tier(generations=8, pop=20, h_games=4, ismcts_top_k=6,
                    ismcts_games=3, elite_frac=0.3, seed=42, verbose=True,
                    seed_cards=None, ga_super=(), cand=None):
    """二段GA: Tier1=Heuristicで全個体を高速ランク、Tier2=高速ISMCTSで上位K体だけを
    忠実評価しエリート選抜・最良決定に使う。=『ISMCTSをGA本走に載せる』実用解。

    Heuristic単独GAはアグロ偏重で『見かけだけメタに勝つ』デッキを選ぶが(meta_validation
    で実証)、エリート選抜をISMCTS忠実評価に委ねることでその幻を排す。ISMCTSは高コスト
    なので全個体でなく有望上位K体のみに使い、評価はキャッシュして再利用する。

    seed_cards={名前:枚数} を渡すと未開拓軸の核カードを毎個体に強制(未知デッキ探索)。
    ga_super=8枚の超次元ゾーン(名前list)を渡すと各個体に超次元ゾーンを持たせる。
    戻り値 (pool, super_pool, best_deck, best_ismcts_score, ga_super)。"""
    from collections import Counter as _C
    pool, super_pool = decks.build_full_pool()
    if cand is None:
        _, cand = ga.build_pools()
    gauntlet = [decks.decklist(n) for n in decks.META]
    seed_cards = {decks.resolve_name(pool, n) or n: c
                  for n, c in (seed_cards or {}).items()}
    for n in seed_cards:                         # シードが火候補に無ければ加える
        if n not in cand:
            cand = cand + [n]
    ga_super = [decks.resolve_name(super_pool, n) or n for n in ga_super]
    rng = random.Random(seed)
    hcache, icache = {}, {}

    def hfit(ind):
        k = ga.deck_key(ind)
        if k not in hcache:
            hcache[k] = fitness_vs_meta(pool, super_pool, ind, gauntlet,
                                        games=h_games, ga_super=ga_super)
        return hcache[k]

    def ifit(ind):
        k = ga.deck_key(ind)
        if k not in icache:
            icache[k] = fitness_vs_meta(pool, super_pool, ind, gauntlet,
                                        games=ismcts_games, ga_super=ga_super,
                                        pilot=fast_ismcts_pilot)
        return icache[k]

    def make_child(parents=None):
        if parents is None:
            d = ga.random_deck(cand, rng)
        else:
            d = ga.mutate(ga.crossover(parents[0], parents[1], cand, rng),
                          cand, rng)
        return _repair_seed(d, seed_cards, cand, rng) if seed_cards else d

    population = [make_child() for _ in range(pop)]
    n_elite = max(2, int(pop * elite_frac))
    best, best_i = None, -1.0
    for gen in range(generations):
        ranked = sorted(population, key=hfit, reverse=True)       # Tier1
        topk = ranked[:ismcts_top_k]
        topk_scored = sorted(topk, key=ifit, reverse=True)        # Tier2(忠実)
        gen_best = topk_scored[0]
        if ifit(gen_best) > best_i:
            best_i, best = ifit(gen_best), gen_best
        if verbose:
            print(f"gen {gen:2d}: ISMCTS最良 {ifit(gen_best):.3f} "
                  f"(H={hfit(gen_best):.3f})  H評価{len(hcache)} I評価{len(icache)}",
                  flush=True)
        elite = topk_scored[:n_elite]            # エリート=ISMCTS上位
        newpop = list(elite)
        while len(newpop) < pop:                 # 交配は Heuristic ランクで(安価・多様)
            a = ga._tournament(ranked, hfit, rng)
            b = ga._tournament(ranked, hfit, rng)
            newpop.append(make_child((a, b)))
        population = newpop
    return pool, super_pool, best, best_i, ga_super


def endurance(hours=3.0, pop=22, games=5, gens_per_epoch=4, elite_frac=0.25,
              hof_size=12, seed=None, outdir=None):
    """実メタ3デッキを相手に、壁時計時間でGAを回す耐久モード。
    連続進化＋殿堂(HoF)＋エポックごとにチェックポイント(発見デッキと対メタ勝率)。"""
    start = time.time()
    deadline = start + hours * 3600
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    outdir = outdir or os.path.join(here, "runs", "endurance_meta")
    os.makedirs(outdir, exist_ok=True)
    logpath = os.path.join(outdir, "log.txt")

    def log(msg):
        line = f"[{_now_jst()}] {msg}"
        print(line, flush=True)
        with open(logpath, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    pool, super_pool = decks.build_full_pool()
    _, cand = ga.build_pools()
    gauntlet = [decks.decklist(n) for n in decks.META]
    named = {n: decks.decklist(n) for n in decks.META}
    rng = random.Random(seed)
    cache = {}

    def fit(ind):
        k = ga.deck_key(ind)
        if k not in cache:
            cache[k] = fitness_vs_meta(pool, super_pool, ind, gauntlet, games=games)
        return cache[k]

    population = [ga.random_deck(cand, rng) for _ in range(pop)]
    n_elite = max(1, int(pop * elite_frac))
    hof = []                       # [(fitness, deck)]
    log(f"耐久(対実メタ)開始: {hours}時間 / pop={pop} games={games} seed={seed}")
    log(f"ガントレット: {', '.join(decks.META)} / 候補 {len(cand)} 種 / 出力 {outdir}")

    epoch = total_gens = 0
    while time.time() < deadline:
        epoch += 1
        for _ in range(gens_per_epoch):
            if time.time() >= deadline:
                break
            scored = sorted(population, key=fit, reverse=True)
            med = fit(scored[len(scored) // 2])
            log(f"  epoch {epoch} gen {total_gens}: best {fit(scored[0]):.3f} "
                f"median {med:.3f} (評価 {len(cache)} / 残り "
                f"{_fmt_dur(max(0, deadline - time.time()))})")
            newpop = list(scored[:n_elite])
            while len(newpop) < pop:
                a = ga._tournament(scored, fit, rng)
                b = ga._tournament(scored, fit, rng)
                newpop.append(ga.mutate(ga.crossover(a, b, cand, rng), cand, rng))
            population = newpop
            total_gens += 1

        seen = {ga.deck_key(d) for _, d in hof}
        for d in sorted(population, key=fit, reverse=True)[:n_elite]:
            if ga.deck_key(d) not in seen:
                hof.append((fit(d), Counter(d)))
                seen.add(ga.deck_key(d))
        hof.sort(key=lambda t: -t[0])
        del hof[hof_size:]
        _checkpoint_meta(outdir, pool, super_pool, named, hof, epoch,
                         total_gens, time.time() - start,
                         max(0, deadline - time.time()), len(cache))
        log(f"epoch {epoch} 完了: HoF最良 {hof[0][0]:.3f} / 殿堂 {len(hof)}件")

    log(f"=== 終了 経過 {_fmt_dur(time.time() - start)} / {total_gens}世代 / "
        f"評価 {len(cache)}デッキ ===")
    if hof:
        log(f"最良デッキ 対メタ平均 {hof[0][0]:.3f}:")
        for ln in ga.describe(pool, hof[0][1]).splitlines():
            log(ln)
    return hof


def _checkpoint_meta(outdir, pool, super_pool, named, hof, epoch, total_gens,
                     elapsed, remaining, n_eval):
    import json
    best_fit, best_deck = hof[0]
    wr = winrates_vs_each(pool, super_pool, best_deck, named, games=12)
    payload = {
        "updated_jst": _now_jst(), "epoch": epoch,
        "total_generations": total_gens, "elapsed": _fmt_dur(elapsed),
        "remaining": _fmt_dur(remaining), "decks_evaluated": n_eval,
        "best_avg_winrate": best_fit,
        "best_vs_each": {k: round(v, 3) for k, v in wr.items()},
        "best_deck": dict(best_deck),
        "best_deck_lines": ga.describe(pool, best_deck).splitlines(),
        "hall_of_fame": [{"rank": i + 1, "avg": round(f, 3),
                          "cards": len(d), "total": sum(d.values())}
                         for i, (f, d) in enumerate(hof)],
    }
    _atomic_write(os.path.join(outdir, "checkpoint.json"),
                  json.dumps(payload, ensure_ascii=False, indent=2))
    lines = [
        "Project MANA — 耐久(対実メタ) 発見デッキ", "=" * 50,
        f"更新(JST): {payload['updated_jst']}  経過 {payload['elapsed']} / 残り "
        f"{payload['remaining']}  エポック {epoch} 世代 {total_gens} 評価 {n_eval}",
        f"■ 暫定ベスト 対メタ平均勝率 {best_fit:.3f}",
        *(f"   vs {k}: {v:.1%}" for k, v in wr.items()), "",
        *payload["best_deck_lines"],
    ]
    _atomic_write(os.path.join(outdir, "report.txt"), "\n".join(lines) + "\n")


def _repair_seed(deck, seed, cand, rng):
    """シード(必須カード)を保ったまま40枚・同名4枚に整える。"""
    for n, c in seed.items():
        deck[n] = max(deck.get(n, 0), c)
    for n in list(deck):
        if deck[n] > ga.MAX_COPIES:
            deck[n] = ga.MAX_COPIES
        if deck[n] <= 0:
            del deck[n]
    total = sum(deck.values())
    while total < ga.DECK_SIZE:
        n = rng.choice(cand)
        if deck[n] < ga.MAX_COPIES:
            deck[n] += 1
            total += 1
    while total > ga.DECK_SIZE:
        removable = [n for n in deck if deck[n] > seed.get(n, 0)]
        if not removable:
            break
        n = rng.choice(removable)
        deck[n] -= 1
        total -= 1
        if deck[n] <= 0:
            del deck[n]
    return deck


def evolve_novel(seed, generations=14, pop=20, games=5, elite_frac=0.25,
                 rng_seed=42, ga_super=(), verbose=True):
    """未開拓軸の核カード(seed={名前:枚数})を毎個体に強制し、メタに勝つシェルをGA探索。
    『人間が軸を選び、GAが最適シェルを発見する』未知デッキ探索。
    ga_super を渡すと GA個体に8枚の超次元ゾーンを持たせる(超次元軸の探索用)。"""
    from collections import Counter as _C
    pool, super_pool = decks.build_full_pool()
    _, cand = ga.build_pools()
    # シードは候補に含まれている必要がある(火プール想定)。
    seed = {decks.resolve_name(pool, n) or n: c for n, c in seed.items()}
    for n in seed:
        if n not in cand:
            cand = cand + [n]
    gauntlet = [decks.decklist(n) for n in decks.META]
    named = {n: decks.decklist(n) for n in decks.META}
    ga_super = [decks.resolve_name(super_pool, n) or n for n in ga_super]
    rng = random.Random(rng_seed)
    cache = {}

    def fit(ind):
        k = ga.deck_key(ind)
        if k not in cache:
            cache[k] = fitness_vs_meta(pool, super_pool, ind, gauntlet,
                                       games=games, ga_super=ga_super)
        return cache[k]

    population = [_repair_seed(_C(), seed, cand, rng) for _ in range(pop)]
    n_elite = max(1, int(pop * elite_frac))
    best = None
    for gen in range(generations):
        scored = sorted(population, key=fit, reverse=True)
        best = scored[0]
        if verbose:
            print(f"gen {gen:2d}: best {fit(best):.3f}  "
                  f"median {fit(scored[len(scored)//2]):.3f}  (評価 {len(cache)})",
                  flush=True)
        newpop = list(scored[:n_elite])
        while len(newpop) < pop:
            a = ga._tournament(scored, fit, rng)
            b = ga._tournament(scored, fit, rng)
            child = _repair_seed(ga.crossover(a, b, cand, rng), seed, cand, rng)
            child = _repair_seed(ga.mutate(child, cand, rng), seed, cand, rng)
            newpop.append(child)
        population = newpop

    score = fit(best)
    print(f"\n=== 発見デッキ(シード={'/'.join(seed)}) 対メタ平均 {score:.3f} ===")
    print(ga.describe(pool, best))
    if ga_super:
        print("超次元ゾーン:", " / ".join(ga_super))
    wr = winrates_vs_each(pool, super_pool, best, named, games=25,
                          ga_super=ga_super)
    print("\n各Tier Sデッキへの勝率:")
    for dn, v in wr.items():
        print(f"  vs {dn}: {v:.1%}")
    hole = sum(c for n, c in best.items()
               if any("超次元" in a.desc or "召喚" in a.desc
                      for a in pool[n].abilities))
    print(f"\nホール呪文採用: {hole}枚 / シード: {dict(seed)}")
    return pool, super_pool, best, score


def main(**kw):
    pool, super_pool, best, score = evolve_vs_meta(**kw)
    print(f"\n=== 発見デッキ 対メタ平均勝率 {score:.3f} ===")
    print(ga.describe(pool, best))
    named = {n: decks.decklist(n) for n in decks.META}
    wr = winrates_vs_each(pool, super_pool, best, named, games=25)
    print("\n各Tier Sデッキへの勝率(着席公平・25x2戦):")
    for dname, w in wr.items():
        print(f"  vs {dname}: {w:.1%}")


if __name__ == "__main__":
    main()

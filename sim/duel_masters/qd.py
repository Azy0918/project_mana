"""
duel_masters.qd
===============
Quality-Diversity(MAP-Elites)によるデッキ"発想"エンジン。

通常GAは単一目的(メタ勝率)で最適化するため、頑健メタ下では最も簡単なアグロ局所最適に
収束し、面白い亜種を捨てる(=発想力が無い)。MAP-Elites は解を**振る舞い(behavior)で
ニッチに分け、各ニッチの最良個体を保持するアーカイブ**を育てる。「勝つ」でなく
「(各ニッチで)新しく・かつ強い」に報酬を与えるので、人間が列挙しない戦略を表面化させる。

振る舞い記述子(BC) = (色アイデンティティ, コストカーブ, 勝ち筋スタイル)。
 - 色: 6枚以上現れる文明の組(火 / 水光 / 闇自然 ...)
 - カーブ: 平均コスト 低(<=2.5)/中(<=4)/高(>4)
 - スタイル: 特殊勝利 / 敗北拒否 / コンボ(G・ゼロ) / ロック / 受け / ビート

候補は全ND多色プール(効果実装済みを優先)。色コヒーレントに初期化/変異して払える
デッキを保つ。適応度は evolve_meta の対メタ勝率(高速Heuristic、探索を回すため)。
アーカイブの注目セルは最後に ISMCTS で忠実検証する(qd_validate)。
"""
from __future__ import annotations
import random
from collections import Counter

from . import ga, decks, carddb, effects, superdim, twinpact, evolve_meta
from .engine import LIGHT, WATER, DARKNESS, FIRE, NATURE

_CIV_ORDER = [LIGHT, WATER, DARKNESS, FIRE, NATURE]


def build_nd_candidates(max_cost=9):
    """全ND多色プール(ゲームはAD込みfull pool、候補名はND・効果/クリーチャー優先)。
    戻り値 (pool, super_pool, cand, by_civ)。by_civ[civ]=その文明を含む候補名。"""
    pool, super_pool = decks.build_full_pool(nd_only=False)
    nd_names = set(carddb.load_pool(nd_only=True))
    cand = []
    for n in nd_names:
        cd = pool.get(n)
        if cd is None or cd.cost > max_cost or cd.field:
            continue
        if cd.ctype == "creature" or cd.abilities or cd.statics or cd.twin_spell:
            cand.append(n)
    return pool, super_pool, cand


def _civ_subpool(pool, cand, civs):
    """civs(集合)＋無色だけで払える候補名(多色は全文明が civs に含まれるもの)。"""
    sub = [n for n in cand if pool[n].civs <= civs]
    return sub if len(sub) >= 12 else cand


def random_civs(rng):
    k = rng.choice([1, 1, 1, 2, 2])      # 主に単色、時々2色
    return frozenset(rng.sample(_CIV_ORDER, k))


def color_coherent_deck(pool, cand, rng, civs=None):
    civs = civs or random_civs(rng)
    sub = _civ_subpool(pool, cand, civs)
    return ga.repair(Counter(), sub, rng), sub


# ---- 振る舞い記述子(BC) -----------------------------------------------------
def _has_static(pool, deck, kind):
    return any(any(s.kind == kind for s in pool[n].statics) for n in deck)


def behavior(pool, deck):
    names = ga.deck_to_list(deck)
    civc = Counter()
    for n in names:
        for c in pool[n].civs:
            civc[c] += 1
    civ_label = "".join(c for c in _CIV_ORDER if civc[c] >= 6) or "無"
    avg = sum(pool[n].cost for n in names) / len(names)
    curve = "低" if avg <= 2.5 else ("中" if avg <= 4.0 else "高")
    if _has_static(pool, deck, "attack_win") or _has_static(pool, deck, "win_on_deckout"):
        style = "特殊勝利"
    elif _has_static(pool, deck, "loss_refusal"):
        style = "敗北拒否"
    elif _has_static(pool, deck, "g_zero"):
        style = "コンボ"
    elif _has_static(pool, deck, "spell_cap") or _has_static(pool, deck, "restrict"):
        style = "ロック"
    else:
        defn = sum(deck[n] for n in deck
                   if {"blocker", "shield_trigger"} & set(pool[n].keywords))
        style = "受け" if defn >= 8 else "ビート"
    return (civ_label, curve, style)


# ---- MAP-Elites -------------------------------------------------------------
def map_elites(iters=300, init=50, games=4, seed=42, max_cost=9, verbose=True):
    """戻り値 (pool, super_pool, archive)。archive[cell]=(fitness, deck, civs)。"""
    rng = random.Random(seed)
    pool, super_pool, cand = build_nd_candidates(max_cost)
    gauntlet = [decks.decklist(n) for n in decks.DECKS]
    cache = {}

    def fit(deck):
        k = ga.deck_key(deck)
        if k not in cache:
            cache[k] = evolve_meta.fitness_vs_meta(pool, super_pool, deck,
                                                   gauntlet, games=games)
        return cache[k]

    archive = {}

    def consider(deck):
        cell = behavior(pool, deck)
        f = fit(deck)
        cur = archive.get(cell)
        if cur is None or f > cur[0]:
            archive[cell] = (f, deck, behavior(pool, deck))
        return cell

    for _ in range(init):                         # 初期: 色コヒーレントなランダム
        d, _sub = color_coherent_deck(pool, cand, rng)
        consider(d)
    for it in range(iters):                       # 反復: エリートから変異して配置
        f, parent, _ = rng.choice(list(archive.values()))
        civs = frozenset(c for n in parent for c in pool[n].civs) or random_civs(rng)
        sub = _civ_subpool(pool, cand, civs)
        child = ga.mutate(Counter(parent), sub, rng, n_swaps=rng.choice([2, 3, 4]))
        consider(child)
        if verbose and (it + 1) % 50 == 0:
            best = max(archive.values(), key=lambda x: x[0])
            print(f"  iter {it+1}: セル数 {len(archive)}  最良 {best[0]:.3f} "
                  f"{best[2]}  (評価 {len(cache)})", flush=True)
    return pool, super_pool, archive


def archive_table(archive):
    """アーカイブを (適応度降順) で行に。返り値=表示用文字列。"""
    rows = sorted(archive.values(), key=lambda x: -x[0])
    out = [f"アーカイブ: {len(archive)}セル(=発見された戦略ニッチ)"]
    for f, deck, cell in rows:
        out.append(f"  {f:.3f}  {'/'.join(cell)}")
    return "\n".join(out)


def qd_validate(pool, super_pool, archive, top=6, games=8):
    """アーカイブから多様な上位セルを ISMCTS で忠実検証(高速Heuristic適応度の裏取り)。"""
    named = {n: decks.decklist(n) for n in decks.DECKS}
    rows = sorted(archive.values(), key=lambda x: -x[0])[:top]
    out = []
    for f, deck, cell in rows:
        main = ga.deck_to_list(deck)
        wr = 0.0
        for dn, dl in named.items():
            wr += decks.play_match(pool, super_pool, (main, []), dl,
                                   games=games, seed0=4242, pilot=decks.eval_pilot)
        wr /= len(named)
        out.append((cell, f, wr, deck))
    return out

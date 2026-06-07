"""
meta_validation
===============
「現環境(Tier S)デッキが本当にメタか」を、忠実シミュレーター上で検証する。

シミュレーターは『現実世界のメタ』であることは証明できない(それは人間プレイヤーが
何を握って勝つかという経験的事実)。だが忠実な評価器(ISMCTS)が揃った今、次の2つの
**シム内の証拠**を出せる:

  証拠① 整合性/バランス: 提供デッキ同士の忠実総当たりが『メタらしい』相性構造
         (じゃんけん)を持つか。
  証拠② 頑健性/最適性(決定的): 提供デッキを固定ガントレットとし、GAで全NDプールから
         『総なめにするデッキ』を探す。それが ISMCTS 忠実評価でも勝率を保てば反証、
         崩壊すれば=デッキ空間に容易な支配的カウンターは無い=メタは頑健、の証拠。

注意(正直な範囲):
 - 効果実装カバレッジが不均一(闇自然36/40 > スコーラー23 > 火光20 > 青白15)なので、
   バランスの数字はカバレッジ差のバイアスを含む。青白は代替6枚でハンデもある。
 - GAは Heuristic で探索するためアグロ寄りの探索になりがち(=容易に届く範囲の反証)。
   より徹底した探索(シード型 novel 軸・ISMCTSをループ内)は別途。

実行: PYTHONPATH=. PYTHONUTF8=1 python meta_validation.py
"""
from __future__ import annotations
import time

from duel_masters import decks, ga, evolve_meta


def round_robin(games=12, seed0=99):
    """証拠①: 4デッキの忠実総当たり(ISMCTS両席)。行vs列の勝率行列と各デッキ平均。"""
    pool, super_pool = decks.build_full_pool(nd_only=False)
    names = list(decks.META)
    DL = {n: decks.decklist(n) for n in names}
    mat = {a: {} for a in names}
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if i == j:
                mat[a][b] = None
            elif j < i:
                mat[a][b] = round(1 - mat[b][a], 3)
            else:
                mat[a][b] = round(decks.play_match(
                    pool, super_pool, DL[a], DL[b], games=games, seed0=seed0,
                    pilot=decks.eval_pilot), 3)
    return names, mat


def challenge(generations=14, pop=20, ga_games=5, eval_games=15):
    """証拠②: GA(Heuristic)が見つける反メタデッキを Heuristic と ISMCTS で再評価。
    戻り値 (ga_main, heuristic_winrates, ismcts_winrates)。"""
    pool, super_pool = decks.build_full_pool(nd_only=False)
    named = {n: decks.decklist(n) for n in decks.META}
    _, _, best, claim = evolve_meta.evolve_vs_meta(
        generations=generations, pop=pop, games=ga_games, seed=42, verbose=False)
    ga_main = ga.deck_to_list(best)

    def ev(pilot, games):
        out = {dn: decks.play_match(pool, super_pool, (ga_main, []), dl,
                                    games=games, seed0=4242, pilot=pilot)
               for dn, dl in named.items()}
        out["平均"] = sum(out[k] for k in named) / len(named)
        return out

    return claim, ev(decks.heuristic_pilot, eval_games + 5), ev(decks.eval_pilot, eval_games)


def main():
    t0 = time.time()
    print("=== 証拠① 忠実総当たり(ISMCTS) 行vs列の勝率 ===", flush=True)
    names, mat = round_robin()
    print("            " + " ".join(f"{n[:6]:>7}" for n in names) + "   平均", flush=True)
    for a in names:
        vals = [mat[a][b] for b in names if mat[a][b] is not None]
        row = " ".join("   --- " if mat[a][b] is None else f"{mat[a][b]:7.3f}"
                       for b in names)
        print(f"{a[:10]:10s}{row}  {sum(vals)/len(vals):6.3f}", flush=True)

    print("\n=== 証拠② 反メタGAデッキ: Heuristic評価 → ISMCTS忠実評価 ===", flush=True)
    claim, h, i = challenge()
    print(f"  GAの主張(Heuristic適応度) 対メタ平均 = {claim:.3f}", flush=True)
    for dn in [n for n in h if n != "平均"]:
        print(f"  vs {dn:16s} Heuristic={h[dn]:.3f}  ISMCTS={i[dn]:.3f}", flush=True)
    print(f"  ── 平均           Heuristic={h['平均']:.3f}  ISMCTS={i['平均']:.3f}"
          f"  (崩壊 {i['平均']-h['平均']:+.3f})", flush=True)
    print(f"\n所要 {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

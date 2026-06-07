"""
duel_masters.synergy
====================
自動シナジー発掘。全NDプールから「起爆役(enabler)」と「受け皿(payoff)」を構造的に
抽出して候補クラスタ(=コンボ/部族の核)を生成し、**経験的リフト**(クラスタ濃縮デッキ
と同色の非コンボ対照デッキの忠実勝率差)で各候補を採点・ランクする。

本文から自明でないシナジーも数値で発掘するのが狙い(人間が思いつかない発想力の素)。
出力した上位クラスタは qd / evolve_two_tier の seed_cards に渡して深掘りできる。

設計:
  tag_roles(pool)        各カードに役割タグ(enabler/payoff/race/named-group)を付ける
  mine_candidates(pool)  部族 / 名前グループ / 起爆→受け皿 の候補クラスタを生成
  score_cluster(...)     クラスタ濃縮デッキ vs 同色対照 のリフトを測定(Heuristic→ISMCTS)
  mine_and_rank(...)     全候補を採点しランク表を返す(時間をかけてとことん調査)
"""
from __future__ import annotations
import re
import random
from collections import Counter

from . import carddb, effects, superdim, twinpact, decks, ga, evolve_meta
from .engine import LIGHT, WATER, DARKNESS, FIRE, NATURE

_CIVS = [LIGHT, WATER, DARKNESS, FIRE, NATURE]

# ---- 役割タグ(本文パターン。多くの効果は未実装=テキストが主信号) ----------------
_ENABLER_PAT = {
    "mill_self": r"自分の山札.*(墓地|マナゾーン)",
    "ramp": r"自分の山札.*マナゾーンに置く|マナゾーンに置く.*加速",
    "costdown": r"コスト.*(少なく|軽く)",
    "cheat_out": r"コストを支払わ(ず|ない).*出す|踏み倒",
    "draw": r"カードを\d*枚?引く",
    "recur": r"墓地から.*(手札|バトルゾーン)",
    "untap": r"アンタップ",
    "discard_self": r"自分の手札.*捨て",
    "search": r"山札から.*(探索|公開して.*手札)",
}
_PAYOFF_PAT = {
    "big_cost": None,                       # cost>=7 creature(下で判定)
    "grave_payoff": r"墓地.*(コスト|枚|体|すべて)",
    "wide_payoff": r"クリーチャーの数|体数|多いほど|バトルゾーンにある.*数",
    "spell_payoff": r"呪文を.*唱えた|この?ターン.*呪文",
}
_RACE_COUNT_RE = re.compile(r"(\d+)\s*(枚|体)以上")
_REF_RE = re.compile(r"《([^》]+)》")


def _full_nd_pool(nd_only=True):
    """ゲーム用 full pool(AD込み)＋候補名。nd_only=FalseでAD全体を候補に。"""
    pool, super_pool = decks.build_full_pool(nd_only=False)
    names = set(carddb.load_pool(nd_only=True)) if nd_only else set(pool)
    return pool, super_pool, names


def tag_roles(pool, nd_names):
    """{name: set(roles)}。roles は enabler/payoff のタグ＋'race:X'＋'named:X'。"""
    tags = {}
    for n in nd_names:
        cd = pool.get(n)
        if cd is None or cd.field:
            continue
        t = set()
        txt = cd.text or ""
        for tag, rx in _ENABLER_PAT.items():
            if rx and re.search(rx, txt):
                t.add("E:" + tag)
        for tag, rx in _PAYOFF_PAT.items():
            if rx and re.search(rx, txt):
                t.add("P:" + tag)
        if cd.ctype == "creature" and (cd.cost or 0) >= 7:
            t.add("P:big_cost")
        # 種族カウント払い(受け皿)
        if _RACE_COUNT_RE.search(txt):
            t.add("P:race_count")
        # 登録済みの構造的kind(確実な信号)
        for s in cd.statics:
            t.add("K:" + s.kind)
        # 種族
        for r in cd.races:
            t.add("race:" + r)
        tags[n] = t
    return tags


def _named_groups(pool, nd_names, min_size=3):
    """《X》参照かつ X を名前に含むカードが min_size 枚以上 → 名前グループ(サイクル)。"""
    refset = Counter()
    for n in nd_names:
        cd = pool.get(n)
        if cd is None:
            continue
        for x in _REF_RE.findall(cd.text or ""):
            refset[x] += 1
    groups = {}
    for x in refset:
        if len(x) < 2:
            continue
        members = [n for n in nd_names if x in n]
        if len(members) >= min_size:
            groups[x] = members
    return groups


def _civ_of_names(pool, names):
    c = Counter()
    for n in names:
        for civ in pool[n].civs:
            c[civ] += 1
    return c


def _dominant_civs(pool, names, k=2):
    """names の主要文明(出現上位 最大k色)。無色のみなら火を既定に。"""
    c = _civ_of_names(pool, names)
    if not c:
        return frozenset({FIRE})
    top = [civ for civ, _ in c.most_common(k)]
    return frozenset(top)


def _civ_subpool(pool, nd_names, civs):
    """civs＋無色だけで払える、効果ありorクリーチャーのND候補名。"""
    out = []
    for n in nd_names:
        cd = pool.get(n)
        if cd is None or cd.field:
            continue
        if not (cd.civs <= civs):
            continue
        if cd.ctype == "creature" or cd.abilities or cd.statics or cd.twin_spell:
            out.append(n)
    return out


# ---- 候補クラスタ生成 -------------------------------------------------------
# 各候補 = dict(label, civs, payoffs[シナジーの肝], support[起爆/部族支援], why)
def mine_candidates(pool, nd_names, tags):
    cands = []

    # 1) 部族シナジー: 主要種族 × その種族の受け皿(race_count/部族支援)
    race_members = {}
    for n, t in tags.items():
        for tag in t:
            if tag.startswith("race:"):
                race_members.setdefault(tag[5:], []).append(n)
    for race, members in race_members.items():
        if len(members) < 14:           # 母数が薄い種族は除外
            continue
        payoffs = [n for n in members if "P:race_count" in tags[n]
                   or "P:wide_payoff" in tags[n]]
        support = [n for n in members
                   if pool[n].ctype == "creature" and (pool[n].cost or 9) <= 4]
        if not payoffs or len(support) < 6:
            continue
        civs = _dominant_civs(pool, members, k=2)
        cands.append(dict(
            label=f"部族:{race}", civs=civs,
            payoffs=payoffs[:6], support=support,
            why=f"{race} {len(members)}枚, 受け皿 {len(payoffs)}枚"))

    # 2) 名前グループ(サイクル): 《X》参照かつ X を名前に持つ群
    for x, members in _named_groups(pool, nd_names).items():
        if len(members) < 4:
            continue
        civs = _dominant_civs(pool, members, k=3)
        cands.append(dict(
            label=f"名前群:{x}", civs=civs,
            payoffs=members[:8], support=[],
            why=f"《{x}》サイクル {len(members)}枚"))

    # 3) 起爆→受け皿アーキタイプ
    def has(n, tag):
        return tag in tags.get(n, ())
    archs = [
        ("自山掘り→墓地蘇生", "E:mill_self", "E:recur"),
        ("軽減/踏み倒し→大型", "E:costdown", "P:big_cost"),
        ("踏み倒し→大型", "E:cheat_out", "P:big_cost"),
        ("ドロー連打→呪文受け皿", "E:draw", "P:spell_payoff"),
    ]
    for label, en_tag, pay_tag in archs:
        enablers = [n for n in nd_names if has(n, en_tag)]
        payoffs = [n for n in nd_names if has(n, pay_tag)]
        if len(enablers) < 4 or len(payoffs) < 3:
            continue
        # 共通文明で固める(最も多い色)
        pool_names = enablers + payoffs
        civs = _dominant_civs(pool, pool_names, k=2)
        en2 = [n for n in enablers if pool[n].civs <= civs][:8]
        pay2 = [n for n in payoffs if pool[n].civs <= civs][:6]
        if len(en2) < 3 or len(pay2) < 2:
            continue
        cands.append(dict(
            label=f"起爆:{label}", civs=civs,
            payoffs=pay2, support=en2,
            why=f"起爆{len(en2)}/受け皿{len(pay2)}({''.join(sorted(civs))})"))
    return cands


# ---- 経験的リフト測定(受け皿入り vs 同色・受け皿なし対照) --------------------
def _build_deck(pool, nd_names, civs, must, rng):
    """must(Counter, 最大4枚)を核に、同色サブプールで40枚に整える。"""
    sub = _civ_subpool(pool, nd_names, civs) or list(nd_names)
    deck = Counter()
    for n, c in must.items():
        if n in pool:
            deck[n] = min(ga.MAX_COPIES, c)
    return ga.repair(deck, sub, rng)


def score_cluster(pool, super_pool, nd_names, cand, gauntlet, rng,
                  games=4, pilot=None):
    """リフト = fit(受け皿入り濃縮) − fit(受け皿を同色汎用に置換した対照)。
    正なら『受け皿が汎用カードより価値を生む=シナジー』。"""
    civs = cand["civs"]
    payoffs = [n for n in cand["payoffs"] if n in pool and pool[n].civs <= civs]
    support = [n for n in cand.get("support", []) if pool[n].civs <= civs]
    if not payoffs:
        return None
    # 濃縮: 受け皿を4枚ずつ + 支援を厚めに + 同色フィラー
    must = Counter()
    for n in payoffs[:4]:
        must[n] = 4
    for n in support[:5]:
        must[n] = max(must[n], 2)
    conc = _build_deck(pool, nd_names, civs, must, rng)
    # 対照: 受け皿を入れず、支援だけ + 同色フィラー(同じ色・枚数構成の"汎用"デッキ)
    ctrl_must = Counter()
    for n in support[:5]:
        ctrl_must[n] = max(ctrl_must[n], 2)
    ctrl = _build_deck(pool, nd_names, civs,
                       {n: c for n, c in ctrl_must.items() if n not in payoffs}, rng)
    fk = dict(games=games, pilot=pilot)
    f_conc = evolve_meta.fitness_vs_meta(pool, super_pool, conc, gauntlet, **fk)
    f_ctrl = evolve_meta.fitness_vs_meta(pool, super_pool, ctrl, gauntlet, **fk)
    return dict(label=cand["label"], civs="".join(sorted(civs)),
                conc=f_conc, ctrl=f_ctrl, lift=f_conc - f_ctrl,
                why=cand["why"], deck=conc, payoffs=payoffs[:4])


def mine_and_rank(games=4, seed=42, ismcts_top=5, verbose=True, nd_only=True):
    """全候補を生成→Heuristicリフトで採点→上位を ISMCTS で再採点しランク。
    nd_only=False でAD全体(約3942種)からシナジーを発掘。"""
    rng = random.Random(seed)
    pool, super_pool, nd = _full_nd_pool(nd_only=nd_only)
    tags = tag_roles(pool, nd)
    cands = mine_candidates(pool, nd, tags)
    gauntlet = [decks.decklist(n) for n in decks.DECKS]
    if verbose:
        print(f"候補クラスタ {len(cands)}件を採点(Heuristicリフト)…", flush=True)
    scored = []
    for c in cands:
        r = score_cluster(pool, super_pool, nd, c, gauntlet, rng, games=games)
        if r:
            scored.append(r)
            if verbose:
                print(f"  {r['label']:22s}[{r['civs']}] 濃縮{r['conc']:.3f} "
                      f"対照{r['ctrl']:.3f} リフト{r['lift']:+.3f}  {r['why']}",
                      flush=True)
    scored.sort(key=lambda r: -r["lift"])
    # 上位を ISMCTS で濃縮デッキの対メタ勝率を確認
    top = scored[:ismcts_top]
    if verbose:
        print("\n上位を ISMCTS忠実評価(濃縮デッキ対メタ)…", flush=True)
    for r in top:
        main = ga.deck_to_list(r["deck"])
        iw = sum(decks.play_match(pool, super_pool, (main, []),
                                  decks.decklist(dn), games=6, seed0=4242,
                                  pilot=decks.eval_pilot) for dn in decks.DECKS) / 4
        r["ismcts"] = iw
        if verbose:
            print(f"  {r['label']:22s} ISMCTS対メタ {iw:.3f} (Heuristicリフト{r['lift']:+.3f})",
                  flush=True)
    return scored


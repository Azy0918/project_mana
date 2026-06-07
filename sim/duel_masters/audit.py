"""
duel_masters.audit
==================
artifact 監査: 「コストに対して強すぎる」カード=未実装のデメリットを持つ疑いを系統的に
洗い出す。シナジー発掘でグランセクト(c1 P12000 T・ブレイカー)が攻撃制限未実装で壊れて
いた件の一般化。GA/QD/シナジー探索は壊れカードに引き寄せられるので、ここを潰すと
すべての探索とメタ評価の忠実度が上がる。

手法: クリーチャーのスタッツ効率(パワー+キーワード価値)/コスト を計算し、高効率の
外れ値を抽出。各候補の本文にデメリット文言(攻撃/召喚できない・条件・離場時など)が
あるのに効果未登録なら『未実装デメリットの疑い』として警告する。
"""
from __future__ import annotations
import re

from . import carddb, effects

_KW_VALUE = {
    "speed_attacker": 2000, "blocker": 1000,
    "w_breaker": 3000, "t_breaker": 6000, "q_breaker": 9000,
    "world_breaker": 12000, "master_breaker": 5000,
}

# 未実装だと壊れる典型デメリット文言
_DRAWBACK_PAT = {
    "攻撃制限": r"攻撃できない",
    "召喚/出せない制限": r"(召喚できない|バトルゾーンに出せない|出せない)",
    "条件付き(なければ/あれば)": r"(なければ|あれば|以上なら|未満なら)",
    "離場/ターン終了で消える": r"(ターンの(終わり|おわり|終了).*(破壊|山札|手札|マナ)|離れた時)",
    "自壊/破壊される": r"(このクリーチャーを破壊する|自身を破壊|破壊される)",
    "タップイン/出た時タップ": r"タップして(バトルゾーン|出)",
    "相手に選ばせる/公開": r"(相手に見せ|相手が選ぶ)",
    "コスト条件召喚": r"あれば.*支払って召喚|支払うかわりに",
}


def stat_value(cd):
    base = cd.power or 0
    for k, v in _KW_VALUE.items():
        if k in cd.keywords:
            base += v
    return base


def _has_effect(cd):
    return bool(cd.abilities or cd.statics or cd.twin_spell)


def audit(nd_only=True, min_power=6000, max_cost=4, eff_thresh=3500,
          require_drawback=True):
    """スタッツ効率の高い外れ値クリーチャーを抽出し、未実装デメリットの疑いを警告。
    戻り値: [(eff, name, cost, power, kw, drawbacks, has_effect, text)] を効率降順。"""
    pool = carddb.load_pool(nd_only=nd_only)
    effects.apply_effects(pool)
    rows = []
    for n, cd in pool.items():
        if cd.ctype != "creature" or not cd.cost:
            continue
        sv = stat_value(cd)
        eff = sv / cd.cost
        # 外れ値: (低コスト高パワー) または (高効率)
        cheap_huge = (cd.cost <= max_cost and (cd.power or 0) >= min_power)
        if not (cheap_huge or eff >= eff_thresh):
            continue
        txt = cd.text or ""
        drawbacks = [label for label, rx in _DRAWBACK_PAT.items()
                     if re.search(rx, txt)]
        if require_drawback and not drawbacks:
            continue
        rows.append((round(eff), n, cd.cost, cd.power, "".join(sorted(cd.keywords)),
                     drawbacks, _has_effect(cd), txt))
    rows.sort(key=lambda r: -r[0])
    return rows


def report(rows, top=40):
    out = [f"artifact監査: 効率外れ値かつデメリット文言あり {len(rows)}件(効率降順)"]
    for eff, n, cost, power, kw, dbs, has, txt in rows[:top]:
        flag = "  [効果登録済]" if has else "  ★未実装の疑い"
        out.append(f"  eff{eff:5d} c{cost} P{power} {kw:14s} {n}{flag}")
        out.append(f"        デメリット: {', '.join(dbs)}")
    return "\n".join(out)

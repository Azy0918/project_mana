"""
duel_masters.gauntlet
=====================
GA の fitness 相手となる「人間風」アーキタイプ・ガントレット。

ga.build_gauntlet の自動2デッキは戦略が単調で順位の分解能が出なかった
(耐久ランで上位が全部 base勝率0.9 に張り付いた)。MetaStone の構成に倣い、
**戦略の異なる複数の固定デッキ**を相手に据えて勝率に幅を作る。火単色には
ブロッカーが無い(火は攻撃的文明)ので「受け」は S・トリガー + 除去呪文で表現。

設計方針:
- 敗北拒否デッキ以外は、プールから役割でプログラム的に構築(カード名のタイポに
  強い)。敗北拒否デッキだけ effects.py 登録済みの核を実名指定し、欠けは除外。
- 全デッキ「プールに実在するカードだけ」で必ず40枚に整える(build_deck が確実に
  通る)。同名4枚まで。
- 敗北拒否デッキを入れることで、進化は「それを倒すか/採り込むか」を迫られ、
  狙いの未開拓軸が表出しやすくなる。
"""
from __future__ import annotations
from collections import Counter

DECK_SIZE = 40
MAX_COPIES = 4

# 敗北拒否パッケージの核(effects.py の登録名と一致させること)。
_LOSS_REFUSAL_CORE = [
    "“血煙” マキシマム", "グッド“MSL”バウンサー",
    "グレイト“S-駆”", "ミサイル“J-飛”", "“E-闘”ララッタ",
    "一番隊 チュチュリス", "“R-夢”ララッタ", "“K-殴”ララッタ",
]


def _creatures(pool, cand):
    return [n for n in cand if pool[n].ctype == "creature"]


def _fill_to_size(deck, filler_names, *, size=DECK_SIZE, cap=MAX_COPIES):
    """deck を filler_names の順で size 枚まで埋める(同名 cap 枚まで)。決定論的。"""
    for n in filler_names:
        total = sum(deck.values())
        if total >= size:
            break
        room = min(cap - deck.get(n, 0), size - total)
        if room > 0:
            deck[n] += room
    return deck


def _from_priority(pool, cand, primary, filler, *, size=DECK_SIZE):
    """primary を優先採用 → filler で40枚に補完。実在カードのみ。"""
    cset = set(cand)
    deck = Counter()
    primary = [n for n in primary if n in cset]
    filler = [n for n in filler if n in cset]
    _fill_to_size(deck, primary, size=size)
    if sum(deck.values()) < size:
        _fill_to_size(deck, filler, size=size)
    return deck


# ---- 各アーキタイプ --------------------------------------------------------

def _aggro(pool, cand):
    """超速アグロ: 1〜3コスの高パワー、スピードアタッカー優先で顔を詰める。"""
    cr = _creatures(pool, cand)
    low = [n for n in cr if pool[n].cost <= 3]
    low.sort(key=lambda n: (pool[n].cost,
                            -((pool[n].power or 0)
                              + (1500 if "speed_attacker" in pool[n].keywords else 0))))
    cheap_filler = sorted(cr, key=lambda n: (pool[n].cost, -(pool[n].power or 0)))
    return _from_priority(pool, cand, low, cheap_filler)


def _midrange(pool, cand):
    """中速ビート: コスト3〜6でパワー効率の良い体、W・ブレイカー優先 + 除去。"""
    cr = _creatures(pool, cand)
    mid = [n for n in cr if 3 <= pool[n].cost <= 6]
    mid.sort(key=lambda n: -((pool[n].power or 0) / max(1, pool[n].cost)
                             + (1500 if "w_breaker" in pool[n].keywords else 0)))
    removal = [n for n in cand if pool[n].ctype == "spell" and pool[n].abilities]
    filler = sorted(cr, key=lambda n: -((pool[n].power or 0) / max(1, pool[n].cost)))
    return _from_priority(pool, cand, mid[:8] + removal + mid[8:], filler)


def _control_burn(pool, cand):
    """受け寄りバーン: S・トリガー持ち + 除去呪文 + 重いフィニッシャー。
    火にブロッカーは無いので、トリガーと除去で受けてから大型で殴り返す。"""
    cr = _creatures(pool, cand)
    st_creatures = [n for n in cr if "shield_trigger" in pool[n].keywords]
    removal = [n for n in cand if pool[n].ctype == "spell" and pool[n].abilities]
    finishers = sorted([n for n in cr if pool[n].cost >= 7],
                       key=lambda n: -(pool[n].power or 0))
    primary = removal + st_creatures + finishers
    filler = sorted(cr, key=lambda n: -(pool[n].power or 0))
    return _from_priority(pool, cand, primary, filler)


def _loss_refusal(pool, cand):
    """敗北拒否コンボ: 血煙/MSL + G・G・G 群 + 軽量火 + 除去。
    狙いの未開拓軸そのもの。進化に『これを倒すか採るか』を迫る相手。"""
    cr = _creatures(pool, cand)
    removal = [n for n in cand if pool[n].ctype == "spell" and pool[n].abilities]
    cheap = sorted([n for n in cr if pool[n].cost <= 3],
                   key=lambda n: (pool[n].cost, -(pool[n].power or 0)))
    primary = _LOSS_REFUSAL_CORE + removal
    filler = cheap + sorted(cr, key=lambda n: pool[n].cost)
    return _from_priority(pool, cand, primary, filler)


def build_human_gauntlet(pool, cand):
    """(name, deck) のリスト。戦略の異なる4アーキタイプ。"""
    builders = [
        ("超速アグロ", _aggro),
        ("中速ビート", _midrange),
        ("受けバーン", _control_burn),
        ("敗北拒否コンボ", _loss_refusal),
    ]
    out = []
    for name, fn in builders:
        deck = fn(pool, cand)
        # 念のため: 万一40枚未満なら最安クリーチャーで補完。
        if sum(deck.values()) < DECK_SIZE:
            _fill_to_size(deck, sorted(_creatures(pool, cand),
                                       key=lambda n: pool[n].cost))
        out.append((name, deck))
    return out

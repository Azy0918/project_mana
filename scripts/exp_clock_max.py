"""ボトルネックはロックではなくクロックか? の検証。

exp_double_lock.py で「ロックを深めると悪化」を確認した。本実験は逆に
クロック(速攻ボディ)を最大化し、ロック(ギガボルバ)の有無で比較する。
  A) pure-aggro: ロック無し・全クロック
  B) clock-max + ギガボルバ: 遅い防御札を速攻ボディに差し替え、ロックは維持
要塞 id=78 相手に多試合で測る。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.effects.store import load_approved_effects_map
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.runner import simulate_matches

GAMES = 400
SEED = 20260615


def rec(conn, name, qty):
    cid, nm, civ, cost, ct, pw, text = conn.execute(
        "select card_id,name,civilization,cost,card_type,power,text from cards where name=? limit 1",
        (name,),
    ).fetchone()
    return dict(card_id=cid, name=nm, civilization=civ or "", cost=cost or 0,
               card_type=ct or "", power=pw or 0, text=text or "", quantity=qty)


def build(conn, spec):
    return [rec(conn, n, q) for n, q in spec]


def count(deck):
    return sum(int(c["quantity"]) for c in deck)


def report(label, s):
    print(f"{label:30s} 勝率 {s.win_rate_a*100:5.1f}%  "
          f"CI95[{s.ci95_low_a*100:4.1f},{s.ci95_high_a*100:4.1f}]  avgT {s.average_turns:4.1f}")


def main():
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    eff = load_approved_effects_map(DEFAULT_DB_PATH)
    fortress = json.loads(conn.execute(
        "select deck_cards_json from generated_decks where id=78").fetchone()[0])

    # 速攻クロック主体の共通骨格(闇火)
    clock_core = [
        ("アッポー・チュリス", 4),       # 火c2
        ("斬込隊長マサト", 4),           # 火c2 SA
        ("エグゼズ・ワイバーン", 4),     # 火c3 SA P5000
        ("音速 ビュン", 4),              # 火c2 SA
        ("クリムゾン・チャージャー", 4), # 火 アグロ
        ("ハンマー野郎 オニドツキ", 4),  # 闇火
        ("地獄門デス・ゲート", 4),       # 除去(ブロッカー処理)
    ]  # = 28

    pure = build(conn, clock_core + [
        ("カニ★ニカ", 4), ("衰弱の影ダーク・メア", 4),
        ("追撃のライゼン", 4),
    ])
    assert count(pure) == 40, count(pure)
    print(f"pure-aggro ({count(pure)}枚, ロック無し) vs 要塞id=78, {GAMES}試合")
    report("pure-aggro (ロック無し)",
           simulate_matches(pure, fortress, games=GAMES, seed=SEED, effects=eff))

    clockmax = build(conn, clock_core + [
        ("ギガボルバ", 4),                # 光ロック維持
        ("カニ★ニカ", 4),
        ("衰弱の影ダーク・メア", 4),
    ])
    assert count(clockmax) == 40, count(clockmax)
    print(f"\nclock-max + ギガボルバ ({count(clockmax)}枚)")
    report("clock-max + ギガボルバ",
           simulate_matches(clockmax, fortress, games=GAMES, seed=SEED, effects=eff))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

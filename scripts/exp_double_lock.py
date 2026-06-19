"""「ロックとクロックの分離」は db 内で解消できるか? の実証実験。

要塞 id=78 は光闇。そのS・トリガーを完全に止めるには db 内では
  ギガボルバ(闇c4 → 光ロック) と フ・レイル(光c6 → 闇ロック)
の両方が要る。id=82 はギガボルバのみ採用で、闇S・トリガーは素通りしている。

本実験は id=82 のベースラインと、フ・レイルを足した「両civロック版」を
要塞 id=78 相手に多試合で比較し、二重ロックが分離限界を緩和するかを測る。
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


def load_deck(conn: sqlite3.Connection, deck_id: int) -> list[dict]:
    j = conn.execute(
        "select deck_cards_json from generated_decks where id=?", (deck_id,)
    ).fetchone()[0]
    return json.loads(j)


def card_record(conn: sqlite3.Connection, name: str) -> dict:
    cid, nm, civ, cost, ct, pw, text = conn.execute(
        "select card_id,name,civilization,cost,card_type,power,text from cards where name=?",
        (name,),
    ).fetchone()
    return dict(card_id=cid, name=nm, civilization=civ or "", cost=cost or 0,
               card_type=ct or "", power=pw or 0, text=text or "", quantity=1)


def deck_count(deck: list[dict]) -> int:
    return sum(int(c.get("quantity", 1)) for c in deck)


def set_qty(deck: list[dict], name: str, qty: int) -> None:
    for c in deck:
        if c["name"] == name:
            c["quantity"] = qty
            return
    raise KeyError(name)


def report(label: str, summary) -> None:
    print(f"{label:32s} 勝率 {summary.win_rate_a*100:5.1f}%  "
          f"CI95[{summary.ci95_low_a*100:4.1f},{summary.ci95_high_a*100:4.1f}]  "
          f"avgT {summary.average_turns:4.1f}  {dict(summary.finish_reasons)}")


def main() -> int:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    effects = load_approved_effects_map(DEFAULT_DB_PATH)
    fortress = load_deck(conn, 78)

    base = load_deck(conn, 82)
    print(f"id=82 baseline ({deck_count(base)}枚) vs 要塞id=78, {GAMES}試合")
    report("baseline (ギガボルバのみ)",
           simulate_matches(base, fortress, games=GAMES, seed=SEED, effects=effects))

    # 両civロック版: 重い非ロックカードを削ってフ・レイル×4を投入。
    # 削る: 炎龍秘伝カイザー・フレイム x2 -> 0, ジャックポット x1 -> 0, ファンタズム・クラッチ 3 -> 2
    dual = [dict(c) for c in load_deck(conn, 82)]
    set_qty(dual, "炎龍秘伝カイザー・フレイム", 0)
    set_qty(dual, "ジャックポット・バトライザー", 0)
    set_qty(dual, "ファンタズム・クラッチ", 2)
    dual = [c for c in dual if int(c.get("quantity", 1)) > 0]
    furail = card_record(conn, "暴風の求道者フ・レイル")
    furail["quantity"] = 4
    dual.append(furail)
    print(f"\ndual lock ({deck_count(dual)}枚): +フ・レイル×4 (光スプラッシュ)")
    report("dual lock (光ロック+闇ロック)",
           simulate_matches(dual, fortress, games=GAMES, seed=SEED, effects=effects))

    # 参考: フ・レイル単独ロック版(ギガボルバ抜き=闇のみロック)で
    # 「片方ロックでは効かない」が光闇どちらでも同様かを確認。
    only_dark = [dict(c) for c in load_deck(conn, 82)]
    set_qty(only_dark, "ギガボルバ", 0)
    set_qty(only_dark, "炎龍秘伝カイザー・フレイム", 0)
    only_dark = [c for c in only_dark if int(c.get("quantity", 1)) > 0]
    f2 = card_record(conn, "暴風の求道者フ・レイル")
    f2["quantity"] = 4
    only_dark.append(f2)
    # 枚数調整
    diff = 40 - deck_count(only_dark)
    if diff != 0:
        set_qty(only_dark, "ファンタズム・クラッチ", 3 + diff)
    print(f"\nonly-dark lock ({deck_count(only_dark)}枚): フ・レイルのみ(闇ロック)")
    report("only-dark (闇ロックのみ)",
           simulate_matches(only_dark, fortress, games=GAMES, seed=SEED, effects=effects))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

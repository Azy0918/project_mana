"""闇単(夜間探索の最有力49.4)を起点に深く精錬し、db最強の非要塞デッキを探す。

要塞は db 内で撃破不能(別途確定)。ゆえに達成可能な発見は「フィールド層の真の天井」。
闇単シードから run_hybrid_search を深く回し、フルメタ+非要塞サブセット双方で採点する。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.effects.store import load_approved_effects_map
from src.battle.hybrid_search import run_hybrid_search
from src.battle.rating.meta_rating import load_meta_battle_decks, rate_deck_against_meta
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.runner import simulate_matches

JL = Path(__file__).resolve().parent.parent / "data" / "reports" / "night_novelty.jsonl"


def load_seed(tag: str):
    deck = None
    for line in JL.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["tag"] == tag:
            deck = r["deck"]
    if not deck:
        raise SystemExit(f"seed {tag} not found")
    import sqlite3
    c = sqlite3.connect(DEFAULT_DB_PATH)
    out = []
    for name, qty in deck:
        row = c.execute(
            "select card_id,name,civilization,cost,card_type,power,text from cards where name=? limit 1",
            (name,)).fetchone()
        if not row:
            continue
        cid, nm, civ, cost, ct, pw, text = row
        out.append(dict(card_id=cid, name=nm, civilization=civ or "", cost=cost or 0,
                        card_type=ct or "", power=pw or 0, text=text or "", quantity=qty))
    return out


def field_winrate(deck, effects, seed):
    decks, _ = load_meta_battle_decks()
    field = [d for d in decks if not ("要塞" in d["deck_name"] or "定義版" in d["deck_name"]
                                       or "対光闇要塞" in d["deck_name"])]
    tot = 0.0
    detail = []
    for i, m in enumerate(field):
        s = simulate_matches(deck, m["cards"], games=60, seed=seed + i, effects=effects)
        tot += s.win_rate_a
        detail.append((m["deck_name"], round(s.win_rate_a, 3)))
    return tot / len(field), sorted(detail, key=lambda x: x[1])


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "yami_mono"
    civ = sys.argv[2].split(",") if len(sys.argv) > 2 else ["闇"]
    seed = int(time.time()) % 100000
    eff = load_approved_effects_map(DEFAULT_DB_PATH)
    seed_deck = load_seed(tag)

    base_field, base_detail = field_winrate(seed_deck, eff, seed)
    print(f"seed {tag}: 非要塞フィールド平均 {base_field*100:.1f}%")

    res = run_hybrid_search(
        db_path=DEFAULT_DB_PATH, generations=22, population_size=18,
        civilizations=civ, seed=seed, sim_games=50, sim_opponents=5,
        sim_weight=0.85, rotate_opponents=True, rotation_period=2,
        max_card_types=18, seed_deck=seed_deck, robustness_weight=0.3,
    )
    best = res["best"]["deck"]
    field, detail = field_winrate(best, eff, seed)
    rating = rate_deck_against_meta(best, f"deepfield_{tag}", games_per_pair=80,
                                    seed=seed, effects=eff, save=False)
    print(f"refined {tag}: 非要塞フィールド平均 {field*100:.1f}%  (seed比 {(field-base_field)*100:+.1f})")
    print(f"  フルメタ強さ {rating['strength_score']}")
    print(f"  field worst3: {detail[:3]}")
    print(f"  field best3:  {detail[-3:]}")
    agg = {}
    for c in best:
        agg[c["name"]] = agg.get(c["name"], 0) + int(c.get("quantity", 1))
    sig = sorted(agg.items(), key=lambda x: -x[1])
    print("  deck:", sig)

    with JL.open("a") as f:
        f.write(json.dumps({"tag": f"deepfield_{tag}", "civs": civ, "seed": seed,
                            "strength_score": rating["strength_score"],
                            "field_winrate": round(field, 4),
                            "deck": sig,
                            "vs_fortress": [(d["opponent"], round(d["win_rate"], 3))
                                            for d in rating["details"]
                                            if "要塞" in d["opponent"] or "定義版" in d["opponent"]],
                            }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

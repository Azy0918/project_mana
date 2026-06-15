"""過大評価是正後の忠実層で、反要塞デッキを再探索する。

第五十二弾で要塞のフルメタ強さが91.3→80.8に下がり、反要塞が約36-38%まで肉薄。
忠実層で要塞を崩せる(勝ち越せる)構築がdb内に在るかを、メタデッキseedから再探索する。

usage: python3 scripts/anti_fortress_refine.py "<seed deck name substr>" "<civs>"
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.effects.store import load_approved_effects_map
from src.battle.hybrid_search import run_hybrid_search
from src.battle.rating.meta_rating import load_meta_battle_decks
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.runner import simulate_matches


def main():
    seed_sub = sys.argv[1] if len(sys.argv) > 1 else "火コントロールv2"
    civs = sys.argv[2].split(",") if len(sys.argv) > 2 else ["火"]
    seed = int(time.time()) % 100000
    eff = load_approved_effects_map(DEFAULT_DB_PATH)
    decks, _ = load_meta_battle_decks()
    fortress = next(d for d in decks if "定義版" in d["deck_name"])
    seed_deck = next(d for d in decks if seed_sub in d["deck_name"])

    def vs_fortress(cards, games=300):
        return simulate_matches(cards, fortress["cards"], games=games, seed=seed, effects=eff).win_rate_a

    base = vs_fortress(seed_deck["cards"])
    print(f"seed [{seed_deck['deck_name'][:30]}] vs 定義版(忠実層): {base*100:.1f}%")

    res = run_hybrid_search(
        db_path=DEFAULT_DB_PATH, generations=20, population_size=18,
        civilizations=civs, seed=seed, sim_games=44, sim_opponents=5,
        sim_weight=0.85, rotate_opponents=True, rotation_period=2,
        max_card_types=18, seed_deck=[dict(c) for c in seed_deck["cards"]],
        robustness_weight=0.3,
    )
    best = res["best"]["deck"]
    win = vs_fortress(best)
    print(f"refined vs 定義版(忠実層): {win*100:.1f}%  (seed比 {(win-base)*100:+.1f})")
    agg = {}
    for c in best:
        agg[c["name"]] = agg.get(c["name"], 0) + int(c.get("quantity", 1))
    print("deck:", sorted(agg.items(), key=lambda x: -x[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

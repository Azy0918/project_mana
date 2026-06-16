"""id=86 火速攻ドラゴンを反復精錬し、要塞を抜いて単独首位を狙う強化ループ。

是正後の忠実層で、seedデッキ→hybrid探索→対要塞(500試合)+フルメタ採点→
改善があれば champion.json を更新。civ splashも試せる。

usage: python3 scripts/strengthen_id86.py <civs> [seed_json_path]
  civs: "火" or "火,光" など。seed未指定なら generated_decks id=86 か champion.json。
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

CHAMP = Path(__file__).resolve().parent.parent / "data" / "reports" / "champion.json"


def load_seed(path_arg):
    import sqlite3
    if path_arg and Path(path_arg).exists():
        d = json.loads(Path(path_arg).read_text())
        return d["deck"]
    if CHAMP.exists():
        return json.loads(CHAMP.read_text())["deck"]
    c = sqlite3.connect(DEFAULT_DB_PATH)
    return json.loads(c.execute("select deck_cards_json from generated_decks where id=86").fetchone()[0])


def expand(deck):
    """[{name,quantity,...}] -> full card dicts (already are)."""
    return [dict(x) for x in deck]


def metrics(deck, eff, fortress, label):
    wins = []
    for sd in (101, 202):
        s = simulate_matches(deck, fortress["cards"], games=500, seed=sd, effects=eff)
        wins.append(s.win_rate_a)
    vf = sum(wins) / len(wins)
    r = rate_deck_against_meta(deck, label, games_per_pair=80, seed=5, effects=eff, save=False)
    return vf, r["strength_score"], r["details"]


def main():
    civs = sys.argv[1].split(",") if len(sys.argv) > 1 else ["火"]
    seed_path = sys.argv[2] if len(sys.argv) > 2 else None
    rng_seed = int(time.time()) % 100000
    eff = load_approved_effects_map(DEFAULT_DB_PATH)
    decks, _ = load_meta_battle_decks()
    fortress = next(d for d in decks if "定義版" in d["deck_name"])

    seed_deck = expand(load_seed(seed_path))
    base_vf, base_str, _ = metrics(seed_deck, eff, fortress, "seed")
    print(f"seed: vs要塞 {base_vf*100:.1f}%  フルメタ {base_str:.1f}")

    res = run_hybrid_search(
        db_path=DEFAULT_DB_PATH, generations=26, population_size=20,
        civilizations=civs, seed=rng_seed, sim_games=48, sim_opponents=6,
        sim_weight=0.85, rotate_opponents=True, rotation_period=2,
        max_card_types=18, seed_deck=seed_deck, robustness_weight=0.3,
    )
    best = res["best"]["deck"]
    vf, strg, details = metrics(best, eff, fortress, f"champ_{'_'.join(civs)}")
    print(f"refined({','.join(civs)}): vs要塞 {vf*100:.1f}%  フルメタ {strg:.1f}  "
          f"(seed比 要塞{(vf-base_vf)*100:+.1f} 強さ{strg-base_str:+.1f})")
    agg = {}
    for cc in best:
        agg[cc["name"]] = agg.get(cc["name"], 0) + int(cc.get("quantity", 1))
    sig = sorted(agg.items(), key=lambda x: -x[1])

    # championは「フルメタ強さ」で判定(要塞超え=単独首位の指標)
    champ_str = json.loads(CHAMP.read_text())["strength"] if CHAMP.exists() else base_str
    if strg > champ_str:
        CHAMP.write_text(json.dumps({"deck": best, "strength": strg, "vs_fortress": vf,
                                     "civs": civs, "sig": sig}, ensure_ascii=False))
        print(f"  ★champion更新: フルメタ {strg:.1f} (旧{champ_str:.1f})")
    print("  deck:", sig)
    det = sorted(details, key=lambda d: d["win_rate"])
    print("  worst3:", [(d["opponent"][:16], round(d["win_rate"], 2)) for d in det[:3]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

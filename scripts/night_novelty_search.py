"""夜間自動運転: 広域 novelty 探索。

要塞専用ではなく、メタ全体に対して組織的に強い未開拓型を頑健性重み付きで掘る。
1回の呼び出しで: 指定civ群でハイブリッド探索 → best をフルメタで採点 →
要塞(光闇)とのマッチを抽出 → 結果をJSONで results/ に追記。
db(generated_decks)には保存しない(id=82の轍を踏まない)。採用判断は人が行う。

usage: python3 scripts/night_novelty_search.py <civ1[,civ2,...]> [tag]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.effects.store import load_approved_effects_map
from src.battle.hybrid_search import run_hybrid_search
from src.battle.rating.meta_rating import rate_deck_against_meta
from src.battle.rating.store import DEFAULT_DB_PATH

OUT = Path(__file__).resolve().parent.parent / "data" / "reports" / "night_novelty.jsonl"


def deck_signature(deck):
    agg = {}
    for c in deck:
        agg[c["name"]] = agg.get(c["name"], 0) + int(c.get("quantity", 1))
    return sorted(agg.items(), key=lambda x: (-x[1], x[0]))


def main():
    civs = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "-" else None
    tag = sys.argv[2] if len(sys.argv) > 2 else (",".join(civs) if civs else "multi")
    seed = int(time.time()) % 100000

    res = run_hybrid_search(
        db_path=DEFAULT_DB_PATH,
        generations=14,
        population_size=16,
        civilizations=civs,
        seed=seed,
        sim_games=40,
        sim_opponents=4,
        sim_weight=0.8,
        rotate_opponents=True,
        rotation_period=3,
        max_card_types=16,
        robustness_weight=0.25,  # 最悪マッチを底上げ=過適合でなく汎用強さを志向
    )
    best = res.get("best")
    if not best:
        print("no best:", res.get("warnings"))
        return 1
    deck = best["deck"]
    eff = load_approved_effects_map(DEFAULT_DB_PATH)
    rating = rate_deck_against_meta(
        deck, f"night_{tag}", games_per_pair=60, seed=seed,
        effects=eff, save=False,
    )
    details = sorted(rating["details"], key=lambda d: d["win_rate"])
    fortress = [d for d in rating["details"] if "要塞" in d["opponent"] or "定義版" in d["opponent"]]
    rec = {
        "tag": tag, "civs": civs, "seed": seed,
        "strength_score": rating.get("strength_score"),
        "win_rate": rating.get("win_rate"),
        "search_sim_win": best["sim_win_rate"],
        "search_worst": best["worst_matchup"],
        "worst3": [(d["opponent"], round(d["win_rate"], 3)) for d in details[:3]],
        "best3": [(d["opponent"], round(d["win_rate"], 3)) for d in details[-3:]],
        "vs_fortress": [(d["opponent"], round(d["win_rate"], 3)) for d in fortress],
        "deck": deck_signature(deck),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"=== {tag} (seed {seed}) ===")
    print(f"meta strength: {rating.get('strength_score')}  avg win {rating.get('win_rate')}")
    print(f"worst3: {rec['worst3']}")
    print(f"best3:  {rec['best3']}")
    print(f"vs要塞: {rec['vs_fortress']}")
    print("deck:", rec["deck"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

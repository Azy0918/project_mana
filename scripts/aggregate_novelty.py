"""night_novelty.jsonl を読み、新規性スコア付きでランク集計する。

新規性 = (デッキ採用カードのうち現メタプール199語彙に無いカードの種類割合)。
強さ(meta strength)と新規性の両方を見て「未開拓かつ競技的」候補を浮かび上がらせる。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.rating.meta_rating import load_meta_battle_decks

JL = Path(__file__).resolve().parent.parent / "data" / "reports" / "night_novelty.jsonl"


def main():
    decks, _ = load_meta_battle_decks()
    vocab = set()
    for d in decks:
        vocab |= {c["name"] for c in d["cards"]}

    rows = []
    for line in JL.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        names = [n for n, q in r["deck"]]
        novel = [n for n in names if n not in vocab]
        novelty = len(novel) / max(1, len(names))
        rows.append((r.get("strength_score") or 0, novelty, r["tag"], r.get("vs_fortress"), novel[:6]))

    rows.sort(reverse=True)
    print(f"{'strength':>8} {'novelty':>7}  tag")
    print("-" * 60)
    for s, nv, tag, fort, novel in rows:
        fb = max((w for _, w in (fort or [])), default=0)
        print(f"{s:8.1f} {nv*100:6.0f}%  {tag:18s} vs要塞best {fb*100:4.1f}%  新規例:{novel}")


if __name__ == "__main__":
    raise SystemExit(main())

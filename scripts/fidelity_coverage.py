"""シミュレーション忠実度カバレッジ計測。

目標: 全カードを exact(現実と1対1)に模擬する。本スクリプトは進捗(あの表)を
自動計測し、exact率を 5178/5178 まで動かす過程を可視化する。

usage: python3 scripts/fidelity_coverage.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.rating.store import DEFAULT_DB_PATH


def measure(db_path: Path = DEFAULT_DB_PATH) -> dict:
    c = sqlite3.connect(db_path)
    tot = c.execute("select count(*) from cards").fetchone()[0]
    appr = c.execute("select count(*) from card_effects where review_status='approved'").fetchone()[0]
    exact = c.execute("select count(*) from card_effects where review_status='approved' and fidelity='exact'").fetchone()[0]
    approx = c.execute("select count(*) from card_effects where review_status='approved' and fidelity='approx'").fetchone()[0]
    draft = c.execute("select count(*) from card_effects where review_status='draft'").fetchone()[0]
    empty = 0
    for (ej,) in c.execute("select effect_json from card_effects where review_status='approved'"):
        if not json.loads(ej).get("abilities"):
            empty += 1
    return {"total": tot, "approved": appr, "exact": exact, "approx": approx,
            "draft": draft, "approved_empty": empty}


def main() -> int:
    m = measure()
    print("=== シミュレーション忠実度カバレッジ ===")
    print(f"  総カード             : {m['total']}")
    print(f"  exact(現実と1対1)    : {m['exact']:5d}  ({m['exact']/m['total']*100:5.1f}%)  ← 目標 {m['total']}")
    print(f"  approx(近似)         : {m['approx']:5d}")
    print(f"  承認済みだが効果空    : {m['approved_empty']:5d}")
    print(f"  draft(未着手)        : {m['draft']:5d}")
    print(f"  残り exact化必要      : {m['total'] - m['exact']:5d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""メタ採用カードの過大評価を網羅是正する(exact-safeバッチ)。

「再帰的報酬ハック」を断つため、メタ採用approxカードの明白な過大評価を一括是正。
各是正はexact-safe(過小評価側)。背景: docs/loop_research.md 第五十一〜五十八弾。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.rating.store import DEFAULT_DB_PATH

# (card名, abilities, note)。abilities=[] は「効果未模擬=under-eval(静的属性のみ)」。
FIXES = [
    ("メガ・ブレード・ドラゴン",
     [{"trigger": "on_play", "actions": [{"op": "destroy_creature", "count": 1, "scope": "opponent"}]},
      {"trigger": "s_trigger", "actions": [{"op": "destroy_creature", "count": 1, "scope": "opponent"}]}],
     "exact-safe是正: 本来は相手ブロッカーのみ全破壊。engineがブロッカー限定できないため1体破壊で近似(過小評価)。旧approxの全クリーチャーx99破壊は盤面全滅の重大な過大評価"),
    ("炸裂の影デス・サークル",
     [{"trigger": "s_trigger", "actions": [{"op": "destroy_creature", "count": 1, "scope": "opponent", "chooser": "opponent"}]}],
     "exact-safe是正: 自己破壊を条件に相手がアンタップ1体(=最弱)を破壊。自己破壊コストは未模擬。旧approxはcontrollerがdestroy×2で過大評価"),
    ("龍装者 ヴィヌフィース/究めし優美のブレイン",
     [{"trigger": "s_trigger", "actions": [{"op": "bounce_creature", "count": 1, "scope": "opponent"}]}],
     "exact-safe是正: 相手1体バウンス。墓地呪文5枚以上でブロッカー獲得は別効果で未模擬。旧approxのbounce×2は過大評価"),
    ("ザ・美食秘宝サイキック・イーター",
     [],
     "exact-safe是正: 効果は『離れた時、相手は自身のサイキック・クリーチャー1体を破壊』という稀な条件付き。engine未模擬=空(ブロッカー本体は静的属性)。旧approxのdestroy×2は過大評価"),
    ("DNA・スパーク",
     [{"trigger": "s_trigger", "actions": [
         {"op": "tap_creature", "count": 99, "scope": "opponent"},
         {"op": "add_shield", "count": 1, "condition": {"kind": "shields_at_most", "count": 2}}]}],
     "exact-safe是正: 相手全タップ+シールド2以下ならシールド化(条件付与)。旧approxはシールド化を無条件適用(軽微な過大評価)"),
]


def main():
    c = sqlite3.connect(DEFAULT_DB_PATH)
    for name, abilities, note in FIXES:
        row = c.execute("select card_id from cards where name=? limit 1", (name,)).fetchone()
        if not row:
            print("MISS", name)
            continue
        cid = row[0]
        ej = json.dumps({"card_id": cid, "name": name, "abilities": abilities, "notes": [note]},
                        ensure_ascii=False)
        c.execute("update card_effects set effect_json=?, fidelity='approx', review_status='approved' where card_id=?",
                  (ej, cid))
        print(f"fixed {name} ({len(abilities)}ability)")
    c.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

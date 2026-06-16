"""忠実パーサの結果を card_effects に同期する(べき等)。

- パーサが解析できたカード → exact(abilities) に設定。
- 以前パーサが exact 化したが今回解析不可になったカード → approx-空に戻す。
- 手書き(note に '忠実パーサ' を含まない)exact は温存。

パーサを拡張するたび本スクリプトを再実行すれば db が追従する。
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.effects.exact_parser import parse_card
from src.battle.rating.store import DEFAULT_DB_PATH

TAG = "忠実パーサ"


def main() -> int:
    c = sqlite3.connect(DEFAULT_DB_PATH)
    rows = c.execute("select card_id,name,card_type,text from cards").fetchall()
    conv: dict[str, tuple[str, list]] = {}
    for cid, name, ct, text in rows:
        r = parse_card(text or "", ct or "")
        if r is not None:
            conv[cid] = (name, r)

    now = datetime.now().isoformat()
    applied = reverted = 0
    for cid, (name, ab) in conv.items():
        ej = json.dumps({"card_id": cid, "name": name, "abilities": ab,
                         "notes": [f"exact: {TAG}(全節カバー)で変換"]}, ensure_ascii=False)
        ex = c.execute("select 1 from card_effects where card_id=?", (cid,)).fetchone()
        if ex:
            c.execute("update card_effects set effect_json=?, review_status='approved', fidelity='exact' where card_id=?", (ej, cid))
        else:
            c.execute("insert into card_effects(card_id,name,effect_json,review_status,fidelity,updated_at) values(?,?,?,'approved','exact',?)", (cid, name, ej, now))
        applied += 1

    # 以前パーサ由来で exact だが今回解析不可 → approx-空に戻す
    for cid, name, ej in c.execute("select card_id,name,effect_json from card_effects where fidelity='exact'").fetchall():
        if cid in conv:
            continue
        try:
            notes = " ".join(json.loads(ej).get("notes", []))
        except Exception:
            notes = ""
        if TAG in notes:
            rej = json.dumps({"card_id": cid, "name": name, "abilities": [],
                              "notes": ["approx: パーサが厳密解析できないため exact 化保留"]}, ensure_ascii=False)
            c.execute("update card_effects set effect_json=?, fidelity='approx' where card_id=?", (rej, cid))
            reverted += 1

    c.commit()
    print(f"exact適用 {applied}枚 / approx戻し {reverted}枚")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

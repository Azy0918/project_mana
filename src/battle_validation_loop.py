"""バトルシミュレーター検証ループ.

生成済み未開拓デッキ (generated_decks) を環境デッキ全レシピ
(meta_deck_cards) と battle_simulator で対戦させ、平均勝率が
目標値 (デフォルト70%) に到達するまで弱点補強→再シミュレーション
を反復する。

改善はシミュレータの特徴量 (_features) の弱いレバーを特定し、
該当roleのカードへ入れ替える形で行う。seedカードは削らない。

使い方:
  python -m src.battle_validation_loop
  python -m src.battle_validation_loop --target 0.7 --max-iterations 30
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_DB_PATH
from src.battle_simulator import simulate_battle, _features

DEFAULT_OUTPUT_DIR = Path("data/reports/battle_validation")

# シミュレータのレバー -> 補強に使うタグ群と最大コスト
LEVER_ACTIONS: dict[str, dict[str, Any]] = {
    "defense": {"tags": ["受け札", "S・トリガー", "G・ストライク", "ブロッカー"], "max_cost": 5},
    "speed": {"tags": ["初動", "低コスト"], "max_cost": 3},
    "finisher": {"tags": ["フィニッシャー", "打点", "スピードアタッカー"], "max_cost": 7},
    "resource": {"tags": ["ドロー", "リソース", "マナ加速"], "max_cost": 4},
    "removal": {"tags": ["除去", "バウンス", "タップ"], "max_cost": 5},
    "meta": {"tags": ["メタ", "ロック", "ハンデス", "踏み倒しメタ"], "max_cost": 4},
}

# _power の重みに概ね比例した改善優先度
LEVER_PRIORITY = ["speed", "finisher", "defense", "resource", "removal", "meta"]

SIM_TRIALS = 400
SIM_SEED = 20260702


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _load_card_pool(db_path: str | Path) -> list[dict[str, Any]]:
    """タグ付きの全カードプール (card dict形式)。"""
    with _connect(db_path) as conn:
        tag_rows = conn.execute(
            """
            SELECT c.name, GROUP_CONCAT(ct.tag, ';') AS tags
            FROM cards c JOIN card_tags ct ON c.card_id = ct.card_id
            GROUP BY c.name
            """
        ).fetchall()
        tags_by_name = {row["name"]: row["tags"] or "" for row in tag_rows}
        rows = conn.execute(
            "SELECT name, cost, civilization, card_type FROM cards"
        ).fetchall()

    pool = []
    for row in rows:
        pool.append(
            {
                "name": str(row["name"] or ""),
                "cost": int(row["cost"] or 0),
                "civilization": str(row["civilization"] or ""),
                "card_type": str(row["card_type"] or ""),
                "tags": tags_by_name.get(str(row["name"] or ""), ""),
            }
        )
    return pool


def load_meta_decks_as_cards(db_path: str | Path) -> list[dict[str, Any]]:
    """meta_deck_cardsをsimulate_battle互換のcard dictリストへ変換する。"""
    pool = {card["name"]: card for card in _load_card_pool(db_path)}
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT deck_name, card_name, count FROM meta_deck_cards ORDER BY id"
        ).fetchall()

    by_deck: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        name = str(row["card_name"])
        base = pool.get(name, {"name": name, "cost": 0, "civilization": "", "tags": ""})
        card = dict(base)
        card["quantity"] = int(row["count"] or 1)
        by_deck.setdefault(str(row["deck_name"]), []).append(card)

    return [
        {"deck_name": deck_name, "cards": cards}
        for deck_name, cards in by_deck.items()
        if sum(int(c.get("quantity") or 0) for c in cards) >= 30
    ]


def simulate_vs_meta(
    deck_cards: list[dict[str, Any]],
    meta_decks: list[dict[str, Any]],
) -> dict[str, Any]:
    """環境デッキ全対面との平均勝率を返す。"""
    matchups = []
    for meta in meta_decks:
        result = simulate_battle(deck_cards, meta["cards"], trials=SIM_TRIALS, seed=SIM_SEED)
        matchups.append(
            {
                "opponent": meta["deck_name"],
                "win_rate": result["deck_a_win_rate"],
                "average_finish_turn": round(result["average_finish_turn"], 1),
            }
        )
    avg = sum(m["win_rate"] for m in matchups) / len(matchups) if matchups else 0.0
    return {"average_win_rate": round(avg, 4), "matchups": matchups}


# ---------------------------------------------------------------------------
# 改善ループ
# ---------------------------------------------------------------------------

def _deck_size(deck_cards: list[dict[str, Any]]) -> int:
    return sum(int(c.get("quantity") or 0) for c in deck_cards)


def _weakest_levers(deck_cards: list[dict[str, Any]]) -> list[str]:
    """シミュレータ特徴量の弱い順にレバーを返す。"""
    features = _features(deck_cards)
    scored = [(features.get(lever, 0.0), lever) for lever in LEVER_ACTIONS]
    scored.sort()
    return [lever for _, lever in scored]


def _cut_candidates(deck_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """削ってよいカードを削る優先度順に返す (seed roleは除外)。"""
    cuttable = [
        c for c in deck_cards
        if "seed" not in str(c.get("role") or "") and int(c.get("quantity") or 0) > 0
    ]
    # flex優先 → 高コスト → タグが薄い
    cuttable.sort(
        key=lambda c: (
            "flex" not in str(c.get("role") or ""),
            -int(c.get("cost") or 0),
            len(str(c.get("tags") or "")),
        )
    )
    return cuttable


def _find_addition(
    pool: list[dict[str, Any]],
    lever: str,
    deck_cards: list[dict[str, Any]],
    target_civs: set[str],
) -> dict[str, Any] | None:
    """レバーを補強する最良カードをプールから選ぶ。"""
    action = LEVER_ACTIONS[lever]
    existing = {str(c.get("name")) for c in deck_cards}
    best: tuple[int, dict[str, Any]] | None = None
    for card in pool:
        if card["name"] in existing:
            continue
        if card["cost"] <= 0 or card["cost"] > action["max_cost"]:
            continue
        civs = {c for c in str(card["civilization"]).split("/") if c and c != "無色"}
        if target_civs and civs and not (civs & target_civs):
            continue
        matched = sum(1 for tag in action["tags"] if tag in card["tags"])
        if matched <= 0:
            continue
        score = matched * 10 + max(0, 6 - card["cost"])
        if best is None or score > best[0]:
            best = (score, card)
    return best[1] if best else None


def improve_deck_until_target(
    deck_cards: list[dict[str, Any]],
    meta_decks: list[dict[str, Any]],
    pool: list[dict[str, Any]],
    civilizations: list[str],
    target: float = 0.70,
    max_iterations: int = 25,
) -> dict[str, Any]:
    """弱点補強→再シミュレーションを目標勝率まで反復する。"""
    target_civs = {c for c in civilizations if c and c != "無色"}
    log: list[str] = []

    current = [dict(c) for c in deck_cards]
    result = simulate_vs_meta(current, meta_decks)
    best_rate = result["average_win_rate"]
    best_deck = [dict(c) for c in current]
    best_result = result
    log.append(f"初期平均勝率: {best_rate:.1%}")

    stall = 0
    lever_cursor = 0
    for iteration in range(1, max_iterations + 1):
        if best_rate >= target:
            break

        # 弱いレバーから順に試すが、停滞したら次のレバーへ回す
        levers = _weakest_levers(current)
        lever = levers[lever_cursor % len(levers)]

        addition = _find_addition(pool, lever, current, target_civs)
        cuts = _cut_candidates(current)
        if addition is None or not cuts:
            lever_cursor += 1
            if lever_cursor >= len(LEVER_ACTIONS):
                log.append(f"反復{iteration}: 補強手段が尽きたため終了")
                break
            continue

        # 3枚入替 (削り側は複数行から集める)
        swap_copies = 3
        removed_desc = []
        remaining_to_cut = swap_copies
        candidate_deck = [dict(c) for c in current]
        cut_names = {str(c.get("name")) for c in cuts[:3]}
        for card in candidate_deck:
            if remaining_to_cut <= 0:
                break
            if str(card.get("name")) in cut_names and "seed" not in str(card.get("role") or ""):
                take = min(int(card.get("quantity") or 0), remaining_to_cut)
                card["quantity"] = int(card.get("quantity") or 0) - take
                remaining_to_cut -= take
                if take:
                    removed_desc.append(f"{card['name']}×{take}")
        candidate_deck = [c for c in candidate_deck if int(c.get("quantity") or 0) > 0]
        added = dict(addition)
        added["quantity"] = swap_copies - remaining_to_cut
        added["role"] = lever
        if added["quantity"] <= 0:
            lever_cursor += 1
            continue
        candidate_deck.append(added)

        new_result = simulate_vs_meta(candidate_deck, meta_decks)
        new_rate = new_result["average_win_rate"]

        if new_rate > best_rate:
            log.append(
                f"反復{iteration}: [{lever}] {'/'.join(removed_desc)} → "
                f"{added['name']}×{added['quantity']}。勝率 {best_rate:.1%} → {new_rate:.1%}"
            )
            current = candidate_deck
            best_rate = new_rate
            best_deck = [dict(c) for c in candidate_deck]
            best_result = new_result
            stall = 0
            lever_cursor = 0
        else:
            stall += 1
            lever_cursor += 1
            log.append(
                f"反復{iteration}: [{lever}] {added['name']} 試行は不発 "
                f"({best_rate:.1%} → {new_rate:.1%})。破棄"
            )
            if stall >= len(LEVER_ACTIONS) * 2:
                log.append(f"反復{iteration}: 全レバーで改善が停滞したため終了")
                break

    reached = best_rate >= target
    log.append(
        f"最終平均勝率: {best_rate:.1%} ({'目標到達' if reached else '目標未達'})"
    )
    return {
        "reached_target": reached,
        "final_win_rate": best_rate,
        "deck_cards": best_deck,
        "simulation": best_result,
        "improvement_log": log,
    }


# ---------------------------------------------------------------------------
# generated_decks 全体への適用
# ---------------------------------------------------------------------------

def run_battle_validation(
    db_path: str | Path = DEFAULT_DB_PATH,
    target: float = 0.70,
    max_iterations: int = 25,
    update_db: bool = True,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """全生成デッキを検証し、目標勝率までの改善を試みる。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    meta_decks = load_meta_decks_as_cards(db_path)
    if not meta_decks:
        raise RuntimeError("meta_deck_cards に環境デッキがありません。")
    pool = _load_card_pool(db_path)

    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, deck_name, civilizations, deck_cards_json FROM generated_decks ORDER BY id"
        ).fetchall()

    results: list[dict[str, Any]] = []
    champions: list[dict[str, Any]] = []

    for row in rows:
        deck_id = int(row["id"])
        try:
            deck_cards = json.loads(row["deck_cards_json"] or "[]")
        except Exception:
            continue
        if _deck_size(deck_cards) < 30:
            continue
        civilizations = [c for c in str(row["civilizations"] or "").split(";") if c]

        outcome = improve_deck_until_target(
            deck_cards,
            meta_decks,
            pool,
            civilizations,
            target=target,
            max_iterations=max_iterations,
        )

        entry = {
            "deck_id": deck_id,
            "deck_name": row["deck_name"],
            "reached_target": outcome["reached_target"],
            "final_win_rate": outcome["final_win_rate"],
            "matchups": outcome["simulation"]["matchups"],
            "improvement_log": outcome["improvement_log"],
        }
        results.append(entry)
        if outcome["reached_target"]:
            champions.append(entry)

        if update_db:
            note_addendum = (
                "\n\nbattle_validation_loop 検証ログ "
                f"({datetime.now().isoformat(timespec='seconds')}):\n"
                + "\n".join(f"- {line}" for line in outcome["improvement_log"])
            )
            with _connect(db_path) as conn:
                conn.execute(
                    """
                    UPDATE generated_decks
                    SET deck_cards_json = ?,
                        meta_score = ?,
                        strategy_note = strategy_note || ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(outcome["deck_cards"], ensure_ascii=False),
                        round(outcome["final_win_rate"] * 100, 1),
                        note_addendum,
                        deck_id,
                    ),
                )
                conn.commit()

    summary = {
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "target_win_rate": target,
        "meta_deck_count": len(meta_decks),
        "validated_decks": len(results),
        "champions": len(champions),
        "champion_ids": [c["deck_id"] for c in champions],
        "results": sorted(results, key=lambda r: r["final_win_rate"], reverse=True),
    }

    json_path = output_dir / "battle_validation.json"
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = output_dir / "battle_validation.md"
    md_path.write_text(validation_summary_to_markdown(summary), encoding="utf-8")
    summary["summary_json"] = str(json_path)
    summary["summary_markdown"] = str(md_path)
    return summary


def validation_summary_to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# バトルシミュレーター検証結果",
        "",
        "> 注意: 統計的代理シミュレーションであり、実ルールの完全再現ではありません。",
        "",
        f"- 実行日時: {summary.get('executed_at')}",
        f"- 目標勝率: {summary.get('target_win_rate'):.0%}",
        f"- 検証デッキ数: {summary.get('validated_decks')}",
        f"- 目標到達: {summary.get('champions')}デッキ (ids={summary.get('champion_ids')})",
        "",
        "| deck_id | deck_name | 平均勝率 | 到達 |",
        "| --- | --- | ---: | --- |",
    ]
    for r in summary.get("results", []):
        lines.append(
            f"| {r['deck_id']} | {str(r['deck_name'])[:45]} | "
            f"{r['final_win_rate']:.1%} | {'○' if r['reached_target'] else '×'} |"
        )
    lines.append("")
    for r in summary.get("results", [])[:5]:
        lines.append(f"## deck {r['deck_id']}: {r['deck_name']}")
        lines.append("")
        for m in r["matchups"]:
            lines.append(f"- vs {m['opponent']}: {m['win_rate']:.1%} (決着T{m['average_finish_turn']})")
        lines.append("")
        lines.append("改善ログ:")
        for line in r["improvement_log"]:
            lines.append(f"- {line}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="生成デッキをバトルシミュレーターで検証・改善する。")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--target", type=float, default=0.70, help="目標平均勝率 (0-1)")
    parser.add_argument("--max-iterations", type=int, default=25, help="デッキごとの改善反復上限")
    parser.add_argument("--no-update", action="store_true", help="DBを更新しない")
    args = parser.parse_args()

    summary = run_battle_validation(
        db_path=args.db,
        target=args.target,
        max_iterations=args.max_iterations,
        update_db=not args.no_update,
        output_dir=args.out,
    )
    print(f"検証: {summary['validated_decks']}デッキ / 目標到達: {summary['champions']}デッキ")
    for r in summary["results"][:10]:
        mark = "○" if r["reached_target"] else "×"
        print(f"  {mark} id={r['deck_id']} {r['final_win_rate']:.1%} {str(r['deck_name'])[:40]}")
    print(f"summary: {summary['summary_json']}")


if __name__ == "__main__":
    main()

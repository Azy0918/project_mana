from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data/cards.db")
DEFAULT_OUT = Path("data/reports/rank_candidate_tests")
DEFAULT_DECK_NAME = "夜間研究Rank1安全補正版"


def get_connection(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table(db_path: Path = DEFAULT_DB) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rank_candidate_test_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                deck_name TEXT NOT NULL,
                opponent_deck TEXT,
                result TEXT,
                play_order TEXT,
                finish_turn INTEGER,
                developed_two_by_turn4 INTEGER,
                finished_by_turn6 INTEGER,
                mana_color_issue INTEGER,
                dead_cards TEXT,
                strong_cards TEXT,
                qqqx_wanted INTEGER,
                removed_light_wanted INTEGER,
                notes TEXT
            )
            """
        )
        conn.commit()


def save_test_match(row: dict[str, Any], db_path: Path = DEFAULT_DB) -> int:
    ensure_table(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO rank_candidate_test_matches (
                created_at, deck_name, opponent_deck, result, play_order, finish_turn,
                developed_two_by_turn4, finished_by_turn6, mana_color_issue,
                dead_cards, strong_cards, qqqx_wanted, removed_light_wanted, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                row.get("deck_name") or DEFAULT_DECK_NAME,
                row.get("opponent_deck") or "",
                row.get("result") or "",
                row.get("play_order") or "",
                _int_or_none(row.get("finish_turn")),
                _bool_int(row.get("developed_two_by_turn4")),
                _bool_int(row.get("finished_by_turn6")),
                _bool_int(row.get("mana_color_issue")),
                row.get("dead_cards") or "",
                row.get("strong_cards") or "",
                _bool_int(row.get("qqqx_wanted")),
                _bool_int(row.get("removed_light_wanted")),
                row.get("notes") or "",
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def load_test_matches(deck_name: str | None = None, db_path: Path = DEFAULT_DB) -> list[dict[str, Any]]:
    ensure_table(db_path)
    with get_connection(db_path) as conn:
        if deck_name:
            rows = conn.execute(
                "SELECT * FROM rank_candidate_test_matches WHERE deck_name = ? ORDER BY id DESC",
                (deck_name,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM rank_candidate_test_matches ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def analyze_test_session(deck_name: str = DEFAULT_DECK_NAME, db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    matches = load_test_matches(deck_name, db_path)
    first_five = list(reversed(matches[:5]))
    total = len(first_five)
    wins = sum(1 for row in first_five if str(row.get("result")) == "win")
    finish_turns = [int(row["finish_turn"]) for row in first_five if row.get("finish_turn") is not None]
    dead = Counter()
    strong = Counter()
    for row in first_five:
        count_terms(row.get("dead_cards") or "", dead)
        count_terms(row.get("strong_cards") or "", strong)
    summary = {
        "deck_name": deck_name,
        "match_count": total,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
        "average_finish_turn": round(sum(finish_turns) / len(finish_turns), 2) if finish_turns else 0.0,
        "turn4_development_rate": rate(first_five, "developed_two_by_turn4"),
        "turn6_finish_rate": rate(first_five, "finished_by_turn6"),
        "mana_color_issue_count": sum(1 for row in first_five if row.get("mana_color_issue")),
        "qqqx_wanted_count": sum(1 for row in first_five if row.get("qqqx_wanted")),
        "removed_light_wanted_count": sum(1 for row in first_five if row.get("removed_light_wanted")),
        "strong_cards": [{"name": k, "count": v} for k, v in strong.most_common()],
        "dead_cards": [{"name": k, "count": v} for k, v in dead.most_common()],
        "matches": first_five,
    }
    summary["verdict"] = judge_session(summary)
    summary["improvement_ideas"] = improvement_ideas(summary)
    return summary


def judge_session(summary: dict[str, Any]) -> str:
    if summary["match_count"] < 5:
        return "追加検証"
    if summary["qqqx_wanted_count"] >= 2 or summary["removed_light_wanted_count"] >= 2:
        return "光/Q.Q.QX.を再検討すべき"
    if summary["mana_color_issue_count"] >= 2:
        return "改良すべき"
    if summary["win_rate"] >= 60 and summary["turn4_development_rate"] >= 60 and summary["turn6_finish_rate"] >= 40:
        return "継続テストすべき"
    if summary["win_rate"] < 40:
        return "没候補"
    return "改良すべき"


def improvement_ideas(summary: dict[str, Any]) -> list[str]:
    ideas = []
    for row in summary.get("dead_cards", [])[:5]:
        ideas.append(f"{row['name']} が腐り札として {row['count']} 回出ています。火自然アグロロックの速度を落とさない同コスト圧力札への差し替え候補です。")
    for row in summary.get("strong_cards", [])[:5]:
        ideas.append(f"{row['name']} が強かったカードとして {row['count']} 回出ています。4枚未満なら増量候補です。")
    if summary.get("qqqx_wanted_count", 0) >= 2:
        ideas.append("Q.Q.QX.が欲しい場面が2回以上あります。光入りQ.Q.QX.ロック案を別枠で再検討してください。")
    if summary.get("removed_light_wanted_count", 0) >= 2:
        ideas.append("抜いた光カードが欲しい場面が2回以上あります。光タッチ型を再検討してください。")
    if summary.get("mana_color_issue_count", 0) >= 2:
        ideas.append("色事故が2回以上あります。火/自然供給と多色比率を見直してください。")
    return ideas or ["5戦ログからは明確な差し替え要求はまだ出ていません。"]


def write_test_report(deck_name: str = DEFAULT_DECK_NAME, db_path: Path = DEFAULT_DB, out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = analyze_test_session(deck_name, db_path)
    (out_dir / "rank_candidate_test_report.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "rank_candidate_test_report.md").write_text(to_markdown(summary), encoding="utf-8")
    return summary


def to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Rank候補 5戦検証レポート",
        "",
        f"- 使用デッキ: {summary['deck_name']}",
        f"- 試合数: {summary['match_count']}",
        f"- 勝率: {summary['win_rate']}%",
        f"- 平均決着ターン: {summary['average_finish_turn']}",
        f"- 4T展開率: {summary['turn4_development_rate']}%",
        f"- 6T詰め率: {summary['turn6_finish_rate']}%",
        f"- 色事故回数: {summary['mana_color_issue_count']}",
        f"- Q.Q.QX.再検討回数: {summary['qqqx_wanted_count']}",
        f"- 抜いた光カード再検討回数: {summary['removed_light_wanted_count']}",
        f"- MANAの結論: {summary['verdict']}",
        "",
        "## 強かったカードランキング",
    ]
    lines.extend([f"- {row['name']}: {row['count']}" for row in summary["strong_cards"]] or ["- なし"])
    lines.append("")
    lines.append("## 腐ったカードランキング")
    lines.extend([f"- {row['name']}: {row['count']}" for row in summary["dead_cards"]] or ["- なし"])
    lines.append("")
    lines.append("## 次の改良案")
    lines.extend(f"- {idea}" for idea in summary["improvement_ideas"])
    lines.append("")
    lines.append("## 5戦結果")
    for row in summary["matches"]:
        lines.append(
            f"- {row.get('opponent_deck')} / {row.get('result')} / {row.get('play_order')} / "
            f"{row.get('finish_turn')}T / 4T展開={bool(row.get('developed_two_by_turn4'))} / "
            f"6T詰め={bool(row.get('finished_by_turn6'))} / 色事故={bool(row.get('mana_color_issue'))}"
        )
    return "\n".join(lines)


def rate(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if row.get(key)) / len(rows) * 100, 1)


def count_terms(value: str, counter: Counter[str]) -> None:
    for part in str(value or "").replace(",", ";").replace("、", ";").split(";"):
        part = part.strip()
        if part:
            counter[part] += 1


def _bool_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    return 1 if str(value).lower() in {"1", "true", "yes", "y", "win", "あり"} else 0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and analyze Rank candidate 5-match test sessions.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--deck", default=DEFAULT_DECK_NAME)
    parser.add_argument("--opponent", default="")
    parser.add_argument("--result", choices=["win", "loss"], default="")
    parser.add_argument("--play-order", choices=["first", "second"], default="")
    parser.add_argument("--finish-turn", type=int, default=None)
    parser.add_argument("--developed-two-by-turn4", default="")
    parser.add_argument("--finished-by-turn6", default="")
    parser.add_argument("--mana-color-issue", default="")
    parser.add_argument("--dead-cards", default="")
    parser.add_argument("--strong-cards", default="")
    parser.add_argument("--qqqx-wanted", default="")
    parser.add_argument("--removed-light-wanted", default="")
    parser.add_argument("--notes", default="")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    db_path = Path(args.db)
    if args.summary or not args.opponent:
        summary = write_test_report(args.deck, db_path)
        print(json.dumps({"verdict": summary["verdict"], "match_count": summary["match_count"]}, ensure_ascii=False, indent=2))
        return
    match_id = save_test_match(
        {
            "deck_name": args.deck,
            "opponent_deck": args.opponent,
            "result": args.result,
            "play_order": args.play_order,
            "finish_turn": args.finish_turn,
            "developed_two_by_turn4": args.developed_two_by_turn4,
            "finished_by_turn6": args.finished_by_turn6,
            "mana_color_issue": args.mana_color_issue,
            "dead_cards": args.dead_cards,
            "strong_cards": args.strong_cards,
            "qqqx_wanted": args.qqqx_wanted,
            "removed_light_wanted": args.removed_light_wanted,
            "notes": args.notes,
        },
        db_path,
    )
    summary = write_test_report(args.deck, db_path)
    print(json.dumps({"saved_id": match_id, "verdict": summary["verdict"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

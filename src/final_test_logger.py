from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data/cards.db")
DEFAULT_OUT = Path("data/reports/final_deck")


def get_connection(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table(db_path: Path = DEFAULT_DB) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS final_test_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                deck_name TEXT,
                deck_version TEXT,
                opponent TEXT,
                format TEXT,
                play_order TEXT,
                result TEXT,
                finish_turn INTEGER,
                opening_hand TEXT,
                key_cards_played TEXT,
                cards_felt_strong TEXT,
                cards_felt_weak TEXT,
                dead_cards TEXT,
                mana_color_issue INTEGER,
                could_pressure_by_turn4 INTEGER,
                could_finish_by_turn6 INTEGER,
                notes TEXT
            )
            """
        )
        conn.commit()


def save_match(row: dict[str, Any], db_path: Path = DEFAULT_DB) -> int:
    ensure_table(db_path)
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO final_test_matches (
                created_at, deck_name, deck_version, opponent, format, play_order,
                result, finish_turn, opening_hand, key_cards_played, cards_felt_strong,
                cards_felt_weak, dead_cards, mana_color_issue, could_pressure_by_turn4,
                could_finish_by_turn6, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                row.get("deck_name", ""),
                row.get("deck_version", ""),
                row.get("opponent", ""),
                row.get("format", ""),
                row.get("play_order", ""),
                row.get("result", ""),
                row.get("finish_turn"),
                row.get("opening_hand", ""),
                row.get("key_cards_played", ""),
                row.get("cards_felt_strong", ""),
                row.get("cards_felt_weak", ""),
                row.get("dead_cards", ""),
                int(bool(row.get("mana_color_issue"))),
                int(bool(row.get("could_pressure_by_turn4"))),
                int(bool(row.get("could_finish_by_turn6"))),
                row.get("notes", ""),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def load_matches(db_path: Path = DEFAULT_DB) -> list[dict[str, Any]]:
    ensure_table(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM final_test_matches ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def summarize_matches(db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    rows = load_matches(db_path)
    total = len(rows)
    wins = sum(1 for row in rows if str(row.get("result", "")).lower() in {"win", "勝ち", "勝利"})
    by_opponent = defaultdict(lambda: {"matches": 0, "wins": 0})
    by_order = defaultdict(lambda: {"matches": 0, "wins": 0})
    finish_turns = []
    strong = Counter()
    weak = Counter()
    dead = Counter()

    for row in rows:
        is_win = str(row.get("result", "")).lower() in {"win", "勝ち", "勝利"}
        opponent = row.get("opponent") or "不明"
        order = row.get("play_order") or "不明"
        by_opponent[opponent]["matches"] += 1
        by_opponent[opponent]["wins"] += int(is_win)
        by_order[order]["matches"] += 1
        by_order[order]["wins"] += int(is_win)
        if row.get("finish_turn") is not None:
            try:
                finish_turns.append(int(row["finish_turn"]))
            except Exception:
                pass
        _count_terms(str(row.get("cards_felt_strong", "")), strong)
        _count_terms(str(row.get("cards_felt_weak", "")), weak)
        _count_terms(str(row.get("dead_cards", "")), dead)

    summary = {
        "total_matches": total,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
        "by_opponent": _rate_rows(by_opponent),
        "by_play_order": _rate_rows(by_order),
        "average_finish_turn": round(sum(finish_turns) / len(finish_turns), 2) if finish_turns else 0.0,
        "pressure_by_turn4_rate": _bool_rate(rows, "could_pressure_by_turn4"),
        "finish_by_turn6_rate": _bool_rate(rows, "could_finish_by_turn6"),
        "mana_color_issue_rate": _bool_rate(rows, "mana_color_issue"),
        "strong_cards": strong.most_common(10),
        "weak_cards": weak.most_common(10),
        "dead_cards": dead.most_common(10),
    }
    write_summary(summary)
    return summary


def write_summary(summary: dict[str, Any], out_dir: Path = DEFAULT_OUT) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "final_test_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# final test summary", ""]
    lines.append(f"- total_matches: {summary['total_matches']}")
    lines.append(f"- win_rate: {summary['win_rate']}%")
    lines.append(f"- average_finish_turn: {summary['average_finish_turn']}")
    lines.append(f"- pressure_by_turn4_rate: {summary['pressure_by_turn4_rate']}%")
    lines.append(f"- finish_by_turn6_rate: {summary['finish_by_turn6_rate']}%")
    lines.append(f"- mana_color_issue_rate: {summary['mana_color_issue_rate']}%")
    lines.append("")
    lines.append("## by opponent")
    for row in summary["by_opponent"]:
        lines.append(f"- {row['key']}: {row['wins']}/{row['matches']} ({row['win_rate']}%)")
    lines.append("")
    lines.append("## strong cards")
    for name, count in summary["strong_cards"]:
        lines.append(f"- {name}: {count}")
    lines.append("")
    lines.append("## weak cards")
    for name, count in summary["weak_cards"]:
        lines.append(f"- {name}: {count}")
    (out_dir / "final_test_summary.md").write_text("\n".join(lines), encoding="utf-8")


def _rate_rows(bucket: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "matches": value["matches"],
            "wins": value["wins"],
            "win_rate": round(value["wins"] / value["matches"] * 100, 1) if value["matches"] else 0.0,
        }
        for key, value in sorted(bucket.items())
    ]


def _bool_rate(rows: list[dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if int(row.get(key) or 0)) / len(rows) * 100, 1)


def _count_terms(value: str, counter: Counter[str]) -> None:
    for term in value.replace("、", ";").replace(",", ";").split(";"):
        term = term.strip()
        if term:
            counter[term] += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Log and summarize final MANA test matches.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--deck", default="MANA実戦版A")
    parser.add_argument("--deck-version", default="A")
    parser.add_argument("--opponent", default="")
    parser.add_argument("--format", default="ND")
    parser.add_argument("--play-order", default="")
    parser.add_argument("--result", default="")
    parser.add_argument("--finish-turn", type=int, default=None)
    parser.add_argument("--opening-hand", default="")
    parser.add_argument("--key-cards-played", default="")
    parser.add_argument("--cards-felt-strong", default="")
    parser.add_argument("--cards-felt-weak", default="")
    parser.add_argument("--dead-cards", default="")
    parser.add_argument("--mana-color-issue", action="store_true")
    parser.add_argument("--could-pressure-by-turn4", action="store_true")
    parser.add_argument("--could-finish-by-turn6", action="store_true")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.summary or not args.opponent:
        summary = summarize_matches(db_path)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    match_id = save_match(
        {
            "deck_name": args.deck,
            "deck_version": args.deck_version,
            "opponent": args.opponent,
            "format": args.format,
            "play_order": args.play_order,
            "result": args.result,
            "finish_turn": args.finish_turn,
            "opening_hand": args.opening_hand,
            "key_cards_played": args.key_cards_played,
            "cards_felt_strong": args.cards_felt_strong,
            "cards_felt_weak": args.cards_felt_weak,
            "dead_cards": args.dead_cards,
            "mana_color_issue": args.mana_color_issue,
            "could_pressure_by_turn4": args.could_pressure_by_turn4,
            "could_finish_by_turn6": args.could_finish_by_turn6,
            "notes": args.notes,
        },
        db_path,
    )
    print(f"saved final_test_match id={match_id}")


if __name__ == "__main__":
    main()

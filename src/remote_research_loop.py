from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data/cards.db")


def connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_tables(conn)
    return conn


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            title TEXT NOT NULL,
            theme_name TEXT NOT NULL,
            format_name TEXT NOT NULL,
            opponent TEXT NOT NULL,
            deck_name TEXT NOT NULL,
            deck_json TEXT NOT NULL,
            candidate_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_session_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            match_no INTEGER NOT NULL,
            opponent TEXT NOT NULL,
            format_name TEXT NOT NULL,
            play_order TEXT NOT NULL,
            result TEXT NOT NULL,
            finish_turn INTEGER,
            yadok_on_time TEXT DEFAULT '',
            trap_effective TEXT DEFAULT '',
            removal_effective TEXT DEFAULT '',
            lock_on_time TEXT DEFAULT '',
            external_zone_effective TEXT DEFAULT '',
            interfered_by_turn5 TEXT DEFAULT '',
            had_win_condition TEXT DEFAULT '',
            strong_cards TEXT DEFAULT '',
            weak_cards TEXT DEFAULT '',
            dead_cards TEXT DEFAULT '',
            loss_reason TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            FOREIGN KEY(session_id) REFERENCES research_sessions(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS research_session_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_summary TEXT NOT NULL,
            action_json TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES research_sessions(id)
        )
        """
    )
    conn.commit()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_format(value: str | None) -> str:
    v = str(value or "").strip().upper()
    return v if v in {"AD", "ND"} else "AD"


def deck_items_from_candidate(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    deck = candidate.get("deck") or candidate.get("cards") or []
    out: list[dict[str, Any]] = []
    if isinstance(deck, list):
        for item in deck:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("card_name") or item.get("card") or ""
            count = item.get("count", 0)
            civilization = item.get("civilization", "")
            cost = item.get("cost", "")
            primary = item.get("primary_role") or item.get("primary") or item.get("role") or ""
            try:
                count = int(count or 0)
            except Exception:
                count = 0
            if name and count > 0:
                out.append(
                    {
                        "count": count,
                        "name": str(name),
                        "civilization": str(civilization),
                        "cost": str(cost),
                        "primary": str(primary),
                    }
                )
    return out


def create_session(
    db_path: str | Path,
    title: str,
    theme_name: str,
    format_name: str,
    opponent: str,
    candidate: dict[str, Any],
    notes: str = "",
) -> int:
    conn = connect(db_path)
    fmt = normalize_format(format_name)
    deck = deck_items_from_candidate(candidate)
    deck_name = str(candidate.get("deck_name") or candidate.get("name") or title)
    ts = now()
    cur = conn.execute(
        """
        INSERT INTO research_sessions (
            created_at, updated_at, title, theme_name, format_name, opponent,
            deck_name, deck_json, candidate_json, status, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
        """,
        (
            ts,
            ts,
            title,
            theme_name,
            fmt,
            opponent,
            deck_name,
            json.dumps(deck, ensure_ascii=False),
            json.dumps(candidate, ensure_ascii=False),
            notes,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_sessions(db_path: str | Path = DEFAULT_DB, limit: int = 20) -> list[dict[str, Any]]:
    conn = connect(db_path)
    rows = conn.execute(
        """
        SELECT s.*,
               COUNT(m.id) AS match_count,
               SUM(CASE WHEN m.result = 'win' THEN 1 ELSE 0 END) AS win_count
        FROM research_sessions s
        LEFT JOIN research_session_matches m ON m.session_id = s.id
        GROUP BY s.id
        ORDER BY s.updated_at DESC, s.id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


def get_session(db_path: str | Path, session_id: int) -> dict[str, Any] | None:
    conn = connect(db_path)
    row = conn.execute("SELECT * FROM research_sessions WHERE id = ?", (int(session_id),)).fetchone()
    return dict(row) if row else None


def add_match(
    db_path: str | Path,
    session_id: int,
    match_no: int,
    opponent: str,
    format_name: str,
    play_order: str,
    result: str,
    finish_turn: int | None = None,
    yadok_on_time: str = "",
    trap_effective: str = "",
    removal_effective: str = "",
    lock_on_time: str = "",
    external_zone_effective: str = "",
    interfered_by_turn5: str = "",
    had_win_condition: str = "",
    strong_cards: str = "",
    weak_cards: str = "",
    dead_cards: str = "",
    loss_reason: str = "",
    notes: str = "",
) -> int:
    conn = connect(db_path)
    ts = now()
    cur = conn.execute(
        """
        INSERT INTO research_session_matches (
            session_id, created_at, match_no, opponent, format_name, play_order,
            result, finish_turn, yadok_on_time, trap_effective, removal_effective,
            lock_on_time, external_zone_effective, interfered_by_turn5,
            had_win_condition, strong_cards, weak_cards, dead_cards, loss_reason, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(session_id),
            ts,
            int(match_no),
            opponent,
            normalize_format(format_name),
            play_order,
            result,
            finish_turn,
            yadok_on_time,
            trap_effective,
            removal_effective,
            lock_on_time,
            external_zone_effective,
            interfered_by_turn5,
            had_win_condition,
            strong_cards,
            weak_cards,
            dead_cards,
            loss_reason,
            notes,
        ),
    )
    conn.execute("UPDATE research_sessions SET updated_at = ? WHERE id = ?", (ts, int(session_id)))
    conn.commit()
    return int(cur.lastrowid)


def list_matches(db_path: str | Path, session_id: int) -> list[dict[str, Any]]:
    conn = connect(db_path)
    rows = conn.execute(
        """
        SELECT * FROM research_session_matches
        WHERE session_id = ?
        ORDER BY match_no ASC, id ASC
        """,
        (int(session_id),),
    ).fetchall()
    return [dict(row) for row in rows]


def split_cards(value: str) -> list[str]:
    text = str(value or "").replace("、", ",").replace("/", ",")
    return [x.strip() for x in text.split(",") if x.strip()]


def summarize_session(db_path: str | Path, session_id: int) -> dict[str, Any]:
    session = get_session(db_path, session_id)
    matches = list_matches(db_path, session_id)
    total = len(matches)
    wins = sum(1 for m in matches if m.get("result") == "win")
    losses = sum(1 for m in matches if m.get("result") == "lose")
    second_total = sum(1 for m in matches if m.get("play_order") == "後攻")
    second_wins = sum(1 for m in matches if m.get("play_order") == "後攻" and m.get("result") == "win")
    interfered = sum(1 for m in matches if m.get("interfered_by_turn5") == "yes")
    win_condition = sum(1 for m in matches if m.get("had_win_condition") == "yes")

    finish_turns = [int(m["finish_turn"]) for m in matches if m.get("finish_turn") not in (None, "")]
    avg_finish = round(sum(finish_turns) / len(finish_turns), 2) if finish_turns else None

    strong = Counter()
    weak = Counter()
    dead = Counter()
    loss_reasons = Counter()
    for m in matches:
        strong.update(split_cards(m.get("strong_cards", "")))
        weak.update(split_cards(m.get("weak_cards", "")))
        dead.update(split_cards(m.get("dead_cards", "")))
        if m.get("loss_reason"):
            loss_reasons.update([str(m.get("loss_reason"))])

    win_rate = round(wins / total * 100, 1) if total else 0.0
    second_win_rate = round(second_wins / second_total * 100, 1) if second_total else 0.0

    if total < 5:
        verdict = "検証中"
        next_action = "5戦まで実戦ログを追加してください。"
    elif wins >= 2:
        verdict = "続行"
        next_action = "10戦検証へ進めます。勝ち筋と腐りカードを追加で確認してください。"
    elif interfered >= 3:
        verdict = "小修正"
        next_action = "止める力はあります。勝ち筋・フィニッシャー・リソースの不足を補う改修へ進んでください。"
    else:
        verdict = "打ち切り候補"
        next_action = "干渉回数が足りません。別テーマ、別色、またはAD外部ゾーン活用へ派生してください。"

    summary = {
        "session": session or {},
        "total_matches": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "second_total": second_total,
        "second_wins": second_wins,
        "second_win_rate": second_win_rate,
        "average_finish_turn": avg_finish,
        "interfered_by_turn5_count": interfered,
        "had_win_condition_count": win_condition,
        "strong_cards": strong.most_common(10),
        "weak_cards": weak.most_common(10),
        "dead_cards": dead.most_common(10),
        "loss_reasons": loss_reasons.most_common(10),
        "verdict": verdict,
        "next_action": next_action,
    }
    save_action(db_path, session_id, "auto_summary", f"{verdict}: {next_action}", summary)
    return summary


def save_action(db_path: str | Path, session_id: int, action_type: str, action_summary: str, action_json: dict[str, Any]) -> int:
    conn = connect(db_path)
    cur = conn.execute(
        """
        INSERT INTO research_session_actions (
            session_id, created_at, action_type, action_summary, action_json
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(session_id),
            now(),
            action_type,
            action_summary,
            json.dumps(action_json, ensure_ascii=False),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def summary_to_markdown(summary: dict[str, Any]) -> str:
    s = summary
    session = s.get("session") or {}
    lines = [
        "# MANA Remote Research Loop 判定",
        "",
        f"- session_id: {session.get('id', '')}",
        f"- theme: {session.get('theme_name', '')}",
        f"- format: {session.get('format_name', '')}",
        f"- opponent: {session.get('opponent', '')}",
        f"- deck: {session.get('deck_name', '')}",
        "",
        "## 結果",
        "",
        f"- total_matches: {s.get('total_matches', 0)}",
        f"- wins: {s.get('wins', 0)}",
        f"- losses: {s.get('losses', 0)}",
        f"- win_rate: {s.get('win_rate', 0)}%",
        f"- second_win_rate: {s.get('second_win_rate', 0)}%",
        f"- average_finish_turn: {s.get('average_finish_turn', '')}",
        f"- 5ターン目までに干渉: {s.get('interfered_by_turn5_count', 0)}回",
        f"- 止めた後の勝ち筋あり: {s.get('had_win_condition_count', 0)}回",
        "",
        "## カード傾向",
        "",
        f"- strong_cards: {s.get('strong_cards', [])}",
        f"- weak_cards: {s.get('weak_cards', [])}",
        f"- dead_cards: {s.get('dead_cards', [])}",
        f"- loss_reasons: {s.get('loss_reasons', [])}",
        "",
        "## 判定",
        "",
        f"- verdict: {s.get('verdict', '')}",
        f"- next_action: {s.get('next_action', '')}",
        "",
    ]
    return "\n".join(lines)


def write_summary_report(db_path: str | Path, session_id: int, out_dir: str | Path = "data/reports/remote_research_loop") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = summarize_session(db_path, session_id)
    path = out_dir / f"session_{session_id}_summary.md"
    path.write_text(summary_to_markdown(summary), encoding="utf-8")
    return path

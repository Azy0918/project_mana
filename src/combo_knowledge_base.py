from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any

import pandas as pd

from src.import_cards import DEFAULT_DB_PATH


REQUIRED_COLUMNS = [
    "combo_name",
    "format",
    "archetype",
    "core_cards",
    "starter_cards",
    "support_cards",
    "payoff_cards",
    "required_zones",
    "required_conditions",
    "main_sequence",
    "win_condition",
    "strengths",
    "weaknesses",
    "counter_cards_or_tags",
    "related_tags",
    "pattern_type",
    "notes",
]


def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_known_combos_table(db_path: Path = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS known_combos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                combo_name TEXT NOT NULL,
                format TEXT,
                archetype TEXT,
                core_cards TEXT,
                starter_cards TEXT,
                support_cards TEXT,
                payoff_cards TEXT,
                required_zones TEXT,
                required_conditions TEXT,
                main_sequence TEXT,
                win_condition TEXT,
                strengths TEXT,
                weaknesses TEXT,
                counter_cards_or_tags TEXT,
                related_tags TEXT,
                pattern_type TEXT,
                notes TEXT
            )
            """
        )
        conn.commit()


def save_known_combo(
    combo_name: str,
    format: str = "ND",
    archetype: str = "",
    core_cards: str = "",
    starter_cards: str = "",
    support_cards: str = "",
    payoff_cards: str = "",
    required_zones: str = "",
    required_conditions: str = "",
    main_sequence: str = "",
    win_condition: str = "",
    strengths: str = "",
    weaknesses: str = "",
    counter_cards_or_tags: str = "",
    related_tags: str = "",
    pattern_type: str = "",
    notes: str = "",
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    ensure_known_combos_table(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO known_combos (
                created_at, updated_at, combo_name, format, archetype,
                core_cards, starter_cards, support_cards, payoff_cards,
                required_zones, required_conditions, main_sequence,
                win_condition, strengths, weaknesses, counter_cards_or_tags,
                related_tags, pattern_type, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                now,
                combo_name.strip(),
                format.strip() or "ND",
                archetype.strip(),
                core_cards.strip(),
                starter_cards.strip(),
                support_cards.strip(),
                payoff_cards.strip(),
                required_zones.strip(),
                required_conditions.strip(),
                main_sequence.strip(),
                win_condition.strip(),
                strengths.strip(),
                weaknesses.strip(),
                counter_cards_or_tags.strip(),
                related_tags.strip(),
                pattern_type.strip(),
                notes.strip(),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def load_known_combos(
    db_path: Path = DEFAULT_DB_PATH,
    format: str | None = None,
    pattern_type: str | None = None,
) -> pd.DataFrame:
    ensure_known_combos_table(db_path)
    clauses = []
    params: list[Any] = []
    if format:
        clauses.append("format = ?")
        params.append(format)
    if pattern_type:
        clauses.append("pattern_type = ?")
        params.append(pattern_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                id, updated_at, combo_name, format, archetype, core_cards,
                starter_cards, support_cards, payoff_cards, required_zones,
                required_conditions, main_sequence, win_condition, strengths,
                weaknesses, counter_cards_or_tags, related_tags, pattern_type, notes
            FROM known_combos
            {where}
            ORDER BY updated_at DESC, id DESC
            """,
            conn,
            params=params,
        )


def load_known_combo_detail(combo_id: int, db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    ensure_known_combos_table(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM known_combos WHERE id = ?", (int(combo_id),)).fetchone()
    return dict(row) if row else None


def delete_known_combo(combo_id: int, db_path: Path = DEFAULT_DB_PATH) -> None:
    ensure_known_combos_table(db_path)
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM known_combos WHERE id = ?", (int(combo_id),))
        conn.commit()


def known_combos_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def empty_known_combo_template() -> bytes:
    return pd.DataFrame(columns=REQUIRED_COLUMNS).to_csv(index=False).encode("utf-8-sig")


def import_known_combos_csv(path: str | Path, db_path: Path = DEFAULT_DB_PATH) -> int:
    source_path = Path(path)
    if not source_path.exists():
        raise FileNotFoundError(f"CSVが見つかりません: {source_path}")
    df = pd.read_csv(source_path, dtype=str).fillna("")
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"必須列が不足しています: {missing}")

    count = 0
    for _, row in df.iterrows():
        if not str(row["combo_name"]).strip():
            continue
        save_known_combo(
            combo_name=row["combo_name"],
            format=row["format"],
            archetype=row["archetype"],
            core_cards=row["core_cards"],
            starter_cards=row["starter_cards"],
            support_cards=row["support_cards"],
            payoff_cards=row["payoff_cards"],
            required_zones=row["required_zones"],
            required_conditions=row["required_conditions"],
            main_sequence=row["main_sequence"],
            win_condition=row["win_condition"],
            strengths=row["strengths"],
            weaknesses=row["weaknesses"],
            counter_cards_or_tags=row["counter_cards_or_tags"],
            related_tags=row["related_tags"],
            pattern_type=row["pattern_type"],
            notes=row["notes"],
            db_path=db_path,
        )
        count += 1
    return count


def summarize_known_combos(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    df = load_known_combos(db_path)
    if df.empty:
        return {"count": 0, "formats": {}, "patterns": {}, "archetypes": {}}
    return {
        "count": len(df),
        "formats": df["format"].replace("", "不明").value_counts().to_dict(),
        "patterns": df["pattern_type"].replace("", "未分類").value_counts().to_dict(),
        "archetypes": df["archetype"].replace("", "未分類").value_counts().to_dict(),
    }

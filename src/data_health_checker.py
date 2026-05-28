from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.search_cards import DEFAULT_DB_PATH


REQUIRED_TABLES = [
    "cards",
    "card_tags",
    "deck_logs",
    "evaluation_logs",
    "battle_logs",
    "evolution_logs",
    "real_match_logs",
    "deck_versions",
    "deck_changes",
    "test_plans",
    "test_plan_targets",
]


def check_data_health(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "status": "NG",
            "ok": False,
            "quick_check": "DBファイルがありません",
            "tables": [],
            "counts": [],
            "orphans": [],
            "issues": [f"DBファイルが見つかりません: {db_path}"],
        }

    issues = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            issues.append(f"SQLite quick_check: {quick_check}")

        existing_tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

        tables = []
        for table in REQUIRED_TABLES:
            exists = table in existing_tables
            if not exists:
                issues.append(f"必要テーブルがありません: {table}")
            tables.append({"table": table, "exists": exists})

        counts = []
        for table in REQUIRED_TABLES:
            if table not in existing_tables:
                continue
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            counts.append({"table": table, "count": int(count)})

        orphans = _check_orphans(conn, existing_tables)
        for item in orphans:
            if item["count"] > 0:
                issues.append(f'{item["check"]}: {item["count"]}件')

    ok = not issues
    return {
        "status": "OK" if ok else "要確認",
        "ok": ok,
        "quick_check": quick_check,
        "tables": tables,
        "counts": counts,
        "orphans": orphans,
        "issues": issues,
    }


def _check_orphans(conn: sqlite3.Connection, existing_tables: set[str]) -> list[dict[str, Any]]:
    checks = [
        (
            "card_tags.card_id が cards に存在しない",
            {"card_tags", "cards"},
            """
            SELECT COUNT(*)
            FROM card_tags ct
            LEFT JOIN cards c ON c.card_id = ct.card_id
            WHERE c.card_id IS NULL
            """,
        ),
        (
            "evaluation_logs.deck_id が deck_logs に存在しない",
            {"evaluation_logs", "deck_logs"},
            """
            SELECT COUNT(*)
            FROM evaluation_logs e
            LEFT JOIN deck_logs d ON d.deck_id = e.deck_id
            WHERE d.deck_id IS NULL
            """,
        ),
        (
            "battle_logs.deck_a_id が deck_logs に存在しない",
            {"battle_logs", "deck_logs"},
            """
            SELECT COUNT(*)
            FROM battle_logs b
            LEFT JOIN deck_logs d ON d.deck_id = b.deck_a_id
            WHERE d.deck_id IS NULL
            """,
        ),
        (
            "battle_logs.deck_b_id が deck_logs に存在しない",
            {"battle_logs", "deck_logs"},
            """
            SELECT COUNT(*)
            FROM battle_logs b
            LEFT JOIN deck_logs d ON d.deck_id = b.deck_b_id
            WHERE d.deck_id IS NULL
            """,
        ),
        (
            "deck_versions.parent_version_id が deck_versions に存在しない",
            {"deck_versions"},
            """
            SELECT COUNT(*)
            FROM deck_versions child
            LEFT JOIN deck_versions parent ON parent.id = child.parent_version_id
            WHERE child.parent_version_id IS NOT NULL
              AND parent.id IS NULL
            """,
        ),
        (
            "deck_changes.version_id が deck_versions に存在しない",
            {"deck_changes", "deck_versions"},
            """
            SELECT COUNT(*)
            FROM deck_changes c
            LEFT JOIN deck_versions v ON v.id = c.version_id
            WHERE v.id IS NULL
            """,
        ),
        (
            "test_plans.deck_version_id が deck_versions に存在しない",
            {"test_plans", "deck_versions"},
            """
            SELECT COUNT(*)
            FROM test_plans p
            LEFT JOIN deck_versions v ON v.id = p.deck_version_id
            WHERE p.deck_version_id IS NOT NULL
              AND v.id IS NULL
            """,
        ),
        (
            "test_plan_targets.test_plan_id が test_plans に存在しない",
            {"test_plan_targets", "test_plans"},
            """
            SELECT COUNT(*)
            FROM test_plan_targets t
            LEFT JOIN test_plans p ON p.id = t.test_plan_id
            WHERE p.id IS NULL
            """,
        ),
    ]

    rows = []
    for label, required_tables, sql in checks:
        if not required_tables.issubset(existing_tables):
            rows.append({"check": label, "count": None, "status": "未確認"})
            continue
        count = int(conn.execute(sql).fetchone()[0])
        rows.append({"check": label, "count": count, "status": "OK" if count == 0 else "要確認"})
    return rows


def health_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    result = check_data_health(db_path)
    return {
        "status": result["status"],
        "issue_count": len(result["issues"]),
        "quick_check": result["quick_check"],
    }

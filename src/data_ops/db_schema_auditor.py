from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DATA_DIR = Path("data")
DEFAULT_OUT = Path("data/reports/db_schema_audit.md")


DECK_HINT_WORDS = [
    "deck",
    "meta",
    "environment",
    "archetype",
    "デッキ",
    "環境",
    "候補",
    "list",
    "card",
]


def safe_preview(value: Any, limit: int = 180) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", "\\n")
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def list_tables(db_path: Path) -> list[str]:
    try:
        con = sqlite3.connect(db_path)
        rows = con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        con.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def table_info(db_path: Path, table: str) -> list[dict[str, Any]]:
    try:
        con = sqlite3.connect(db_path)
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        con.close()
        return [
            {
                "cid": r[0],
                "name": r[1],
                "type": r[2],
                "notnull": r[3],
                "default": r[4],
                "pk": r[5],
            }
            for r in rows
        ]
    except Exception:
        return []


def row_count(db_path: Path, table: str) -> int:
    try:
        con = sqlite3.connect(db_path)
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        con.close()
        return int(n)
    except Exception:
        return -1


def sample_rows(db_path: Path, table: str, limit: int = 3) -> list[dict[str, Any]]:
    try:
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row
        rows = con.execute(f"SELECT * FROM {table} LIMIT {limit}").fetchall()
        con.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def score_table(table: str, cols: list[str]) -> int:
    blob = " ".join([table] + cols).lower()
    score = 0
    for word in DECK_HINT_WORDS:
        if word.lower() in blob:
            score += 1
    # Strong hints
    for strong in ["deck_name", "deck_list", "cards", "card_name", "deck_json", "main_deck", "archetype", "meta_name"]:
        if strong in blob:
            score += 3
    return score


def audit(data_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for db_path in sorted(data_dir.rglob("*.db")):
        tables = list_tables(db_path)
        for table in tables:
            cols_info = table_info(db_path, table)
            cols = [c["name"] for c in cols_info]
            n = row_count(db_path, table)
            samples = sample_rows(db_path, table, 3)
            results.append(
                {
                    "db_path": str(db_path),
                    "table": table,
                    "row_count": n,
                    "columns": cols,
                    "score": score_table(table, cols),
                    "samples": samples,
                }
            )
    results.sort(key=lambda r: (r["score"], r["row_count"]), reverse=True)
    return results


def write_report(results: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# DB schema audit")
    lines.append("")
    lines.append("保存済み環境デッキの場所を探すため、data配下のSQLite DBを監査しました。")
    lines.append("")
    lines.append("| score | db | table | rows | columns |")
    lines.append("| --- | --- | --- | ---: | --- |")
    for r in results:
        cols = ", ".join(r["columns"])
        lines.append(f"| {r['score']} | {r['db_path']} | {r['table']} | {r['row_count']} | {cols} |")

    lines.append("")
    lines.append("## high-score table samples")
    for r in results[:20]:
        lines.append("")
        lines.append(f"### {r['db_path']} :: {r['table']}")
        lines.append("")
        lines.append(f"- score: {r['score']}")
        lines.append(f"- rows: {r['row_count']}")
        lines.append(f"- columns: {', '.join(r['columns'])}")
        lines.append("")
        if not r["samples"]:
            lines.append("サンプルなし")
            continue
        for i, row in enumerate(r["samples"], start=1):
            lines.append(f"#### sample {i}")
            for k, v in row.items():
                lines.append(f"- {k}: {safe_preview(v)}")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SQLite DB schemas under data/ to find saved meta/environment decks.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    results = audit(Path(args.data_dir))
    write_report(results, Path(args.out))

    print("db_count:", len(set(r["db_path"] for r in results)))
    print("table_count:", len(results))
    print("report:", args.out)
    print("top candidates:")
    for r in results[:10]:
        print(r["score"], r["db_path"], r["table"], r["row_count"], ",".join(r["columns"]))


if __name__ == "__main__":
    main()

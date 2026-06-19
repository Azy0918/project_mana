from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.battle.effects.draft_generator import generate_draft_effect_script
from src.battle.effects.schema import validate_effect_script

# src.import_cards はStreamlit依存を含むため、ルールカーネルからは参照しない
ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "cards.db"

REVIEW_STATUSES = {"draft", "approved", "rejected"}

# 下書き生成時にテキストを完全変換できたとみなすnotes(自動承認の対象)
CLEAN_NOTES = {
    "",
    "能力テキストなし(バニラ)",
    # 後半面の省略は意図した過小評価(exact-safe)であり、前半面が完全変換なら承認可
    "ツインパクト後半面は面選択未対応のため省略(exact-safe)",
}


def ensure_card_effects_table(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS card_effects (
                card_id TEXT PRIMARY KEY,
                name TEXT,
                effect_json TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'draft',
                notes TEXT,
                fidelity TEXT NOT NULL DEFAULT 'approx',
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(card_effects)").fetchall()}
        if "fidelity" not in columns:
            conn.execute("ALTER TABLE card_effects ADD COLUMN fidelity TEXT NOT NULL DEFAULT 'approx'")


def upsert_effect_script(
    script: dict[str, Any],
    review_status: str = "draft",
    db_path: Path = DEFAULT_DB_PATH,
    fidelity: str = "approx",
) -> list[str]:
    """EffectScriptを保存する。検証エラーがあれば保存せずエラー一覧を返す。"""
    if review_status not in REVIEW_STATUSES:
        return [f"未知のreview_status '{review_status}' (対応: {sorted(REVIEW_STATUSES)})"]
    errors = validate_effect_script(script)
    if errors:
        return errors
    ensure_card_effects_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO card_effects (card_id, name, effect_json, review_status, notes, fidelity, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(card_id) DO UPDATE SET
                name = excluded.name,
                effect_json = excluded.effect_json,
                review_status = excluded.review_status,
                notes = excluded.notes,
                fidelity = excluded.fidelity,
                updated_at = excluded.updated_at
            """,
            (
                script["card_id"],
                script.get("name", ""),
                json.dumps(script, ensure_ascii=False),
                review_status,
                "\n".join(script.get("notes", [])),
                fidelity if fidelity in ("exact", "approx") else "approx",
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
    return []


def get_effect_script(
    card_id: str,
    db_path: Path = DEFAULT_DB_PATH,
    approved_only: bool = False,
) -> dict[str, Any] | None:
    ensure_card_effects_table(db_path)
    query = "SELECT effect_json, review_status FROM card_effects WHERE card_id = ?"
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(query, (card_id,)).fetchone()
    if row is None:
        return None
    if approved_only and row[1] != "approved":
        return None
    script = json.loads(row[0])
    script["review_status"] = row[1]
    return script


def list_effect_scripts(
    db_path: Path = DEFAULT_DB_PATH,
    review_status: str | None = None,
) -> list[dict[str, Any]]:
    ensure_card_effects_table(db_path)
    query = "SELECT card_id, name, effect_json, review_status, notes, updated_at FROM card_effects"
    params: tuple[Any, ...] = ()
    if review_status:
        query += " WHERE review_status = ?"
        params = (review_status,)
    query += " ORDER BY card_id"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
    results = []
    for card_id, name, effect_json, status, notes, updated_at in rows:
        script = json.loads(effect_json)
        results.append(
            {
                "card_id": card_id,
                "name": name,
                "abilities": script.get("abilities", []),
                "review_status": status,
                "notes": notes,
                "updated_at": updated_at,
            }
        )
    return results


def load_approved_effects_map(
    db_path: Path = DEFAULT_DB_PATH,
    exact_only: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """承認済みEffectScriptを card_id -> abilities のマップで返す(カーネル実行用)。

    exact_only=True で精密変換(fidelity='exact')のみに限定する。
    ループ探索など近似が許されない用途で使う(自動下書きは常にapprox)。
    """
    ensure_card_effects_table(db_path)
    query = "SELECT card_id, effect_json FROM card_effects WHERE review_status = 'approved'"
    if exact_only:
        query += " AND fidelity = 'exact'"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(query).fetchall()
    effects: dict[str, list[dict[str, Any]]] = {}
    for card_id, effect_json in rows:
        abilities = json.loads(effect_json).get("abilities", [])
        if abilities:
            effects[card_id] = abilities
    return effects


def generate_drafts_for_missing_cards(db_path: Path = DEFAULT_DB_PATH) -> int:
    """card_effects未登録のカードに対してEffectScript下書きを生成・保存する。"""
    ensure_card_effects_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT c.card_id, c.name, c.civilization, c.cost, c.card_type, c.power, c.text
            FROM cards c
            LEFT JOIN card_effects e ON e.card_id = c.card_id
            WHERE e.card_id IS NULL
            """
        ).fetchall()
    created = 0
    for row in rows:
        script = generate_draft_effect_script(dict(row))
        if not upsert_effect_script(script, review_status="draft", db_path=db_path):
            created += 1
    return created


def regenerate_unapproved_drafts(db_path: Path = DEFAULT_DB_PATH) -> int:
    """draft状態のスクリプトを最新の下書き生成ロジックで作り直す。

    approved / rejected は人手・自動承認済みの判断として保持する。
    命令セットや抽出パターンを拡張した後に呼ぶことで変換率を引き上げる。
    """
    ensure_card_effects_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT c.card_id, c.name, c.civilization, c.cost, c.card_type, c.power, c.text
            FROM cards c
            JOIN card_effects e ON e.card_id = c.card_id
            WHERE e.review_status = 'draft'
            """
        ).fetchall()
    updated = 0
    for row in rows:
        script = generate_draft_effect_script(dict(row))
        if not upsert_effect_script(script, review_status="draft", db_path=db_path):
            updated += 1
    return updated


def approve_clean_drafts(db_path: Path = DEFAULT_DB_PATH) -> int:
    """テキストを完全変換できた下書き(notesが警告なし)を一括承認する。

    部分変換(未変換テキスト残りの警告付き)はdraftのまま残し、人手レビュー対象とする。
    自律シミュレーション実行時に、レビュー待ちで効果が全く使われない状態を避けるための機能。
    """
    ensure_card_effects_table(db_path)
    placeholders = ",".join("?" for _ in CLEAN_NOTES)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            f"""
            UPDATE card_effects
            SET review_status = 'approved', updated_at = ?
            WHERE review_status = 'draft' AND (notes IS NULL OR notes IN ({placeholders}))
            """,
            (datetime.now().isoformat(timespec="seconds"), *CLEAN_NOTES),
        )
        return cursor.rowcount


DEFAULT_CURATED_DIR = ROOT_DIR / "data" / "effect_scripts"


def apply_curated_scripts(
    curated_dir: Path = DEFAULT_CURATED_DIR,
    db_path: Path = DEFAULT_DB_PATH,
) -> tuple[int, list[str]]:
    """カード名キーのキュレーション済みEffectScriptを承認済みとして適用する。

    curated_dir/*.json の各ファイルは [{"name": カード名, "abilities": [...], "note": 任意}] 形式。
    自動変換できない複雑カードへの人手(またはAI)による近似定義を、再生成後も常に上書き適用する。
    戻り値は (適用したカード数, 見つからなかったカード名)。
    """
    if not curated_dir.exists():
        return 0, []
    ensure_card_effects_table(db_path)
    applied = 0
    missing: list[str] = []
    with sqlite3.connect(db_path) as conn:
        for json_file in sorted(curated_dir.glob("*.json")):
            entries = json.loads(json_file.read_text(encoding="utf-8"))
            for entry in entries:
                name = entry["name"]
                card_ids = [
                    row[0] for row in conn.execute("SELECT card_id FROM cards WHERE name = ?", (name,))
                ]
                if not card_ids:
                    missing.append(name)
                    continue
                for card_id in card_ids:
                    script = {
                        "card_id": card_id,
                        "name": name,
                        "abilities": entry.get("abilities", []),
                        "notes": [f"キュレーション適用: {entry.get('note', '')}".rstrip(": ")],
                    }
                    errors = upsert_effect_script(
                        script, review_status="approved", db_path=db_path,
                        fidelity=entry.get("fidelity", "approx"),
                    )
                    if errors:
                        # 検証エラーは黙殺せず警告として返す(スキーマ未対応キー等の検知)
                        missing.append(f"{name}: {' / '.join(errors)}")
                    else:
                        applied += 1
    return applied, missing


def coverage_summary(db_path: Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """カードDB全体に対するEffectScript整備状況を返す(ダッシュボード表示用)。"""
    ensure_card_effects_table(db_path)
    with sqlite3.connect(db_path) as conn:
        total_cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        status_rows = conn.execute(
            "SELECT review_status, COUNT(*) FROM card_effects GROUP BY review_status"
        ).fetchall()
    status_counts = {status: count for status, count in status_rows}
    registered = sum(status_counts.values())
    approved = status_counts.get("approved", 0)
    return {
        "total_cards": total_cards,
        "registered": registered,
        "status_counts": status_counts,
        "approved_rate": approved / total_cards if total_cards else 0.0,
        "registered_rate": registered / total_cards if total_cards else 0.0,
    }

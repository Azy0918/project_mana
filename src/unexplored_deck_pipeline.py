"""未開拓デッキ生成パイプライン (route-based C1 orchestrator).

これまで分断されていた
  route_seed_generator -> route_deck_expander -> route_deck_validator
を一気通貫で実行し、検証を通過した未開拓デッキ候補を
generated_decks テーブルへ自動保存するオーケストレーター。

使い方:
  python -m src.unexplored_deck_pipeline
  python -m src.unexplored_deck_pipeline --max-seeds 80 --expand-limit 10 --allow-fixable
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_DB_PATH
from src.deck_condition_analyzer import analyze_deck_condition
from src.generated_deck_store import save_generated_deck
from src.route_seed_generator import generate_route_seed_candidates
from src.route_deck_expander import expand_route_seed_to_deck
from src.route_deck_validator import validate_expanded_deck

DEFAULT_OUTPUT_DIR = Path("data/reports/unexplored_deck_pipeline")

# 検証結果 -> 保存可否の既定ポリシー
SAVEABLE_VERDICTS_STRICT = {"検証OK"}
SAVEABLE_VERDICTS_LOOSE = {"検証OK", "要修正"}


def _deck_rows_to_deck_cards(deck_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """expander の deck_rows を generated_deck_store / deck_condition_analyzer
    が期待する card dict 形式へ変換する。"""
    cards: list[dict[str, Any]] = []
    for row in deck_rows:
        cards.append(
            {
                "name": row.get("card_name", ""),
                "civilization": row.get("civilization", ""),
                "cost": row.get("cost", 0),
                "card_type": row.get("card_type", ""),
                "tags": row.get("tags", ""),
                "quantity": int(row.get("count") or 0),
                "role": row.get("role", ""),
            }
        )
    return cards


def _focus_tags_for_route(route_type: str) -> list[str]:
    mapping = {
        "lock_confirmed_win": ["ロック", "呪文ロック", "攻撃制限"],
        "damage_overflow_win": ["打点", "踏み倒し", "スピードアタッカー"],
        "loop_converted_win": ["リソース", "回収", "墓地利用"],
        "alternate_effect_win": ["特殊勝利", "山札操作", "シールド追加"],
        "opponent_deckout_win": ["山札操作", "ドロー", "攻撃制限"],
    }
    return mapping.get(route_type, [])


def _build_strategy_note(
    candidate: dict[str, Any],
    expansion: dict[str, Any],
    validation: dict[str, Any],
) -> str:
    parts = [
        "unexplored_deck_pipeline v1 による自動生成。",
        f"route_type={candidate.get('route_type', '-')}",
        f"seed={expansion.get('route_seed_cards', '-')}",
        f"adjusted_route_score={candidate.get('adjusted_route_score', '-')}",
        f"validation={validation.get('validation_verdict', '-')} (警告{validation.get('warning_count', 0)}件)",
    ]
    warnings = validation.get("warnings") or []
    if warnings:
        parts.append("主要警告: " + " / ".join(warnings[:3]))
    route_eval = expansion.get("route_evaluation") or {}
    if route_eval.get("route_evaluation_comment"):
        parts.append(str(route_eval["route_evaluation_comment"]))
    parts.append("実戦投入前に人間レビュー必須。")
    return "\n".join(parts)


def _pick_diverse_candidates(
    candidates: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """route_type別にスコア降順でラウンドロビン選択し、生成デッキの偏りを防ぐ。"""
    by_route: dict[str, list[dict[str, Any]]] = {}
    for c in candidates:
        by_route.setdefault(str(c.get("route_type") or ""), []).append(c)
    for pool in by_route.values():
        pool.sort(key=lambda c: int(c.get("adjusted_route_score") or 0), reverse=True)

    picked: list[dict[str, Any]] = []
    route_order = sorted(
        by_route,
        key=lambda rt: int(by_route[rt][0].get("adjusted_route_score") or 0),
        reverse=True,
    )
    index = 0
    while len(picked) < limit and any(by_route.values()):
        route = route_order[index % len(route_order)]
        pool = by_route.get(route) or []
        if pool:
            picked.append(pool.pop(0))
        index += 1
        if index > limit * len(route_order) + len(candidates):
            break
    return picked


def _deck_fingerprint(deck_rows: list[dict[str, Any]]) -> tuple:
    """デッキ内容の重複判定キー。カード名と枚数の組を正規化する。"""
    return tuple(sorted(
        (str(row.get("card_name") or ""), int(row.get("count") or 0))
        for row in deck_rows
    ))


def run_unexplored_deck_pipeline(
    db_path: str | Path = DEFAULT_DB_PATH,
    max_seeds: int = 50,
    expand_limit: int = 8,
    min_adjusted_score: int = 55,
    allow_fixable: bool = False,
    save_to_db: bool = True,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    """seed生成→40枚化→検証→保存 を一気通貫で実行する。

    Returns a summary dict with per-candidate results and saved deck ids.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saveable_verdicts = SAVEABLE_VERDICTS_LOOSE if allow_fixable else SAVEABLE_VERDICTS_STRICT

    # 1. route seed 候補生成 (評価込み)
    candidates = generate_route_seed_candidates(
        db_path=db_path,
        max_candidates=max_seeds,
        evaluate=True,
        strict_quality_filter=True,
    )
    eligible = [
        c for c in candidates
        if int(c.get("adjusted_route_score") or 0) >= min_adjusted_score
    ]
    picked = _pick_diverse_candidates(eligible, expand_limit)

    results: list[dict[str, Any]] = []
    saved_ids: list[int] = []
    seen_fingerprints: set[tuple] = set()

    for candidate in picked:
        entry: dict[str, Any] = {
            "deck_name": candidate.get("deck_name", "-"),
            "route_type": candidate.get("route_type", "-"),
            "adjusted_route_score": candidate.get("adjusted_route_score"),
            "seed_cards": candidate.get("route_seed_cards", ""),
        }

        # 2. 40枚化
        try:
            expansion = expand_route_seed_to_deck(candidate, db_path=db_path)
        except Exception as exc:
            entry["status"] = "expand_error"
            entry["error"] = str(exc)
            results.append(entry)
            continue

        # 2.5 内容重複の排除（seedが違っても展開結果がほぼ同じケースを除外）
        fingerprint = _deck_fingerprint(expansion.get("deck_rows", []))
        if fingerprint in seen_fingerprints:
            entry["status"] = "duplicate_deck"
            results.append(entry)
            continue
        seen_fingerprints.add(fingerprint)

        # 3. 検証
        validation = validate_expanded_deck(expansion)
        verdict = validation.get("validation_verdict", "棄却候補")
        entry["validation_verdict"] = verdict
        entry["warning_count"] = validation.get("warning_count", 0)

        if verdict not in saveable_verdicts:
            entry["status"] = "rejected"
            results.append(entry)
            continue

        # 4. DB保存
        if not save_to_db:
            entry["status"] = "validated_not_saved"
            results.append(entry)
            continue

        deck_cards = _deck_rows_to_deck_cards(expansion.get("deck_rows", []))
        civilizations = [
            civ for civ in str(expansion.get("target_civilizations", "")).split("/") if civ
        ]
        route_type = str(candidate.get("route_type") or "")
        focus_tags = _focus_tags_for_route(route_type)
        analysis = analyze_deck_condition(deck_cards, civilizations, focus_tags, [])

        deck_eval = expansion.get("deck_evaluation") or {}
        evaluation = deck_eval if isinstance(deck_eval, dict) else {}

        deck_name = f"未開拓 {route_type}: {expansion.get('route_seed_cards', '')[:40]}"
        try:
            deck_id = save_generated_deck(
                deck_name=deck_name,
                civilizations=civilizations,
                deck_type=route_type,
                focus_tags=focus_tags,
                avoid_tags=[],
                strategy_note=_build_strategy_note(candidate, expansion, validation),
                deck_cards=deck_cards,
                analysis=analysis,
                evaluation=evaluation,
                candidate_origin="route_based",
                db_path=Path(db_path),
            )
        except Exception as exc:
            entry["status"] = "save_error"
            entry["error"] = str(exc)
            results.append(entry)
            continue

        saved_ids.append(deck_id)
        entry["status"] = "saved"
        entry["generated_deck_id"] = deck_id
        entry["deck_size"] = expansion.get("deck_size")
        results.append(entry)

    summary = {
        "executed_at": datetime.now().isoformat(timespec="seconds"),
        "seed_candidates_total": len(candidates),
        "expanded_count": len(picked),
        "saved_count": len(saved_ids),
        "saved_deck_ids": saved_ids,
        "allow_fixable": allow_fixable,
        "min_adjusted_score": min_adjusted_score,
        "results": results,
    }

    summary_path = output_dir / "pipeline_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = output_dir / "pipeline_summary.md"
    md_path.write_text(pipeline_summary_to_markdown(summary), encoding="utf-8")
    summary["summary_json"] = str(summary_path)
    summary["summary_markdown"] = str(md_path)
    return summary


def pipeline_summary_to_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# 未開拓デッキ生成パイプライン実行結果",
        "",
        f"- 実行日時: {summary.get('executed_at', '-')}",
        f"- seed候補数: {summary.get('seed_candidates_total', 0)}",
        f"- 40枚化対象: {summary.get('expanded_count', 0)}",
        f"- 保存デッキ数: {summary.get('saved_count', 0)}",
        f"- 要修正も保存: {summary.get('allow_fixable', False)}",
        "",
        "| deck_name | route_type | score | 検証 | 警告数 | status | deck_id |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in summary.get("results", []):
        lines.append(
            f"| {row.get('deck_name', '-')} | {row.get('route_type', '-')} | "
            f"{row.get('adjusted_route_score', '-')} | {row.get('validation_verdict', '-')} | "
            f"{row.get('warning_count', '-')} | {row.get('status', '-')} | "
            f"{row.get('generated_deck_id', '-')} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="未開拓デッキ生成パイプラインを実行する。")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite DB path")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_DIR), help="Output directory")
    parser.add_argument("--max-seeds", type=int, default=50, help="seed候補の最大数")
    parser.add_argument("--expand-limit", type=int, default=8, help="40枚化する候補数")
    parser.add_argument("--min-score", type=int, default=55, help="40枚化する最小adjusted_route_score")
    parser.add_argument("--allow-fixable", action="store_true", help="要修正判定のデッキも保存する")
    parser.add_argument("--dry-run", action="store_true", help="DB保存を行わない")
    args = parser.parse_args()

    summary = run_unexplored_deck_pipeline(
        db_path=args.db,
        max_seeds=args.max_seeds,
        expand_limit=args.expand_limit,
        min_adjusted_score=args.min_score,
        allow_fixable=args.allow_fixable,
        save_to_db=not args.dry_run,
        output_dir=args.out,
    )
    print(f"seed候補: {summary['seed_candidates_total']}")
    print(f"40枚化: {summary['expanded_count']}")
    print(f"保存: {summary['saved_count']} -> ids={summary['saved_deck_ids']}")
    print(f"summary: {summary['summary_json']}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.combo_knowledge_base import load_known_combos
from src.import_cards import DEFAULT_DB_PATH
from src.route_proof_searcher import list_proof_win_conditions, search_route_proofs


DEFAULT_OUT = Path("data/reports/rediscovery")


def _split_names(value: Any) -> list[str]:
    return [name.strip() for name in str(value or "").split(";") if name.strip()]


def _route_card_names(row: dict[str, Any]) -> set[str]:
    # route_seed_cardsの区切りは " / "。ツインパクト名は "A/B" のように
    # 空白なしの "/" を含むため、空白付き区切りでのみ分割する。
    names: set[str] = set()
    for column in ["route_seed_cards", "route_cards"]:
        value = row.get(column, "")
        if isinstance(value, (list, tuple)):
            names.update(str(v).strip() for v in value if str(v).strip())
        else:
            names.update(part.strip() for part in str(value).split(" / ") if part.strip())
    return names


def _expected_conditions(combo_notes: Any) -> list[str]:
    """seedのnotes欄(例: 'route想定: lock_confirmed_win / opponent_deckout_win')から想定勝利条件を拾う。"""
    keys = list(list_proof_win_conditions())
    found = [key for key in keys if key in str(combo_notes or "")]
    return found or keys


def check_anchored_rediscovery(
    db_path: Path = DEFAULT_DB_PATH,
    max_depth: int = 2,
    beam_width: int = 60,
    max_total_cost: int = 24,
    limit: int = 80,
) -> list[dict[str, Any]]:
    """コアカードを起点に固定した探索で、残りのコアカードを見つけられるかを判定する。

    実運用(seed起点でデッキを組む)に近い条件での再現性テスト。
    コア1枚のコンボはアンカー探索が自明になるため対象外(グローバル判定を使う)。
    """
    combos = load_known_combos(db_path)
    results: list[dict[str, Any]] = []
    for _, combo in combos.iterrows():
        core = _split_names(combo.get("core_cards"))
        if len(core) < 2:
            continue
        conditions = _expected_conditions(combo.get("notes"))
        best = {"found": set(), "route": None, "anchor": "", "condition": ""}
        for anchor in core:
            partners = set(core) - {anchor}
            for condition_key in conditions:
                rows = search_route_proofs(
                    db_path=db_path,
                    win_condition=condition_key,
                    max_depth=max_depth,
                    beam_width=beam_width,
                    max_total_cost=max_total_cost,
                    limit=limit,
                    anchor_card_name=anchor,
                )
                for row in rows:
                    found = partners & _route_card_names(row)
                    if len(found) > len(best["found"]):
                        best = {"found": found, "route": row, "anchor": anchor, "condition": condition_key}
                    if found == partners:
                        break
                if best["found"] == partners:
                    break
            if best["found"] == partners:
                break
        partners_needed = len(core) - 1
        status = (
            "full"
            if len(best["found"]) >= partners_needed
            else ("partial" if best["found"] else "miss")
        )
        route = best["route"] or {}
        results.append(
            {
                "combo_name": str(combo.get("combo_name", "")),
                "core_cards": sorted(core),
                "status": status,
                "anchor": best["anchor"],
                "found_partners": sorted(best["found"]),
                "condition": best["condition"],
                "matched_route_cards": str(route.get("route_seed_cards", "")),
                "matched_proof_score": route.get("proof_score", ""),
            }
        )
    return results


def collect_route_pool(
    db_path: Path = DEFAULT_DB_PATH,
    max_depth: int = 3,
    beam_width: int = 60,
    max_total_cost: int = 24,
    limit_per_condition: int = 120,
) -> list[dict[str, Any]]:
    """全勝利条件でルート証明探索を実行し、候補ルートをまとめて返す。"""
    rows: list[dict[str, Any]] = []
    for condition_key in list_proof_win_conditions():
        rows.extend(
            search_route_proofs(
                db_path=db_path,
                win_condition=condition_key,
                max_depth=max_depth,
                beam_width=beam_width,
                max_total_cost=max_total_cost,
                limit=limit_per_condition,
            )
        )
    return rows


def check_rediscovery(
    db_path: Path = DEFAULT_DB_PATH,
    route_rows: list[dict[str, Any]] | None = None,
    **search_kwargs: Any,
) -> dict[str, Any]:
    """既知コンボのコアカードをルート探索が自力で再発見できたかを判定する。

    判定基準:
    - full: コアカード全部が同一ルート内に同時に出現
    - partial: コアカード2枚以上(コア1枚のコンボは1枚)が同一ルート内に出現
    - miss: 上記いずれも満たさない
    """
    combos = load_known_combos(db_path)
    rows = route_rows if route_rows is not None else collect_route_pool(db_path, **search_kwargs)
    route_sets = [
        {"names": _route_card_names(row), "row": row}
        for row in rows
        if _route_card_names(row)
    ]

    results: list[dict[str, Any]] = []
    for _, combo in combos.iterrows():
        core = set(_split_names(combo.get("core_cards")))
        if not core:
            continue
        need_partial = 1 if len(core) == 1 else 2
        best: dict[str, Any] = {"overlap": 0, "route": None}
        status = "miss"
        for entry in route_sets:
            overlap = len(core & entry["names"])
            if overlap > best["overlap"]:
                best = {"overlap": overlap, "route": entry["row"]}
            if overlap >= len(core):
                status = "full"
                best = {"overlap": overlap, "route": entry["row"]}
                break
        if status != "full" and best["overlap"] >= need_partial:
            status = "partial"
        route = best["route"] or {}
        results.append(
            {
                "combo_name": str(combo.get("combo_name", "")),
                "pattern_type": str(combo.get("pattern_type", "")),
                "core_cards": sorted(core),
                "core_size": len(core),
                "status": status,
                "best_overlap": best["overlap"],
                "matched_route_type": str(route.get("route_type", "")),
                "matched_route_cards": str(route.get("route_seed_cards", "")),
                "matched_proof_score": route.get("proof_score", ""),
            }
        )

    full = sum(1 for r in results if r["status"] == "full")
    partial = sum(1 for r in results if r["status"] == "partial")
    total = len(results)
    anchored = check_anchored_rediscovery(db_path)
    anchored_full = sum(1 for r in anchored if r["status"] == "full")
    anchored_total = len(anchored)
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "total_known_combos": total,
        "full_rediscovered": full,
        "partial_rediscovered": partial,
        "missed": total - full - partial,
        "full_rate": round(full / total, 3) if total else 0.0,
        "full_or_partial_rate": round((full + partial) / total, 3) if total else 0.0,
        "route_pool_size": len(rows),
        "results": results,
        "anchored_total": anchored_total,
        "anchored_full": anchored_full,
        "anchored_full_rate": round(anchored_full / anchored_total, 3) if anchored_total else 0.0,
        "anchored_results": anchored,
    }


def rediscovery_report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 既知コンボ再発見率レポート",
        "",
        f"- 実行日時: {report['created_at']}",
        f"- 既知コンボ数: {report['total_known_combos']}",
        f"- 探索ルート候補数: {report['route_pool_size']}",
        f"- 完全再発見 (コア全カード同居): {report['full_rediscovered']}件",
        f"- 部分再発見 (コア2枚以上同居): {report['partial_rediscovered']}件",
        f"- 未発見: {report['missed']}件",
        f"- 完全再発見率: {report['full_rate']:.1%}",
        f"- 完全+部分再発見率: {report['full_or_partial_rate']:.1%}",
        "",
        "| コンボ | 型 | コア枚数 | 判定 | 一致数 | 一致ルート型 | 一致ルートカード |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["results"]:
        lines.append(
            "| {combo} | {pattern} | {size} | {status} | {overlap} | {rtype} | {rcards} |".format(
                combo=row["combo_name"],
                pattern=row["pattern_type"],
                size=row["core_size"],
                status=row["status"],
                overlap=row["best_overlap"],
                rtype=row["matched_route_type"],
                rcards=str(row["matched_route_cards"]).replace("|", "\\|"),
            )
        )
    lines.append("")
    lines.append("判定基準: full=コアカード全部が同一ルート内に出現 / partial=コア2枚以上(コア1枚のコンボは1枚)が同一ルート内に出現")

    anchored = report.get("anchored_results", [])
    if anchored:
        lines.extend(
            [
                "",
                "## アンカー探索 (コアカード起点固定)",
                "",
                f"- 対象コンボ (コア2枚以上): {report['anchored_total']}件",
                f"- 相方カード発見: {report['anchored_full']}件",
                f"- アンカー再発見率: {report['anchored_full_rate']:.1%}",
                "",
                "| コンボ | 判定 | アンカー | 発見した相方 | 勝利条件 | 一致ルートカード |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in anchored:
            lines.append(
                "| {combo} | {status} | {anchor} | {partners} | {cond} | {rcards} |".format(
                    combo=row["combo_name"],
                    status=row["status"],
                    anchor=row["anchor"],
                    partners=";".join(row["found_partners"]),
                    cond=row["condition"],
                    rcards=str(row["matched_route_cards"]).replace("|", "\\|"),
                )
            )
        lines.append("")
        lines.append("アンカー探索: コアカード1枚を起点に固定し、探索器が残りのコアカードを相方として拾えるかを見る。実運用(seed起点の構築)に近い条件。")
    return "\n".join(lines)


def write_rediscovery_outputs(report: dict[str, Any], output_dir: Path = DEFAULT_OUT) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "rediscovery_report.md"
    json_path = output_dir / "rediscovery_report.json"
    md_path.write_text(rediscovery_report_to_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="既知コンボ再発見率チェッカー")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--beam-width", type=int, default=60)
    parser.add_argument("--max-total-cost", type=int, default=24)
    parser.add_argument("--limit-per-condition", type=int, default=120)
    args = parser.parse_args()

    report = check_rediscovery(
        db_path=Path(args.db),
        max_depth=args.max_depth,
        beam_width=args.beam_width,
        max_total_cost=args.max_total_cost,
        limit_per_condition=args.limit_per_condition,
    )
    paths = write_rediscovery_outputs(report, Path(args.out))
    print(f"既知コンボ: {report['total_known_combos']}件")
    print(f"完全再発見: {report['full_rediscovered']}件 / 部分再発見: {report['partial_rediscovered']}件 / 未発見: {report['missed']}件")
    print(f"完全再発見率: {report['full_rate']:.1%} / 完全+部分: {report['full_or_partial_rate']:.1%}")
    for key, path in paths.items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_VALIDATION_JSON = Path("data/reports/expanded_route_decks/route_deck_validation.json")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _short(text: Any, limit: int = 120) -> str:
    s = str(text or "").replace("\n", " ").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def load_route_deck_validation_results(
    validation_json_path: str | Path = DEFAULT_VALIDATION_JSON,
) -> list[dict[str, Any]]:
    path = Path(validation_json_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def summarize_validation_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "total": len(results),
        "検証OK": 0,
        "要修正": 0,
        "棄却候補": 0,
        "その他": 0,
    }
    for row in results:
        verdict = str(row.get("validation_verdict") or "")
        if verdict in counts:
            counts[verdict] += 1
        else:
            counts["その他"] += 1
    return counts


def pick_top_validated_routes(
    results: list[dict[str, Any]],
    limit: int = 5,
    prefer_ok: bool = True,
) -> list[dict[str, Any]]:
    def sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
        verdict = str(row.get("validation_verdict") or "")
        if verdict == "検証OK":
            verdict_rank = 0
        elif verdict == "要修正":
            verdict_rank = 1
        elif verdict == "棄却候補":
            verdict_rank = 2
        else:
            verdict_rank = 3

        warning_count = _safe_int(row.get("warning_count"), 99)

        win_plan = row.get("win_plan") or {}
        seed = row.get("seed_connection") or {}
        # Higher practical counts are better, but keep as negative for ascending sort.
        practical_strength = (
            _safe_int(win_plan.get("defense_count"))
            + _safe_int(win_plan.get("resource_count"))
            + _safe_int(win_plan.get("win_count"))
            + _safe_int(win_plan.get("removal_count"))
            + (5 if seed.get("seed_shared_tags") else 0)
        )
        return (verdict_rank, warning_count, -practical_strength)

    rows = sorted(results, key=sort_key)
    if prefer_ok:
        ok_rows = [row for row in rows if row.get("validation_verdict") == "検証OK"]
        if ok_rows:
            return ok_rows[:limit]
    return rows[:limit]


def validation_result_to_brief_rows(results: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in results[:limit]:
        seed = row.get("seed_connection") or {}
        win = row.get("win_plan") or {}
        civ = row.get("civilization") or {}
        rows.append(
            {
                "deck_name": row.get("deck_name", ""),
                "route_type": row.get("route_type", ""),
                "判定": row.get("validation_verdict", ""),
                "警告数": row.get("warning_count", 0),
                "seed": row.get("route_seed_cards", ""),
                "共有タグ": seed.get("seed_shared_tags", ""),
                "防御": win.get("defense_count", ""),
                "リソース": win.get("resource_count", ""),
                "勝ち手段": win.get("win_count", ""),
                "除去": win.get("removal_count", ""),
                "多色": civ.get("multicolor_count", ""),
                "文明外": civ.get("off_civilization_count", ""),
            }
        )
    return rows


def _markdown_table(rows: list[dict[str, Any]], empty_message: str = "該当なし") -> list[str]:
    if not rows:
        return [empty_message]

    columns = list(rows[0].keys())
    lines = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for row in rows:
        values = []
        for column in columns:
            values.append(_short(row.get(column, ""), 80))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def build_route_validation_brief_section(
    validation_json_path: str | Path = DEFAULT_VALIDATION_JSON,
    table_limit: int = 10,
    detail_limit: int = 5,
) -> str:
    results = load_route_deck_validation_results(validation_json_path)
    lines: list[str] = []

    lines.append("## route_seed 展開デッキ検証結果")
    lines.append("")

    if not results:
        lines.append("route_seed展開デッキ検証結果はまだありません。")
        lines.append("")
        lines.append("生成するには以下を実行してください。")
        lines.append("")
        lines.append("```powershell")
        lines.append("python -m src.route_seed_generator")
        lines.append("python -m src.route_deck_expander")
        lines.append("python -m src.route_deck_validator")
        lines.append("```")
        return "\n".join(lines)

    counts = summarize_validation_counts(results)
    lines.append("### 検証サマリー")
    lines.append("")
    lines.append(f"- 検証対象: {counts['total']}件")
    lines.append(f"- 検証OK: {counts['検証OK']}件")
    lines.append(f"- 要修正: {counts['要修正']}件")
    lines.append(f"- 棄却候補: {counts['棄却候補']}件")
    if counts["その他"]:
        lines.append(f"- その他: {counts['その他']}件")
    lines.append("")

    ordered = pick_top_validated_routes(results, limit=table_limit, prefer_ok=False)
    brief_rows = validation_result_to_brief_rows(ordered, limit=table_limit)
    lines.append("### 検証結果一覧")
    lines.append("")
    lines.extend(_markdown_table(brief_rows, empty_message="検証結果はありません。"))
    lines.append("")

    top_ok = pick_top_validated_routes(results, limit=detail_limit, prefer_ok=True)
    lines.append("### 優先レビュー候補")
    lines.append("")
    for index, row in enumerate(top_ok, start=1):
        seed = row.get("seed_connection") or {}
        win = row.get("win_plan") or {}
        evo = row.get("evolution") or {}
        civ = row.get("civilization") or {}
        warnings = row.get("warnings") or []

        lines.append(f"#### {index}. {row.get('deck_name', '-')}")
        lines.append("")
        lines.append(f"- 判定: {row.get('validation_verdict', '-')}")
        lines.append(f"- route_type: {row.get('route_type', '-')}")
        lines.append(f"- seed: {row.get('route_seed_cards', '-')}")
        lines.append(f"- warning_count: {row.get('warning_count', 0)}")
        lines.append(f"- seed共有タグ: {seed.get('seed_shared_tags') or '-'}")
        lines.append(
            "- 主要指標: "
            f"defense={win.get('defense_count', '-')}, "
            f"resource={win.get('resource_count', '-')}, "
            f"win={win.get('win_count', '-')}, "
            f"removal={win.get('removal_count', '-')}, "
            f"multicolor={civ.get('multicolor_count', '-')}, "
            f"off_civ={civ.get('off_civilization_count', '-')}, "
            f"evolution_like={evo.get('evolution_like_count', '-')}"
        )
        if warnings:
            lines.append("- 警告:")
            for warning in warnings[:5]:
                lines.append(f"  - {warning}")
        else:
            lines.append("- 警告: なし")
        lines.append("")

    needs_fix = [row for row in results if row.get("validation_verdict") == "要修正"]
    if needs_fix:
        lines.append("### 要修正候補の主な理由")
        lines.append("")
        for row in needs_fix[:detail_limit]:
            warnings = row.get("warnings") or []
            lines.append(f"- {row.get('deck_name', '-')}: " + " / ".join(map(str, warnings[:3])))
        lines.append("")

    lines.append("### 次の実験候補")
    lines.append("")
    if top_ok:
        best = top_ok[0]
        lines.append(f"- 最優先: {best.get('deck_name', '-')}")
        lines.append(f"- seed: {best.get('route_seed_cards', '-')}")
        lines.append("- 推奨アクション: 一人回しシミュレーション、手札事故確認、対速攻・対墓地・対呪文系の仮想対面チェック。")
    else:
        lines.append("- 検証OK候補がないため、要修正候補のseed接続と条件付きカードを見直してください。")

    return "\n".join(lines)


def write_route_validation_brief_section(
    output_path: str | Path = "data/reports/expanded_route_decks/route_validation_brief_section.md",
    validation_json_path: str | Path = DEFAULT_VALIDATION_JSON,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_route_validation_brief_section(validation_json_path),
        encoding="utf-8",
    )
    return output_path


if __name__ == "__main__":
    path = write_route_validation_brief_section()
    print(path)

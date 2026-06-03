from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from io import StringIO
from pathlib import Path
from typing import Any


EVOLUTION_TERMS = ["進化", "NEO進化", "超無限進化", "マナ進化", "墓地進化", "手札進化"]
CONDITIONAL_PAYOFF_TERMS = ["侵略", "革命チェンジ", "G・ゼロ", "メクレイド", "ハイパー化", "タマシード"]
DEFENSE_TERMS = ["S・トリガー", "G・ストライク", "受け札", "ブロッカー", "攻撃制限", "シールド追加"]
WIN_TERMS = ["フィニッシャー", "打点", "ロック", "呪文ロック", "特殊勝利", "山札操作"]
RESOURCE_TERMS = ["初動", "マナ加速", "ドロー", "リソース", "サーチ候補", "山札操作"]
REMOVAL_TERMS = ["除去", "バウンス", "パワー低下", "マッハファイター", "盤面処理"]


def _split_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[;/／,\n]+", str(value))
    return [str(item).strip() for item in raw if str(item).strip()]


def _card_tags(row: dict[str, Any]) -> set[str]:
    return set(_split_terms(row.get("tags", "")))


def _card_civs(row: dict[str, Any]) -> set[str]:
    return {c for c in _split_terms(row.get("civilization", "")) if c and c != "無色"}


def _count_if(deck_rows: list[dict[str, Any]], terms: list[str]) -> int:
    total = 0
    for row in deck_rows:
        blob = f"{row.get('card_name','')};{row.get('tags','')};{row.get('role','')}"
        if any(term in blob for term in terms):
            total += int(row.get("count") or 0)
    return total


def _rows_if(deck_rows: list[dict[str, Any]], terms: list[str]) -> list[dict[str, Any]]:
    rows = []
    for row in deck_rows:
        blob = f"{row.get('card_name','')};{row.get('tags','')};{row.get('role','')}"
        if any(term in blob for term in terms):
            rows.append(row)
    return rows


def _main_civilizations(deck_rows: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in deck_rows:
        count = int(row.get("count") or 0)
        for civ in _card_civs(row):
            counter[civ] += count
    return counter


def _load_expanded_json(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def _load_expanded_markdown_tables(path: str | Path) -> list[dict[str, Any]]:
    """Fallback parser for expanded_route_decks.md.

    Prefer expanded_route_decks.json when available. This parser extracts each
    "## デッキ案" table as an expansion-like dict.
    """
    text = Path(path).read_text(encoding="utf-8")
    chunks = re.split(r"\n---\n", text)
    expansions: list[dict[str, Any]] = []
    for chunk in chunks:
        if "## デッキ案" not in chunk:
            continue
        title_match = re.search(r"^#\s+(.+)$", chunk, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "expanded deck"

        route_type_match = re.search(r"- route_type:\s*(.+)", chunk)
        seed_match = re.search(r"- route_seed_cards:\s*(.+)", chunk)
        target_civs_match = re.search(r"- target_civilizations:\s*(.+)", chunk)

        table_part = chunk.split("## デッキ案", 1)[1]
        table_part = table_part.split("## 人間レビュー観点", 1)[0]
        rows: list[dict[str, Any]] = []
        for line in table_part.splitlines():
            line = line.strip()
            if not line.startswith("|") or "---" in line or "カード名" in line:
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 7:
                continue
            try:
                count = int(cells[0])
            except Exception:
                continue
            rows.append(
                {
                    "count": count,
                    "card_name": cells[1],
                    "civilization": cells[2],
                    "cost": int(cells[3]) if cells[3].isdigit() else 0,
                    "card_type": cells[4],
                    "role": cells[5],
                    "tags": cells[6],
                }
            )

        expansions.append(
            {
                "deck_name": title,
                "route_type": route_type_match.group(1).strip() if route_type_match else "",
                "route_seed_cards": seed_match.group(1).strip() if seed_match else "",
                "target_civilizations": target_civs_match.group(1).strip() if target_civs_match else "",
                "deck_rows": rows,
            }
        )
    return expansions


def load_expanded_decks(path: str | Path = "data/reports/expanded_route_decks/expanded_route_decks.json") -> list[dict[str, Any]]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        return _load_expanded_json(path)
    return _load_expanded_markdown_tables(path)


def validate_evolution_conditions(deck_rows: list[dict[str, Any]]) -> dict[str, Any]:
    evolution_rows = _rows_if(deck_rows, EVOLUTION_TERMS)
    low_cost_creatures = [
        row for row in deck_rows
        if int(row.get("cost") or 0) <= 4 and "クリーチャー" in str(row.get("card_type", ""))
    ]
    low_cost_count = sum(int(row.get("count") or 0) for row in low_cost_creatures)
    evolution_count = sum(int(row.get("count") or 0) for row in evolution_rows)

    warnings: list[str] = []
    if evolution_count >= 4 and low_cost_count < 12:
        warnings.append(f"進化/条件付きカードが多い一方、低コスト進化元候補が少なめです: 進化系{evolution_count}枚 / 低コスト候補{low_cost_count}枚")

    conditional_rows = _rows_if(deck_rows, CONDITIONAL_PAYOFF_TERMS)
    conditional_count = sum(int(row.get("count") or 0) for row in conditional_rows)
    if conditional_count >= 6:
        warnings.append(f"侵略/革命チェンジ/G・ゼロ/メクレイド等の条件付きカードが多めです: {conditional_count}枚。条件成立を手動確認してください。")

    return {
        "evolution_like_count": evolution_count,
        "conditional_payoff_count": conditional_count,
        "low_cost_creature_count": low_cost_count,
        "evolution_warnings": warnings,
        "evolution_cards": ";".join(row.get("card_name", "") for row in evolution_rows[:10]),
    }


def validate_civilization_base(deck_rows: list[dict[str, Any]], target_civilizations: str = "") -> dict[str, Any]:
    civ_counter = _main_civilizations(deck_rows)
    target_civs = set(_split_terms(target_civilizations.replace("/", ";")))
    off_civ_count = 0
    five_color_count = 0
    multicolor_count = 0

    for row in deck_rows:
        count = int(row.get("count") or 0)
        civs = _card_civs(row)
        if len(civs) >= 2:
            multicolor_count += count
        if len(civs) >= 5:
            five_color_count += count
        if target_civs and civs and not bool(civs & target_civs):
            off_civ_count += count

    warnings: list[str] = []
    if multicolor_count >= 24:
        warnings.append(f"多色カードが多く、序盤の色事故リスクがあります: {multicolor_count}枚")
    if five_color_count >= 3:
        warnings.append(f"5色カードが多めです: {five_color_count}枚")
    if off_civ_count >= 4:
        warnings.append(f"seed文明外カードが多めです: {off_civ_count}枚")
    for civ, count in civ_counter.items():
        if target_civs and civ in target_civs and count < 10:
            warnings.append(f"主要文明 {civ} の枚数が少なめです: {count}枚相当")

    return {
        "civilization_counts": dict(civ_counter),
        "multicolor_count": multicolor_count,
        "five_color_count": five_color_count,
        "off_civilization_count": off_civ_count,
        "civilization_warnings": warnings,
    }


def validate_seed_connection(expansion: dict[str, Any]) -> dict[str, Any]:
    deck_rows = expansion.get("deck_rows", [])
    seed_names = _split_terms(str(expansion.get("route_seed_cards", "")).replace(" / ", ";"))
    seed_rows = []
    for name in seed_names:
        for row in deck_rows:
            if name and (name == row.get("card_name") or name in str(row.get("card_name", ""))):
                seed_rows.append(row)
                break

    seed_tag_sets = [_card_tags(row) for row in seed_rows]
    shared_tags = set.intersection(*seed_tag_sets) if len(seed_tag_sets) >= 2 else set()
    union_tags = set.union(*seed_tag_sets) if seed_tag_sets else set()

    support_count = _count_if(deck_rows, RESOURCE_TERMS)
    removal_count = _count_if(deck_rows, REMOVAL_TERMS)
    defense_count = _count_if(deck_rows, DEFENSE_TERMS)
    win_count = _count_if(deck_rows, WIN_TERMS)

    warnings: list[str] = []
    if len(seed_rows) < len(seed_names):
        warnings.append("一部seedカードがデッキ内に見つかりません。")
    if len(seed_rows) >= 2 and not shared_tags:
        warnings.append("seedカード同士の共有タグがなく、接続が弱い可能性があります。")
    if len(seed_rows) >= 2 and len(shared_tags) <= 1:
        warnings.append(f"seed接続が薄めです。共有タグ: {','.join(sorted(shared_tags)) or '-'}")
    if support_count < 10:
        warnings.append(f"seedへ到達する初動/リソース/サーチが少なめです: {support_count}枚相当")
    if win_count < 8:
        warnings.append(f"勝ち切り手段が少なめです: {win_count}枚相当")
    if defense_count < 8:
        warnings.append(f"速攻対面への受け札が少なめです: {defense_count}枚相当")

    return {
        "seed_cards_found": len(seed_rows),
        "seed_cards_expected": len(seed_names),
        "seed_shared_tags": ";".join(sorted(shared_tags)),
        "seed_union_tags": ";".join(sorted(union_tags)),
        "support_count": support_count,
        "removal_count": removal_count,
        "defense_count": defense_count,
        "win_count": win_count,
        "seed_connection_warnings": warnings,
    }


def validate_win_plan(deck_rows: list[dict[str, Any]], route_type: str = "") -> dict[str, Any]:
    defense_count = _count_if(deck_rows, DEFENSE_TERMS)
    win_count = _count_if(deck_rows, WIN_TERMS)
    resource_count = _count_if(deck_rows, RESOURCE_TERMS)
    removal_count = _count_if(deck_rows, REMOVAL_TERMS)

    lock_count = _count_if(deck_rows, ["ロック", "呪文ロック", "攻撃制限"])
    damage_count = _count_if(deck_rows, ["打点", "フィニッシャー", "スピードアタッカー", "アンブロッカブル"])
    loop_count = _count_if(deck_rows, ["回収", "墓地利用", "踏み倒し", "リソース"])
    alt_count = _count_if(deck_rows, ["特殊勝利", "シールド追加", "山札操作"])

    warnings: list[str] = []
    if route_type == "lock_confirmed_win" and lock_count < 8:
        warnings.append(f"lock_confirmed_winに対してロック/行動制限要素が少なめです: {lock_count}枚相当")
    if route_type == "damage_overflow_win" and damage_count < 10:
        warnings.append(f"damage_overflow_winに対して打点要素が少なめです: {damage_count}枚相当")
    if route_type == "loop_converted_win" and loop_count < 10:
        warnings.append(f"loop_converted_winに対して循環/リソース要素が少なめです: {loop_count}枚相当")
    if route_type == "alternate_effect_win" and alt_count < 10:
        warnings.append(f"alternate_effect_winに対して特殊条件形成要素が少なめです: {alt_count}枚相当")

    if defense_count < 8:
        warnings.append("防御が薄く、速攻対面で検証前に崩れる可能性があります。")
    if resource_count < 10:
        warnings.append("初動/リソースが少なく、seedへ到達しにくい可能性があります。")
    if removal_count < 5:
        warnings.append("除去/盤面処理が少なめです。")
    if win_count < 8:
        warnings.append("勝ち切り手段が薄い可能性があります。")

    return {
        "defense_count": defense_count,
        "win_count": win_count,
        "resource_count": resource_count,
        "removal_count": removal_count,
        "lock_count": lock_count,
        "damage_count": damage_count,
        "loop_count": loop_count,
        "alternate_count": alt_count,
        "win_plan_warnings": warnings,
    }


def classify_validation(all_warnings: list[str], hard_errors: list[str]) -> str:
    if hard_errors:
        return "棄却候補"
    if len(all_warnings) >= 6:
        return "要修正"
    if len(all_warnings) >= 3:
        return "要修正"
    return "検証OK"


def validate_expanded_deck(expansion: dict[str, Any]) -> dict[str, Any]:
    deck_rows = expansion.get("deck_rows", [])
    route_type = str(expansion.get("route_type") or "")
    target_civs = str(expansion.get("target_civilizations") or "")

    hard_errors: list[str] = []
    total_cards = sum(int(row.get("count") or 0) for row in deck_rows)
    if total_cards != 40:
        hard_errors.append(f"デッキ枚数が40ではありません: {total_cards}")

    evolution = validate_evolution_conditions(deck_rows)
    civs = validate_civilization_base(deck_rows, target_civs)
    seed = validate_seed_connection(expansion)
    win_plan = validate_win_plan(deck_rows, route_type)

    all_warnings: list[str] = []
    for section in [evolution, civs, seed, win_plan]:
        for key, value in section.items():
            if key.endswith("_warnings") and isinstance(value, list):
                all_warnings.extend(value)

    verdict = classify_validation(all_warnings, hard_errors)

    return {
        "deck_name": expansion.get("deck_name", ""),
        "route_type": route_type,
        "route_seed_cards": expansion.get("route_seed_cards", ""),
        "target_civilizations": target_civs,
        "deck_size": total_cards,
        "validation_verdict": verdict,
        "hard_errors": hard_errors,
        "warning_count": len(all_warnings),
        "warnings": all_warnings,
        "evolution": evolution,
        "civilization": civs,
        "seed_connection": seed,
        "win_plan": win_plan,
    }


def validate_expanded_decks(expansions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [validate_expanded_deck(expansion) for expansion in expansions]


def validation_to_markdown(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# route_deck_validator 検証結果")
    lines.append("")
    if not results:
        lines.append("検証対象がありません。")
        return "\n".join(lines)

    headers = [
        "deck_name",
        "route_type",
        "validation_verdict",
        "warning_count",
        "deck_size",
        "route_seed_cards",
    ]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in results:
        lines.append("| " + " | ".join(str(row.get(h, "")).replace("\n", " ") for h in headers) + " |")
    lines.append("")

    for idx, row in enumerate(results, start=1):
        lines.append(f"## {idx}. {row.get('deck_name') or '-'}")
        lines.append("")
        lines.append(f"- 判定: {row.get('validation_verdict')}")
        lines.append(f"- route_type: {row.get('route_type')}")
        lines.append(f"- seed: {row.get('route_seed_cards')}")
        lines.append(f"- warning_count: {row.get('warning_count')}")
        if row.get("hard_errors"):
            lines.append("- hard_errors:")
            for err in row["hard_errors"]:
                lines.append(f"  - {err}")

        warnings = row.get("warnings") or []
        if warnings:
            lines.append("")
            lines.append("### 警告")
            for warning in warnings:
                lines.append(f"- {warning}")
        else:
            lines.append("")
            lines.append("### 警告")
            lines.append("- 大きな警告はありません。")

        seed = row.get("seed_connection") or {}
        win = row.get("win_plan") or {}
        evo = row.get("evolution") or {}
        civ = row.get("civilization") or {}

        lines.append("")
        lines.append("### 主要指標")
        lines.append(f"- defense_count: {win.get('defense_count', '-')}")
        lines.append(f"- resource_count: {win.get('resource_count', '-')}")
        lines.append(f"- win_count: {win.get('win_count', '-')}")
        lines.append(f"- removal_count: {win.get('removal_count', '-')}")
        lines.append(f"- seed_shared_tags: {seed.get('seed_shared_tags') or '-'}")
        lines.append(f"- evolution_like_count: {evo.get('evolution_like_count', '-')}")
        lines.append(f"- conditional_payoff_count: {evo.get('conditional_payoff_count', '-')}")
        lines.append(f"- multicolor_count: {civ.get('multicolor_count', '-')}")
        lines.append(f"- off_civilization_count: {civ.get('off_civilization_count', '-')}")
        lines.append("")

    return "\n".join(lines)


def validation_to_csv(results: list[dict[str, Any]]) -> str:
    columns = [
        "deck_name",
        "route_type",
        "route_seed_cards",
        "target_civilizations",
        "deck_size",
        "validation_verdict",
        "warning_count",
        "warnings",
    ]
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in results:
        flat = dict(row)
        flat["warnings"] = " / ".join(row.get("warnings") or [])
        writer.writerow(flat)
    return output.getvalue()


def write_validation_report(
    expanded_path: str | Path = "data/reports/expanded_route_decks/expanded_route_decks.json",
    output_dir: str | Path = "data/reports/expanded_route_decks",
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    expansions = load_expanded_decks(expanded_path)
    results = validate_expanded_decks(expansions)

    md_path = output_dir / "route_deck_validation.md"
    csv_path = output_dir / "route_deck_validation.csv"
    json_path = output_dir / "route_deck_validation.json"

    md_path.write_text(validation_to_markdown(results), encoding="utf-8")
    csv_path.write_text(validation_to_csv(results), encoding="utf-8-sig")
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"markdown": md_path, "csv": csv_path, "json": json_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate expanded Project MANA route decks.")
    parser.add_argument("--expanded", default="data/reports/expanded_route_decks/expanded_route_decks.json")
    parser.add_argument("--out", default="data/reports/expanded_route_decks")
    args = parser.parse_args()

    paths = write_validation_report(expanded_path=args.expanded, output_dir=args.out)
    print(f"markdown: {paths['markdown']}")
    print(f"csv: {paths['csv']}")
    print(f"json: {paths['json']}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/cards.csv")
DEFAULT_OUT_DIR = Path("data/reports/card_audit_v2")

# v2 policy:
# - cards.csv is treated as official Duel Masters Plays card list.
# - Do NOT call cards "unimplemented".
# - Do NOT exclude Field cards or main-deck spells that mention 超次元.
# - Separate clear exclusions from needs-review cards.
#
# Reason:
# Official card list includes cards that refer to extra zones, but the main-deck
# card itself can still be deck-buildable. v1 was too strict and incorrectly
# excluded many ホール spells and D2 Field cards.

CLEAR_EXCLUDED_CARD_TYPE_TERMS = [
    "ドラグハート",
    "禁断の鼓動",
    "デュエリスト",
]

NEEDS_REVIEW_TEXT_TERMS = [
    "下記に表示している対象カードを生成することで獲得します",
    "超次元",
    "覚醒",
    "龍解",
    "禁断解放",
]

MAIN_DECK_ALLOWED_TYPES = [
    "クリーチャー",
    "呪文",
    "タマシード",
    "フィールド",
    "城",
    "クロスギア",
]


def normalize_card_name(name: str) -> str:
    value = str(name or "")
    value = value.replace("\ufeff", "")
    value = re.sub(r"\s+", " ", value).strip()
    return value


def load_cards(path: str | Path = DEFAULT_INPUT) -> list[dict[str, Any]]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def has_clear_excluded_type(row: dict[str, Any]) -> bool:
    card_type = str(row.get("card_type", ""))
    return any(term in card_type for term in CLEAR_EXCLUDED_CARD_TYPE_TERMS)


def has_review_marker(row: dict[str, Any]) -> bool:
    blob = ";".join([
        str(row.get("card_type", "")),
        str(row.get("race", "")),
        str(row.get("text", "")),
        str(row.get("tags", "")),
    ])
    return any(term in blob for term in NEEDS_REVIEW_TEXT_TERMS)


def is_main_deck_type(row: dict[str, Any]) -> bool:
    card_type = str(row.get("card_type", ""))
    if not card_type:
        return False
    return any(term in card_type for term in MAIN_DECK_ALLOWED_TYPES)


def deck_eligibility_status(row: dict[str, Any]) -> str:
    if has_clear_excluded_type(row):
        return "excluded"
    if not is_main_deck_type(row):
        return "needs_review"
    if has_review_marker(row):
        return "needs_review"
    return "eligible"


def eligibility_reason(row: dict[str, Any]) -> str:
    status = deck_eligibility_status(row)
    if status == "eligible":
        return ""
    if has_clear_excluded_type(row):
        return f"明確な特殊カードタイプ: {row.get('card_type', '')}"
    if not is_main_deck_type(row):
        return f"カードタイプ確認が必要: {row.get('card_type', '')}"
    if has_review_marker(row):
        return "超次元/覚醒/龍解/生成付属などの記述あり。メイン投入可否は手動確認"
    return "要確認"


def dedupe_same_name_cards(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_name[normalize_card_name(row.get("name", ""))].append(row)

    representatives: list[dict[str, Any]] = []
    status_rank = {"eligible": 0, "needs_review": 1, "excluded": 2}

    for name, group in by_name.items():
        group = sorted(
            group,
            key=lambda r: (
                status_rank.get(deck_eligibility_status(r), 9),
                len(str(r.get("text", ""))),
                str(r.get("card_id", "")),
            ),
        )
        rep = dict(group[0])
        statuses = Counter(deck_eligibility_status(row) for row in group)

        rep["duplicate_count"] = str(len(group))
        rep["normalized_name"] = name
        rep["all_card_ids"] = ";".join(str(r.get("card_id", "")) for r in group)
        rep["deck_eligibility_status"] = deck_eligibility_status(rep)
        rep["eligibility_reason"] = eligibility_reason(rep)
        rep["duplicate_statuses"] = ";".join(f"{k}:{v}" for k, v in statuses.items())
        representatives.append(rep)

    representatives.sort(key=lambda r: normalize_card_name(r.get("name", "")))
    return representatives


def build_audit(rows: list[dict[str, Any]], deduped: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts = Counter(row.get("card_type", "") for row in rows)
    name_counts = Counter(normalize_card_name(row.get("name", "")) for row in rows)
    duplicate_names = {name: count for name, count in name_counts.items() if count > 1}
    status_counts = Counter(row.get("deck_eligibility_status", "") for row in deduped)
    raw_status_counts = Counter(deck_eligibility_status(row) for row in rows)

    return {
        "raw_count": len(rows),
        "unique_name_count": len(name_counts),
        "duplicate_name_count": len(duplicate_names),
        "deduped_count": len(deduped),
        "deduped_eligible_count": status_counts.get("eligible", 0),
        "deduped_needs_review_count": status_counts.get("needs_review", 0),
        "deduped_excluded_count": status_counts.get("excluded", 0),
        "raw_eligible_count": raw_status_counts.get("eligible", 0),
        "raw_needs_review_count": raw_status_counts.get("needs_review", 0),
        "raw_excluded_count": raw_status_counts.get("excluded", 0),
        "type_counts": dict(type_counts.most_common()),
        "top_duplicates": dict(sorted(duplicate_names.items(), key=lambda x: x[1], reverse=True)[:50]),
    }


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_audit_markdown(path: str | Path, audit: dict[str, Any], deduped: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Project MANA cards.csv 監査レポート v2")
    lines.append("")
    lines.append("## v2方針")
    lines.append("")
    lines.append("- cards.csv はデュエプレ公式カードリスト由来として扱う。")
    lines.append("- フィールドや超次元ホール呪文は自動除外しない。")
    lines.append("- 明確な特殊カードタイプだけ excluded にする。")
    lines.append("- 超次元/覚醒/龍解などの記述があるカードは needs_review にする。")
    lines.append("- 生成では eligible を基本に使い、研究時だけ needs_review を許可する。")
    lines.append("")
    lines.append("## サマリー")
    lines.append("")
    for key in [
        "raw_count",
        "unique_name_count",
        "duplicate_name_count",
        "deduped_count",
        "deduped_eligible_count",
        "deduped_needs_review_count",
        "deduped_excluded_count",
        "raw_eligible_count",
        "raw_needs_review_count",
        "raw_excluded_count",
    ]:
        lines.append(f"- {key}: {audit.get(key)}")
    lines.append("")
    lines.append("## カードタイプ件数")
    lines.append("")
    lines.append("| card_type | count |")
    lines.append("| --- | --- |")
    for card_type, count in audit.get("type_counts", {}).items():
        lines.append(f"| {card_type} | {count} |")
    lines.append("")
    lines.append("## 同名重複 上位50")
    lines.append("")
    lines.append("| name | count |")
    lines.append("| --- | --- |")
    for name, count in audit.get("top_duplicates", {}).items():
        lines.append(f"| {name} | {count} |")
    lines.append("")
    lines.append("## needs_review 候補 上位100")
    lines.append("")
    lines.append("| name | card_type | reason | duplicate_count |")
    lines.append("| --- | --- | --- | --- |")
    for row in [r for r in deduped if r.get("deck_eligibility_status") == "needs_review"][:100]:
        lines.append(
            f"| {row.get('name','')} | {row.get('card_type','')} | "
            f"{row.get('eligibility_reason','')} | {row.get('duplicate_count','')} |"
        )
    lines.append("")
    lines.append("## excluded 候補")
    lines.append("")
    lines.append("| name | card_type | reason | duplicate_count |")
    lines.append("| --- | --- | --- | --- |")
    for row in [r for r in deduped if r.get("deck_eligibility_status") == "excluded"][:100]:
        lines.append(
            f"| {row.get('name','')} | {row.get('card_type','')} | "
            f"{row.get('eligibility_reason','')} | {row.get('duplicate_count','')} |"
        )
    lines.append("")
    lines.append("## 次の判断")
    lines.append("")
    lines.append("- MANAの通常デッキ生成は cards_eligible_deduped.csv を使う。")
    lines.append("- needs_reviewは別ファイルに分け、研究モードまたは手動確認時のみ使う。")
    lines.append("- ND/AD判定にはカードセット情報が必要。現在CSVだけでは厳密判定不可。")
    path.write_text("\n".join(lines), encoding="utf-8")


def run(input_path: str | Path = DEFAULT_INPUT, out_dir: str | Path = DEFAULT_OUT_DIR) -> dict[str, Path]:
    rows = load_cards(input_path)
    deduped = dedupe_same_name_cards(rows)
    eligible_rows = [row for row in deduped if row.get("deck_eligibility_status") == "eligible"]
    review_rows = [row for row in deduped if row.get("deck_eligibility_status") == "needs_review"]
    excluded_rows = [row for row in deduped if row.get("deck_eligibility_status") == "excluded"]
    audit = build_audit(rows, deduped)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_path = out_dir / "cards_deduped_with_eligibility_v2.csv"
    eligible_path = out_dir / "cards_eligible_deduped.csv"
    review_path = out_dir / "cards_needs_review_deduped.csv"
    excluded_path = out_dir / "cards_excluded_deduped.csv"
    report_path = out_dir / "cards_audit_report_v2.md"

    write_csv(all_path, deduped)
    write_csv(eligible_path, eligible_rows)
    write_csv(review_path, review_rows)
    write_csv(excluded_path, excluded_rows)
    write_audit_markdown(report_path, audit, deduped)

    return {
        "all": all_path,
        "eligible": eligible_path,
        "needs_review": review_path,
        "excluded": excluded_path,
        "report": report_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Project MANA cards.csv v2.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    paths = run(args.input, args.out)
    for key, path in paths.items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()

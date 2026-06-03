from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_INPUT = Path("data/cards.csv")
DEFAULT_OUT_DIR = Path("data/reports/card_pool")
DEFAULT_SOURCE_SUSPECTS = Path("data/source_suspect_cards.csv")


# Important terminology:
# - cards.csv is treated as the official raw card record list.
# - Multiple records with the same name are NOT "bad duplicates".
#   They can represent alternate arts, packs, rarities, or versions.
# - Deck generation still needs a name-level pool because deck copy limits are
#   normally judged by card name, not by illustration/version record.
#
# Therefore this script creates:
# 1. official_card_records_with_pool_status.csv  : all raw records preserved
# 2. cards_generation_name_pool.csv              : one representative per card name
# 3. cards_generation_name_pool_strict.csv       : name pool minus source_suspect cards
# 4. cards_needs_review_name_pool.csv
# 5. cards_excluded_name_pool.csv
# 6. card_pool_report.md


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


def load_csv(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not fieldnames:
        path.write_text("", encoding="utf-8-sig")
        return

    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_source_suspects(path: str | Path = DEFAULT_SOURCE_SUSPECTS) -> dict[str, str]:
    rows = load_csv(path)
    suspects: dict[str, str] = {}
    for row in rows:
        name = normalize_card_name(row.get("card_name", ""))
        if name:
            suspects[name] = str(row.get("reason", "") or "公式dmps検索で未確認")
    return suspects


def has_clear_excluded_type(row: dict[str, Any]) -> bool:
    card_type = str(row.get("card_type", ""))
    return any(term in card_type for term in CLEAR_EXCLUDED_CARD_TYPE_TERMS)


def is_main_deck_type(row: dict[str, Any]) -> bool:
    card_type = str(row.get("card_type", ""))
    if not card_type:
        return False
    return any(term in card_type for term in MAIN_DECK_ALLOWED_TYPES)


def has_review_marker(row: dict[str, Any]) -> bool:
    blob = ";".join([
        str(row.get("card_type", "")),
        str(row.get("race", "")),
        str(row.get("text", "")),
        str(row.get("tags", "")),
    ])
    return any(term in blob for term in NEEDS_REVIEW_TEXT_TERMS)


def pool_status(row: dict[str, Any]) -> str:
    if has_clear_excluded_type(row):
        return "excluded"
    if not is_main_deck_type(row):
        return "needs_review"
    if has_review_marker(row):
        return "needs_review"
    return "eligible"


def pool_reason(row: dict[str, Any]) -> str:
    status = pool_status(row)
    if status == "eligible":
        return ""
    if has_clear_excluded_type(row):
        return f"明確な特殊カードタイプ: {row.get('card_type', '')}"
    if not is_main_deck_type(row):
        return f"カードタイプ確認が必要: {row.get('card_type', '')}"
    if has_review_marker(row):
        return "超次元/覚醒/龍解/生成付属などの記述あり。メイン投入可否は手動確認"
    return "要確認"


def annotate_raw_records(rows: list[dict[str, Any]], suspects: dict[str, str]) -> list[dict[str, Any]]:
    name_counts = Counter(normalize_card_name(row.get("name", "")) for row in rows)
    annotated: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        normalized_name = normalize_card_name(item.get("name", ""))
        status = pool_status(item)
        reason = pool_reason(item)

        if normalized_name in suspects:
            item["source_verification_status"] = "source_suspect"
            item["source_verification_reason"] = suspects[normalized_name]
        else:
            item["source_verification_status"] = ""
            item["source_verification_reason"] = ""

        item["normalized_name"] = normalized_name
        item["name_record_count"] = str(name_counts[normalized_name])
        item["generation_pool_status"] = status
        item["generation_pool_reason"] = reason
        annotated.append(item)

    return annotated


def choose_name_representative(group: list[dict[str, Any]]) -> dict[str, Any]:
    status_rank = {"eligible": 0, "needs_review": 1, "excluded": 2}

    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        # Prefer:
        # 1. eligible over review/excluded
        # 2. records that are not source_suspect
        # 3. richer text/tags, because MANA needs effect information
        # 4. stable card_id
        return (
            status_rank.get(row.get("generation_pool_status", ""), 9),
            row.get("source_verification_status") == "source_suspect",
            -len(str(row.get("text", ""))),
            -len(str(row.get("tags", ""))),
            str(row.get("card_id", "")),
        )

    return dict(sorted(group, key=key)[0])


def build_name_pool(raw_annotated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in raw_annotated:
        by_name[normalize_card_name(row.get("name", ""))].append(row)

    name_pool: list[dict[str, Any]] = []
    for normalized_name, group in by_name.items():
        rep = choose_name_representative(group)
        statuses = Counter(row.get("generation_pool_status", "") for row in group)
        source_statuses = Counter(row.get("source_verification_status", "") or "verified_unknown" for row in group)

        rep["name_record_count"] = str(len(group))
        rep["all_card_ids"] = ";".join(str(row.get("card_id", "")) for row in group)
        rep["name_record_statuses"] = ";".join(f"{k}:{v}" for k, v in sorted(statuses.items()))
        rep["name_record_source_statuses"] = ";".join(f"{k}:{v}" for k, v in sorted(source_statuses.items()))
        rep["name_pool_note"] = "同名別絵柄/別収録をカード名単位の生成用代表に集約"
        name_pool.append(rep)

    name_pool.sort(key=lambda r: normalize_card_name(r.get("name", "")))
    return name_pool


def build_report(
    raw_rows: list[dict[str, Any]],
    raw_annotated: list[dict[str, Any]],
    name_pool: list[dict[str, Any]],
    strict_pool: list[dict[str, Any]],
) -> str:
    type_counts = Counter(row.get("card_type", "") for row in raw_rows)
    raw_status_counts = Counter(row.get("generation_pool_status", "") for row in raw_annotated)
    name_status_counts = Counter(row.get("generation_pool_status", "") for row in name_pool)
    source_suspect_count_raw = sum(1 for row in raw_annotated if row.get("source_verification_status") == "source_suspect")
    source_suspect_count_names = sum(1 for row in name_pool if row.get("source_verification_status") == "source_suspect")
    name_counts = Counter(normalize_card_name(row.get("name", "")) for row in raw_rows)
    multi_record_names = {name: count for name, count in name_counts.items() if count > 1}

    lines: list[str] = []
    lines.append("# Project MANA card pool report")
    lines.append("")
    lines.append("## 方針")
    lines.append("")
    lines.append("- `cards.csv` は公式カードリスト由来の全カードレコードとして保持する。")
    lines.append("- 同名カードが複数あることは異常ではない。別絵柄、別パック、別バージョンの可能性がある。")
    lines.append("- MANAのデッキ生成では、同名4枚制限を扱うためカード名単位の代表プールを使う。")
    lines.append("- 公式dmps検索で出ない疑いのカードは `source_suspect_cards.csv` で除外する。")
    lines.append("")
    lines.append("## サマリー")
    lines.append("")
    lines.append(f"- official_raw_record_count: {len(raw_rows)}")
    lines.append(f"- unique_card_name_count: {len(name_counts)}")
    lines.append(f"- multi_record_name_count: {len(multi_record_names)}")
    lines.append(f"- generation_name_pool_count: {len(name_pool)}")
    lines.append(f"- strict_generation_name_pool_count: {len(strict_pool)}")
    lines.append(f"- raw_source_suspect_count: {source_suspect_count_raw}")
    lines.append(f"- name_source_suspect_count: {source_suspect_count_names}")
    lines.append("")
    lines.append("## raw generation_pool_status")
    lines.append("")
    for status, count in raw_status_counts.most_common():
        lines.append(f"- {status}: {count}")
    lines.append("")
    lines.append("## name_pool generation_pool_status")
    lines.append("")
    for status, count in name_status_counts.most_common():
        lines.append(f"- {status}: {count}")
    lines.append("")
    lines.append("## カードタイプ件数")
    lines.append("")
    lines.append("| card_type | count |")
    lines.append("| --- | --- |")
    for card_type, count in type_counts.most_common():
        lines.append(f"| {card_type} | {count} |")
    lines.append("")
    lines.append("## 同名レコード数 上位50")
    lines.append("")
    lines.append("| name | record_count |")
    lines.append("| --- | --- |")
    for name, count in sorted(multi_record_names.items(), key=lambda x: x[1], reverse=True)[:50]:
        lines.append(f"| {name} | {count} |")
    lines.append("")
    lines.append("## source_suspect name pool")
    lines.append("")
    suspects = [row for row in name_pool if row.get("source_verification_status") == "source_suspect"]
    if not suspects:
        lines.append("- なし")
    else:
        lines.append("| name | reason |")
        lines.append("| --- | --- |")
        for row in suspects[:100]:
            lines.append(f"| {row.get('name','')} | {row.get('source_verification_reason','')} |")
    lines.append("")
    lines.append("## 次の使い分け")
    lines.append("")
    lines.append("- 公式原本: `data/cards.csv`")
    lines.append("- 生成用カード名プール: `data/reports/card_pool/cards_generation_name_pool.csv`")
    lines.append("- 実戦寄りの厳格生成プール: `data/reports/card_pool/cards_generation_name_pool_strict.csv`")
    lines.append("- DB化するなら、まず strict を使う。")
    return "\n".join(lines)


def run(
    input_path: str | Path = DEFAULT_INPUT,
    out_dir: str | Path = DEFAULT_OUT_DIR,
    suspects_path: str | Path = DEFAULT_SOURCE_SUSPECTS,
) -> dict[str, Path]:
    input_path = Path(input_path)
    out_dir = Path(out_dir)
    suspects_path = Path(suspects_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_rows = load_csv(input_path)
    suspects = load_source_suspects(suspects_path)
    raw_annotated = annotate_raw_records(raw_rows, suspects)
    name_pool = build_name_pool(raw_annotated)

    generation_name_pool = [
        row for row in name_pool
        if row.get("generation_pool_status") == "eligible"
    ]
    generation_name_pool_strict = [
        row for row in generation_name_pool
        if row.get("source_verification_status") != "source_suspect"
    ]
    needs_review_pool = [
        row for row in name_pool
        if row.get("generation_pool_status") == "needs_review"
    ]
    excluded_pool = [
        row for row in name_pool
        if row.get("generation_pool_status") == "excluded"
    ]
    source_suspect_pool = [
        row for row in name_pool
        if row.get("source_verification_status") == "source_suspect"
    ]

    raw_path = out_dir / "official_card_records_with_pool_status.csv"
    pool_path = out_dir / "cards_generation_name_pool.csv"
    strict_path = out_dir / "cards_generation_name_pool_strict.csv"
    review_path = out_dir / "cards_needs_review_name_pool.csv"
    excluded_path = out_dir / "cards_excluded_name_pool.csv"
    source_suspect_path = out_dir / "cards_source_suspect_name_pool.csv"
    report_path = out_dir / "card_pool_report.md"

    # Keep raw field order plus appended fields.
    raw_fieldnames = list(raw_annotated[0].keys()) if raw_annotated else []
    pool_fieldnames = list(name_pool[0].keys()) if name_pool else raw_fieldnames

    write_csv(raw_path, raw_annotated, raw_fieldnames)
    write_csv(pool_path, generation_name_pool, pool_fieldnames)
    write_csv(strict_path, generation_name_pool_strict, pool_fieldnames)
    write_csv(review_path, needs_review_pool, pool_fieldnames)
    write_csv(excluded_path, excluded_pool, pool_fieldnames)
    write_csv(source_suspect_path, source_suspect_pool, pool_fieldnames)

    report_path.write_text(
        build_report(raw_rows, raw_annotated, name_pool, generation_name_pool_strict),
        encoding="utf-8",
    )

    return {
        "raw": raw_path,
        "generation_name_pool": pool_path,
        "strict_generation_name_pool": strict_path,
        "needs_review": review_path,
        "excluded": excluded_path,
        "source_suspect": source_suspect_path,
        "report": report_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Project MANA card pools with correct raw-record/name-pool terminology.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--suspects", default=str(DEFAULT_SOURCE_SUSPECTS))
    args = parser.parse_args()

    paths = run(args.input, args.out, args.suspects)
    for key, path in paths.items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()

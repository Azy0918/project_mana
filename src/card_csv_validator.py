from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_CSV_PATH
from src.tag_suggester import suggest_missing_tags


REQUIRED_COLUMNS = [
    "card_id",
    "name",
    "civilization",
    "cost",
    "card_type",
    "power",
    "race",
    "text",
    "tags",
]

VALID_CIVILIZATIONS = {
    "火",
    "水",
    "自然",
    "光",
    "闇",
    "無色",
}
CIVILIZATION_ALIASES = {
    "火文明": "火",
    "水文明": "水",
    "自然文明": "自然",
    "光文明": "光",
    "闇文明": "闇",
    "火/自然文明": "火/自然",
    "水/闇文明": "水/闇",
}


def _issue(level: str, row: int | None, field: str, message: str) -> dict[str, Any]:
    return {"level": level, "row": row, "field": field, "message": message}


def _split_civilizations(value: str) -> list[str]:
    normalized = value.replace("／", "/").replace(",", "/").replace("、", "/")
    return [part.strip() for part in normalized.split("/") if part.strip()]


def _check_civilization(value: str, row_number: int) -> list[dict[str, Any]]:
    issues = []
    if value in CIVILIZATION_ALIASES:
        issues.append(
            _issue(
                "warning",
                row_number,
                "civilization",
                f"`{value}` は `{CIVILIZATION_ALIASES[value]}` に寄せるのがおすすめです。",
            )
        )
        return issues

    if "文明" in value:
        issues.append(_issue("warning", row_number, "civilization", "`文明` は省いて表記してください。"))

    for civ in _split_civilizations(value):
        if civ not in VALID_CIVILIZATIONS:
            issues.append(_issue("error", row_number, "civilization", f"`{civ}` は未知の文明表記です。"))
    return issues


def validate_cards_csv(csv_path: Path = DEFAULT_CSV_PATH) -> dict[str, Any]:
    errors = []
    warnings = []
    rows = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        for column in REQUIRED_COLUMNS:
            if column not in fieldnames:
                errors.append(_issue("error", None, column, f"必須列 `{column}` がありません。"))

        if errors:
            return {"ok": False, "errors": errors, "warnings": warnings, "rows": rows}

        rows = list(reader)

    card_ids = [row["card_id"].strip() for row in rows]
    duplicated_ids = {card_id for card_id, count in Counter(card_ids).items() if card_id and count > 1}

    for index, row in enumerate(rows, start=2):
        card_id = row["card_id"].strip()
        name = row["name"].strip()
        cost = row["cost"].strip()
        tags = row["tags"].strip()
        text = row["text"].strip()
        civilization = row["civilization"].strip()

        if not card_id:
            errors.append(_issue("error", index, "card_id", "card_id が空欄です。"))
        elif card_id in duplicated_ids:
            errors.append(_issue("error", index, "card_id", f"card_id `{card_id}` が重複しています。"))

        if not name:
            errors.append(_issue("error", index, "name", "name が空欄です。"))

        if not cost:
            errors.append(_issue("error", index, "cost", "cost が空欄です。"))
        elif not cost.isdigit():
            errors.append(_issue("error", index, "cost", f"cost `{cost}` は数値ではありません。"))

        if not tags:
            warnings.append(_issue("warning", index, "tags", "tags が空欄です。"))

        if not civilization:
            errors.append(_issue("error", index, "civilization", "civilization が空欄です。"))
        else:
            for issue in _check_civilization(civilization, index):
                (errors if issue["level"] == "error" else warnings).append(issue)

        missing_tags = suggest_missing_tags(text, tags)
        if missing_tags:
            warnings.append(
                _issue(
                    "warning",
                    index,
                    "tags",
                    "能力テキストから追加候補があります: " + " / ".join(missing_tags),
                )
            )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "rows": rows,
    }

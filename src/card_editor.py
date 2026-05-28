from __future__ import annotations

import csv
import shutil
from datetime import datetime
from pathlib import Path

from src.card_csv_validator import VALID_CIVILIZATIONS as BASE_CIVILIZATIONS
from src.import_cards import DEFAULT_CSV_PATH


CARD_COLUMNS = [
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

VALID_CIVILIZATIONS = [
    "火",
    "水",
    "自然",
    "光",
    "闇",
    "無色",
    "火/水",
    "火/自然",
    "火/光",
    "火/闇",
    "水/自然",
    "水/光",
    "水/闇",
    "自然/光",
    "自然/闇",
    "光/闇",
]

VALID_CARD_TYPES = [
    "クリーチャー",
    "呪文",
    "進化クリーチャー",
    "クロスギア",
]


def backup_csv(csv_path: str | Path = DEFAULT_CSV_PATH) -> Path:
    path = Path(csv_path)
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.stem}_{timestamp}{path.suffix}"

    if path.exists():
        shutil.copy2(path, backup_path)

    return backup_path


def read_cards(csv_path: str | Path = DEFAULT_CSV_PATH) -> list[dict]:
    path = Path(csv_path)
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_cards(csv_path: str | Path, cards: list[dict]) -> None:
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CARD_COLUMNS)
        writer.writeheader()
        for card in cards:
            writer.writerow({column: card.get(column, "") for column in CARD_COLUMNS})


def validate_card(card: dict, existing_cards: list[dict] | None = None, original_card_id: str | None = None) -> list[str]:
    errors = []
    existing_cards = existing_cards or []

    card_id = str(card.get("card_id", "")).strip()
    name = str(card.get("name", "")).strip()
    civilization = str(card.get("civilization", "")).strip()
    cost = str(card.get("cost", "")).strip()
    card_type = str(card.get("card_type", "")).strip()
    tags = str(card.get("tags", "")).strip()

    if not card_id:
        errors.append("card_id は必須です。")
    if not name:
        errors.append("カード名は必須です。")
    if not cost.isdigit():
        errors.append("コストは数値で入力してください。")
    if civilization not in VALID_CIVILIZATIONS and civilization not in BASE_CIVILIZATIONS:
        errors.append(f"文明 `{civilization}` は選択肢にありません。")
    if card_type not in VALID_CARD_TYPES:
        errors.append(f"カードタイプ `{card_type}` は選択肢にありません。")
    if not tags:
        errors.append("タグは1つ以上入力してください。")

    for existing in existing_cards:
        existing_id = existing.get("card_id", "")
        if existing_id == card_id and existing_id != original_card_id:
            errors.append(f"card_id が重複しています: {card_id}")
            break

    return errors


def add_card(csv_path: str | Path, card: dict) -> Path:
    cards = read_cards(csv_path)
    errors = validate_card(card, cards)
    if errors:
        raise ValueError(" / ".join(errors))

    backup_path = backup_csv(csv_path)
    cards.append({column: card.get(column, "") for column in CARD_COLUMNS})
    write_cards(csv_path, cards)
    return backup_path


def update_card(csv_path: str | Path, card_id: str, updated_card: dict) -> Path:
    cards = read_cards(csv_path)
    errors = validate_card(updated_card, cards, original_card_id=card_id)
    if errors:
        raise ValueError(" / ".join(errors))

    found = False
    new_cards = []
    for card in cards:
        if card.get("card_id") == card_id:
            found = True
            new_cards.append({column: updated_card.get(column, "") for column in CARD_COLUMNS})
        else:
            new_cards.append(card)

    if not found:
        raise ValueError(f"更新対象の card_id が見つかりません: {card_id}")

    backup_path = backup_csv(csv_path)
    write_cards(csv_path, new_cards)
    return backup_path


def find_card_by_name(cards: list[dict], keyword: str) -> list[dict]:
    keyword = keyword.strip()
    if not keyword:
        return cards
    return [
        card
        for card in cards
        if keyword in card.get("name", "") or keyword in card.get("text", "")
    ]

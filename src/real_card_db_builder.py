from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH, import_cards
from src.tag_suggester import suggest_tags


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

COLUMN_ALIASES = {
    "card_id": ["card_id", "id", "カードID", "カード番号", "管理番号", "品番"],
    "name": ["name", "カード名", "名前"],
    "civilization": ["civilization", "文明", "文明名"],
    "cost": ["cost", "コスト", "マナコスト"],
    "card_type": ["card_type", "タイプ", "カードタイプ", "種類"],
    "power": ["power", "パワー"],
    "race": ["race", "種族"],
    "text": ["text", "能力", "テキスト", "カードテキスト", "効果"],
    "tags": ["tags", "タグ"],
}


def build_real_cards_csv(
    source_path: str | Path,
    output_csv_path: str | Path = DEFAULT_CSV_PATH,
    backup: bool = True,
) -> int:
    source_path = Path(source_path)
    output_csv_path = Path(output_csv_path)

    if not source_path.exists():
        raise FileNotFoundError(f"実カードCSVが見つかりません: {source_path}")

    source_df = pd.read_csv(source_path, dtype=str).fillna("")
    cards_df = normalize_real_cards(source_df)

    if backup and output_csv_path.exists():
        backup_dir = output_csv_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(output_csv_path, backup_dir / f"cards_before_real_import_{timestamp}.csv")

    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    cards_df.to_csv(output_csv_path, index=False, encoding="utf-8-sig")
    return len(cards_df)


def build_real_cards_db(
    source_path: str | Path,
    output_csv_path: str | Path = DEFAULT_CSV_PATH,
    db_path: str | Path = DEFAULT_DB_PATH,
    backup: bool = True,
) -> int:
    count = build_real_cards_csv(source_path, output_csv_path, backup=backup)
    import_cards(Path(output_csv_path), Path(db_path))
    return count


def normalize_real_cards(source_df: pd.DataFrame) -> pd.DataFrame:
    normalized = pd.DataFrame()
    for target_column in REQUIRED_COLUMNS:
        source_column = _find_source_column(source_df, COLUMN_ALIASES[target_column])
        if source_column is None:
            normalized[target_column] = ""
        else:
            normalized[target_column] = source_df[source_column].astype(str).fillna("").str.strip()

    if normalized["card_id"].eq("").any():
        normalized["card_id"] = [
            value if value else f"REAL-{index:05d}"
            for index, value in enumerate(normalized["card_id"], start=1)
        ]

    normalized["civilization"] = normalized["civilization"].apply(_normalize_civilization)
    normalized["cost"] = normalized["cost"].apply(_normalize_cost)
    normalized["card_type"] = normalized["card_type"].apply(_normalize_card_type)
    normalized["power"] = normalized["power"].apply(_normalize_power)
    normalized["tags"] = normalized.apply(_normalize_tags, axis=1)

    missing_required = [
        column
        for column in ["name", "civilization", "cost", "card_type", "text"]
        if normalized[column].eq("").any()
    ]
    if missing_required:
        raise ValueError(f"実カードDB化に必要な値が不足しています: {missing_required}")

    normalized = normalized.drop_duplicates(subset=["card_id"], keep="first")
    return normalized[REQUIRED_COLUMNS]


def _find_source_column(source_df: pd.DataFrame, aliases: list[str]) -> str | None:
    source_columns = {str(column).strip(): column for column in source_df.columns}
    for alias in aliases:
        if alias in source_columns:
            return source_columns[alias]
    return None


def _normalize_civilization(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    replacements = {
        "自然文明": "自然",
        "水文明": "水",
        "闇文明": "闇",
        "火文明": "火",
        "光文明": "光",
        "ゼロ文明": "無色",
        "ゼロ": "無色",
        "無文明": "無色",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    for separator in [",", "、", "・", " "]:
        text = text.replace(separator, "/")
    parts = [part for part in text.split("/") if part]
    return "/".join(dict.fromkeys(parts))


def _normalize_cost(value: str) -> str:
    text = str(value).strip()
    if not text:
        return ""
    if "∞" in text:
        return "99"
    digits = "".join(char for char in text if char.isdigit())
    return digits or text


def _normalize_power(value: str) -> str:
    text = str(value).strip()
    if not text or text == "-":
        return ""
    digits = "".join(char for char in text if char.isdigit())
    return digits


def _normalize_card_type(value: str) -> str:
    text = str(value).strip()
    if "クリーチャー" in text:
        return "クリーチャー"
    if "呪文" in text:
        return "呪文"
    if "クロスギア" in text:
        return "クロスギア"
    if "城" in text:
        return "城"
    if "フィールド" in text:
        return "フィールド"
    return text


def _normalize_tags(row: pd.Series) -> str:
    tags = _split_tags(str(row.get("tags", "")))
    text = str(row.get("text", ""))
    card_type = str(row.get("card_type", ""))
    civilization = str(row.get("civilization", ""))
    cost = _safe_int(str(row.get("cost", "")))
    tags.extend(suggest_tags(text))

    if "S・トリガー" in text or "S-トリガー" in text:
        tags.extend(["S・トリガー", "受け札"])
    if "進化" in card_type or "進化" in text:
        tags.append("進化")
    if "カードを" in text and ("引" in text or "ドロー" in text):
        tags.extend(["ドロー", "リソース"])
    if "マナゾーン" in text and ("置" in text or "増" in text):
        tags.extend(["マナ加速", "初動"])
    if "破壊" in text or "手札に戻" in text or "シールド" in text and "墓地" in text:
        tags.append("除去")
    if "スピードアタッカー" in text:
        tags.append("速攻")
    if "ブロッカー" in text:
        tags.append("受け札")
    if "墓地" in text:
        tags.append("墓地利用")
    if "/" in civilization:
        tags.append("多色")
    if cost is not None and cost <= 3:
        tags.append("低コスト")
    if cost is not None and cost >= 7:
        tags.append("フィニッシャー")

    return ";".join(dict.fromkeys(tag for tag in tags if tag))


def _split_tags(value: str) -> list[str]:
    tags: list[str] = []
    for tag in value.replace(",", ";").replace("、", ";").split(";"):
        tag = tag.strip()
        if tag:
            tags.append(tag)
    return tags


def _safe_int(value: str) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="実カードCSVから cards.csv と cards.db を作成します。")
    parser.add_argument("source", type=Path, help="実カードデータのCSV")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    count = build_real_cards_db(
        source_path=args.source,
        output_csv_path=args.csv,
        db_path=args.db,
        backup=not args.no_backup,
    )
    print(f"{count} real cards imported to {args.db}")


if __name__ == "__main__":
    main()

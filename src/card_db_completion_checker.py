from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


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


@dataclass
class CompletionCheckResult:
    total_cards: int
    unique_names: int
    duplicate_name_count: int
    civilization_counts: dict[str, int]
    card_type_counts: dict[str, int]
    cost_band_counts: dict[str, int]
    tag_counts: dict[str, int]
    key_category_counts: dict[str, int]
    warnings: list[str]
    score: int


def load_cards(path: str | Path) -> pd.DataFrame:
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"CSVが見つかりません: {path}")

    df = pd.read_csv(path, dtype=str).fillna("")

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"必須列が不足しています: {missing}")

    return df


def _split_tags(value: str) -> list[str]:
    if not value:
        return []

    tags = []
    for tag in str(value).replace(",", ";").replace("、", ";").split(";"):
        tag = tag.strip()
        if tag:
            tags.append(tag)

    return tags


def _count_tag(df: pd.DataFrame, keyword: str) -> int:
    return int(df["tags"].apply(lambda x: keyword in _split_tags(x)).sum())


def _count_tag_contains(df: pd.DataFrame, keyword: str) -> int:
    return int(df["tags"].apply(lambda x: keyword in str(x)).sum())


def _make_cost_band(cost: str) -> str:
    try:
        value = int(float(cost))
    except Exception:
        return "不明"

    if value <= 2:
        return "1〜2"
    if value <= 4:
        return "3〜4"
    if value <= 6:
        return "5〜6"
    if value <= 8:
        return "7〜8"
    return "9以上"


def check_completion(df: pd.DataFrame) -> CompletionCheckResult:
    work = df.copy().fillna("")

    total_cards = len(work)
    unique_names = work["name"].nunique()
    duplicate_name_count = total_cards - unique_names

    civilization_counts = (
        work["civilization"]
        .replace("", "不明")
        .value_counts()
        .to_dict()
    )

    card_type_counts = (
        work["card_type"]
        .replace("", "不明")
        .value_counts()
        .to_dict()
    )

    work["_cost_band"] = work["cost"].apply(_make_cost_band)
    cost_band_counts = work["_cost_band"].value_counts().to_dict()

    all_tags: list[str] = []
    for value in work["tags"]:
        all_tags.extend(_split_tags(value))

    tag_counts = pd.Series(all_tags).value_counts().to_dict() if all_tags else {}

    key_category_counts = {
        "初動": _count_tag(work, "初動"),
        "低コスト": _count_tag(work, "低コスト"),
        "マナ加速": _count_tag(work, "マナ加速"),
        "ドロー": _count_tag(work, "ドロー"),
        "リソース": _count_tag(work, "リソース"),
        "除去": _count_tag(work, "除去"),
        "軽量除去": _count_tag(work, "軽量除去"),
        "受け札": _count_tag(work, "受け札"),
        "S・トリガー": _count_tag(work, "S・トリガー"),
        "ハンデス": _count_tag(work, "ハンデス"),
        "墓地利用": _count_tag(work, "墓地利用"),
        "リアニメイト": _count_tag(work, "リアニメイト"),
        "進化": _count_tag(work, "進化"),
        "進化元": _count_tag(work, "進化元"),
        "フィニッシャー": _count_tag(work, "フィニッシャー"),
        "速攻": _count_tag(work, "速攻"),
        "コントロール": _count_tag(work, "コントロール"),
        "コンボ": _count_tag(work, "コンボ"),
        "多色": _count_tag(work, "多色"),
        "仮カード": _count_tag(work, "仮カード"),
    }

    warnings: list[str] = []

    thresholds = {
        "初動": 80,
        "受け札": 80,
        "S・トリガー": 60,
        "除去": 80,
        "ドロー": 50,
        "リソース": 70,
        "フィニッシャー": 80,
        "進化元": 40,
        "マナ加速": 50,
        "多色": 80,
    }

    for key, minimum in thresholds.items():
        actual = key_category_counts.get(key, 0)
        if actual < minimum:
            warnings.append(f"{key} が少なめです: {actual}枚 / 目安 {minimum}枚")

    base_civilizations = ["自然", "水", "闇", "火", "光"]
    for civ in base_civilizations:
        count = sum(
            v for k, v in civilization_counts.items()
            if civ in str(k).split("/")
        )
        if count < 100:
            warnings.append(f"{civ}文明のカードが少なめです: {count}枚 / 目安 100枚")

    if total_cards < 1000:
        warnings.append(f"総カード数が少なめです: {total_cards}枚 / 目安 1000枚以上")

    if duplicate_name_count > total_cards * 0.3:
        warnings.append(
            f"同名重複が多めです: {duplicate_name_count}件。重複整理を推奨します。"
        )

    score = 100

    for warning in warnings:
        score -= 5

    if total_cards >= 1000:
        score += 5

    if total_cards >= 1200:
        score += 5

    score = max(0, min(100, score))

    return CompletionCheckResult(
        total_cards=total_cards,
        unique_names=unique_names,
        duplicate_name_count=duplicate_name_count,
        civilization_counts=civilization_counts,
        card_type_counts=card_type_counts,
        cost_band_counts=cost_band_counts,
        tag_counts=tag_counts,
        key_category_counts=key_category_counts,
        warnings=warnings,
        score=score,
    )

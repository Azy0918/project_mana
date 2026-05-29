from __future__ import annotations

import pandas as pd


SORT_COLUMNS = {
    "作成日時": "created_at",
    "条件適合スコア": "condition_score",
    "評価スコア": "evaluation_score",
    "文明一致率": "civilization_match_rate",
    "初動": "starter_count",
    "受け札": "defense_count",
    "フィニッシャー": "finisher_count",
    "平均コスト": "average_cost",
}


def filter_and_sort_generated_decks(
    decks: pd.DataFrame,
    deck_type: str = "",
    sort_label: str = "条件適合スコア",
    ascending: bool = False,
) -> pd.DataFrame:
    if decks.empty:
        return decks

    result = decks.copy()
    if deck_type:
        result = result[result["deck_type"] == deck_type]

    sort_column = SORT_COLUMNS.get(sort_label, "condition_score")
    if sort_column in result.columns:
        result = result.sort_values(sort_column, ascending=ascending, na_position="last")

    return result


def available_deck_types(decks: pd.DataFrame) -> list[str]:
    if decks.empty or "deck_type" not in decks.columns:
        return []
    return sorted(deck_type for deck_type in decks["deck_type"].dropna().unique() if deck_type)


def generated_decks_to_csv(decks: pd.DataFrame) -> bytes:
    return decks.to_csv(index=False).encode("utf-8-sig")


def comparison_summary(decks: pd.DataFrame) -> list[dict[str, str]]:
    if decks.empty:
        return []

    rows = []
    metrics = [
        ("条件適合スコア", "condition_score"),
        ("評価スコア", "evaluation_score"),
        ("文明一致率", "civilization_match_rate"),
        ("初動", "starter_count"),
        ("受け札", "defense_count"),
        ("フィニッシャー", "finisher_count"),
    ]
    for label, column in metrics:
        if column not in decks.columns or decks[column].dropna().empty:
            continue
        best = decks.sort_values(column, ascending=False, na_position="last").iloc[0]
        rows.append(
            {
                "指標": label,
                "最高デッキ": str(best.get("deck_name", "")),
                "値": str(best.get(column, "")),
            }
        )
    return rows

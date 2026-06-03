from __future__ import annotations

from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_DB_PATH
from src.meta_deck_store import load_meta_decks


def split_values(value: str) -> list[str]:
    items: list[str] = []
    for item in str(value or "").replace(",", ";").replace("、", ";").split(";"):
        item = item.strip()
        if item and item not in items:
            items.append(item)
    return items


def analyze_deck_against_meta(
    deck: list[dict[str, Any]],
    db_path: Path = DEFAULT_DB_PATH,
    limit: int = 5,
    format: str | None = None,
) -> dict[str, Any]:
    meta_df = load_meta_decks(db_path, format=format)
    if meta_df.empty:
        return {
            "meta_deck_count": 0,
            "max_similarity": 0.0,
            "closest_meta_decks": [],
            "unknown_score": 100,
            "comments": ["環境デッキDBが未登録です。未知性判定には環境データ登録が必要です。"],
        }

    deck_names = {str(card.get("name", "")).strip() for card in deck if str(card.get("name", "")).strip()}
    deck_tags = set()
    deck_civs = set()
    for card in deck:
        deck_tags.update(split_values(str(card.get("tags", ""))))
        deck_civs.update(split_values(str(card.get("civilization", "")).replace("/", ";")))

    rows = []
    for _, meta in meta_df.iterrows():
        key_cards = set(split_values(meta.get("key_cards", "")))
        meta_civs = set(split_values(str(meta.get("civilizations", "")).replace("/", ";")))
        type_hit = 1 if str(meta.get("deck_type", "")) in deck_tags else 0

        card_overlap = len(deck_names.intersection(key_cards))
        card_score = card_overlap / max(1, len(key_cards)) * 70
        civ_score = len(deck_civs.intersection(meta_civs)) / max(1, len(meta_civs)) * 20 if meta_civs else 0
        type_score = type_hit * 10
        similarity = round(min(100.0, card_score + civ_score + type_score), 1)

        rows.append(
            {
                "環境デッキ": meta.get("deck_name", ""),
                "Tier": meta.get("tier", ""),
                "形式": meta.get("format", ""),
                "タイプ": meta.get("deck_type", ""),
                "類似度": similarity,
                "一致キーカード": card_overlap,
                "参考URL": meta.get("source_url", ""),
            }
        )

    rows = sorted(rows, key=lambda row: row["類似度"], reverse=True)[:limit]
    max_similarity = rows[0]["類似度"] if rows else 0.0
    unknown_score = max(0, round(100 - max_similarity))
    comments = []
    if max_similarity >= 60:
        comments.append("既存環境デッキとの類似度が高めです。未知性より改良型として扱うのが妥当です。")
    elif max_similarity >= 35:
        comments.append("環境デッキの要素を一部含む派生候補です。差別化ポイントを確認してください。")
    else:
        comments.append("登録済み環境デッキとは離れており、未知性の高い候補です。")

    return {
        "meta_deck_count": len(meta_df),
        "max_similarity": max_similarity,
        "closest_meta_decks": rows,
        "unknown_score": unknown_score,
        "comments": comments,
    }

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from src.card_recommender import recommend_cards_by_tags
from src.evaluate_deck import evaluate_deck, split_tags
from src.search_cards import DEFAULT_DB_PATH


OPPONENT_COUNTER_TAGS = {
    "速攻": ["受け札", "S・トリガー", "除去", "初動"],
    "中速": ["除去", "リソース", "フィニッシャー"],
    "コントロール": ["ドロー", "リソース", "フィニッシャー", "ハンデス"],
    "コンボ": ["メタカード", "ハンデス", "速攻"],
    "受け特化": ["リソース", "フィニッシャー", "ロック"],
}


def infer_needed_tags(performance_stats: dict[str, Any]) -> list[str]:
    needed_tags: list[str] = []

    for opponent, item in performance_stats.get("by_opponent", {}).items():
        if item.get("matches", 0) >= 2 and item.get("win_rate", 100) < 45:
            needed_tags.extend(OPPONENT_COUNTER_TAGS.get(opponent, ["除去", "リソース"]))

    by_play_order = performance_stats.get("by_play_order", {})
    first = by_play_order.get("先攻", {}).get("win_rate")
    second = by_play_order.get("後攻", {}).get("win_rate")
    if first is not None and second is not None and first - second >= 20:
        needed_tags.extend(["初動", "受け札", "S・トリガー"])

    return sorted(set(needed_tags))


def infer_weaknesses(performance_stats: dict[str, Any]) -> list[str]:
    weaknesses = []
    for opponent, item in performance_stats.get("by_opponent", {}).items():
        if item.get("matches", 0) >= 2 and item.get("win_rate", 100) < 45:
            weaknesses.append(f"{opponent}対面")

    by_play_order = performance_stats.get("by_play_order", {})
    first = by_play_order.get("先攻", {}).get("win_rate")
    second = by_play_order.get("後攻", {}).get("win_rate")
    if first is not None and second is not None and first - second >= 20:
        weaknesses.append("後攻時")

    return weaknesses


def extract_dead_card_names(performance_stats: dict[str, Any], limit: int = 8) -> list[str]:
    return [name for name, _count in performance_stats.get("dead_cards", [])[:limit]]


def _deck_civilizations(deck: list[dict[str, Any]]) -> list[str]:
    counter: Counter[str] = Counter()
    for card in deck:
        quantity = int(card.get("quantity", 1))
        for civ in str(card.get("civilization", "")).split("/"):
            civ = civ.strip()
            if civ:
                counter[civ] += quantity
    return [civ for civ, _count in counter.most_common(3)]


def _removal_priority(card: dict[str, Any], dead_names: set[str]) -> tuple[int, int, str]:
    tags = set(split_tags(card.get("tags")))
    cost = int(card.get("cost") or 0)
    priority = 0
    if card.get("name") in dead_names:
        priority += 100
    if cost >= 7:
        priority += 20
    if cost >= 5:
        priority += 8
    if tags.intersection({"フィニッシャー", "ロック"}):
        priority += 5
    if tags.intersection({"初動", "受け札", "S・トリガー"}):
        priority -= 15
    return (priority, cost, str(card.get("name", "")))


def suggest_cut_cards(
    deck: list[dict[str, Any]],
    performance_stats: dict[str, Any],
    max_cuts: int = 6,
) -> list[dict[str, Any]]:
    dead_names = set(extract_dead_card_names(performance_stats))
    candidates = sorted(deck, key=lambda card: _removal_priority(card, dead_names), reverse=True)

    cuts = []
    remaining = max_cuts
    for card in candidates:
        if remaining <= 0:
            break
        priority = _removal_priority(card, dead_names)[0]
        if priority <= 0 and cuts:
            break
        quantity = min(int(card.get("quantity", 1)), remaining, 2 if card.get("name") in dead_names else 1)
        if quantity <= 0:
            continue
        cuts.append(
            {
                "name": card.get("name", ""),
                "quantity": quantity,
                "reason": "腐ったカード記録" if card.get("name") in dead_names else "高コスト・役割過多の調整候補",
            }
        )
        remaining -= quantity

    return cuts


def _add_or_increment(deck: list[dict[str, Any]], card: dict[str, Any], quantity: int) -> None:
    for current in deck:
        if current.get("card_id") == card.get("card_id"):
            current["quantity"] = min(4, int(current.get("quantity", 1)) + quantity)
            return
    new_card = dict(card)
    new_card["quantity"] = min(4, quantity)
    deck.append(new_card)


def build_improved_deck(
    deck: list[dict[str, Any]],
    cut_cards: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    improved = [dict(card) for card in deck]

    for cut in cut_cards:
        remaining_cut = int(cut.get("quantity", 0))
        for card in improved:
            if remaining_cut <= 0:
                break
            if card.get("name") != cut.get("name"):
                continue
            removable = min(int(card.get("quantity", 1)), remaining_cut)
            card["quantity"] = int(card.get("quantity", 1)) - removable
            remaining_cut -= removable

    improved = [card for card in improved if int(card.get("quantity", 0)) > 0]
    add_slots = sum(int(card.get("quantity", 0)) for card in cut_cards)

    for card in recommendations:
        if add_slots <= 0:
            break
        current_count = sum(int(item.get("quantity", 1)) for item in improved if item.get("name") == card.get("name"))
        quantity = min(4 - current_count, add_slots, 2)
        if quantity <= 0:
            continue
        _add_or_increment(improved, card, quantity)
        add_slots -= quantity

    return sorted(improved, key=lambda card: (int(card.get("cost") or 0), str(card.get("name", ""))))


def create_improvement_plan(
    deck: list[dict[str, Any]],
    performance_stats: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 12,
) -> dict[str, Any]:
    needed_tags = infer_needed_tags(performance_stats)
    weaknesses = infer_weaknesses(performance_stats)
    dead_cards = extract_dead_card_names(performance_stats)
    civilizations = _deck_civilizations(deck)
    recommendations = recommend_cards_by_tags(
        db_path=db_path,
        tags=needed_tags,
        civilizations=civilizations,
        exclude_names=[card.get("name", "") for card in deck],
        limit=limit,
    )
    cut_cards = (
        suggest_cut_cards(deck, performance_stats, max_cuts=min(6, max(2, len(recommendations))))
        if recommendations
        else []
    )
    improved_deck = build_improved_deck(deck, cut_cards, recommendations)

    before = evaluate_deck(deck) if deck else None
    after = evaluate_deck(improved_deck) if improved_deck else None

    return {
        "weaknesses": weaknesses,
        "needed_tags": needed_tags,
        "dead_cards": dead_cards,
        "cut_cards": cut_cards,
        "recommendations": recommendations,
        "improved_deck": improved_deck,
        "before": before,
        "after": after,
        "notes": _build_notes(weaknesses, needed_tags, dead_cards, recommendations),
    }


def _build_notes(
    weaknesses: list[str],
    needed_tags: list[str],
    dead_cards: list[str],
    recommendations: list[dict[str, Any]],
) -> list[str]:
    notes = []
    if weaknesses:
        notes.append("弱点として " + "、".join(weaknesses) + " が検出されました。")
    if needed_tags:
        notes.append("優先して増やすタグは " + "、".join(needed_tags) + " です。")
    if dead_cards:
        notes.append("腐ったカード記録があるカードを削減候補にしています。")
    if needed_tags and not recommendations:
        notes.append("現在のカードDBでは推奨タグに合う差し替え候補が少ないため、CSV拡充の余地があります。")
    if not needed_tags:
        notes.append("明確な弱点タグはまだ出ていません。追加ログを集めると改良精度が上がります。")
    return notes

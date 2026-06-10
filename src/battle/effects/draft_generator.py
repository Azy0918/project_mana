from __future__ import annotations

import re
from typing import Any

# 能力テキストからEffectScriptの下書きを自動生成する。
# キーワード抽出ベースのため誤りを含みうる。人手レビュー(review_status)を経て
# "approved" になったものだけをカーネル実行に使う想定。

_COUNT_PATTERN = re.compile(r"(\d+)\s*(?:枚|体)")


def _extract_count(sentence: str) -> int:
    match = _COUNT_PATTERN.search(sentence)
    if match:
        return max(1, min(10, int(match.group(1))))
    return 1


def _sentence_actions(sentence: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    count = _extract_count(sentence)
    if re.search(r"カードを(\d+枚)?引", sentence) or "ドロー" in sentence:
        actions.append({"op": "draw", "count": count})
    if "マナゾーンに置" in sentence:
        actions.append({"op": "deck_top_to_mana", "count": count})
    if "破壊" in sentence and "相手" in sentence:
        action: dict[str, Any] = {"op": "destroy_creature", "count": count, "scope": "opponent"}
        power_match = re.search(r"パワー\s*(\d+)\s*以下", sentence)
        if power_match:
            action["max_power"] = int(power_match.group(1))
        actions.append(action)
    if "手札に戻" in sentence and "相手" in sentence:
        actions.append({"op": "bounce_creature", "count": count, "scope": "opponent"})
    if "タップ" in sentence and "相手" in sentence and "アンタップ" not in sentence:
        actions.append({"op": "tap_creature", "count": count, "scope": "opponent"})
    return actions


def _infer_trigger(card: dict[str, Any], text: str) -> str:
    card_type = str(card.get("card_type", ""))
    if "攻撃する時" in text or "攻撃時" in text:
        return "on_attack"
    if "破壊された時" in text:
        return "on_destroyed"
    if "呪文" in card_type:
        return "on_cast"
    return "on_play"


def generate_draft_effect_script(card: dict[str, Any]) -> dict[str, Any]:
    """カード1枚分のEffectScript下書きを生成する。

    抽出できた効果がない場合は abilities が空のスクリプトを返す(バニラ扱い)。
    """
    text = str(card.get("text", "") or "")
    abilities: list[dict[str, Any]] = []
    notes: list[str] = []

    sentences = [s for s in re.split(r"[。\n]", text) if s.strip()]
    main_actions: list[dict[str, Any]] = []
    for sentence in sentences:
        main_actions.extend(_sentence_actions(sentence))

    if main_actions:
        trigger = _infer_trigger(card, text)
        abilities.append({"trigger": trigger, "actions": main_actions})
        if "S・トリガー" in text:
            abilities.append({"trigger": "s_trigger", "actions": main_actions})

    covered_length = sum(len(s) for s in sentences if _sentence_actions(s))
    total_length = sum(len(s) for s in sentences)
    if total_length and covered_length < total_length:
        notes.append("テキストの一部を効果に変換できていません。レビューで補完してください。")
    if not text:
        notes.append("能力テキストなし(バニラ)")

    return {
        "card_id": str(card.get("card_id", "")),
        "name": str(card.get("name", "")),
        "abilities": abilities,
        "notes": notes,
    }

from __future__ import annotations

import re
from typing import Any

# 能力テキストからEffectScriptの下書きを自動生成する。
# キーワード抽出ベースのため誤りを含みうる。人手レビュー(review_status)を経て
# "approved" になったものだけをカーネル実行に使う想定。

_COUNT_PATTERN = re.compile(r"(\d+)\s*(?:枚|体)")

# 注釈テキスト(全角/半角括弧内のリマインダ)。変換対象から除外する
_REMINDER_PATTERN = re.compile(r"（[^）]*）|\([^)]*\)")

# 「すべて」系の全体効果に使う実用上の上限
ALL_COUNT = 99

# カーネルが直接処理するキーワードのみの行(EffectScript変換不要=変換済み扱い)
_KERNEL_KEYWORD_SENTENCE = re.compile(
    r"^(?:このクリーチャーは)?"
    r"(?:S・トリガー|(?:ドラゴン・)?[WT]・ブレイカー|ブロッカー|スピードアタッカー"
    r"|パワーアタッカー\s*\+?\s*\d+|マッハファイター"
    r"|ブロックされない|相手プレイヤーを攻撃できない|攻撃できない)"
    r"(?:を(?:持つ|得る))?$"
)

# ツインパクトの面区切りなど、効果ではない構造トークン行
_STRUCTURAL_SENTENCE = re.compile(r"^【[^】]*】$")


def _normalize_sentences(text: str) -> list[str]:
    """注釈括弧を除去し、行頭記号(■◇▶など)を落とした文のリストにする。"""
    stripped = _REMINDER_PATTERN.sub("", text)
    sentences = []
    for raw in re.split(r"[。\n]", stripped):
        sentence = raw.strip().lstrip("■◇▶●・ ").strip()
        if sentence:
            sentences.append(sentence)
    return sentences


def _is_kernel_keyword_sentence(sentence: str) -> bool:
    return bool(_KERNEL_KEYWORD_SENTENCE.match(sentence)) or bool(_STRUCTURAL_SENTENCE.match(sentence))


def _extract_count(sentence: str) -> int:
    if "すべて" in sentence or "全て" in sentence:
        return ALL_COUNT
    match = _COUNT_PATTERN.search(sentence)
    if match:
        return max(1, min(10, int(match.group(1))))
    return 1


def _sentence_actions(sentence: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    count = _extract_count(sentence)
    if re.search(r"カードを(\d+枚)?引", sentence) or "ドロー" in sentence:
        actions.append({"op": "draw", "count": count})
    if "山札" in sentence and "マナゾーンに置" in sentence and "相手" not in sentence:
        actions.append({"op": "deck_top_to_mana", "count": count})
    if "相手のクリーチャー" in sentence and "マナゾーンに置" in sentence:
        actions.append({"op": "send_creature_to_mana", "count": count, "scope": "opponent"})
    if "マナゾーンから" in sentence and "バトルゾーンに出" in sentence:
        action = {"op": "summon_from_mana", "count": count}
        cost_match = re.search(r"コスト\s*(\d+)\s*以下", sentence)
        if cost_match:
            action["max_cost"] = int(cost_match.group(1))
        actions.append(action)
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
    if re.search(r"シールド(ゾーン)?に(置|加え)", sentence) and "相手" not in sentence:
        actions.append({"op": "add_shield", "count": count})
    if "相手" in sentence and ("捨て" in sentence or "ハンデス" in sentence):
        actions.append({"op": "discard_opponent_hand", "count": count})
    if "山札の上" in sentence and "墓地に置" in sentence and "相手" not in sentence:
        actions.append({"op": "deck_top_to_grave", "count": count})
    if "墓地から" in sentence and re.search(r"手札に(戻|加え)", sentence):
        actions.append({"op": "grave_to_hand", "count": count})
    if "手札から" in sentence and re.search(r"(コストを)?支払わ(ずに|ない)", sentence) and "出す" in sentence:
        action = {"op": "summon_from_hand", "count": count}
        cost_match = re.search(r"コスト\s*(\d+)\s*以下", sentence)
        if cost_match:
            action["max_cost"] = int(cost_match.group(1))
        actions.append(action)
    if "アンタップ" in sentence and "相手" not in sentence:
        actions.append({"op": "untap_creature", "count": count, "scope": "self"})
    if "相手のシールド" in sentence and "墓地に置" in sentence:
        actions.append({"op": "burn_opponent_shield", "count": count})
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

    sentences = _normalize_sentences(text)
    main_actions: list[dict[str, Any]] = []
    for sentence in sentences:
        main_actions.extend(_sentence_actions(sentence))

    if main_actions:
        trigger = _infer_trigger(card, text)
        abilities.append({"trigger": trigger, "actions": main_actions})
        if "S・トリガー" in text:
            abilities.append({"trigger": "s_trigger", "actions": main_actions})

    # キーワードのみの文はカーネルが直接処理するため変換済みとみなす
    uncovered = [
        s for s in sentences if not _sentence_actions(s) and not _is_kernel_keyword_sentence(s)
    ]
    if uncovered:
        notes.append("テキストの一部を効果に変換できていません。レビューで補完してください。")
    if not text:
        notes.append("能力テキストなし(バニラ)")

    return {
        "card_id": str(card.get("card_id", "")),
        "name": str(card.get("name", "")),
        "abilities": abilities,
        "notes": notes,
    }

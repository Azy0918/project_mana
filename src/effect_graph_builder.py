from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from src.effect_semantics import infer_effect_semantics
from src.search_cards import DEFAULT_DB_PATH, search_cards


@dataclass
class EffectNode:
    card_id: str
    name: str
    civilization: str
    cost: int | None
    card_type: str
    tags: list[str]
    outputs: list[str]
    inputs: list[str]
    value_signals: list[str]
    semantics: dict[str, Any]


def build_effect_graph(
    db_path: str | Path = DEFAULT_DB_PATH,
    keyword: str = "",
    limit: int | None = None,
) -> list[EffectNode]:
    cards = search_cards(Path(db_path), keyword=keyword)
    if limit is not None:
        cards = cards[: int(limit)]
    return [infer_effect_node(card) for card in cards]


def infer_effect_node(card: dict[str, Any]) -> EffectNode:
    text = str(card.get("text", "") or "")
    tags = _split_tags(card.get("tags", ""))
    semantics = infer_effect_semantics(card)
    outputs = _infer_outputs(card, semantics, text)
    inputs = _infer_inputs(card, semantics, text)
    value_signals = _infer_value_signals(card, semantics, text)

    return EffectNode(
        card_id=str(card.get("card_id", "") or ""),
        name=str(card.get("name", "") or ""),
        civilization=str(card.get("civilization", "") or ""),
        cost=_safe_cost(card.get("cost")),
        card_type=str(card.get("card_type", "") or ""),
        tags=tags,
        outputs=outputs,
        inputs=inputs,
        value_signals=value_signals,
        semantics=semantics,
    )


def node_to_row(node: EffectNode) -> dict[str, Any]:
    return {
        "カードID": node.card_id,
        "カード名": node.name,
        "文明": node.civilization,
        "コスト": node.cost if node.cost is not None else "",
        "種類": node.card_type,
        "出力": " / ".join(node.outputs),
        "入力条件": " / ".join(node.inputs),
        "価値": " / ".join(node.value_signals),
    }


def _infer_outputs(
    card: dict[str, Any],
    semantics: dict[str, Any],
    text: str,
) -> list[str]:
    haystack = _haystack(text)
    delta = semantics.get("state_delta", {})
    outputs: list[str] = []

    if delta.get("hand", 0) > 0:
        outputs.append("hand_plus")
    if delta.get("mana", 0) > 0:
        outputs.append("mana_plus")
    if delta.get("graveyard", 0) > 0:
        outputs.append("graveyard_plus")
    if delta.get("board", 0) > 0:
        outputs.append("board_plus")
    if delta.get("shield", 0) > 0:
        outputs.append("shield_plus")
    if delta.get("board", 0) < 0 or any(keyword in haystack for keyword in ["破壊", "手札に戻す", "パワーを-", "パワーを0", "山札の下"]):
        outputs.append("board_control")
    if delta.get("hand", 0) < 0 or any(keyword in haystack for keyword in ["手札を捨て", "手札から選び"]):
        outputs.append("opponent_hand_minus")
    if "cost_bypass" in semantics.get("constraint_breaks", []):
        outputs.append("cost_bypass")
    if "zone_bypass" in semantics.get("constraint_breaks", []):
        outputs.append("external_zone_access")
    if "recursion_candidate" in semantics.get("special_mechanics", []):
        outputs.append("recursion")
    if "loop_candidate" in semantics.get("special_mechanics", []):
        outputs.append("repeatable_action")
    # 「アンタップ」単体はマナや防御のアンタップも拾うため、攻撃準備の文脈に限る
    if any(keyword in haystack for keyword in ["スピードアタッカー", "召喚酔いしない", "攻撃できる", "アンタップし、攻撃"]):
        outputs.append("attack_ready")
    if any(keyword in haystack for keyword in ["進化クリーチャーの下", "下に置", "下から"]):
        outputs.append("evolution_stack_manipulation")
    if any(keyword in haystack for keyword in ["呪文を唱え", "唱えてもよい", "呪文を使"]):
        outputs.append("spell_cast")
    if any(keyword in haystack for keyword in ["山札を見る", "山札から", "サーチ"]):
        outputs.append("search")
    # 「バトルゾーンに出た時」(単なるcip誘発)を展開能力と誤認しないよう、出す/出しの形のみ
    if any(keyword in haystack for keyword in ["バトルゾーンに出す", "バトルゾーンに出し", "踏み倒し"]):
        outputs.append("creature_deploy")

    return _unique(outputs)


def _infer_inputs(
    card: dict[str, Any],
    semantics: dict[str, Any],
    text: str,
) -> list[str]:
    haystack = _haystack(text)
    cost = _safe_cost(card.get("cost"))
    inputs: list[str] = []

    if cost is not None and cost >= 7:
        inputs.append("needs_mana")
    if any(keyword in haystack for keyword in ["手札から", "手札を", "手札が"]):
        inputs.append("needs_hand")
    if any(keyword in haystack for keyword in ["墓地", "墓地から", "墓地に"]):
        inputs.append("needs_graveyard")
    if any(keyword in haystack for keyword in ["マナゾーンから", "マナゾーンに", "マナ武装", "マナが"]):
        inputs.append("needs_mana_zone")
    if any(keyword in haystack for keyword in ["自分のクリーチャー", "クリーチャーが", "バトルゾーンに"]):
        inputs.append("needs_board")
    if any(keyword in haystack for keyword in ["シールド", "S・トリガー"]):
        inputs.append("needs_shield")
    if "進化" in haystack:
        inputs.append("needs_evolution_base")
    if any(keyword in haystack for keyword in ["侵略", "革命チェンジ", "攻撃する時", "攻撃した時"]):
        inputs.append("needs_attack")
    if any(keyword in haystack for keyword in ["呪文を唱えた時", "呪文を唱える", "呪文を"]):
        inputs.append("needs_spell_cast")
    if any(keyword in haystack for keyword in ["G・ゼロ", "Gゼロ"]):
        inputs.append("needs_free_cast_condition")
    if any(keyword in haystack for keyword in ["進化クリーチャーの下", "一番上", "下に置"]):
        inputs.append("needs_evolution_stack")
    if any(keyword in haystack for keyword in ["コストを支払わず", "踏み倒し"]):
        inputs.append("needs_payoff")
    if _contains_count_condition(haystack):
        inputs.append("needs_count_condition")

    return _unique(inputs)


def _infer_value_signals(
    card: dict[str, Any],
    semantics: dict[str, Any],
    text: str,
) -> list[str]:
    haystack = _haystack(text)
    signals: list[str] = []
    cost = _safe_cost(card.get("cost"))
    if cost is not None and cost >= 7:
        signals.append("payoff")
    if cost is not None and cost <= 3 and any(keyword in haystack for keyword in ["マナゾーン", "カードを引", "バトルゾーンに出", "手札に加える"]):
        signals.append("starter")
    if any(keyword in haystack for keyword in ["S・トリガー", "G・ストライク", "ブロッカー", "攻撃を中止"]):
        signals.append("defense")
    if any(keyword in haystack for keyword in ["コストを支払わず", "G・ゼロ", "唱えてもよい", "もう一度", "進化クリーチャーの下"]):
        signals.append("combo")
    if semantics.get("terminal_effects"):
        signals.append("terminal")
    if any(item in semantics.get("special_mechanics", []) for item in ["loop_candidate", "recursion_candidate"]):
        signals.append("engine")
    if any(keyword in haystack for keyword in ["ゲームに勝つ", "追加ターン", "すべて破壊"]):
        signals.append("high_impact")
    return _unique(signals)


def _safe_cost(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _split_tags(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    return [tag.strip() for tag in str(value).replace(",", ";").replace("、", ";").split(";") if tag.strip()]


def _haystack(text: str) -> str:
    return text


def _contains_count_condition(value: str) -> bool:
    return bool(re.search(r"\d+枚以上|\d+体以上|\d+つ以上", value))


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

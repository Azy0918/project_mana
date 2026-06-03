from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.effect_graph_builder import infer_effect_node
from src.search_cards import DEFAULT_DB_PATH, search_cards
from src.state_transition_model import infer_state_transition


def build_card_effect_feature(card: dict[str, Any]) -> dict[str, Any]:
    text = str(card.get("text", "") or "")
    node = infer_effect_node(card)
    transition = infer_state_transition(card)

    feature = {
        "card_id": str(card.get("card_id", "") or ""),
        "name": str(card.get("name", "") or ""),
        "trigger": _infer_trigger(text),
        "timing": _infer_timing(text, node.cost),
        "source_zone": _infer_source_zone(text),
        "target_zone": _infer_target_zone(text),
        "target_scope": _infer_target_scope(text),
        "condition_signals": _join(node.inputs),
        "cost_signals": _infer_cost_signals(text, node.cost),
        "output_signals": _join(node.outputs),
        "restriction_breaks": _join(node.semantics.get("constraint_breaks", [])),
        "repeatability": _infer_repeatability(text, node.outputs),
        "uncertainty": _infer_uncertainty(text),
        "vulnerability": _infer_vulnerability(text, node.inputs, node.outputs),
        "win_contribution": _infer_win_contribution(text, transition.payoff_score, node.value_signals),
        "matchup_roles": _infer_matchup_roles(text, transition.delta),
        "earliest_turn": _infer_earliest_turn(node.cost, node.outputs),
        "state_delta_json": json.dumps(transition.delta, ensure_ascii=False, sort_keys=True),
    }
    return feature


def build_card_effect_features(
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    cards = search_cards(Path(db_path))
    if limit is not None:
        cards = cards[: int(limit)]
    return [build_card_effect_feature(card) for card in cards]


def _infer_trigger(text: str) -> str:
    rules = [
        ("出た時", ["出た時", "バトルゾーンに出た時", "出した時"]),
        ("攻撃時", ["攻撃する時", "攻撃した時"]),
        ("破壊時", ["破壊された時", "破壊した時"]),
        ("召喚時", ["召喚した時"]),
        ("呪文詠唱時", ["呪文を唱えた時", "呪文を唱える時"]),
        ("ターン開始時", ["ターンのはじめ", "ターン開始時"]),
        ("ターン終了時", ["ターンの終わり", "ターン終了時"]),
        ("シールドトリガー", ["S・トリガー", "シールド・トリガー"]),
        ("常在", ["自分の", "相手の", "すべての"]),
    ]
    return _first_match(text, rules, default="使用時")


def _infer_timing(text: str, cost: int | None) -> str:
    if any(keyword in text for keyword in ["S・トリガー", "G・ストライク", "シールド・トリガー"]):
        return "defensive_reactive"
    if any(keyword in text for keyword in ["侵略", "革命チェンジ", "攻撃する時"]):
        return "attack_phase"
    if cost is not None and cost <= 3:
        return "early"
    if cost is not None and cost <= 6:
        return "mid"
    return "late"


def _infer_source_zone(text: str) -> str:
    zones = []
    for zone, keywords in {
        "deck": ["山札"],
        "hand": ["手札"],
        "graveyard": ["墓地"],
        "mana": ["マナゾーン"],
        "battle_zone": ["バトルゾーン"],
        "shield": ["シールド"],
        "extra_deck": ["超次元", "超GR", "ドラグハート"],
    }.items():
        if any(keyword in text for keyword in keywords):
            zones.append(zone)
    return _join(zones)


def _infer_target_zone(text: str) -> str:
    zones = []
    for zone, keywords in {
        "hand": ["手札に加", "手札に戻", "カードを引"],
        "mana": ["マナゾーンに置", "マナゾーンに加"],
        "graveyard": ["墓地に置", "墓地に送", "破壊"],
        "battle_zone": ["バトルゾーンに出", "召喚"],
        "shield": ["シールドに加", "シールドゾーンに置"],
        "deck": ["山札に戻", "山札の下"],
    }.items():
        if any(keyword in text for keyword in keywords):
            zones.append(zone)
    return _join(zones)


def _infer_target_scope(text: str) -> str:
    scopes = []
    for scope, keywords in {
        "self": ["自分"],
        "opponent": ["相手"],
        "creature": ["クリーチャー"],
        "spell": ["呪文"],
        "evolution": ["進化クリーチャー", "進化"],
        "cost_limited": ["コスト"],
        "civilization_limited": ["文明"],
        "race_limited": ["種族"],
        "power_limited": ["パワー"],
        "all": ["すべて"],
        "random": ["ランダム"],
    }.items():
        if any(keyword in text for keyword in keywords):
            scopes.append(scope)
    return _join(scopes)


def _infer_cost_signals(text: str, cost: int | None) -> str:
    signals = []
    if cost is not None:
        if cost <= 3:
            signals.append("low_cost")
        elif cost <= 6:
            signals.append("mid_cost")
        else:
            signals.append("high_cost")
    if any(keyword in text for keyword in ["手札を捨て", "墓地に置く", "破壊して"]):
        signals.append("additional_resource_cost")
    if any(keyword in text for keyword in ["コストを支払わず", "G・ゼロ", "ただちに"]):
        signals.append("cost_bypass")
    return _join(signals)


def _infer_repeatability(text: str, outputs: list[str]) -> str:
    if any(keyword in text for keyword in ["各ターン", "毎ターン", "ターンのはじめ"]):
        return "every_turn"
    if any(keyword in text for keyword in ["攻撃する時", "攻撃した時"]):
        return "on_attack"
    if any(keyword in text for keyword in ["唱えてもよい", "もう一度", "アンタップ", "再び"]) or "repeatable_action" in outputs:
        return "repeatable_candidate"
    if "recursion" in outputs:
        return "recursion_candidate"
    return "single_use_or_static"


def _infer_uncertainty(text: str) -> str:
    signals = []
    if any(keyword in text for keyword in ["山札の上", "上から"]):
        signals.append("topdeck_dependent")
    if "ランダム" in text:
        signals.append("random")
    if any(keyword in text for keyword in ["相手が選", "相手は"]):
        signals.append("opponent_dependent")
    if any(keyword in text for keyword in ["してもよい", "選んでもよい"]):
        signals.append("optional")
    return _join(signals) or "deterministic_or_text_unknown"


def _infer_vulnerability(text: str, inputs: list[str], outputs: list[str]) -> str:
    signals = []
    if any(input_signal in inputs for input_signal in ["needs_graveyard", "needs_evolution_stack"]):
        signals.append("graveyard_or_stack_hate")
    if "needs_spell_cast" in inputs or "spell_cast" in outputs:
        signals.append("spell_lock")
    if "needs_hand" in inputs:
        signals.append("hand_disruption")
    if "needs_board" in inputs or "needs_attack" in inputs:
        signals.append("creature_removal")
    if any(keyword in text for keyword in ["離れない", "破壊されない", "かわりに"]):
        signals.append("has_resilience")
    return _join(signals)


def _infer_win_contribution(text: str, payoff_score: int, value_signals: list[str]) -> str:
    signals = []
    if any(keyword in text for keyword in ["ゲームに勝つ", "追加ターン"]):
        signals.append("terminal_win")
    if any(keyword in text for keyword in ["スピードアタッカー", "攻撃できる", "ブロックされない"]):
        signals.append("damage_push")
    if any(keyword in text for keyword in ["すべて破壊", "すべて手札", "すべて墓地"]):
        signals.append("reset_or_sweep")
    if "payoff" in value_signals or payoff_score >= 35:
        signals.append("payoff")
    return _join(signals)


def _infer_matchup_roles(text: str, delta: dict[str, int]) -> str:
    roles = []
    if delta.get("defense", 0) > 0 or any(keyword in text for keyword in ["S・トリガー", "ブロッカー", "G・ストライク"]):
        roles.append("anti_aggro")
    if delta.get("disruption", 0) > 0 or any(keyword in text for keyword in ["手札を捨て", "唱えられない"]):
        roles.append("anti_combo")
    if delta.get("resource_loop", 0) > 0 or delta.get("hand", 0) > 0:
        roles.append("anti_control")
    if "墓地" in text and any(keyword in text for keyword in ["山札", "手札", "バトルゾーン"]):
        roles.append("graveyard_plan")
    return _join(roles)


def _infer_earliest_turn(cost: int | None, outputs: list[str]) -> int:
    if "cost_bypass" in outputs:
        return 3
    if cost is None:
        return 0
    return max(1, min(10, cost))


def _first_match(text: str, rules: list[tuple[str, list[str]]], default: str) -> str:
    for label, keywords in rules:
        if any(keyword in text for keyword in keywords):
            return label
    return default


def _join(values: list[str]) -> str:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return ";".join(result)

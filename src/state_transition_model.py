from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.effect_graph_builder import EffectNode, build_effect_graph, infer_effect_node
from src.search_cards import DEFAULT_DB_PATH, search_cards
from src.win_condition_model import assess_win_condition_reach


STATE_KEYS = [
    "hand",
    "mana",
    "graveyard",
    "board",
    "shield",
    "tempo",
    "damage_pressure",
    "resource_loop",
    "win_progress",
    "disruption",
    "defense",
    "action_window",
    "turn_count",
    "summon_permission",
    "cast_permission",
    "attack_permission",
    "zone_change_permission",
    "trigger_window",
    "replacement_shield",
    "replacement_destroy",
    "effect_permission",
    "lose_condition",
    "alternate_win_progress",
    "opponent_action_lock",
    "board_persistence",
    "deck_out_prevention",
    "opponent_deck_pressure",
]


@dataclass
class StateTransition:
    card_id: str
    card_name: str
    civilization: str
    cost: int | None
    card_type: str
    requires: dict[str, int]
    delta: dict[str, int]
    enables: list[str]
    payoff_score: int
    speed_score: int
    stability_score: int
    comments: list[str]


def infer_state_transition(card: dict[str, Any]) -> StateTransition:
    node = infer_effect_node(card)
    return transition_from_node(node)


def transition_from_node(node: EffectNode) -> StateTransition:
    requires = {key: 0 for key in STATE_KEYS}
    delta = {key: 0 for key in STATE_KEYS}

    base_delta = node.semantics.get("state_delta", {})
    for key in ["hand", "mana", "graveyard", "board", "shield"]:
        delta[key] = int(base_delta.get(key, 0))

    _apply_outputs(node, delta)
    _apply_special_effects(node, delta)
    _apply_inputs(node, requires)

    payoff_score = _payoff_score(node, delta)
    speed_score = _speed_score(node, delta)
    stability_score = _stability_score(node, delta)

    return StateTransition(
        card_id=node.card_id,
        card_name=node.name,
        civilization=node.civilization,
        cost=node.cost,
        card_type=node.card_type,
        requires=requires,
        delta=delta,
        enables=_enabled_states(delta),
        payoff_score=payoff_score,
        speed_score=speed_score,
        stability_score=stability_score,
        comments=_build_comments(node, requires, delta, payoff_score, speed_score, stability_score),
    )


def build_state_transitions(
    db_path: str | Path = DEFAULT_DB_PATH,
    keyword: str = "",
    limit: int | None = None,
) -> list[StateTransition]:
    cards = search_cards(Path(db_path), keyword=keyword)
    if limit is not None:
        cards = cards[: int(limit)]
    return [infer_state_transition(card) for card in cards]


def transition_to_row(transition: StateTransition) -> dict[str, Any]:
    return {
        "カード名": transition.card_name,
        "文明": transition.civilization,
        "コスト": transition.cost if transition.cost is not None else "",
        "種類": transition.card_type,
        "要求状態": _compact_vector(transition.requires),
        "状態変化": _compact_vector(transition.delta),
        "有効化": " / ".join(transition.enables),
        "速度": transition.speed_score,
        "安定": transition.stability_score,
        "リターン": transition.payoff_score,
        "コメント": " / ".join(transition.comments),
    }


def analyze_transition_chain(source: StateTransition, target: StateTransition) -> dict[str, Any]:
    satisfied = []
    missing = []
    for key, required in target.requires.items():
        if required <= 0:
            continue
        if source.delta.get(key, 0) >= required:
            satisfied.append(key)
        else:
            missing.append(key)

    combined_delta = {key: source.delta.get(key, 0) + target.delta.get(key, 0) for key in STATE_KEYS}
    chain_score = _chain_score(source, target, satisfied, missing, combined_delta)
    win_reach = assess_win_condition_reach(combined_delta)

    return {
        "起点カード": source.card_name,
        "接続先カード": target.card_name,
        "満たす状態": " / ".join(satisfied) if satisfied else "なし",
        "不足状態": " / ".join(missing) if missing else "なし",
        "合成状態変化": _compact_vector(combined_delta),
        "連鎖スコア": chain_score,
        "勝利条件候補": win_reach["best_condition"],
        "勝利到達スコア": win_reach["best_score"],
        "MANAコメント": _chain_comment(source, target, satisfied, missing, combined_delta),
    }


def analyze_state_chains_from_db(
    db_path: str | Path = DEFAULT_DB_PATH,
    keyword: str = "",
    limit: int = 300,
    max_results: int = 100,
) -> list[dict[str, Any]]:
    transitions = build_state_transitions(db_path=db_path, keyword=keyword, limit=limit)
    rows = []
    seen: set[tuple[str, str]] = set()
    for source in transitions:
        for target in transitions:
            if source.card_id == target.card_id or source.card_name == target.card_name:
                continue
            key = (source.card_name, target.card_name)
            if key in seen:
                continue
            seen.add(key)
            analysis = analyze_transition_chain(source, target)
            if analysis["連鎖スコア"] <= 0:
                continue
            rows.append(analysis)
    rows.sort(key=lambda row: row["連鎖スコア"], reverse=True)
    return rows[:max_results]


def _apply_outputs(node: EffectNode, delta: dict[str, int]) -> None:
    # resource_loop / win_progress は探索の識別力を担う希少状態。
    # 単なる墓地肥やしや踏み倒しには付与せず、真の再使用・終端効果に限定する。
    if "mana_plus" in node.outputs:
        delta["tempo"] += 1
    if "hand_plus" in node.outputs or "search" in node.outputs:
        delta["stability"] = delta.get("stability", 0) + 1
    if "board_plus" in node.outputs or "creature_deploy" in node.outputs:
        delta["damage_pressure"] += 1
    if "attack_ready" in node.outputs:
        delta["damage_pressure"] += 2
        delta["tempo"] += 1
    if "board_control" in node.outputs:
        delta["disruption"] += 2
        delta["defense"] += 1
    if "opponent_hand_minus" in node.outputs:
        delta["disruption"] += 2
    if "shield_plus" in node.outputs:
        delta["defense"] += 2
    if "cost_bypass" in node.outputs or "external_zone_access" in node.outputs:
        delta["tempo"] += 2
    if "repeatable_action" in node.outputs:
        delta["resource_loop"] += 2
    elif "recursion" in node.outputs:
        delta["resource_loop"] += 1
    if "evolution_stack_manipulation" in node.outputs:
        delta["resource_loop"] += 1


def _apply_special_effects(node: EffectNode, delta: dict[str, int]) -> None:
    # 生成済みコメント(「追加ターンなど終端効果の候補があります」等)をhaystackに
    # 混ぜるとキーワードが自己汚染するため、カード名と原文のみを対象にする。
    name = str(node.semantics.get("name", "") or "")
    mechanics = node.semantics.get("special_mechanics", [])
    terminals = node.semantics.get("terminal_effects", [])
    breaks = node.semantics.get("constraint_breaks", [])
    card_text = str(node.semantics.get("raw_text", "") or "")
    haystack = f"{name} {card_text}"

    if "extra_turn" in terminals:
        delta["turn_count"] += 1
        delta["action_window"] += 2
        delta["tempo"] += 3
        delta["win_progress"] += 2
    if "extra_win" in terminals:
        delta["alternate_win_progress"] += 3
        delta["win_progress"] += 3
    if "reset_effect" in terminals or any(keyword in haystack for keyword in ["すべて破壊", "すべて墓地", "すべて手札", "すべて山札"]):
        delta["disruption"] += 3
        delta["zone_change_permission"] += 1
    if "replacement_or_immunity" in breaks or any(keyword in haystack for keyword in ["かわりに", "置換", "離れない", "破壊されない"]):
        delta["replacement_destroy"] += 1
        delta["board_persistence"] += 2
    if "cost_bypass" in breaks:
        delta["summon_permission"] += 1
        delta["action_window"] += 1
    if "zone_bypass" in breaks or "external_zone_access" in mechanics:
        delta["zone_change_permission"] += 2

    # 行動制限系は主語が相手の場合のみロックとして扱う。
    # 「(このクリーチャーは)攻撃できない」のような自分側デメリットを
    # opponent_action_lock に数えると、ロック探索の識別力が消える。
    sentences = _text_sentences(card_text)
    if _opponent_restriction(sentences, ["呪文を唱えられない", "呪文を唱えることができない", "唱えられない"]):
        delta["cast_permission"] -= 2
        delta["opponent_action_lock"] += 2
        delta["disruption"] += 2
    if _opponent_restriction(sentences, ["召喚できない", "召喚することができない"]):
        delta["summon_permission"] -= 2
        delta["opponent_action_lock"] += 2
    if _opponent_restriction(sentences, ["攻撃できない", "攻撃することができない"]):
        delta["attack_permission"] -= 2
        delta["opponent_action_lock"] += 1
        delta["defense"] += 1
    if any(keyword in haystack for keyword in ["シールドを墓地に置", "シールド焼却", "ブレイクするかわり"]):
        delta["trigger_window"] -= 2
        delta["replacement_shield"] += 1
        delta["disruption"] += 1
    if _opponent_restriction(sentences, ["能力を無視", "能力を失", "効果を無視"]):
        delta["effect_permission"] -= 2
        delta["opponent_action_lock"] += 2
    # 自分の敗北を置換する効果(シャコガイル型)。相手が負ける置換は特殊勝利側で扱う。
    if any(
        "相手" not in sentence
        and any(keyword in sentence for keyword in ["山札がなくなるかわり", "山札の最後", "負けるかわり"])
        for sentence in sentences
    ):
        delta["lose_condition"] -= 1
        delta["deck_out_prevention"] += 1
    if "opponent_lose_win" in terminals:
        delta["alternate_win_progress"] += 3
        delta["win_progress"] += 2
    # 山札破壊圧は相手の山札に触れる効果に限る。「自分の山札の上から」は対象外。
    if any(
        ("相手" in sentence or "自身" in sentence) and "山札" in sentence
        for sentence in sentences
    ) or any(keyword in haystack for keyword in ["相手はカードを引", "相手にカードを引"]):
        delta["opponent_deck_pressure"] += 1


def _text_sentences(text: str) -> list[str]:
    import re

    return [sentence for sentence in re.split(r"[。\n■◇【】]", str(text or "")) if sentence]


def _opponent_restriction(sentences: list[str], patterns: list[str]) -> bool:
    """相手を主語とする行動制限か。「相手」を含む文でパターンが出た場合のみ真。"""
    return any(
        "相手" in sentence and any(pattern in sentence for pattern in patterns)
        for sentence in sentences
    )


def _apply_inputs(node: EffectNode, requires: dict[str, int]) -> None:
    mapping = {
        "needs_mana": "mana",
        "needs_hand": "hand",
        "needs_graveyard": "graveyard",
        "needs_mana_zone": "mana",
        "needs_board": "board",
        "needs_shield": "shield",
        "needs_evolution_base": "board",
        "needs_attack": "damage_pressure",
        "needs_spell_cast": "resource_loop",
        "needs_free_cast_condition": "tempo",
        "needs_evolution_stack": "resource_loop",
        "needs_payoff": "hand",
        "needs_count_condition": "resource_loop",
    }
    for input_signal in node.inputs:
        state_key = mapping.get(input_signal)
        if state_key:
            requires[state_key] += 1


def _payoff_score(node: EffectNode, delta: dict[str, int]) -> int:
    score = 0
    score += max(0, delta.get("win_progress", 0)) * 18
    score += max(0, delta.get("damage_pressure", 0)) * 10
    score += max(0, delta.get("resource_loop", 0)) * 8
    if "terminal" in node.value_signals:
        score += 30
    if "payoff" in node.value_signals:
        score += 12
    return min(100, score)


def _speed_score(node: EffectNode, delta: dict[str, int]) -> int:
    score = max(0, delta.get("tempo", 0)) * 18
    if node.cost is not None and node.cost <= 3:
        score += 18
    if "starter" in node.value_signals:
        score += 15
    return min(100, score)


def _stability_score(node: EffectNode, delta: dict[str, int]) -> int:
    score = max(0, delta.get("hand", 0)) * 10
    score += max(0, delta.get("stability", 0)) * 14
    score += max(0, delta.get("defense", 0)) * 8
    if "engine" in node.value_signals:
        score += 12
    return min(100, score)


def _enabled_states(delta: dict[str, int]) -> list[str]:
    return [key for key in STATE_KEYS if delta.get(key, 0) > 0]


def _compact_vector(vector: dict[str, int]) -> str:
    parts = [f"{key}:{value:+d}" for key, value in vector.items() if value]
    return " / ".join(parts) if parts else "なし"


def _build_comments(
    node: EffectNode,
    requires: dict[str, int],
    delta: dict[str, int],
    payoff_score: int,
    speed_score: int,
    stability_score: int,
) -> list[str]:
    comments = []
    if any(value > 0 for value in requires.values()):
        comments.append("要求状態あり")
    if speed_score >= 35:
        comments.append("速度変換候補")
    if stability_score >= 25:
        comments.append("安定化候補")
    if payoff_score >= 35:
        comments.append("勝ち筋変換候補")
    if delta.get("disruption", 0) > 0:
        comments.append("相手状態を崩す候補")
    if not comments:
        comments.append("小さな状態変換")
    return comments


def _chain_score(
    source: StateTransition,
    target: StateTransition,
    satisfied: list[str],
    missing: list[str],
    combined_delta: dict[str, int],
) -> int:
    if not satisfied:
        return 0
    score = len(satisfied) * 22
    score -= len(missing) * 8
    score += target.payoff_score // 3
    score += source.speed_score // 4
    score += max(0, combined_delta.get("win_progress", 0)) * 10
    score += max(0, combined_delta.get("damage_pressure", 0)) * 4
    score += max(0, assess_win_condition_reach(combined_delta)["best_score"]) // 4
    return max(0, min(100, score))


def _chain_comment(
    source: StateTransition,
    target: StateTransition,
    satisfied: list[str],
    missing: list[str],
    combined_delta: dict[str, int],
) -> str:
    if not satisfied:
        return "起点カードの状態変換は、接続先の要求状態をまだ満たしていません。"
    comment = (
        f"{source.card_name} が {', '.join(satisfied)} を作り、"
        f"{target.card_name} の要求状態に接続する候補です。"
    )
    if missing:
        comment += f" ただし不足状態があります: {', '.join(missing)}。"
    if combined_delta.get("win_progress", 0) > 0:
        comment += " 合成後に勝ち筋進行が増えます。"
    if combined_delta.get("disruption", 0) > 0:
        comment += " 相手状態への干渉も含みます。"
    win_reach = assess_win_condition_reach(combined_delta)
    if win_reach["best_score"] > 0:
        comment += f" {win_reach['comment']}"
    return comment

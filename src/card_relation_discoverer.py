from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.effect_graph_builder import EffectNode, build_effect_graph
from src.search_cards import DEFAULT_DB_PATH


@dataclass(frozen=True)
class RelationRule:
    source_output: str
    target_input: str
    relation_type: str
    reason: str
    base_score: int


RELATION_RULES = [
    RelationRule("mana_plus", "needs_mana", "加速接続", "Aがマナを増やし、Bの高コスト行動へ早く到達できます。", 62),
    RelationRule("mana_plus", "needs_mana_zone", "マナ条件接続", "Aがマナゾーンを増やし、Bのマナ条件を満たしやすくします。", 58),
    RelationRule("hand_plus", "needs_hand", "手札接続", "Aが手札を増やし、Bの手札要求や選択肢を支えます。", 54),
    RelationRule("graveyard_plus", "needs_graveyard", "墓地接続", "Aが墓地を作り、Bの墓地条件や墓地利用へ接続します。", 66),
    RelationRule("board_plus", "needs_board", "盤面接続", "Aが盤面を作り、Bのクリーチャー数・場参照条件を満たしやすくします。", 56),
    RelationRule("creature_deploy", "needs_evolution_base", "進化元接続", "Aがクリーチャーを用意し、Bの進化元になれる可能性があります。", 60),
    RelationRule("attack_ready", "needs_attack", "攻撃条件接続", "Aが攻撃可能な状態を作り、Bの侵略・革命チェンジ・攻撃時条件に接続します。", 70),
    RelationRule("spell_cast", "needs_spell_cast", "呪文連鎖", "Aの呪文詠唱が、Bの呪文回数・詠唱誘発条件に接続します。", 64),
    RelationRule("cost_bypass", "needs_payoff", "踏み倒し接続", "Aがコスト制約を外し、Bの高出力カードを通常より早く使える候補です。", 74),
    RelationRule("external_zone_access", "needs_payoff", "外部ゾーン接続", "Aが外部ゾーンに触り、Bの通常ゾーン外リソース利用へ接続します。", 68),
    RelationRule("recursion", "needs_hand", "再利用接続", "Aがカードを回収し、Bを繰り返し使う候補になります。", 60),
    RelationRule("repeatable_action", "needs_spell_cast", "ループ接続", "Aの再使用性が、Bの詠唱誘発や回数参照へ接続します。", 76),
    RelationRule("evolution_stack_manipulation", "needs_evolution_stack", "退化接続", "Aが進化元や重なりに触り、Bの退化・下敷き利用へ接続します。", 78),
    RelationRule("shield_plus", "needs_shield", "シールド接続", "Aがシールドを増やし、Bのシールド条件や耐久計画へ接続します。", 54),
    RelationRule("search", "needs_payoff", "探索接続", "Aが山札から探し、Bの勝ち筋や高出力札への到達率を上げます。", 58),
]


def discover_relations_from_db(
    db_path: str | Path = DEFAULT_DB_PATH,
    keyword: str = "",
    card_limit: int | None = None,
    max_results: int = 100,
    min_score: int = 60,
) -> list[dict[str, Any]]:
    nodes = build_effect_graph(db_path=db_path, keyword=keyword, limit=card_limit)
    return discover_card_relations(nodes, max_results=max_results, min_score=min_score)


def discover_card_relations(
    nodes: list[EffectNode],
    max_results: int = 100,
    min_score: int = 60,
    max_targets_per_rule: int = 40,
) -> list[dict[str, Any]]:
    targets_by_input: dict[str, list[EffectNode]] = {}
    for node in nodes:
        for input_signal in node.inputs:
            targets_by_input.setdefault(input_signal, []).append(node)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for source in nodes:
        for rule in RELATION_RULES:
            if rule.source_output not in source.outputs:
                continue
            for target in targets_by_input.get(rule.target_input, [])[:max_targets_per_rule]:
                if source.card_id == target.card_id:
                    continue
                key = (source.name, target.name, rule.relation_type)
                if key in seen:
                    continue
                seen.add(key)
                score = _score_relation(source, target, rule)
                if score < min_score:
                    continue
                rows.append(_relation_row(source, target, rule, score))

    rows.sort(key=lambda row: (row["関係スコア"], row["構造差分"]), reverse=True)
    return rows[:max_results]


def _score_relation(source: EffectNode, target: EffectNode, rule: RelationRule) -> int:
    score = rule.base_score

    if "starter" in source.value_signals:
        score += 8
    if "payoff" in target.value_signals:
        score += 10
    if "combo" in source.value_signals or "combo" in target.value_signals:
        score += 8
    if "terminal" in target.value_signals or "high_impact" in target.value_signals:
        score += 12
    if "engine" in source.value_signals or "engine" in target.value_signals:
        score += 6
    if source.cost is not None and source.cost <= 3:
        score += 6
    if target.cost is not None and target.cost >= 7:
        score += 5
    if source.civilization and target.civilization and source.civilization != target.civilization:
        score += 4
    score += _structure_distance(source, target)

    return max(0, min(100, score))


def _relation_row(
    source: EffectNode,
    target: EffectNode,
    rule: RelationRule,
    score: int,
) -> dict[str, Any]:
    structure_distance = _structure_distance(source, target)
    return {
        "関係スコア": score,
        "構造差分": structure_distance,
        "関係タイプ": rule.relation_type,
        "起点カード": source.name,
        "起点文明": source.civilization,
        "起点コスト": source.cost if source.cost is not None else "",
        "接続先カード": target.name,
        "接続先文明": target.civilization,
        "接続先コスト": target.cost if target.cost is not None else "",
        "接続理由": rule.reason,
        "起点出力": rule.source_output,
        "接続先条件": rule.target_input,
        "起点価値": " / ".join(source.value_signals),
        "接続先価値": " / ".join(target.value_signals),
        "MANA仮説": _build_hypothesis(source, target, rule, structure_distance),
    }


def _build_hypothesis(
    source: EffectNode,
    target: EffectNode,
    rule: RelationRule,
    structure_distance: int,
) -> str:
    if structure_distance >= 10:
        relation_note = "文明・コスト帯・価値役割に差分があり、既存の直感から外れた接続候補です。"
    else:
        relation_note = "構造差分は小さめですが、効果の入出力としては成立候補です。"
    return (
        f"{source.name} の {rule.source_output} が、{target.name} の {rule.target_input} を支える候補です。"
        f"{relation_note} デッキ化する場合は成立ターン、必要枚数、妨害耐性を検査してください。"
    )


def _structure_distance(source: EffectNode, target: EffectNode) -> int:
    distance = 0
    if source.civilization and target.civilization and source.civilization != target.civilization:
        distance += 4
    if source.card_type and target.card_type and source.card_type != target.card_type:
        distance += 3
    if source.cost is not None and target.cost is not None and abs(source.cost - target.cost) >= 4:
        distance += 4
    if set(source.value_signals).isdisjoint(set(target.value_signals)):
        distance += 4
    return min(15, distance)

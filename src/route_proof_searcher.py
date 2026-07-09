from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from src.card_effect_feature_store import load_card_effect_features
from src.card_reference_extractor import (
    change_link,
    deploy_link,
    extract_reference_profile,
    madness_link,
    ride_condition_link,
)
from src.combo_knowledge_base import load_known_combos
from src.effect_semantics import has_extra_turn_text, has_self_win_text
from src.import_cards import DEFAULT_DB_PATH
from src.search_cards import search_cards
from src.state_transition_model import STATE_KEYS, infer_state_transition
from src.win_condition_model import WIN_CONDITIONS


REPORT_DIR = Path("data/reports")
WIN_PROGRESS_STATES = [
    "win_progress",
    "alternate_win_progress",
    "damage_pressure",
    "opponent_deck_pressure",
    "opponent_action_lock",
    "extra_turn",
    "repeated_attack",
    "terminal_win",
]
LOOP_OUTPUT_TO_WIN_STATES = [
    "win_progress",
    "alternate_win_progress",
    "damage_pressure",
    "opponent_deck_pressure",
    "extra_turn",
    "repeated_attack",
    "terminal_win",
]


@dataclass(frozen=True)
class ProofWinCondition:
    key: str
    required_states: list[str]
    helper_states: list[str]
    risk_states: list[str]
    comment: str


@dataclass(frozen=True)
class ProofCardNode:
    card_id: str
    name: str
    cost: int
    civilization: str
    card_type: str
    tags: str
    input_states: tuple[str, ...]
    produced_states: dict[str, int]
    risk_states: tuple[str, ...]
    proof_terms: tuple[str, ...]
    text: str = ""
    power: int | None = None
    race: str = ""
    reference: Any = None


@dataclass(frozen=True)
class ProofRoute:
    route_type: str
    cards: tuple[ProofCardNode, ...]
    produced_states: dict[str, int]
    total_cost: int
    proof_score: int
    missing_states: tuple[str, ...]
    required_support_roles: tuple[str, ...]
    proof_comment: str
    reference_links: int = 0


def list_proof_win_conditions() -> dict[str, ProofWinCondition]:
    conditions = {
        condition.key: ProofWinCondition(
            key=condition.key,
            required_states=list(condition.required_states),
            helper_states=list(condition.supporting_states),
            risk_states=list(condition.risk_states),
            comment=condition.summary,
        )
        for condition in WIN_CONDITIONS
    }
    conditions["loop_converted_win"] = ProofWinCondition(
        key="loop_converted_win",
        required_states=["resource_loop", "loop_output_to_win"],
        helper_states=[
            "action_window",
            "turn_count",
            "win_progress",
            "alternate_win_progress",
            "damage_pressure",
        ],
        risk_states=["opponent_action_lock", "effect_permission"],
        comment="リソースループを実際の勝利出力へ変換する勝ち筋。",
    )
    return conditions


def search_route_proofs(
    db_path: str | Path = DEFAULT_DB_PATH,
    win_condition: str = "loop_converted_win",
    missing_state: str = "",
    required_missing_state: str | None = None,
    max_depth: int = 3,
    beam_width: int = 40,
    max_total_cost: int = 18,
    limit: int = 30,
    anchor_card_name: str = "",
) -> list[dict[str, Any]]:
    db_path = Path(db_path)
    if required_missing_state:
        missing_state = required_missing_state
    conditions = list_proof_win_conditions()
    if win_condition not in conditions:
        win_condition = "loop_converted_win"

    condition = _condition_for_missing_state(conditions[win_condition], missing_state)
    all_nodes = load_proof_card_nodes(db_path)
    nodes = _rank_node_pool(all_nodes, condition, missing_state)[:900]
    # 勝利状態を直接出さないエネイブラー(踏み倒し/展開/再利用)は
    # 上記ランキングでプール落ちしやすいため、別枠で追加する。
    pooled_ids = {node.card_id for node in nodes}
    enablers = sorted(
        (node for node in all_nodes if node.card_id not in pooled_ids and _enabler_score(node) > 0),
        key=_enabler_score,
        reverse=True,
    )
    nodes = nodes + enablers[:200]
    known_combo_sets = _load_known_combo_sets(db_path)

    start_states = _initial_states_for_missing(missing_state)
    beams: list[ProofRoute] = [
        ProofRoute(
            route_type=condition.key,
            cards=(),
            produced_states=start_states,
            total_cost=0,
            proof_score=0,
            missing_states=tuple(condition.required_states),
            required_support_roles=(),
            proof_comment="",
        )
    ]
    if anchor_card_name:
        # 起点カードを固定した探索。テーマ研究や既知コンボ再発見検証で、
        # 「このカードを含む勝ち筋ルート」だけを列挙したい場合に使う。
        anchor = next((node for node in all_nodes if node.name == anchor_card_name), None)
        if anchor is None:
            return []
        if all(node.card_id != anchor.card_id for node in nodes):
            nodes = [anchor] + nodes
        beams = [
            _score_route(
                condition=condition,
                cards=(anchor,),
                produced_states=_apply_virtual_states(_merge_states(start_states, anchor.produced_states)),
                total_cost=anchor.cost,
                max_total_cost=max_total_cost,
                missing_state=missing_state,
                known_combo_sets=known_combo_sets,
            )
        ]
    found: list[ProofRoute] = []

    for _depth in range(1, max(1, int(max_depth)) + 1):
        expanded: list[ProofRoute] = []
        seen: set[tuple[str, ...]] = set()
        for route in beams:
            used_ids = {card.card_id for card in route.cards}
            used_names = {card.name for card in route.cards}
            for node in nodes:
                if node.card_id in used_ids or node.name in used_names:
                    continue
                total_cost = route.total_cost + node.cost
                if total_cost > max_total_cost:
                    continue
                cards = route.cards + (node,)
                key = tuple(card.card_id for card in cards)
                if key in seen:
                    continue
                seen.add(key)
                produced_states = _apply_virtual_states(_merge_states(route.produced_states, node.produced_states))
                expanded.append(
                    _score_route(
                        condition=condition,
                        cards=cards,
                        produced_states=produced_states,
                        total_cost=total_cost,
                        max_total_cost=max_total_cost,
                        missing_state=missing_state,
                        known_combo_sets=known_combo_sets,
                    )
                )
        expanded.sort(key=lambda route: route.proof_score, reverse=True)
        beams = expanded[: max(1, int(beam_width))]
        # 参照リンク(踏み倒し/チェンジ/侵略/進化元)を持つルートは、
        # スコア上位に届かなくても別枠で残す。実コンボは汎用グッドスタッフに
        # スコアで劣ることが多く、リンクこそがコンボ性の証拠のため。
        beam_keys = {tuple(card.card_id for card in route.cards) for route in beams}
        linked = [
            route
            for route in expanded
            if route.reference_links > 0
            and tuple(card.card_id for card in route.cards) not in beam_keys
        ]
        beams = beams + linked[: max(8, int(beam_width) // 4)]
        found.extend(beams)

    unique: dict[tuple[str, tuple[str, ...]], ProofRoute] = {}
    for route in found:
        card_key = tuple(card.name for card in route.cards)
        key = (route.route_type, card_key)
        if key not in unique or route.proof_score > unique[key].proof_score:
            unique[key] = route

    ranked = sorted(unique.values(), key=lambda route: route.proof_score, reverse=True)
    # 出力にも参照リンク持ちルートの枠を確保する(上位limitに届かなくても報告する)
    linked_quota = max(4, int(limit) // 4)
    selected = list(ranked[:limit])
    selected_keys = {tuple(card.card_id for card in route.cards) for route in selected}
    for route in ranked[limit:]:
        if linked_quota <= 0:
            break
        if route.reference_links > 0 and tuple(card.card_id for card in route.cards) not in selected_keys:
            selected.append(route)
            linked_quota -= 1
    selected = selected[: int(limit) + max(4, int(limit) // 4)]
    return [_route_to_row(route, index + 1) for index, route in enumerate(selected)]


def load_proof_card_nodes(db_path: str | Path = DEFAULT_DB_PATH) -> list[ProofCardNode]:
    db_path = Path(db_path)
    try:
        feature_rows = _load_feature_rows(db_path)
        if feature_rows:
            return [
                node
                for node in (_node_from_feature_row(row) for row in feature_rows)
                if not _is_excluded_node(node)
            ]
    except Exception:
        pass

    nodes: list[ProofCardNode] = []
    try:
        for card in search_cards(db_path):
            transition = infer_state_transition(card)
            delta = {key: int(value) for key, value in transition.delta.items() if int(value) != 0}
            card_text = str(card.get("text", "") or "")
            node = ProofCardNode(
                card_id=str(card.get("card_id", "")),
                name=str(card.get("name", "")),
                cost=_safe_cost(card.get("cost"), default=6),
                civilization=str(card.get("civilization", "")),
                card_type=str(card.get("card_type", "")),
                tags=str(card.get("tags", "")),
                input_states=tuple(key for key, value in transition.requires.items() if value > 0),
                produced_states=_apply_virtual_states(_merge_states(delta, _virtual_states_from_blob(card))),
                risk_states=tuple(_risk_states_from_delta(delta)),
                proof_terms=tuple(_split_terms(str(card.get("tags", "")))),
                text=card_text,
                power=_safe_power(card.get("power")),
                race=str(card.get("race", "") or ""),
                reference=extract_reference_profile(card_text),
            )
            if not _is_excluded_node(node):
                nodes.append(node)
    except Exception:
        return []
    return nodes


def route_proof_candidates_to_csv(rows: list[dict[str, Any]]) -> str:
    output = StringIO()
    columns = [
        "deck_name",
        "candidate_origin",
        "route_type",
        "proof_score",
        "route_seed_cards",
        "state_chain",
        "produced_states",
        "missing_states",
        "required_support_roles",
        "proof_comment",
        "total_cost",
        "depth",
    ]
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def route_proof_candidates_to_markdown(
    rows: list[dict[str, Any]],
    limit: int = 30,
    win_condition: str = "",
    missing_state: str = "",
) -> str:
    route_types = sorted({str(row.get("route_type", "")) for row in rows if row.get("route_type")})
    best_score = max([int(row.get("proof_score", 0) or 0) for row in rows], default=0)
    summary_win = win_condition or (";".join(route_types) if route_types else "未指定")
    lines = [
        "# route_proof_searcher 候補",
        "",
        "勝利条件モデルから逆算した、勝利証明型ルート候補です。",
        "現段階では完全なルール証明ではなく、状態変換連鎖の仮説を機械的に並べるための土台です。",
        "",
        "## サマリー",
        "",
        f"- win_condition: {summary_win}",
        f"- candidate_count: {len(rows)}",
        f"- best_proof_score: {best_score}",
        f"- missing_state: {missing_state or 'なし'}",
        "",
    ]
    if not rows:
        lines.append("候補は見つかりませんでした。")
        return "\n".join(lines)

    lines.extend(
        [
            "## 候補一覧",
            "",
            "| deck_name | route_type | proof_score | total_cost | depth | route_seed_cards | missing_states | required_support_roles |",
            "| --- | --- | ---: | ---: | ---: | --- | --- | --- |",
        ]
    )
    for row in rows[:limit]:
        lines.append(
            "| {deck_name} | {route_type} | {proof_score} | {total_cost} | {depth} | {cards} | {missing} | {roles} |".format(
                deck_name=_escape_md(row.get("deck_name", "")),
                route_type=_escape_md(row.get("route_type", "")),
                proof_score=row.get("proof_score", 0),
                total_cost=row.get("total_cost", ""),
                depth=row.get("depth", ""),
                cards=_escape_md(row.get("route_seed_cards", "")),
                missing=_escape_md(row.get("missing_states", "")),
                roles=_escape_md(row.get("required_support_roles", "")),
            )
        )
    lines.append("")
    lines.append("## 上位候補詳細")
    lines.append("")

    for index, row in enumerate(rows[: min(limit, 10)], start=1):
        lines.append(f"## {index}. {row.get('deck_name', 'proof_based候補')}")
        lines.append("")
        lines.append(f"- candidate_origin: {row.get('candidate_origin', 'proof_based')}")
        lines.append(f"- route_type: {row.get('route_type', '')}")
        lines.append(f"- proof_score: {row.get('proof_score', 0)}")
        lines.append(f"- route_seed_cards: {row.get('route_seed_cards', '')}")
        lines.append(f"- total_cost: {row.get('total_cost', '')}")
        lines.append(f"- missing_states: {row.get('missing_states', '') or 'なし'}")
        lines.append(f"- required_support_roles: {row.get('required_support_roles', '') or 'なし'}")
        lines.append("")
        lines.append("### state_chain")
        lines.append(str(row.get("state_chain", "")))
        lines.append("")
        lines.append("### produced_states")
        lines.append(str(row.get("produced_states", "")))
        lines.append("")
        lines.append("### proof_comment")
        lines.append(str(row.get("proof_comment", "")))
        lines.append("")
    return "\n".join(lines)


def write_route_proof_outputs(
    rows: list[dict[str, Any]],
    output_dir: str | Path = REPORT_DIR,
    win_condition: str = "",
    missing_state: str = "",
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "md": output_dir / "route_proof_candidates.md",
        "csv": output_dir / "route_proof_candidates.csv",
        "json": output_dir / "route_proof_candidates.json",
    }
    paths["md"].write_text(
        route_proof_candidates_to_markdown(
            rows,
            win_condition=win_condition,
            missing_state=missing_state,
        ),
        encoding="utf-8",
    )
    paths["csv"].write_text(route_proof_candidates_to_csv(rows), encoding="utf-8-sig")
    paths["json"].write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return paths


def _load_feature_rows(db_path: Path) -> list[dict[str, Any]]:
    if not _table_exists(db_path, "card_effect_features"):
        return []
    try:
        df = load_card_effect_features(db_path)
    except Exception:
        return []
    if df.empty:
        return []

    card_meta = _load_card_meta(db_path)
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        data = row.to_dict()
        meta = card_meta.get(str(data.get("card_id", "")), {})
        data.update({key: value for key, value in meta.items() if value is not None})
        rows.append(data)
    return rows


def _load_card_meta(db_path: Path) -> dict[str, dict[str, Any]]:
    if not _table_exists(db_path, "cards"):
        return {}
    sql = """
        SELECT
            c.card_id,
            c.civilization,
            c.cost,
            c.card_type,
            c.power,
            c.race,
            c.text,
            COALESCE(GROUP_CONCAT(ct.tag, ';'), '') AS tags
        FROM cards c
        LEFT JOIN card_tags ct ON ct.card_id = c.card_id
        GROUP BY c.card_id
    """
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            return {str(row["card_id"]): dict(row) for row in conn.execute(sql).fetchall()}
    except Exception:
        return {}


def _node_from_feature_row(row: dict[str, Any]) -> ProofCardNode:
    delta = _parse_state_delta(row.get("state_delta_json"))
    delta = _apply_virtual_states(_merge_states(delta, _virtual_states_from_blob(row)))
    terms = _split_terms(row.get("tags", ""))
    terms.extend(_split_terms(row.get("output_signals", "")))
    terms.extend(_split_terms(row.get("win_contribution", "")))
    text = str(row.get("text", "") or "")
    return ProofCardNode(
        card_id=str(row.get("card_id", "")),
        name=str(row.get("name", "")),
        cost=_safe_cost(row.get("cost"), default=_safe_cost(row.get("earliest_turn"), default=6)),
        civilization=str(row.get("civilization", "")),
        card_type=str(row.get("card_type", "")),
        tags=str(row.get("tags", "")),
        input_states=tuple(_condition_signal_to_states(row.get("condition_signals", ""))),
        produced_states=delta,
        risk_states=tuple(_risk_states_from_delta(delta)),
        proof_terms=tuple(dict.fromkeys(terms)),
        text=text,
        power=_safe_power(row.get("power")),
        race=str(row.get("race", "") or ""),
        reference=extract_reference_profile(text),
    )


def _condition_for_missing_state(
    base: ProofWinCondition,
    missing_state: str,
) -> ProofWinCondition:
    if missing_state != "loop_output_to_win":
        return base
    return ProofWinCondition(
        key="loop_converted_win",
        required_states=["resource_loop", "loop_output_to_win"],
        helper_states=[
            "win_progress",
            "alternate_win_progress",
            "damage_pressure",
            "opponent_deck_pressure",
            "turn_count",
        ],
        risk_states=base.risk_states,
        comment="resource_loopを実際の勝利出力へ変換する補完探索。",
    )


def _initial_states_for_missing(missing_state: str) -> dict[str, int]:
    if missing_state == "loop_output_to_win":
        return {"resource_loop": 2}
    return {}


ENABLER_DEPLOY_TERMS = {"cost_bypass", "creature_deploy"}
ENABLER_POOL_TERMS = {"cost_bypass", "creature_deploy", "recursion", "spell_cast"}


def _enabler_score(node: ProofCardNode) -> int:
    terms = set(node.proof_terms)
    score = 0
    if "cost_bypass" in terms:
        score += 20
    if "creature_deploy" in terms:
        score += 14
    if "recursion" in terms:
        score += 10
    if "spell_cast" in terms:
        score += 6
    if score and node.cost <= 5:
        score += 8
    return score


def _rank_node_pool(
    nodes: list[ProofCardNode],
    condition: ProofWinCondition,
    missing_state: str,
) -> list[ProofCardNode]:
    def node_score(node: ProofCardNode) -> int:
        score = 0
        for state in condition.required_states:
            score += max(0, node.produced_states.get(state, 0)) * 35
        for state in condition.helper_states:
            score += max(0, node.produced_states.get(state, 0)) * 12
        for state in WIN_PROGRESS_STATES:
            score += max(0, node.produced_states.get(state, 0)) * 10
        if missing_state == "loop_output_to_win":
            if node.produced_states.get("loop_output_to_win", 0) > 0:
                score += 40
            if node.produced_states.get("resource_loop", 0) > 0:
                score += 3
        if node.cost <= 3:
            score += 12
        elif node.cost >= 8:
            score -= 8
        return score

    ranked = [node for node in nodes if node_score(node) > 0]
    ranked.sort(key=node_score, reverse=True)
    return ranked or nodes


def _score_route(
    condition: ProofWinCondition,
    cards: tuple[ProofCardNode, ...],
    produced_states: dict[str, int],
    total_cost: int,
    max_total_cost: int,
    missing_state: str,
    known_combo_sets: list[set[str]],
) -> ProofRoute:
    missing_states = [
        state for state in condition.required_states if produced_states.get(state, 0) <= 0
    ]
    # permission系の負値は「相手の行動を封じる」効果(例: デル・フィンのcast_permission:-2)。
    # ロック勝ちルートでは正の自己許可と同様に加点対象とする。
    helper_hits = [
        state
        for state in condition.helper_states
        if produced_states.get(state, 0) > 0
        or (
            condition.key == "lock_confirmed_win"
            and state.endswith("_permission")
            and produced_states.get(state, 0) < 0
        )
    ]
    required_coverage = len(condition.required_states) - len(missing_states)
    required_strength = sum(
        min(2, max(0, produced_states.get(state, 0)))
        for state in condition.required_states
    )
    win_state_hits = sum(1 for state in WIN_PROGRESS_STATES if produced_states.get(state, 0) > 0)

    score = 0
    score += required_coverage * 22
    score += required_strength * 6
    score += min(16, len(helper_hits) * 4)
    score += min(16, win_state_hits * 4)
    score += max(0, max_total_cost - total_cost)
    score += max(0, 8 - len(cards) * 2)

    if condition.key == "loop_converted_win" and produced_states.get("resource_loop", 0) > 0:
        if produced_states.get("loop_output_to_win", 0) > 0:
            score += 10
        else:
            score -= 32

    risk_score = _route_risk_score(condition, produced_states, cards)
    score -= risk_score

    if missing_state == "loop_output_to_win":
        has_win_output = produced_states.get("loop_output_to_win", 0) > 0
        if has_win_output:
            score += 12
        else:
            if "loop_output_to_win" not in missing_states:
                missing_states.append("loop_output_to_win")
            score -= 24

    if total_cost >= 18:
        score -= 14
    elif total_cost >= 13:
        score -= 8
    reference_links = _reference_bonus(cards)
    score += reference_links
    if _is_known_combo_exact(cards, known_combo_sets):
        score -= 6
    if _route_type_mismatch(condition.key, produced_states):
        score -= 12

    required_support_roles = _required_support_roles(missing_states, total_cost, risk_score)
    proof_score = max(0, min(100, int(score)))
    if total_cost >= 13:
        proof_score = min(proof_score, 84)
    elif total_cost >= 9:
        proof_score = min(proof_score, 90)
    if len(cards) == 1 and total_cost >= 7:
        proof_score = min(proof_score, 88)
    return ProofRoute(
        route_type=condition.key,
        cards=cards,
        produced_states=produced_states,
        total_cost=total_cost,
        proof_score=proof_score,
        missing_states=tuple(dict.fromkeys(missing_states)),
        required_support_roles=tuple(required_support_roles),
        proof_comment=_proof_comment(condition, cards, produced_states, missing_states, required_support_roles, risk_score),
        reference_links=reference_links,
    )


def _reference_bonus(cards: tuple[ProofCardNode, ...]) -> int:
    """カード間のメカニズム参照(踏み倒し先条件、革命チェンジ元条件、マッドネス)を加点する。

    状態の単純加算では「AがBを実際に出せる」関係を評価できないため、
    テキストから抽出した参照条件の充足をペア単位で確認する。
    """
    if len(cards) < 2:
        return 0
    bonus = 0
    for enabler in cards:
        if enabler.reference is None:
            continue
        for target in cards:
            if target is enabler:
                continue
            if deploy_link(
                enabler.reference,
                target_civ=target.civilization,
                target_cost=target.cost,
                target_power=target.power,
                target_type=target.card_type,
                target_name=target.name,
                target_text=target.text,
                target_race=target.race,
                target_is_evolution="進化" in target.card_type,
            ):
                bonus += 14
            if target.reference is not None and change_link(
                target.reference,
                source_civ=enabler.civilization,
                source_cost=enabler.cost,
                source_type=enabler.card_type,
                source_name=enabler.name,
                source_text=enabler.text,
                source_race=enabler.race,
            ):
                bonus += 12
            if target.reference is not None and ride_condition_link(
                target.reference.invasion_condition,
                source_civ=enabler.civilization,
                source_cost=enabler.cost,
                source_type=enabler.card_type,
                source_name=enabler.name,
                source_text=enabler.text,
                source_race=enabler.race,
            ):
                bonus += 12
            if target.reference is not None:
                evolution = target.reference.evolution_condition
                # 「進化：クリーチャー」のような無条件進化は識別力がないため対象外
                if evolution is not None and (evolution.civs or evolution.race_terms or evolution.needs_dragon):
                    if ride_condition_link(
                        evolution,
                        source_civ=enabler.civilization,
                        source_cost=enabler.cost,
                        source_type=enabler.card_type,
                        source_name=enabler.name,
                        source_text=enabler.text,
                        source_race=enabler.race,
                    ):
                        bonus += 9 if (evolution.race_terms or evolution.needs_dragon) else 5
            if target.reference is not None and madness_link(target.reference, enabler.reference):
                bonus += 10
    return min(26, bonus)


def _safe_power(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _route_risk_score(
    condition: ProofWinCondition,
    produced_states: dict[str, int],
    cards: tuple[ProofCardNode, ...],
) -> int:
    score = 0
    for state in condition.risk_states:
        value = produced_states.get(state, 0)
        if value < 0:
            score += abs(value) * 3
        elif value > 0 and state in {"trigger_window", "replacement_shield", "effect_permission"}:
            score += value * 4
    high_cost_cards = sum(1 for card in cards if card.cost >= 8)
    score += max(0, high_cost_cards - 1) * 5
    return score


def _required_support_roles(missing_states: list[str], total_cost: int, risk_score: int) -> list[str]:
    roles = []
    for state in missing_states:
        if state == "loop_output_to_win":
            roles.append("ループ出力の明確化")
        elif state == "resource_loop":
            roles.append("再利用/循環エンジン")
        elif state in {"damage_pressure", "attack_permission", "board"}:
            roles.append("打点形成")
        elif state == "alternate_win_progress":
            roles.append("特殊勝利条件の進行")
        elif state == "opponent_deck_pressure":
            roles.append("相手山札圧力")
        elif state == "opponent_action_lock":
            roles.append("相手行動ロック")
        else:
            roles.append(f"{state}補完")
    if total_cost >= 13:
        roles.append("マナ加速/コスト軽減")
    if risk_score >= 10:
        roles.append("防御/妨害耐性")
    return list(dict.fromkeys(roles))


def _proof_comment(
    condition: ProofWinCondition,
    cards: tuple[ProofCardNode, ...],
    produced_states: dict[str, int],
    missing_states: list[str],
    required_support_roles: list[str],
    risk_score: int,
) -> str:
    card_names = " / ".join(card.name for card in cards)
    active = _compact_states(produced_states)
    if missing_states:
        return (
            f"{condition.key}への状態変換候補です。seed={card_names}。"
            f"作れている状態は {active}。不足は {', '.join(missing_states)}。"
            f"次は {', '.join(required_support_roles) if required_support_roles else '補助役割'} を探します。"
        )
    if risk_score > 0:
        return (
            f"{condition.key}の必須状態を満たす候補です。seed={card_names}。"
            f"ただしリスク補正が {risk_score} あるため、防御要求と成立ターンを確認します。"
        )
    return f"{condition.key}の必須状態を満たす勝利証明候補です。seed={card_names}。作れている状態は {active}。"


def _route_to_row(route: ProofRoute, rank: int) -> dict[str, Any]:
    card_names = [card.name for card in route.cards]
    produced = {key: value for key, value in sorted(route.produced_states.items()) if value}
    return {
        "deck_name": f"proof_based {route.route_type} #{rank}",
        "candidate_origin": "proof_based",
        "route_type": route.route_type,
        "proof_score": route.proof_score,
        "route_seed_cards": " / ".join(card_names),
        "state_chain": _state_chain(route),
        "produced_states": json.dumps(produced, ensure_ascii=False),
        "missing_states": ";".join(route.missing_states),
        "required_support_roles": ";".join(route.required_support_roles),
        "proof_comment": route.proof_comment,
        "total_cost": route.total_cost,
        "depth": len(route.cards),
        "reference_links": route.reference_links,
    }


def _state_chain(route: ProofRoute) -> str:
    parts = []
    running: dict[str, int] = {}
    if route.produced_states.get("resource_loop", 0) and route.cards:
        # Missing-state補完探索では既存ループを起点にする場合がある。
        first_delta = route.cards[0].produced_states
        if route.produced_states.get("resource_loop", 0) > first_delta.get("resource_loop", 0):
            parts.append("resource_loop(existing)")
            running["resource_loop"] = 2
    for card in route.cards:
        running = _merge_states(running, card.produced_states)
        parts.append(f"{card.name} ({_compact_states(card.produced_states)})")
    parts.append(f"{route.route_type} ({_compact_states(route.produced_states)})")
    return " -> ".join(parts)


def _apply_virtual_states(states: dict[str, int]) -> dict[str, int]:
    updated = dict(states)
    if any(updated.get(state, 0) > 0 for state in LOOP_OUTPUT_TO_WIN_STATES):
        updated["loop_output_to_win"] = max(1, int(updated.get("loop_output_to_win", 0)))
    return {key: value for key, value in updated.items() if value}


def _virtual_states_from_blob(value: dict[str, Any]) -> dict[str, int]:
    blob = " ".join(
        str(value.get(key, "") or "")
        for key in [
            "name",
            "text",
            "tags",
            "output_signals",
            "restriction_breaks",
            "win_contribution",
            "matchup_roles",
        ]
    )
    delta: dict[str, int] = {}
    # テキスト全文の「ゲームに勝つ」は「相手がゲームに勝つ時、かわりに〜」型の
    # 防御置換も拾ってしまうため、主語判定つきのヘルパーで判定する。
    win_text_hit = has_self_win_text(str(value.get("text", "") or ""))
    meta_blob = " ".join(
        str(value.get(key, "") or "")
        for key in ["tags", "output_signals", "win_contribution"]
    )
    if win_text_hit or any(keyword in meta_blob for keyword in ["terminal_win", "特殊勝利"]):
        delta["terminal_win"] = 1
        delta["alternate_win_progress"] = max(delta.get("alternate_win_progress", 0), 3)
        delta["win_progress"] = max(delta.get("win_progress", 0), 2)
    if has_extra_turn_text(str(value.get("text", "") or "")):
        delta["extra_turn"] = 1
        delta["turn_count"] = max(delta.get("turn_count", 0), 1)
        delta["win_progress"] = max(delta.get("win_progress", 0), 1)
    if any(keyword in blob for keyword in ["アンタップ", "追加攻撃", "連続攻撃", "もう一度攻撃"]):
        delta["repeated_attack"] = 1
        delta["damage_pressure"] = max(delta.get("damage_pressure", 0), 2)
    if any(keyword in blob for keyword in ["スピードアタッカー", "アンブロッカブル", "打点"]):
        delta["damage_pressure"] = max(delta.get("damage_pressure", 0), 1)
    if any(keyword in blob for keyword in ["相手の山札", "山札送り", "山札の上から", "相手はカードを引"]):
        delta["opponent_deck_pressure"] = max(delta.get("opponent_deck_pressure", 0), 1)
    return delta


def _parse_state_delta(value: Any) -> dict[str, int]:
    try:
        data = json.loads(str(value or "{}"))
    except Exception:
        data = {}
    return {
        str(key): int(raw)
        for key, raw in data.items()
        if str(key) in STATE_KEYS and _safe_int(raw) != 0
    }


def _condition_signal_to_states(value: Any) -> list[str]:
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
    return [mapping[term] for term in _split_terms(value) if term in mapping]


def _risk_states_from_delta(delta: dict[str, int]) -> list[str]:
    return [key for key, value in delta.items() if value < 0]


def _merge_states(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    merged = dict(left)
    for key, value in right.items():
        merged[key] = int(merged.get(key, 0)) + int(value)
    return {key: value for key, value in merged.items() if value}


def _compact_states(states: dict[str, int]) -> str:
    parts = [f"{key}:{value:+d}" for key, value in sorted(states.items()) if value]
    return " / ".join(parts) if parts else "なし"


def _split_terms(value: Any) -> list[str]:
    terms = []
    for term in str(value or "").replace(",", ";").replace("、", ";").split(";"):
        term = term.strip()
        if term:
            terms.append(term)
    return terms


def _safe_cost(value: Any, default: int = 6) -> int:
    try:
        parsed = int(float(str(value).strip()))
        return max(0, parsed)
    except Exception:
        return default


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _route_type_mismatch(route_type: str, produced_states: dict[str, int]) -> bool:
    if route_type == "alternate_effect_win":
        return produced_states.get("alternate_win_progress", 0) <= 0 and produced_states.get("terminal_win", 0) <= 0
    if route_type == "opponent_deckout_win":
        return produced_states.get("opponent_deck_pressure", 0) <= 0
    if route_type == "lock_confirmed_win":
        return produced_states.get("opponent_action_lock", 0) <= 0
    if route_type == "damage_overflow_win":
        return produced_states.get("damage_pressure", 0) <= 0 or (
            produced_states.get("attack_permission", 0) <= 0
            and produced_states.get("repeated_attack", 0) <= 0
        )
    if route_type == "direct_attack_win":
        return produced_states.get("damage_pressure", 0) <= 0 or produced_states.get("attack_permission", 0) <= 0
    if route_type == "loop_converted_win":
        return produced_states.get("resource_loop", 0) <= 0 or produced_states.get("loop_output_to_win", 0) <= 0
    return False


def _is_excluded_node(node: ProofCardNode) -> bool:
    blob = " ".join(
        [
            node.name,
            node.civilization,
            node.card_type,
            node.tags,
            " ".join(node.proof_terms),
        ]
    )
    if node.cost <= 0:
        return True
    return any(
        keyword in blob
        for keyword in [
            "超次元",
            "サイキック",
            "ドラグハート",
            "龍魂",
            "覚醒",
            "禁断",
            "GRクリーチャー",
            "オレガ・オーラ",
        ]
    )


def _load_known_combo_sets(db_path: Path) -> list[set[str]]:
    try:
        df = load_known_combos(db_path)
        if df.empty:
            return []
        combos = []
        for _, row in df.iterrows():
            names = []
            for column in ["core_cards", "starter_cards", "support_cards", "payoff_cards"]:
                names.extend(_split_terms(row.get(column, "")))
            if names:
                combos.append(set(names))
        return combos
    except Exception:
        return []


def _is_known_combo_exact(cards: tuple[ProofCardNode, ...], known_combo_sets: list[set[str]]) -> bool:
    if not known_combo_sets:
        return False
    names = {card.name for card in cards}
    if len(names) < 2:
        return False
    return any(names and names == combo_set for combo_set in known_combo_sets)


def _table_exists(db_path: Path, table_name: str) -> bool:
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
        return row is not None
    except Exception:
        return False


def _escape_md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Project MANA route proof searcher")
    parser.add_argument("--win", default="loop_converted_win", help="勝利条件キー")
    parser.add_argument("--missing", default="", help="補完したい不足状態")
    parser.add_argument("--all", action="store_true", help="全勝利条件を探索する")
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--beam-width", type=int, default=40)
    parser.add_argument("--max-total-cost", type=int, default=18)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--out", default=str(REPORT_DIR), help="出力ディレクトリ")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    args = parser.parse_args()

    win_condition = "loop_converted_win" if args.missing == "loop_output_to_win" else args.win
    if args.all:
        rows = []
        condition_keys = list(list_proof_win_conditions())
        per_condition_limit = max(1, args.limit // max(1, len(condition_keys)))
        for condition_key in condition_keys:
            rows.extend(
                search_route_proofs(
                    db_path=Path(args.db),
                    win_condition=condition_key,
                    missing_state="",
                    max_depth=args.max_depth,
                    beam_width=args.beam_width,
                    max_total_cost=args.max_total_cost,
                    limit=per_condition_limit,
                )
            )
        summary_win_condition = "all"
    else:
        rows = search_route_proofs(
            db_path=Path(args.db),
            win_condition=win_condition,
            missing_state=args.missing,
            max_depth=args.max_depth,
            beam_width=args.beam_width,
            max_total_cost=args.max_total_cost,
            limit=args.limit,
        )
        summary_win_condition = win_condition
    paths = write_route_proof_outputs(
        rows,
        output_dir=Path(args.out),
        win_condition=summary_win_condition,
        missing_state=args.missing,
    )
    print(f"route_proof_candidates: {len(rows)}")
    for key, path in paths.items():
        print(f"{key}: {path}")
    for row in rows[:5]:
        print(f"- {row['deck_name']} score={row['proof_score']} seed={row['route_seed_cards']}")


if __name__ == "__main__":
    main()

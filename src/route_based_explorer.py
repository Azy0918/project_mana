from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from src.card_effect_feature_store import load_card_effect_features
from src.deck_condition_analyzer import analyze_deck_condition
from src.evaluate_deck import evaluate_deck
from src.generated_deck_store import save_generated_deck
from src.import_cards import DEFAULT_DB_PATH
from src.search_cards import search_cards


ROUTE_TYPES = [
    "lock_confirmed_win",
    "loop_converted_win",
    "alternate_effect_win",
    "opponent_deckout_win",
    "damage_overflow_win",
]


ROUTE_CONFIG = {
    "lock_confirmed_win": {
        "required": ["opponent_action_lock"],
        "support": ["disruption", "board_persistence", "defense", "cast_permission", "summon_permission", "attack_permission"],
        "comment": "相手の有効行動を減らし、こちらの勝ち筋だけを残すルートです。",
    },
    "loop_converted_win": {
        "required": ["resource_loop"],
        "support": ["action_window", "turn_count", "win_progress", "alternate_win_progress", "damage_pressure"],
        "comment": "リソースループを打点、特殊勝利、追加ターンなどへ変換するルートです。",
    },
    "alternate_effect_win": {
        "required": ["alternate_win_progress"],
        "support": ["hand", "shield", "board", "resource_loop", "turn_count"],
        "comment": "カード効果による特殊勝利条件へ到達するルートです。",
    },
    "opponent_deckout_win": {
        "required": ["opponent_deck_pressure"],
        "support": ["disruption", "defense", "resource_loop", "opponent_action_lock"],
        "comment": "相手の山札・ドローを勝利条件へ変換するルートです。",
    },
    "damage_overflow_win": {
        "required": ["damage_pressure", "board"],
        "support": ["attack_permission", "tempo", "action_window", "turn_count"],
        "comment": "過剰打点を作り、受け札を踏んでも押し切るルートです。",
    },
}


@dataclass
class RouteSeed:
    route_type: str
    seed_cards: list[dict[str, Any]]
    state_chain: str
    required_states: list[str]
    produced_states: dict[str, int]
    route_score: int
    route_comment: str
    required_mana_estimate: int
    earliest_route_turn: int
    route_reproducibility_score: int
    route_risk_score: int
    missing_support_states: list[str]
    required_support_roles: list[str]


def discover_route_seeds(
    db_path: str | Path = DEFAULT_DB_PATH,
    route_type: str = "lock_confirmed_win",
    max_seeds: int = 5,
) -> list[RouteSeed]:
    db_path = Path(db_path)
    if route_type not in ROUTE_CONFIG:
        raise ValueError(f"未知のroute_typeです: {route_type}")

    cards = {str(card.get("card_id")): card for card in search_cards(db_path)}
    rows = load_card_effect_features(db_path)
    scored = []
    for _, row in rows.iterrows():
        card_id = str(row.get("card_id", ""))
        card = cards.get(card_id)
        if not card:
            continue
        delta = _parse_delta(row.get("state_delta_json", "{}"))
        score = _route_score(delta, route_type, str(row.get("win_contribution", "")), row.get("earliest_turn"))
        if score <= 0:
            continue
        scored.append((score, card, delta))

    scored.sort(key=lambda item: item[0], reverse=True)
    seeds = []
    seen_pairs: set[frozenset[str]] = set()
    for score, card, delta in scored[: max(max_seeds * 3, max_seeds)]:
        seed_cards = [card]
        partner = _find_partner(card, scored, route_type)
        if partner:
            # A/BとB/Aは同一seedとして扱う
            pair_key = frozenset({str(card.get("name", "")), str(partner[1].get("name", ""))})
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            seed_cards.append(partner[1])
            produced = _merge_delta(delta, partner[2])
            combined_score = min(100, score + partner[0] // 3)
        else:
            produced = delta
            combined_score = min(100, score)
        metrics = _route_metrics(seed_cards, route_type, produced)
        seeds.append(
            RouteSeed(
                route_type=route_type,
                seed_cards=seed_cards,
                state_chain=_build_state_chain(seed_cards, route_type, produced),
                required_states=list(ROUTE_CONFIG[route_type]["required"]),
                produced_states={key: value for key, value in produced.items() if value},
                route_score=_adjusted_route_score(combined_score, metrics, produced, route_type),
                route_comment=str(ROUTE_CONFIG[route_type]["comment"]),
                required_mana_estimate=metrics["required_mana_estimate"],
                earliest_route_turn=metrics["earliest_route_turn"],
                route_reproducibility_score=metrics["route_reproducibility_score"],
                route_risk_score=metrics["route_risk_score"],
                missing_support_states=metrics["missing_support_states"],
                required_support_roles=metrics["required_support_roles"],
            )
        )
        if len(seeds) >= max_seeds:
            break
    return seeds


def build_route_based_deck(
    seed: RouteSeed,
    db_path: str | Path = DEFAULT_DB_PATH,
    deck_size: int = 40,
) -> list[dict[str, Any]]:
    db_path = Path(db_path)
    cards = {str(card.get("card_id")): card for card in search_cards(db_path)}
    rows = load_card_effect_features(db_path)
    scored = []
    for _, row in rows.iterrows():
        card = cards.get(str(row.get("card_id", "")))
        if not card:
            continue
        delta = _parse_delta(row.get("state_delta_json", "{}"))
        score = _route_score(delta, seed.route_type, str(row.get("win_contribution", "")), row.get("earliest_turn"))
        if _safe_cost(card) <= 3 and any(delta.get(key, 0) > 0 for key in ["hand", "mana", "tempo", "defense"]):
            score += 12
        if score > 0:
            scored.append((score, card))
    scored.sort(key=lambda item: item[0], reverse=True)

    deck_by_id: dict[str, dict[str, Any]] = {}
    for card in seed.seed_cards:
        _add_card(deck_by_id, card, 4)

    for score, card in scored:
        if _deck_size(deck_by_id) >= deck_size:
            break
        quantity = 3 if score >= 70 else 2
        if _safe_cost(card) <= 3:
            quantity = max(quantity, 3)
        _add_card(deck_by_id, card, quantity)

    if _deck_size(deck_by_id) < deck_size:
        for card in cards.values():
            if _deck_size(deck_by_id) >= deck_size:
                break
            _add_card(deck_by_id, card, 1)

    _trim_deck(deck_by_id, deck_size)
    return list(deck_by_id.values())


def run_route_based_exploration_and_save(
    db_path: str | Path = DEFAULT_DB_PATH,
    route_type: str = "lock_confirmed_win",
    save_top_n: int = 1,
    deck_size: int = 40,
) -> dict[str, Any]:
    db_path = Path(db_path)
    seeds = discover_route_seeds(db_path, route_type=route_type, max_seeds=max(save_top_n, 1))
    saved_rows = []
    for index, seed in enumerate(seeds[:save_top_n], start=1):
        deck = build_route_based_deck(seed, db_path=db_path, deck_size=deck_size)
        analysis = analyze_deck_condition(
            deck,
            civilizations=[],
            focus_tags=[],
            avoid_tags=[],
            target_starter_count=8,
            target_defense_count=6,
            target_finisher_count=3,
        )
        evaluation = evaluate_deck(deck)
        saved_id = save_generated_deck(
            deck_name=f"route_based v0 {route_type} #{index}",
            civilizations=[],
            deck_type=route_type,
            focus_tags=[],
            avoid_tags=[],
            strategy_note=_route_note(seed),
            deck_cards=deck,
            analysis=analysis,
            evaluation=evaluation,
            format="ND",
            candidate_origin="route_based",
            db_path=db_path,
        )
        saved_rows.append(
            {
                "保存ID": saved_id,
                "route_type": route_type,
                "route_score": seed.route_score,
                "required_mana_estimate": seed.required_mana_estimate,
                "earliest_route_turn": seed.earliest_route_turn,
                "route_reproducibility_score": seed.route_reproducibility_score,
                "route_risk_score": seed.route_risk_score,
                "route_seed_cards": " / ".join(card.get("name", "") for card in seed.seed_cards),
                "state_chain": seed.state_chain,
            }
        )
    return {"route_type": route_type, "seeds": [seed.__dict__ for seed in seeds], "saved_rows": saved_rows}


def _route_score(delta: dict[str, int], route_type: str, win_contribution: str = "", earliest_turn: Any = None) -> int:
    config = ROUTE_CONFIG[route_type]
    score = 0
    score += sum(max(0, int(delta.get(key, 0))) for key in config["required"]) * 36
    score += sum(max(0, int(delta.get(key, 0))) for key in config["support"]) * 10
    if "terminal_win" in win_contribution:
        score += 20
    if "payoff" in win_contribution:
        score += 8
    try:
        turn = int(float(earliest_turn))
        if turn <= 3:
            score += 8
    except Exception:
        pass
    return max(0, min(100, score))


def _route_metrics(seed_cards: list[dict[str, Any]], route_type: str, produced: dict[str, int]) -> dict[str, Any]:
    costs = [_safe_cost(card) for card in seed_cards]
    required_mana = max(costs) if costs else 0
    earliest_turn = max(2, required_mana)
    support_states = list(ROUTE_CONFIG[route_type]["support"])
    missing_support = [state for state in support_states if produced.get(state, 0) <= 0]
    support_roles = _required_support_roles(route_type, required_mana, missing_support)
    reproducibility = 100
    reproducibility -= max(0, required_mana - 4) * 10
    reproducibility -= max(0, len(seed_cards) - 1) * 8
    reproducibility -= len(missing_support) * 5
    if produced.get("hand", 0) > 0 or produced.get("mana", 0) > 0:
        reproducibility += 8
    reproducibility = max(0, min(100, reproducibility))

    risk = 0
    risk += max(0, required_mana - 5) * 12
    risk += len(missing_support) * 6
    if route_type in {"lock_confirmed_win", "alternate_effect_win"} and produced.get("defense", 0) <= 0:
        risk += 12
    if route_type == "damage_overflow_win" and produced.get("trigger_window", 0) < 0:
        risk -= 8
    risk = max(0, min(100, risk))

    return {
        "required_mana_estimate": required_mana,
        "earliest_route_turn": earliest_turn,
        "route_reproducibility_score": reproducibility,
        "route_risk_score": risk,
        "missing_support_states": missing_support,
        "required_support_roles": support_roles,
    }


def _adjusted_route_score(base_score: int, metrics: dict[str, Any], produced: dict[str, int], route_type: str) -> int:
    score = min(85, int(base_score))
    score += metrics["route_reproducibility_score"] // 5
    score -= metrics["route_risk_score"] // 3
    score -= max(0, metrics["required_mana_estimate"] - 5) * 7
    if produced.get("opponent_action_lock", 0) > 0:
        score += 8
    if produced.get("alternate_win_progress", 0) > 0:
        score += 10
    if produced.get("damage_pressure", 0) > 0 and route_type == "damage_overflow_win":
        score += 8
    if produced.get("resource_loop", 0) > 0 and route_type == "loop_converted_win":
        score += 8
    return max(0, min(100, score))


def _required_support_roles(route_type: str, required_mana: int, missing_support: list[str]) -> list[str]:
    roles = []
    if required_mana >= 5:
        roles.extend(["初動", "マナ加速", "リソース"])
    if "defense" in missing_support:
        roles.append("受け札")
    if route_type in {"lock_confirmed_win", "alternate_effect_win", "loop_converted_win"}:
        roles.append("時間稼ぎ")
    if route_type == "damage_overflow_win":
        roles.extend(["展開札", "打点補助"])
    if route_type == "opponent_deckout_win":
        roles.extend(["防御札", "山札干渉"])
    return list(dict.fromkeys(roles))


def _find_partner(seed_card: dict[str, Any], scored: list[tuple[int, dict[str, Any], dict[str, int]]], route_type: str):
    seed_id = str(seed_card.get("card_id", ""))
    seed_name = str(seed_card.get("name", ""))
    for score, card, delta in scored:
        # 同名の別刷り(card_id違い)を相方に選ばない
        if str(card.get("card_id", "")) == seed_id or str(card.get("name", "")) == seed_name:
            continue
        if score < 20:
            continue
        return score, card, delta
    return None


def _route_note(seed: RouteSeed) -> str:
    return "\n".join(
        [
            "route_based v0",
            f"route_type: {seed.route_type}",
            f"route_score: {seed.route_score}",
            f"required_mana_estimate: {seed.required_mana_estimate}",
            f"earliest_route_turn: {seed.earliest_route_turn}",
            f"route_reproducibility_score: {seed.route_reproducibility_score}",
            f"route_risk_score: {seed.route_risk_score}",
            "missing_support_states: " + " / ".join(seed.missing_support_states),
            "required_support_roles: " + " / ".join(seed.required_support_roles),
            "route_seed_cards: " + " / ".join(card.get("name", "") for card in seed.seed_cards),
            f"state_chain: {seed.state_chain}",
            "required_states: " + " / ".join(seed.required_states),
            "produced_states: " + json.dumps(seed.produced_states, ensure_ascii=False),
            f"route_comment: {seed.route_comment}",
        ]
    )


def _parse_delta(value: Any) -> dict[str, int]:
    if isinstance(value, dict):
        return {str(key): int(val) for key, val in value.items() if val}
    try:
        data = json.loads(str(value or "{}"))
        return {str(key): int(val) for key, val in data.items() if val}
    except Exception:
        return {}


def _merge_delta(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    keys = set(left) | set(right)
    return {key: int(left.get(key, 0)) + int(right.get(key, 0)) for key in keys}


def _build_state_chain(seed_cards: list[dict[str, Any]], route_type: str, produced: dict[str, int]) -> str:
    names = " -> ".join(card.get("name", "") for card in seed_cards)
    states = " / ".join(f"{key}:{value:+d}" for key, value in produced.items() if value)
    return f"{names} -> {route_type} ({states})"


def _add_card(deck_by_id: dict[str, dict[str, Any]], card: dict[str, Any], quantity: int) -> None:
    card_id = str(card.get("card_id", ""))
    if not card_id:
        return
    existing = deck_by_id.get(card_id)
    if existing is None:
        existing = dict(card)
        existing["quantity"] = 0
        deck_by_id[card_id] = existing
    existing["quantity"] = min(4, int(existing.get("quantity", 0)) + int(quantity))


def _deck_size(deck_by_id: dict[str, dict[str, Any]]) -> int:
    return sum(int(card.get("quantity", 0)) for card in deck_by_id.values())


def _trim_deck(deck_by_id: dict[str, dict[str, Any]], deck_size: int) -> None:
    while _deck_size(deck_by_id) > deck_size:
        for card_id in list(deck_by_id.keys())[::-1]:
            if _deck_size(deck_by_id) <= deck_size:
                break
            deck_by_id[card_id]["quantity"] -= 1
            if deck_by_id[card_id]["quantity"] <= 0:
                del deck_by_id[card_id]


def _safe_cost(card: dict[str, Any]) -> int:
    try:
        return int(float(str(card.get("cost", "") or 0)))
    except Exception:
        return 0

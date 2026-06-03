from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_DB_PATH


WIN_STATE_WEIGHTS = {
    "opponent_action_lock": 18,
    "alternate_win_progress": 18,
    "resource_loop": 14,
    "damage_pressure": 12,
    "opponent_deck_pressure": 12,
    "board_persistence": 8,
    "defense": 8,
    "disruption": 7,
    "win_progress": 10,
    "attack_permission": 5,
    "cast_permission": 5,
    "summon_permission": 5,
    "board": 4,
    "hand": 3,
    "mana": 3,
    "graveyard": 3,
    "shield": 3,
}

ROUTE_TYPE_HINTS = {
    "lock_confirmed_win": {
        "states": {"opponent_action_lock", "cast_permission", "summon_permission", "attack_permission", "disruption"},
        "tags": {"ロック", "呪文ロック", "攻撃制限", "ハンデス", "制限", "妨害"},
        "known_patterns": {"discard_lock", "shield_resource_win"},
    },
    "loop_converted_win": {
        "states": {"resource_loop", "action_window", "win_progress", "alternate_win_progress", "damage_pressure"},
        "tags": {"ループ", "再利用", "踏み倒し", "回収", "アンタップ", "コンボ", "リソース"},
        "known_patterns": {"cheat_etb_chain", "spell_chain_finish"},
    },
    "alternate_effect_win": {
        "states": {"alternate_win_progress", "shield", "hand", "board", "resource_loop"},
        "tags": {"特殊勝利", "シールド追加", "山札操作", "耐久", "コンボ"},
        "known_patterns": {"shield_resource_win", "deck_manipulation_win"},
    },
    "opponent_deckout_win": {
        "states": {"opponent_deck_pressure", "defense", "disruption", "opponent_action_lock"},
        "tags": {"山札切れ", "山札操作", "ライブラリアウト", "ドロー", "防御", "ロック"},
        "known_patterns": {"deck_manipulation_win"},
    },
    "damage_overflow_win": {
        "states": {"damage_pressure", "board", "attack_permission", "tempo"},
        "tags": {"打点", "スピードアタッカー", "侵略", "革命チェンジ", "踏み倒し", "速攻", "ビート"},
        "known_patterns": {"attack_trigger_cheat", "tribal_swarm", "cheat_etb_chain"},
    },
}


@dataclass
class CardInfo:
    name: str
    cost: int
    civilization: str = ""
    card_type: str = ""
    tags: str = ""
    text: str = ""


def _connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _safe_json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


def _split_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[;/／,\n]+", str(value))
    terms = []
    for item in raw:
        text = str(item).strip()
        if text:
            terms.append(text)
    return terms


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", "", str(name or "")).replace("　", "")


def _extract_state_delta(candidate: dict[str, Any]) -> dict[str, int]:
    """Extract state deltas from candidate fields.

    Supports both structured dicts and state_chain text like:
      "... (win_progress:+1 / opponent_action_lock:+3)"
    """
    merged: dict[str, int] = {}

    for key in ("state_delta", "state_delta_total", "state_delta_json"):
        data = _safe_json_loads(candidate.get(key), {})
        if isinstance(data, dict):
            for state, value in data.items():
                try:
                    merged[str(state)] = merged.get(str(state), 0) + int(float(value))
                except Exception:
                    pass

    state_chain = candidate.get("state_chain", "")
    if isinstance(state_chain, list):
        state_chain = " / ".join(map(str, state_chain))
    for state, sign, number in re.findall(r"([A-Za-z_]+)\s*:\s*([+-])\s*(\d+)", str(state_chain)):
        value = int(number) * (1 if sign == "+" else -1)
        merged[state] = merged.get(state, 0) + value

    produced_states = candidate.get("produced_states", [])
    for state in _split_terms(produced_states):
        merged[state] = max(merged.get(state, 0), 1)

    return merged


def _extract_seed_card_names(candidate: dict[str, Any]) -> list[str]:
    for key in ("route_seed_cards", "seed_cards", "core_cards"):
        value = candidate.get(key)
        if value:
            return _split_terms(value)
    strategy_note = str(candidate.get("strategy_note") or "")
    match = re.search(r"route_seed_cards\s*:\s*([^\n]+)", strategy_note)
    if match:
        return _split_terms(match.group(1))
    return []


def _fetch_cards_by_names(seed_cards: list[str], db_path: str | Path = DEFAULT_DB_PATH) -> list[CardInfo]:
    if not seed_cards:
        return []

    normalized_targets = {_normalize_name(name): name for name in seed_cards}
    cards: list[CardInfo] = []

    with _connect(db_path) as conn:
        if not _table_exists(conn, "cards"):
            return []

        cols = _columns(conn, "cards")
        name_col = "name" if "name" in cols else None
        if not name_col:
            return []

        select_cols = [
            "name",
            "cost" if "cost" in cols else "0 AS cost",
            "civilization" if "civilization" in cols else "'' AS civilization",
            "card_type" if "card_type" in cols else "'' AS card_type",
            "text" if "text" in cols else "'' AS text",
        ]
        query = f"SELECT {', '.join(select_cols)} FROM cards"
        rows = conn.execute(query).fetchall()

        tags_by_name: dict[str, str] = {}
        if _table_exists(conn, "card_tags"):
            tag_cols = _columns(conn, "card_tags")
            if {"card_id", "tag"} <= tag_cols and "card_id" in cols:
                tag_rows = conn.execute(
                    """
                    SELECT c.name, GROUP_CONCAT(ct.tag, ';') AS tags
                    FROM cards c
                    JOIN card_tags ct ON c.card_id = ct.card_id
                    GROUP BY c.name
                    """
                ).fetchall()
                tags_by_name = {row["name"]: row["tags"] or "" for row in tag_rows}

        for row in rows:
            db_name = str(row["name"])
            db_norm = _normalize_name(db_name)
            if db_norm in normalized_targets or any(db_norm in target or target in db_norm for target in normalized_targets):
                try:
                    cost = int(row["cost"] or 0)
                except Exception:
                    cost = 0
                cards.append(
                    CardInfo(
                        name=db_name,
                        cost=cost,
                        civilization=str(row["civilization"] or ""),
                        card_type=str(row["card_type"] or ""),
                        tags=tags_by_name.get(db_name, ""),
                        text=str(row["text"] or ""),
                    )
                )

    # Preserve user seed order as much as possible.
    order = {_normalize_name(name): idx for idx, name in enumerate(seed_cards)}
    cards.sort(key=lambda c: min([order.get(k, 999) for k in order if k in _normalize_name(c.name) or _normalize_name(c.name) in k] or [999]))
    return cards


def estimate_required_mana(seed_cards: list[str], db_path: str | Path = DEFAULT_DB_PATH) -> int:
    cards = _fetch_cards_by_names(seed_cards, db_path)
    if not cards:
        return 0
    return max(card.cost for card in cards)


def estimate_earliest_route_turn(seed_cards: list[str], db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """Rough Duel Masters Plays turn estimate.

    v0 heuristic:
    - Normal play reaches N mana around turn N.
    - Ramp/charger support may advance by 1 turn if present in seed.
    - Very heavy routes have a minimum practical setup tax.
    """
    cards = _fetch_cards_by_names(seed_cards, db_path)
    if not cards:
        return 0

    required_mana = max(card.cost for card in cards)
    joined = " ".join([card.tags + " " + card.text for card in cards])
    ramp_bonus = 1 if any(term in joined for term in ["マナ加速", "チャージャー", "マナゾーンに置く", "ブースト"]) else 0
    setup_tax = 1 if len(cards) >= 3 else 0
    if required_mana >= 9:
        setup_tax += 1

    return max(1, required_mana - ramp_bonus + setup_tax)


def _route_type_from_candidate(candidate: dict[str, Any]) -> str:
    route_type = str(candidate.get("route_type") or "").strip()
    if route_type:
        return route_type
    deck_type = str(candidate.get("deck_type") or "")
    for key in ROUTE_TYPE_HINTS:
        if key in deck_type:
            return key
    strategy_note = str(candidate.get("strategy_note") or "")
    for key in ROUTE_TYPE_HINTS:
        if key in strategy_note:
            return key
    return "unknown"


def _route_relevant_terms(candidate: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH) -> set[str]:
    terms: set[str] = set()
    route_type = _route_type_from_candidate(candidate)
    if route_type:
        terms.add(route_type)
    for value in [
        candidate.get("route_seed_cards", ""),
        candidate.get("seed_cards", ""),
        candidate.get("state_chain", ""),
        candidate.get("strategy_note", ""),
        candidate.get("route_comment", ""),
        candidate.get("deck_type", ""),
    ]:
        terms.update(_split_terms(value))
    terms.update(_extract_state_delta(candidate).keys())

    cards = _fetch_cards_by_names(_extract_seed_card_names(candidate), db_path)
    for card in cards:
        terms.update(_split_terms(card.tags))
        terms.update(_split_terms(card.civilization))
        for token in re.findall(r"[A-Za-z_]+|[一-龥ぁ-んァ-ンーA-Za-z0-9・]+", card.text):
            if len(token) >= 2:
                terms.add(token)

    return {term.strip() for term in terms if term and len(term.strip()) >= 2}


def calculate_route_reproducibility(candidate: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH) -> int:
    seed_cards = _extract_seed_card_names(candidate)
    cards = _fetch_cards_by_names(seed_cards, db_path)
    if not seed_cards:
        return 20

    score = 65

    # More seed pieces means less reproducibility.
    score -= max(0, len(seed_cards) - 2) * 10

    if cards:
        avg_cost = sum(card.cost for card in cards) / len(cards)
        if avg_cost >= 8:
            score -= 20
        elif avg_cost >= 6:
            score -= 12
        elif avg_cost <= 3:
            score += 8

        joined = " ".join([card.tags + " " + card.text for card in cards])
        if any(term in joined for term in ["サーチ", "山札", "手札に加える", "ドロー"]):
            score += 10
        if any(term in joined for term in ["マナ加速", "チャージャー", "マナゾーンに置く"]):
            score += 10
        if any(term in joined for term in ["コストを支払わず", "踏み倒し", "超次元ゾーンから"]):
            score += 6

    earliest = estimate_earliest_route_turn(seed_cards, db_path)
    if earliest >= 9:
        score -= 18
    elif earliest >= 7:
        score -= 10
    elif earliest <= 4:
        score += 8

    return max(0, min(100, int(score)))


def calculate_route_risk(candidate: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH) -> int:
    seed_cards = _extract_seed_card_names(candidate)
    cards = _fetch_cards_by_names(seed_cards, db_path)
    risk = 30

    required_mana = estimate_required_mana(seed_cards, db_path)
    earliest = estimate_earliest_route_turn(seed_cards, db_path)

    if required_mana >= 10:
        risk += 25
    elif required_mana >= 8:
        risk += 18
    elif required_mana >= 6:
        risk += 8

    if earliest >= 9:
        risk += 22
    elif earliest >= 7:
        risk += 14
    elif earliest <= 4:
        risk -= 8

    if len(seed_cards) >= 3:
        risk += 8
    if len(seed_cards) >= 4:
        risk += 8

    joined = " ".join([card.tags + " " + card.text for card in cards])
    if any(term in joined for term in ["S・トリガー", "G・ストライク", "ブロッカー", "シールド追加", "攻撃できない"]):
        risk -= 10
    if any(term in joined for term in ["マナ加速", "チャージャー"]):
        risk -= 6
    if any(term in joined for term in ["サーチ", "ドロー", "手札に加える"]):
        risk -= 5

    # Route type specific risk: slow lock/control routes can be vulnerable to speed.
    route_type = _route_type_from_candidate(candidate)
    if route_type in {"lock_confirmed_win", "alternate_effect_win", "opponent_deckout_win"} and earliest >= 7:
        risk += 10

    return max(0, min(100, int(risk)))


def _load_known_combos(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        if not _table_exists(conn, "known_combos"):
            return []
        cols = _columns(conn, "known_combos")
        wanted = [
            "combo_name",
            "format",
            "archetype",
            "pattern_type",
            "core_cards",
            "starter_cards",
            "support_cards",
            "payoff_cards",
            "required_conditions",
            "main_sequence",
            "win_condition",
            "related_tags",
            "notes",
        ]
        select_cols = [col for col in wanted if col in cols]
        if not select_cols:
            return []
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM known_combos").fetchall()
        return [dict(row) for row in rows]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_nearest_known_combo(candidate: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    route_terms = _route_relevant_terms(candidate, db_path)
    route_type = _route_type_from_candidate(candidate)
    hint_patterns = ROUTE_TYPE_HINTS.get(route_type, {}).get("known_patterns", set())

    best: dict[str, Any] = {
        "nearest_known_combo": "",
        "known_combo_similarity": 0,
        "difference_from_known_combo": "既知コンボDBに十分近い候補は見つかりませんでした。",
        "known_combo_pattern_type": "",
    }

    for combo in _load_known_combos(db_path):
        combo_text = " ".join(str(combo.get(key, "") or "") for key in combo)
        combo_terms = set(_split_terms(combo_text))
        for token in re.findall(r"[A-Za-z_]+|[一-龥ぁ-んァ-ンーA-Za-z0-9・]+", combo_text):
            if len(token) >= 2:
                combo_terms.add(token)

        score = int(round(_jaccard(route_terms, combo_terms) * 100))
        pattern_type = str(combo.get("pattern_type") or "")
        if pattern_type in hint_patterns:
            score += 18
        if route_type and route_type in combo_text:
            score += 12
        score = max(0, min(100, score))

        if score > best["known_combo_similarity"]:
            best = {
                "nearest_known_combo": str(combo.get("combo_name") or ""),
                "known_combo_similarity": score,
                "difference_from_known_combo": _describe_known_combo_difference(candidate, combo, score),
                "known_combo_pattern_type": pattern_type,
            }

    return best


def _describe_known_combo_difference(candidate: dict[str, Any], combo: dict[str, Any], similarity: int) -> str:
    route_type = _route_type_from_candidate(candidate)
    combo_name = str(combo.get("combo_name") or "既知コンボ")
    pattern_type = str(combo.get("pattern_type") or "")
    seed_cards = " / ".join(_extract_seed_card_names(candidate)) or "seed不明"

    if similarity >= 75:
        prefix = f"{combo_name}にかなり近い既知派生です。"
    elif similarity >= 50:
        prefix = f"{combo_name}と一部構造が近い候補です。"
    else:
        prefix = f"{combo_name}との共通点は限定的です。"

    if route_type == "lock_confirmed_win":
        detail = "ロック/制圧方向は既知構造に近い一方、seedカードの接続順や盤面リセットからロックへ向かう点が差分です。"
    elif route_type == "loop_converted_win":
        detail = "リソース循環を勝利状態へ変換できているかが差分確認点です。"
    elif route_type == "alternate_effect_win":
        detail = "特殊勝利条件に必要な前提状態をどこまで自前で作れるかが差分確認点です。"
    elif route_type == "opponent_deckout_win":
        detail = "相手山札圧力と自分の防御/山札切れ回避を両立できるかが差分確認点です。"
    elif route_type == "damage_overflow_win":
        detail = "既知の攻撃起点・横展開型と比べ、受け札を踏んでも押し切れる過剰打点があるかが差分確認点です。"
    else:
        detail = "route_typeが不明なため、状態変換連鎖の終端を追加確認してください。"

    return f"{prefix} pattern_type={pattern_type} / seed={seed_cards}。{detail}"


def _load_meta_decks(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        if not _table_exists(conn, "meta_decks"):
            return []
        cols = _columns(conn, "meta_decks")
        wanted = [
            "deck_name",
            "format",
            "tier",
            "civilizations",
            "deck_type",
            "key_cards",
            "good_matchups",
            "bad_matchups",
            "notes",
        ]
        select_cols = [col for col in wanted if col in cols]
        if not select_cols:
            return []
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM meta_decks").fetchall()
        return [dict(row) for row in rows]


def find_target_meta_decks(candidate: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH, limit: int = 5) -> list[dict[str, Any]]:
    route_terms = _route_relevant_terms(candidate, db_path)
    route_type = _route_type_from_candidate(candidate)
    hint_tags = ROUTE_TYPE_HINTS.get(route_type, {}).get("tags", set())

    scored: list[dict[str, Any]] = []
    for deck in _load_meta_decks(db_path):
        deck_text = " ".join(str(deck.get(key, "") or "") for key in deck)
        deck_terms = set(_split_terms(deck_text))
        for token in re.findall(r"[A-Za-z_]+|[一-龥ぁ-んァ-ンーA-Za-z0-9・]+", deck_text):
            if len(token) >= 2:
                deck_terms.add(token)

        overlap = int(round(_jaccard(route_terms, deck_terms) * 100))
        score = overlap

        deck_type = str(deck.get("deck_type") or "")
        if route_type == "lock_confirmed_win" and deck_type in {"コントロール", "ビッグマナ", "カウンター", "コンボ"}:
            score += 18
        if route_type == "damage_overflow_win" and deck_type in {"ビート", "速攻", "ワンショット"}:
            score += 10
        if hint_tags and (hint_tags & deck_terms):
            score += 8

        tier = str(deck.get("tier") or "")
        if tier == "S":
            score += 8
        elif tier == "A":
            score += 4

        if score <= 0:
            continue

        scored.append(
            {
                "deck_name": str(deck.get("deck_name") or ""),
                "format": str(deck.get("format") or ""),
                "tier": tier,
                "deck_type": deck_type,
                "meta_hit_score": max(0, min(100, score)),
                "meta_hit_reason": _describe_meta_hit(candidate, deck),
            }
        )

    scored.sort(key=lambda row: row["meta_hit_score"], reverse=True)
    return scored[:limit]


def _describe_meta_hit(candidate: dict[str, Any], deck: dict[str, Any]) -> str:
    route_type = _route_type_from_candidate(candidate)
    deck_name = str(deck.get("deck_name") or "環境デッキ")
    deck_type = str(deck.get("deck_type") or "")

    if route_type == "lock_confirmed_win":
        return f"{deck_name}は{deck_type or '不明'}系です。呪文ロック・攻撃制限・行動制限が刺さる可能性があります。ただし成立ターンが遅い場合、速攻/ビートには間に合いません。"
    if route_type == "loop_converted_win":
        return f"{deck_name}に対して、リソースループが防御や打点へ変換できれば長期戦で差が出る可能性があります。"
    if route_type == "alternate_effect_win":
        return f"{deck_name}に対して、通常の打点勝負を避けて特殊勝利へ向かえる点が差分です。条件達成速度を確認してください。"
    if route_type == "opponent_deckout_win":
        return f"{deck_name}に対して、山札圧力と防御を両立できれば別軸勝利を狙えます。自分の山札切れリスクに注意してください。"
    if route_type == "damage_overflow_win":
        return f"{deck_name}に対して、受け札を踏んでも押し切る過剰打点が作れるかを確認してください。"
    return f"{deck_name}との状態変換の重なりがあります。route_typeと刺さる状態を追加確認してください。"


def infer_required_support(candidate: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    seed_cards = _extract_seed_card_names(candidate)
    cards = _fetch_cards_by_names(seed_cards, db_path)
    route_type = _route_type_from_candidate(candidate)
    joined = " ".join([card.tags + " " + card.text for card in cards])
    required_roles: list[str] = []
    missing_states: list[str] = []

    required_mana = estimate_required_mana(seed_cards, db_path)
    earliest = estimate_earliest_route_turn(seed_cards, db_path)

    if required_mana >= 7 and not any(term in joined for term in ["マナ加速", "チャージャー", "コスト軽減"]):
        required_roles.append("マナ加速/コスト軽減")
        missing_states.append("mana_acceleration")

    if earliest >= 6 and not any(term in joined for term in ["S・トリガー", "G・ストライク", "ブロッカー", "攻撃できない", "シールド追加"]):
        required_roles.append("序盤防御/受け札")
        missing_states.append("early_defense")

    if not any(term in joined for term in ["ドロー", "手札に加える", "サーチ", "山札を見る"]):
        required_roles.append("サーチ/ドロー")
        missing_states.append("access_to_seed")

    if route_type == "lock_confirmed_win" and not any(term in joined for term in ["打点", "T・ブレイカー", "W・ブレイカー", "スピードアタッカー"]):
        required_roles.append("ロック後の勝ち手段")
        missing_states.append("post_lock_payoff")

    if route_type == "loop_converted_win" and "resource_loop" not in _extract_state_delta(candidate):
        required_roles.append("ループ出力の明確化")
        missing_states.append("loop_output_to_win")

    return {
        "required_support_roles": ";".join(dict.fromkeys(required_roles)),
        "missing_support_states": ";".join(dict.fromkeys(missing_states)),
    }


def apply_score_caps(candidate: dict[str, Any], evaluation: dict[str, Any], raw_score: int) -> dict[str, Any]:
    """Apply v1 score caps to prevent overconfident route evaluation.

    The goal is not to prove a candidate is bad. The goal is to separate:
      - "structurally promising but unverified"
      - "actually ready for priority testing"

    raw_adjusted_route_score is preserved, and adjusted_route_score becomes the
    capped score.
    """
    route_type = str(evaluation.get("route_type") or candidate.get("route_type") or "")
    seed_cards = _extract_seed_card_names(candidate)
    seed_count = len(seed_cards)
    known_similarity = int(evaluation.get("known_combo_similarity") or 0)
    required_mana = int(evaluation.get("required_mana_estimate") or 0)
    earliest_turn = int(evaluation.get("earliest_route_turn") or 0)
    risk = int(evaluation.get("route_risk_score") or 0)
    reproducibility = int(evaluation.get("route_reproducibility_score") or 0)
    target_meta_decks = str(evaluation.get("target_meta_decks") or "")
    support_roles = str(evaluation.get("required_support_roles") or "")
    state_delta = _extract_state_delta(candidate)

    capped = int(raw_score)
    reasons: list[str] = []

    # Very low evidence against known combo DB means we do not know whether this is
    # truly a coherent route or just a tag-based coincidence.
    if known_similarity < 20:
        capped = min(capped, 78)
        reasons.append("既知コンボ類似度が20未満で、構造接続が未確認")
    elif known_similarity < 30:
        capped = min(capped, 85)
        reasons.append("既知コンボ類似度が低く、既知構造との接続確認が必要")

    # Two-card seeds are attractive but often over-scored. Cap unless the state
    # chain clearly includes a win-progressing terminal signal.
    if seed_count <= 2:
        terminal_signals = [
            state_delta.get("win_progress", 0) > 0,
            state_delta.get("alternate_win_progress", 0) > 0,
            state_delta.get("damage_pressure", 0) >= 2,
            state_delta.get("opponent_action_lock", 0) >= 2,
            state_delta.get("resource_loop", 0) >= 2,
        ]
        if not any(terminal_signals):
            capped = min(capped, 70)
            reasons.append("2枚seedだが勝利状態への出力が明確ではない")
        else:
            capped = min(capped, 88)
            reasons.append("2枚seedのため、実接続と再現性確認までは上限88")

    # Lock routes are often over-rated by broad tags. If the lock scope is not
    # explicit enough, cap it.
    if route_type == "lock_confirmed_win":
        lock_strength = 0
        lock_strength += max(0, int(state_delta.get("opponent_action_lock", 0)))
        lock_strength += max(0, -int(state_delta.get("cast_permission", 0)))
        lock_strength += max(0, -int(state_delta.get("summon_permission", 0)))
        lock_strength += max(0, -int(state_delta.get("attack_permission", 0)))
        if lock_strength <= 1:
            capped = min(capped, 72)
            reasons.append("lock_confirmed_winだがロック範囲が限定的/不明")
        elif lock_strength <= 3:
            capped = min(capped, 82)
            reasons.append("lock_confirmed_winだが完全ロックかは未確認")

    # If candidate only matches meta decks broadly, don't allow perfect score.
    if target_meta_decks:
        meta_count = len([x for x in target_meta_decks.split(";") if x.strip()])
        if meta_count >= 4 and known_similarity < 30:
            capped = min(capped, 82)
            reasons.append("環境刺さり先が広い一方、タグ一致寄りの可能性")
    else:
        capped = min(capped, 75)
        reasons.append("刺さり候補環境デッキが未確認")

    # Basic practical caps.
    if required_mana >= 8:
        capped = min(capped, 55)
        reasons.append("必要マナが重い")
    elif required_mana >= 7:
        capped = min(capped, 70)
        reasons.append("必要マナがやや重い")

    if earliest_turn >= 8:
        capped = min(capped, 55)
        reasons.append("成立ターンが遅い")
    elif earliest_turn >= 7:
        capped = min(capped, 70)
        reasons.append("成立ターンがやや遅い")

    if risk >= 70:
        capped = min(capped, 55)
        reasons.append("リスクスコアが高い")
    elif risk >= 45:
        capped = min(capped, 75)
        reasons.append("リスクスコアが中程度以上")

    if reproducibility < 40:
        capped = min(capped, 55)
        reasons.append("再現性スコアが低い")
    elif reproducibility < 65:
        capped = min(capped, 75)
        reasons.append("再現性スコアが中程度")

    if support_roles:
        capped = min(capped, 75)
        reasons.append("不足補助役割が残っている")

    return {
        "raw_adjusted_route_score": int(raw_score),
        "adjusted_route_score": max(0, min(100, int(capped))),
        "score_cap_reasons": ";".join(dict.fromkeys(reasons)),
    }


def _route_comment_from_score(adjusted_score: int, cap_reasons: str = "") -> str:
    if adjusted_score <= 20:
        return (
            "実戦候補としては低優先度です。必要マナ・成立ターン・再現性・リスクの面で厳しいため、"
            "構造学習用または失敗例として残してください。"
        )
    if adjusted_score <= 50:
        return (
            "研究候補ですが、そのまま実戦投入するには不安があります。"
            "不足補助役割を追加し、必要マナ・成立ターン・再現性を改善してから再評価してください。"
        )
    if adjusted_score <= 75:
        base = "研究検証候補です。"
        if cap_reasons:
            base += f" ただしスコア上限理由があります: {cap_reasons}。"
        return base + " カード間の実接続、フォーマット適合、環境対面を確認してください。"
    if adjusted_score <= 90:
        base = "実戦検証候補です。"
        if cap_reasons:
            base += f" スコア上限理由: {cap_reasons}。"
        return base + " 環境デッキへの刺さり先と、速攻対面への耐性を重点確認してください。"
    return (
        "優先実戦検証候補です。既知コンボとの差分、環境への刺さり、再現性を実戦ログで確認してください。"
    )


def calculate_adjusted_route_score(candidate: dict[str, Any], evaluation: dict[str, Any]) -> int:
    base = int(float(candidate.get("route_score") or evaluation.get("route_score") or 50))
    score = base

    state_delta = _extract_state_delta(candidate)
    for state, value in state_delta.items():
        if value > 0:
            score += min(12, WIN_STATE_WEIGHTS.get(state, 0) * min(value, 3) // 3)

    # Reality checks.
    required_mana = int(evaluation.get("required_mana_estimate") or 0)
    earliest = int(evaluation.get("earliest_route_turn") or 0)
    reproducibility = int(evaluation.get("route_reproducibility_score") or 0)
    risk = int(evaluation.get("route_risk_score") or 0)
    known_similarity = int(evaluation.get("known_combo_similarity") or 0)
    target_meta_decks = evaluation.get("target_meta_decks") or []

    if required_mana >= 10:
        score -= 30
    elif required_mana >= 8:
        score -= 22
    elif required_mana >= 6:
        score -= 8

    if earliest >= 9:
        score -= 28
    elif earliest >= 7:
        score -= 18
    elif earliest >= 5:
        score -= 6

    score += (reproducibility - 50) // 3
    score -= risk // 4

    if known_similarity >= 80:
        score -= 12
    elif known_similarity >= 65:
        score -= 6

    if target_meta_decks:
        score += min(12, len(target_meta_decks) * 3)
        # If slow, don't over-credit meta targeting.
        if earliest >= 7:
            score -= 8

    if evaluation.get("missing_support_states"):
        score -= min(16, len(_split_terms(evaluation["missing_support_states"])) * 4)

    return max(0, min(100, int(score)))


def evaluate_route_candidate(candidate: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    """Evaluate one route_based candidate.

    The function is intentionally schema-light so it can evaluate:
    - rows from generated_decks
    - route_seed dicts from route_based_explorer
    - hand-written route candidates

    Returns a dict that can be merged into candidate metadata or printed in
    mana_context_brief.
    """
    seed_cards = _extract_seed_card_names(candidate)
    route_type = _route_type_from_candidate(candidate)
    required_mana = estimate_required_mana(seed_cards, db_path)
    earliest_turn = estimate_earliest_route_turn(seed_cards, db_path)
    reproducibility = calculate_route_reproducibility(candidate, db_path)
    risk = calculate_route_risk(candidate, db_path)
    known = find_nearest_known_combo(candidate, db_path)
    meta_targets = find_target_meta_decks(candidate, db_path, limit=5)
    support = infer_required_support(candidate, db_path)

    result: dict[str, Any] = {
        "route_type": route_type,
        "route_seed_cards": " / ".join(seed_cards),
        "required_mana_estimate": required_mana,
        "earliest_route_turn": earliest_turn,
        "route_reproducibility_score": reproducibility,
        "route_risk_score": risk,
        "missing_support_states": support["missing_support_states"],
        "required_support_roles": support["required_support_roles"],
        "nearest_known_combo": known["nearest_known_combo"],
        "known_combo_similarity": known["known_combo_similarity"],
        "difference_from_known_combo": known["difference_from_known_combo"],
        "known_combo_pattern_type": known.get("known_combo_pattern_type", ""),
        "target_meta_decks": ";".join(
            f"{row['deck_name']}({row.get('format') or '-'}/Tier {row.get('tier') or '-'})"
            for row in meta_targets
        ),
        "meta_hit_reason": " / ".join(row["meta_hit_reason"] for row in meta_targets[:3]),
        "target_meta_deck_rows": meta_targets,
    }
    raw_adjusted_score = calculate_adjusted_route_score(candidate, result)
    cap_result = apply_score_caps(candidate, result, raw_adjusted_score)
    result.update(cap_result)

    adjusted_score = int(result.get("adjusted_route_score") or 0)
    result["route_evaluation_comment"] = _route_comment_from_score(
        adjusted_score,
        str(result.get("score_cap_reasons") or ""),
    )

    return result


def evaluate_route_candidates(candidates: list[dict[str, Any]], db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates:
        row = dict(candidate)
        try:
            row.update(evaluate_route_candidate(candidate, db_path))
        except Exception as exc:
            row["route_evaluation_error"] = str(exc)
        rows.append(row)
    rows.sort(key=lambda r: int(r.get("adjusted_route_score") or r.get("route_score") or 0), reverse=True)
    return rows


def evaluate_saved_route_based_decks(db_path: str | Path = DEFAULT_DB_PATH, limit: int = 20) -> list[dict[str, Any]]:
    """Evaluate saved generated_decks rows where candidate_origin=route_based.

    This is useful for mana_context_brief integration.
    """
    with _connect(db_path) as conn:
        if not _table_exists(conn, "generated_decks"):
            return []
        cols = _columns(conn, "generated_decks")
        select_cols = [
            col
            for col in [
                "id",
                "deck_name",
                "format",
                "candidate_origin",
                "deck_type",
                "strategy_note",
                "route_type",
                "route_score",
                "route_seed_cards",
                "state_chain",
                "created_at",
            ]
            if col in cols
        ]
        if not select_cols:
            return []

        where = "candidate_origin = 'route_based'" if "candidate_origin" in cols else "deck_type LIKE '%win%'"
        order = "created_at DESC" if "created_at" in cols else "id DESC"
        rows = conn.execute(
            f"SELECT {', '.join(select_cols)} FROM generated_decks WHERE {where} ORDER BY {order} LIMIT ?",
            (int(limit),),
        ).fetchall()

    return evaluate_route_candidates([dict(row) for row in rows], db_path)


def route_evaluation_to_markdown(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "## route_based 再評価\n\nroute_based候補はまだありません。\n"

    headers = [
        "deck_name",
        "route_type",
        "route_score",
        "raw_adjusted_route_score",
        "adjusted_route_score",
        "score_cap_reasons",
        "required_mana_estimate",
        "earliest_route_turn",
        "route_reproducibility_score",
        "route_risk_score",
        "nearest_known_combo",
        "known_combo_similarity",
        "target_meta_decks",
    ]

    lines = ["## route_based 再評価", ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(h, "")).replace("\n", " ") for h in headers) + " |")

    lines.append("")
    for row in rows[:5]:
        lines.append(f"### {row.get('deck_name') or row.get('route_type') or 'route_based候補'}")
        lines.append(f"- raw_adjusted_route_score: {row.get('raw_adjusted_route_score', '-')}")
        lines.append(f"- adjusted_route_score: {row.get('adjusted_route_score', '-')}")
        lines.append(f"- score_cap_reasons: {row.get('score_cap_reasons') or '-'}")
        lines.append(f"- 近い既知コンボ: {row.get('nearest_known_combo') or '-'}")
        lines.append(f"- 既知コンボ類似度: {row.get('known_combo_similarity', 0)}")
        lines.append(f"- 既知コンボとの差分: {row.get('difference_from_known_combo') or '-'}")
        lines.append(f"- 刺さり候補: {row.get('target_meta_decks') or '-'}")
        lines.append(f"- 刺さる理由: {row.get('meta_hit_reason') or '-'}")
        lines.append(f"- 不足補助: {row.get('required_support_roles') or '-'}")
        lines.append(f"- コメント: {row.get('route_evaluation_comment') or '-'}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    rows = evaluate_saved_route_based_decks(DEFAULT_DB_PATH)
    print(route_evaluation_to_markdown(rows))

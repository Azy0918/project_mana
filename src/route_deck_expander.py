from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_DB_PATH
from src.evaluate_deck import evaluate_deck
from src.route_candidate_evaluator import evaluate_route_candidate


@dataclass
class CardRow:
    name: str
    cost: int
    civilization: str = ""
    card_type: str = ""
    tags: str = ""
    text: str = ""

    @property
    def tag_set(self) -> set[str]:
        return set(_split_terms(self.tags))

    @property
    def civ_set(self) -> set[str]:
        return set(_split_terms(self.civilization))


DEFAULT_ROLE_PLAN = {
    "seed": 4,
    "starter": 8,
    "defense": 8,
    "resource": 6,
    "removal": 6,
    "payoff": 6,
    "flex": 2,
}

ROUTE_ROLE_BIAS = {
    "lock_confirmed_win": {
        "starter": ["初動", "低コスト", "サーチ候補", "マナ加速"],
        "defense": ["受け札", "S・トリガー", "G・ストライク", "ブロッカー", "攻撃制限"],
        "resource": ["ドロー", "リソース", "ハンデス", "山札操作"],
        "removal": ["除去", "バウンス", "パワー低下", "盤面処理"],
        "payoff": ["ロック", "呪文ロック", "フィニッシャー", "打点"],
        "flex": ["シールド追加", "攻撃制限", "墓地利用", "多色"],
    },
    "damage_overflow_win": {
        "starter": ["初動", "低コスト", "サーチ候補", "マナ加速"],
        "defense": ["受け札", "S・トリガー", "G・ストライク"],
        "resource": ["ドロー", "リソース", "サーチ候補"],
        "removal": ["除去", "バウンス", "盤面処理"],
        "payoff": ["打点", "フィニッシャー", "スピードアタッカー", "侵略", "革命チェンジ", "踏み倒し"],
        "flex": ["アンブロッカブル", "攻撃制限", "テンポ"],
    },
    "loop_converted_win": {
        "starter": ["初動", "低コスト", "サーチ候補", "マナ加速"],
        "defense": ["受け札", "S・トリガー", "G・ストライク", "ブロッカー"],
        "resource": ["ドロー", "リソース", "回収", "墓地利用", "山札操作"],
        "removal": ["除去", "バウンス", "ハンデス"],
        "payoff": ["フィニッシャー", "打点", "ロック", "特殊勝利", "踏み倒し"],
        "flex": ["コンボ", "墓地利用", "踏み倒し"],
    },
    "alternate_effect_win": {
        "starter": ["初動", "低コスト", "サーチ候補", "マナ加速"],
        "defense": ["受け札", "S・トリガー", "G・ストライク", "ブロッカー", "シールド追加"],
        "resource": ["ドロー", "リソース", "山札操作", "シールド操作"],
        "removal": ["除去", "バウンス", "攻撃制限"],
        "payoff": ["特殊勝利", "フィニッシャー", "山札操作", "ロック"],
        "flex": ["シールド追加", "耐久", "コンボ"],
    },
    "opponent_deckout_win": {
        "starter": ["初動", "低コスト", "サーチ候補", "マナ加速"],
        "defense": ["受け札", "S・トリガー", "G・ストライク", "ブロッカー", "攻撃制限"],
        "resource": ["ドロー", "リソース", "山札操作", "ハンデス"],
        "removal": ["除去", "バウンス", "攻撃制限"],
        "payoff": ["山札操作", "ロック", "呪文ロック", "フィニッシャー"],
        "flex": ["シールド追加", "耐久", "ハンデス"],
    },
}

BANNED_SEED_TERMS = ["ドラグハート", "サイキック", "超次元", "龍魂", "覚醒", "禁断", "鼓動", "セル"]


def _connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _split_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[;/／,\n]+", str(value))
    return [str(item).strip() for item in raw if str(item).strip()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _load_cards(db_path: str | Path = DEFAULT_DB_PATH) -> list[CardRow]:
    with _connect(db_path) as conn:
        if not _table_exists(conn, "cards"):
            return []
        cols = _columns(conn, "cards")
        if "name" not in cols:
            return []

        select_cols = [
            "name",
            "cost" if "cost" in cols else "0 AS cost",
            "civilization" if "civilization" in cols else "'' AS civilization",
            "card_type" if "card_type" in cols else "'' AS card_type",
            "text" if "text" in cols else "'' AS text",
        ]
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM cards").fetchall()

        tags_by_name: dict[str, str] = {}
        if _table_exists(conn, "card_tags") and {"card_id", "tag"} <= _columns(conn, "card_tags"):
            card_cols = _columns(conn, "cards")
            if "card_id" in card_cols:
                try:
                    tag_rows = conn.execute(
                        """
                        SELECT c.name, GROUP_CONCAT(ct.tag, ';') AS tags
                        FROM cards c
                        JOIN card_tags ct ON c.card_id = ct.card_id
                        GROUP BY c.name
                        """
                    ).fetchall()
                    tags_by_name = {row["name"]: row["tags"] or "" for row in tag_rows}
                except Exception:
                    tags_by_name = {}

    cards: list[CardRow] = []
    for row in rows:
        try:
            cost = int(row["cost"] or 0)
        except Exception:
            cost = 0
        cards.append(
            CardRow(
                name=str(row["name"] or ""),
                cost=cost,
                civilization=str(row["civilization"] or ""),
                card_type=str(row["card_type"] or ""),
                tags=_dedupe_tags(tags_by_name.get(str(row["name"] or ""), "")),
                text=str(row["text"] or ""),
            )
        )
    return cards


def _find_cards_by_names(names: list[str], all_cards: list[CardRow]) -> list[CardRow]:
    wanted = [_norm(name) for name in names if str(name).strip()]
    found: list[CardRow] = []
    seen: set[str] = set()
    for wanted_name in wanted:
        exact = [card for card in all_cards if _norm(card.name) == wanted_name]
        partial = [card for card in all_cards if wanted_name in _norm(card.name) or _norm(card.name) in wanted_name]
        for card in exact + partial:
            key = _norm(card.name)
            if key and key not in seen:
                seen.add(key)
                found.append(card)
                break
    return found


def _extract_seed_names(candidate: dict[str, Any]) -> list[str]:
    for key in ["route_seed_cards", "seed_cards", "core_cards"]:
        value = candidate.get(key)
        if value:
            return _split_terms(value)
    return []


def _is_main_deck_candidate(card: CardRow) -> bool:
    blob = f"{card.name};{card.card_type};{card.tags};{card.text}"
    if card.cost <= 0:
        return False
    return not any(term in blob for term in BANNED_SEED_TERMS)


def _civilization_profile(seed_cards: list[CardRow]) -> set[str]:
    civs: set[str] = set()
    for card in seed_cards:
        civs.update(card.civ_set)
    return {civ for civ in civs if civ and civ != "無色"}


def _civilization_score(card: CardRow, target_civs: set[str]) -> int:
    if not target_civs:
        return 0
    civs = card.civ_set
    if not civs:
        return 0
    if "無色" in civs:
        return 2
    overlap = len(civs & target_civs)
    if overlap:
        return overlap * 8
    # Allow light splashes but discourage unrelated colors.
    return -10


def _is_five_color(card: CardRow) -> bool:
    civs = {civ for civ in card.civ_set if civ and civ != "無色"}
    return len(civs) >= 5


def _tag_overload_penalty(card: CardRow) -> int:
    tag_count = len(card.tag_set)
    if tag_count >= 13:
        return 18
    if tag_count >= 10:
        return 10
    if tag_count >= 8:
        return 4
    return 0


def _role_cost_penalty(card: CardRow, role: str) -> int:
    base_role = _role_base(role)
    limit = ROLE_COST_LIMITS.get(base_role)
    if limit is None:
        return 0
    over = card.cost - limit
    if over <= 0:
        return 0
    if base_role == "removal":
        return over * 18
    if base_role == "payoff":
        return over * 8
    return over * 10


def _quality_score_penalty(card: CardRow, role: str, used_counts: Counter[str] | None = None) -> int:
    penalty = 0
    penalty += _tag_overload_penalty(card)
    penalty += _role_cost_penalty(card, role)

    if _is_five_color(card):
        penalty += 16
        if used_counts:
            five_color_used = 0
            # used_counts has normalized names only, so this exact count cannot be
            # derived cheaply. The deck-level pass handles final warnings.
            # Keep this as a fixed penalty.
            penalty += 0

    if _is_multicolor(card):
        penalty += 3

    if role == "removal" and card.cost >= 7:
        penalty += 25
    if role == "payoff" and card.cost >= 7:
        penalty += 8
    if role in {"starter", "defense", "resource"} and card.cost >= 6:
        penalty += 15

    return penalty


def _role_score(card: CardRow, role: str, role_tags: list[str], target_civs: set[str], seed_names: set[str]) -> int:
    if _norm(card.name) in seed_names:
        return -999
    if not _is_main_deck_candidate(card):
        return -999

    blob = f"{card.name};{card.tags};{card.text}"
    matched = sum(1 for tag in role_tags if tag in blob)
    if matched <= 0:
        return -999

    score = matched * 14
    score += _civilization_score(card, target_civs)
    score += max(0, 8 - card.cost)

    if "低コスト" in card.tags or card.cost <= 3:
        score += 4
    if "S・トリガー" in card.tags or "G・ストライク" in card.tags:
        score += 3
    if "多色" in card.tags and len(target_civs) >= 2:
        score += 2

    score -= _quality_score_penalty(card, role)
    return score


def _max_copies_for_card_role(card: CardRow, role: str, used_counts: Counter[str]) -> int:
    base_role = _role_base(role)

    if base_role == "removal" and card.cost >= 7:
        return 1
    if base_role == "payoff" and card.cost >= 7:
        return 2
    if _is_five_color(card):
        return 2
    if len(card.tag_set) >= 13 and base_role not in {"starter", "defense"}:
        return 2
    if base_role in {"starter", "defense"}:
        return 4
    if base_role == "payoff":
        return 3
    return 3


def _pick_cards_for_role(
    all_cards: list[CardRow],
    role: str,
    role_tags: list[str],
    target_civs: set[str],
    seed_names: set[str],
    copies_needed: int,
    used_counts: Counter[str],
) -> list[tuple[CardRow, int, str]]:
    scored: list[tuple[int, CardRow]] = []
    for card in all_cards:
        key = _norm(card.name)
        if used_counts[key] >= 4:
            continue
        score = _role_score(card, role, role_tags, target_civs, seed_names)
        if score > -999:
            scored.append((score, card))
    scored.sort(key=lambda x: (x[0], -x[1].cost), reverse=True)

    picked: list[tuple[CardRow, int, str]] = []
    remaining = copies_needed
    for score, card in scored:
        if remaining <= 0:
            break
        key = _norm(card.name)
        available = 4 - used_counts[key]
        if available <= 0:
            continue

        max_role_copies = _max_copies_for_card_role(card, role, used_counts)
        copies = min(max_role_copies, available, remaining)

        if copies <= 0:
            continue

        picked.append((card, copies, role))
        used_counts[key] += copies
        remaining -= copies

    return picked


def _route_role_tags(route_type: str) -> dict[str, list[str]]:
    return ROUTE_ROLE_BIAS.get(route_type) or ROUTE_ROLE_BIAS["lock_confirmed_win"]


ROLE_COST_LIMITS = {
    "starter": 3,
    "defense": 5,
    "resource": 5,
    "removal": 6,
    "payoff": 8,
    "flex": 6,
    "flex_fill": 6,
}


def _dedupe_tags(tags: str) -> str:
    seen: list[str] = []
    for tag in _split_terms(tags):
        if tag not in seen:
            seen.append(tag)
    return ";".join(seen)


def _merge_deck_items(deck_items: list[tuple[CardRow, int, str]]) -> list[tuple[CardRow, int, str]]:
    """Merge duplicate card rows and combine roles.

    Earlier v1 output could split the same card as 3 copies + 1 copy if picked
    by the same role in multiple passes. This function guarantees one display
    row per card name.
    """
    merged: dict[str, tuple[CardRow, int, list[str]]] = {}
    for card, copies, role in deck_items:
        key = _norm(card.name)
        if key not in merged:
            merged[key] = (card, 0, [])
        base_card, current_copies, roles = merged[key]
        if role not in roles:
            roles.append(role)
        merged[key] = (base_card, current_copies + int(copies), roles)

    rows: list[tuple[CardRow, int, str]] = []
    for card, copies, roles in merged.values():
        rows.append((card, min(4, copies), "/".join(roles)))
    rows.sort(key=lambda item: (item[2] != "seed", item[0].cost, item[0].name))
    return rows


def _is_multicolor(card: CardRow) -> bool:
    civs = [civ for civ in card.civ_set if civ and civ != "無色"]
    return len(civs) >= 2


def _is_off_civilization(card: CardRow, target_civs: set[str]) -> bool:
    if not target_civs:
        return False
    civs = {civ for civ in card.civ_set if civ and civ != "無色"}
    if not civs:
        return False
    return not bool(civs & target_civs)


def _role_base(role: str) -> str:
    # role can be "resource/flex" after merge; judge by the first role.
    return str(role or "").split("/")[0]


def _card_quality_warning(card: CardRow, copies: int, role: str, target_civs: set[str]) -> list[str]:
    warnings: list[str] = []
    base_role = _role_base(role)
    cost_limit = ROLE_COST_LIMITS.get(base_role)
    if cost_limit is not None and card.cost > cost_limit:
        warnings.append(f"{base_role}枠としては高コスト")

    if _is_off_civilization(card, target_civs):
        warnings.append("seed文明外カード")

    if len(card.tag_set) >= 10:
        warnings.append("重要タグ過多の可能性")

    if copies >= 4 and base_role in {"payoff", "removal"} and card.cost >= 7:
        warnings.append("重いカードが4枚近い採用")

    if "進化" in card.tags and not any(tag in card.tags for tag in ["サーチ候補", "低コスト", "初動"]):
        # Not always bad, but worth reviewing when auto-picked.
        warnings.append("進化条件の確認が必要")

    return warnings


def analyze_expanded_deck_quality(
    deck_rows: list[dict[str, Any]],
    target_civs: set[str],
) -> dict[str, Any]:
    total_cards = sum(int(row.get("count") or 0) for row in deck_rows)
    weighted_cost = sum(int(row.get("count") or 0) * int(row.get("cost") or 0) for row in deck_rows)
    average_cost = round(weighted_cost / total_cards, 2) if total_cards else 0

    role_counts: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    multicolor_count = 0
    off_civ_count = 0
    high_cost_count = 0
    suspicious: list[dict[str, Any]] = []

    for row in deck_rows:
        count = int(row.get("count") or 0)
        role = str(row.get("role") or "")
        role_counts[role] += count

        card = CardRow(
            name=str(row.get("card_name") or ""),
            cost=int(row.get("cost") or 0),
            civilization=str(row.get("civilization") or ""),
            card_type=str(row.get("card_type") or ""),
            tags=str(row.get("tags") or ""),
            text="",
        )

        if _is_multicolor(card):
            multicolor_count += count
        if _is_off_civilization(card, target_civs):
            off_civ_count += count
        if card.cost >= 7:
            high_cost_count += count
        for tag in _split_terms(card.tags):
            tag_counter[tag] += count

        warning_list = _card_quality_warning(card, count, role, target_civs)
        if warning_list:
            suspicious.append(
                {
                    "card_name": card.name,
                    "count": count,
                    "role": role,
                    "cost": card.cost,
                    "civilization": card.civilization,
                    "warnings": ";".join(warning_list),
                }
            )

    deck_warnings: list[str] = []
    if total_cards != 40:
        deck_warnings.append(f"デッキ枚数が40ではありません: {total_cards}")
    if average_cost >= 5.5:
        deck_warnings.append(f"平均コストが高めです: {average_cost}")
    if high_cost_count >= 8:
        deck_warnings.append(f"コスト7以上が多めです: {high_cost_count}枚")
    if multicolor_count >= 24:
        deck_warnings.append(f"多色カードが多めです: {multicolor_count}枚")
    if off_civ_count >= 6:
        deck_warnings.append(f"seed文明外カードが多めです: {off_civ_count}枚")

    starter_count = sum(count for role, count in role_counts.items() if "starter" in role)
    defense_count = sum(count for role, count in role_counts.items() if "defense" in role)
    payoff_count = sum(count for role, count in role_counts.items() if "payoff" in role or "seed" in role)

    if starter_count < 8:
        deck_warnings.append(f"starter枠が少なめです: {starter_count}枚")
    if defense_count < 6:
        deck_warnings.append(f"defense枠が少なめです: {defense_count}枚")
    if payoff_count < 6:
        deck_warnings.append(f"勝ち手段/payoffが少なめです: {payoff_count}枚")

    # Tag overuse warnings, but don't make them fatal.
    for tag in ["初動", "受け札", "マナ加速", "フィニッシャー", "除去"]:
        if tag_counter.get(tag, 0) >= 28:
            deck_warnings.append(f"{tag}タグが多すぎます。タグ過剰の可能性: {tag_counter[tag]}枚相当")

    return {
        "average_cost": average_cost,
        "multicolor_count": multicolor_count,
        "off_civilization_count": off_civ_count,
        "high_cost_count": high_cost_count,
        "role_counts": dict(role_counts),
        "top_tags": dict(tag_counter.most_common(20)),
        "deck_quality_warnings": deck_warnings,
        "suspicious_inclusions": suspicious[:20],
    }


def _deck_count(deck_items: list[tuple[CardRow, int, str]]) -> int:
    return sum(int(copies) for _, copies, _ in deck_items)


def _needs_auto_replace(card: CardRow, copies: int, role: str) -> bool:
    base_role = _role_base(role)
    if base_role == "removal" and card.cost >= 7:
        return True
    if base_role == "payoff" and card.cost >= 7 and copies > 2:
        return True
    if _is_five_color(card) and copies > 2:
        return True
    if len(card.tag_set) >= 13 and base_role not in {"starter", "defense", "seed"} and copies > 2:
        return True
    return False


def _auto_replace_bad_inclusions(
    deck_items: list[tuple[CardRow, int, str]],
    all_cards: list[CardRow],
    target_civs: set[str],
    seed_name_keys: set[str],
    route_type: str = "lock_confirmed_win",
) -> tuple[list[tuple[CardRow, int, str]], list[str]]:
    """Try to reduce obviously bad auto-picked cards.

    This pass is conservative:
    - Never removes seed cards.
    - Reduces high-cost removal/payoff over-copying.
    - Fills holes with role-compatible lower-risk alternatives.
    """
    notes: list[str] = []
    used_counts: Counter[str] = Counter()
    new_items: list[tuple[CardRow, int, str]] = []

    for card, copies, role in deck_items:
        key = _norm(card.name)
        if "seed" in role:
            new_items.append((card, copies, role))
            used_counts[key] += copies
            continue

        if _needs_auto_replace(card, copies, role):
            base_role = _role_base(role)
            keep = 0
            if base_role == "removal" and card.cost >= 7:
                keep = min(1, copies)
            elif base_role == "payoff" and card.cost >= 7:
                keep = min(2, copies)
            elif _is_five_color(card):
                keep = min(2, copies)
            else:
                keep = min(2, copies)

            cut = copies - keep
            if keep > 0:
                new_items.append((card, keep, role))
                used_counts[key] += keep
            if cut > 0:
                notes.append(f"{card.name} を {copies}→{keep} に減量: {role}枠の品質制約")
        else:
            new_items.append((card, copies, role))
            used_counts[key] += copies

    deficit = 40 - _deck_count(new_items)
    if deficit <= 0:
        return new_items, notes

    role_tags_map = _route_role_tags(route_type)
    # Fill by priority: starter/defense/resource/removal/payoff/flex with low-risk cards.
    fill_roles = ["starter", "defense", "resource", "removal", "payoff", "flex"]
    for role in fill_roles:
        if deficit <= 0:
            break
        role_tags = role_tags_map.get(role, [])
        picked = _pick_cards_for_role(
            all_cards,
            role,
            role_tags,
            target_civs,
            seed_name_keys,
            deficit,
            used_counts,
        )
        for card, copies, picked_role in picked:
            # Reject high-risk fills.
            if _needs_auto_replace(card, copies, picked_role):
                continue
            new_items.append((card, copies, picked_role))
            deficit -= copies
            notes.append(f"{card.name} を {copies}枚補充: {picked_role}")
            if deficit <= 0:
                break

    return new_items, notes


def expand_route_seed_to_deck(
    candidate: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
    target_size: int = 40,
    seed_copies: int = 4,
) -> dict[str, Any]:
    """Expand a route seed into a rough 40-card deck proposal.

    This does not save to DB. It returns a dict with deck rows and evaluation.
    """
    all_cards = _load_cards(db_path)
    seed_names = _extract_seed_names(candidate)
    seed_cards = _find_cards_by_names(seed_names, all_cards)
    route_type = str(candidate.get("route_type") or "lock_confirmed_win")

    if not seed_cards:
        raise ValueError("seed cards were not found in DB")

    target_civs = _civilization_profile(seed_cards)
    seed_name_keys = {_norm(card.name) for card in seed_cards}
    used_counts: Counter[str] = Counter()
    deck_items: list[tuple[CardRow, int, str]] = []

    for card in seed_cards:
        if not _is_main_deck_candidate(card):
            continue
        copies = min(seed_copies, 4, max(1, target_size - sum(c for _, c, _ in deck_items)))
        deck_items.append((card, copies, "seed"))
        used_counts[_norm(card.name)] += copies

    role_plan = dict(DEFAULT_ROLE_PLAN)
    # Seed slots are already consumed. Keep the rest role-balanced.
    current_count = sum(copies for _, copies, _ in deck_items)
    remaining_target = max(0, target_size - current_count)

    role_tags = _route_role_tags(route_type)
    ordered_roles = ["starter", "defense", "resource", "removal", "payoff", "flex"]
    for role in ordered_roles:
        if remaining_target <= 0:
            break
        requested = min(role_plan.get(role, 0), remaining_target)
        picked = _pick_cards_for_role(
            all_cards,
            role,
            role_tags.get(role, []),
            target_civs,
            seed_name_keys,
            requested,
            used_counts,
        )
        deck_items.extend(picked)
        remaining_target = target_size - sum(copies for _, copies, _ in deck_items)

    # Fill remaining slots with broad low-risk cards in civ.
    if remaining_target > 0:
        flex_tags = ["初動", "受け札", "ドロー", "リソース", "除去", "打点", "フィニッシャー"]
        picked = _pick_cards_for_role(
            all_cards,
            "flex_fill",
            flex_tags,
            target_civs,
            seed_name_keys,
            remaining_target,
            used_counts,
        )
        deck_items.extend(picked)

    # Trim if role picking overshot.
    while sum(copies for _, copies, _ in deck_items) > target_size and deck_items:
        card, copies, role = deck_items[-1]
        if copies > 1:
            deck_items[-1] = (card, copies - 1, role)
        else:
            deck_items.pop()

    # Apply quality-aware reduction/replacement before final display merge.
    deck_items, auto_replace_notes = _auto_replace_bad_inclusions(
        deck_items,
        all_cards,
        target_civs,
        seed_name_keys,
        route_type=route_type,
    )

    # Merge duplicate display rows and re-trim if capping duplicate copies changed size.
    deck_items = _merge_deck_items(deck_items)
    while sum(copies for _, copies, _ in deck_items) > target_size and deck_items:
        card, copies, role = deck_items[-1]
        if "seed" in role:
            # Avoid cutting seed unless absolutely necessary.
            deck_items.insert(0, deck_items.pop())
            if all(c <= 1 or "seed" in r for _, c, r in deck_items):
                break
            continue
        if copies > 1:
            deck_items[-1] = (card, copies - 1, role)
        else:
            deck_items.pop()

    deck_rows = [
        {
            "count": copies,
            "card_name": card.name,
            "civilization": card.civilization,
            "cost": card.cost,
            "card_type": card.card_type,
            "tags": _dedupe_tags(card.tags),
            "role": role,
        }
        for card, copies, role in deck_items
    ]

    deck_name = f"expanded {candidate.get('deck_name') or route_type}"
    quality = analyze_expanded_deck_quality(deck_rows, target_civs)

    expansion = {
        "deck_name": deck_name,
        "candidate_origin": "route_seed_expanded",
        "route_type": route_type,
        "route_seed_cards": " / ".join(card.name for card in seed_cards),
        "target_civilizations": "/".join(sorted(target_civs)) if target_civs else "",
        "deck_size": sum(row["count"] for row in deck_rows),
        "average_cost": quality["average_cost"],
        "multicolor_count": quality["multicolor_count"],
        "off_civilization_count": quality["off_civilization_count"],
        "high_cost_count": quality["high_cost_count"],
        "role_counts": quality["role_counts"],
        "top_tags": quality["top_tags"],
        "deck_quality_warnings": quality["deck_quality_warnings"],
        "suspicious_inclusions": quality["suspicious_inclusions"],
        "auto_replace_notes": auto_replace_notes,
        "deck_rows": deck_rows,
        "strategy_note": (
            "route_deck_expander v3 による粗い40枚化。"
            "seed固定、文明寄せ、初動/受け/リソース/除去/payoffを補完し、"
            "同名集約・タグ重複除去・品質診断を実施。実戦前に人間レビュー必須。"
        ),
    }

    # Route evaluation for the seed itself.
    try:
        expansion["route_evaluation"] = evaluate_route_candidate(candidate, db_path)
    except Exception as exc:
        expansion["route_evaluation_error"] = str(exc)

    # Existing evaluate_deck may expect a list of card names or card rows depending on implementation.
    # Keep this non-fatal.
    try:
        flat_names: list[str] = []
        for row in deck_rows:
            flat_names.extend([row["card_name"]] * int(row["count"]))
        expansion["flat_deck_names"] = flat_names
        expansion["deck_evaluation"] = evaluate_deck(flat_names, db_path)
    except Exception as exc:
        expansion["deck_evaluation_error"] = str(exc)

    return expansion


def expand_route_seed_candidates(
    candidates: list[dict[str, Any]],
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 5,
    min_adjusted_score: int = 70,
) -> list[dict[str, Any]]:
    picked = [
        candidate for candidate in candidates
        if int(candidate.get("adjusted_route_score") or 0) >= min_adjusted_score
    ]
    picked.sort(key=lambda c: int(c.get("adjusted_route_score") or 0), reverse=True)

    expanded: list[dict[str, Any]] = []
    for candidate in picked[:limit]:
        try:
            expanded.append(expand_route_seed_to_deck(candidate, db_path=db_path))
        except Exception as exc:
            expanded.append({
                "deck_name": f"expand error: {candidate.get('deck_name', '-')}",
                "error": str(exc),
                "source_candidate": candidate,
            })
    return expanded


def deck_expansion_to_markdown(expansion: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# {expansion.get('deck_name', 'route seed expanded deck')}")
    lines.append("")
    if "error" in expansion:
        lines.append(f"ERROR: {expansion['error']}")
        return "\n".join(lines)

    lines.append(f"- candidate_origin: {expansion.get('candidate_origin', '-')}")
    lines.append(f"- route_type: {expansion.get('route_type', '-')}")
    lines.append(f"- route_seed_cards: {expansion.get('route_seed_cards', '-')}")
    lines.append(f"- target_civilizations: {expansion.get('target_civilizations', '-')}")
    lines.append(f"- deck_size: {expansion.get('deck_size', '-')}")
    lines.append(f"- average_cost: {expansion.get('average_cost', '-')}")
    lines.append(f"- multicolor_count: {expansion.get('multicolor_count', '-')}")
    lines.append(f"- off_civilization_count: {expansion.get('off_civilization_count', '-')}")
    lines.append(f"- high_cost_count: {expansion.get('high_cost_count', '-')}")
    lines.append(f"- strategy_note: {expansion.get('strategy_note', '-')}")
    lines.append("")

    lines.append("## デッキ品質診断")
    lines.append("")
    warnings = expansion.get("deck_quality_warnings") or []
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- 大きな品質警告はありません。")
    lines.append("")

    auto_notes = expansion.get("auto_replace_notes") or []
    if auto_notes:
        lines.append("### 自動修正メモ")
        lines.append("")
        for note in auto_notes:
            lines.append(f"- {note}")
        lines.append("")

    role_counts = expansion.get("role_counts") or {}
    if role_counts:
        lines.append("### role別枚数")
        lines.append("")
        lines.append("| role | 枚数 |")
        lines.append("| --- | --- |")
        for role, count in role_counts.items():
            lines.append(f"| {role} | {count} |")
        lines.append("")

    suspicious = expansion.get("suspicious_inclusions") or []
    if suspicious:
        lines.append("### 怪しい採用")
        lines.append("")
        lines.append("| カード名 | 枚数 | role | コスト | 文明 | 警告 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for row in suspicious:
            lines.append(
                f"| {row.get('card_name', '')} | {row.get('count', '')} | {row.get('role', '')} | "
                f"{row.get('cost', '')} | {row.get('civilization', '')} | {row.get('warnings', '')} |"
            )
        lines.append("")

    route_eval = expansion.get("route_evaluation") or {}
    if route_eval:
        lines.append("## route評価")
        lines.append("")
        for key in [
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
            "route_evaluation_comment",
        ]:
            lines.append(f"- {key}: {route_eval.get(key, '-')}")
        lines.append("")

    lines.append("## デッキ案")
    lines.append("")
    lines.append("| 枚数 | カード名 | 文明 | コスト | 種類 | role | タグ |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for row in expansion.get("deck_rows", []):
        lines.append(
            f"| {row.get('count', '')} | {row.get('card_name', '')} | {row.get('civilization', '')} | "
            f"{row.get('cost', '')} | {row.get('card_type', '')} | {row.get('role', '')} | {row.get('tags', '')} |"
        )

    lines.append("")
    lines.append("## 人間レビュー観点")
    lines.append("")
    lines.append("- seedカード同士が本当に同一デッキ内で接続するか。")
    lines.append("- 文明基盤が無理なく成立するか。")
    lines.append("- 速攻対面に間に合う受け札があるか。")
    lines.append("- 勝ち切り手段がseed以外にもあるか。")
    lines.append("- タグ過剰で選ばれたカードが混ざっていないか。")
    return "\n".join(lines)


def expansions_to_markdown(expansions: list[dict[str, Any]]) -> str:
    chunks = ["# route_seed expanded decks", ""]
    for index, expansion in enumerate(expansions, start=1):
        chunks.append(f"---\n\n")
        chunks.append(deck_expansion_to_markdown(expansion))
        chunks.append("")
    return "\n".join(chunks)


def expansion_to_csv(expansion: dict[str, Any]) -> str:
    rows = expansion.get("deck_rows", [])
    if not rows:
        return ""
    output = StringIO()
    columns = ["count", "card_name", "civilization", "cost", "card_type", "role", "tags"]
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def load_route_seed_candidates_csv(path: str | Path) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(StringIO(text))
    return [dict(row) for row in reader]


def write_expanded_decks_from_candidates_csv(
    candidates_csv: str | Path = "data/reports/route_seed_candidates.csv",
    output_dir: str | Path = "data/reports/expanded_route_decks",
    db_path: str | Path = DEFAULT_DB_PATH,
    limit: int = 5,
    min_adjusted_score: int = 70,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = load_route_seed_candidates_csv(candidates_csv)
    expansions = expand_route_seed_candidates(
        candidates,
        db_path=db_path,
        limit=limit,
        min_adjusted_score=min_adjusted_score,
    )

    md_path = output_dir / "expanded_route_decks.md"
    md_path.write_text(expansions_to_markdown(expansions), encoding="utf-8")

    for index, expansion in enumerate(expansions, start=1):
        csv_path = output_dir / f"expanded_route_deck_{index}.csv"
        csv_path.write_text(expansion_to_csv(expansion), encoding="utf-8-sig")

    summary_path = output_dir / "expanded_route_decks.json"
    summary_path.write_text(json.dumps(expansions, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "markdown": md_path,
        "json": summary_path,
        "output_dir": output_dir,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand Project MANA route seed candidates into rough deck proposals.")
    parser.add_argument("--candidates", default="data/reports/route_seed_candidates.csv", help="route_seed_candidates.csv path")
    parser.add_argument("--out", default="data/reports/expanded_route_decks", help="Output directory")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite DB path")
    parser.add_argument("--limit", type=int, default=5, help="Number of candidates to expand")
    parser.add_argument("--min-score", type=int, default=70, help="Minimum adjusted_route_score")
    args = parser.parse_args()

    paths = write_expanded_decks_from_candidates_csv(
        candidates_csv=args.candidates,
        output_dir=args.out,
        db_path=args.db,
        limit=args.limit,
        min_adjusted_score=args.min_score,
    )
    print(f"markdown: {paths['markdown']}")
    print(f"json: {paths['json']}")
    print(f"output_dir: {paths['output_dir']}")


if __name__ == "__main__":
    main()

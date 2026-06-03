from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.current_meta_deck_regenerator import (
    Card,
    DeckCard,
    is_defense_card,
    is_external_or_zero,
    is_lock_card,
    is_low_attack_card,
    is_resource_card,
    load_cards,
    split_civs,
)
from src.current_meta_matchup_simulator import DeckCard as MatchupDeckCard
from src.final_deck_auditor import (
    FinalDeck,
    audit_final_deck,
    estimate_matchups,
    final_primary_role,
    final_secondary_roles,
)


DEFAULT_DB = Path("data/cards.db")
DEFAULT_NIGHT_RESULTS = Path("data/reports/night_research/night_research_results.json")
DEFAULT_FINAL_REPORT = Path("data/reports/final_deck/final_deck_report.json")
DEFAULT_OUT = Path("data/reports/rank1_safety_refine")
QQQX_NAME = "Q.Q.QX./終葬 5.S.D."
ARCHETYPE_GOALS = {
    "火自然アグロロック": {
        "required_civilizations": ["火", "自然"],
        "optional_civilizations": [],
        "min_effective_supply": {"火": 16, "自然": 16},
        "min_attack": 28,
        "min_low_attack": 28,
        "min_defense": 10,
        "min_resource": 10,
        "max_avg_cost": 3.2,
        "max_high_cost": 0,
        "require_qqqx": False,
        "description": "2〜4ターン目の展開、火/自然供給、6ターン目までの詰めを重視。光とQ.Q.QX.は必須評価から外します。",
    },
    "光入りQ.Q.QX.ロック": {
        "required_civilizations": ["自然", "光"],
        "optional_civilizations": ["火"],
        "min_effective_supply": {"光": 8, "自然": 12},
        "min_attack": 20,
        "min_low_attack": 16,
        "min_defense": 8,
        "min_resource": 10,
        "max_avg_cost": 4.2,
        "max_high_cost": 2,
        "require_qqqx": True,
        "description": "Q.Q.QX.または光ロック札を評価対象に含めます。",
    },
    "受け寄せコントロール": {
        "required_civilizations": [],
        "optional_civilizations": ["光", "水", "闇", "火", "自然"],
        "min_effective_supply": {},
        "min_attack": 12,
        "min_low_attack": 6,
        "min_defense": 16,
        "min_resource": 12,
        "max_avg_cost": 4.8,
        "max_high_cost": 8,
        "require_qqqx": False,
        "description": "受け札とリソースを重視する長期戦型です。",
    },
    "リソース型中速": {
        "required_civilizations": [],
        "optional_civilizations": ["光", "水", "闇", "火", "自然"],
        "min_effective_supply": {},
        "min_attack": 18,
        "min_low_attack": 10,
        "min_defense": 8,
        "min_resource": 14,
        "max_avg_cost": 4.4,
        "max_high_cost": 6,
        "require_qqqx": False,
        "description": "中盤以降の手札・マナ・盤面リソースを重視します。",
    },
}
PREFERRED_SAFE_REPLACEMENTS = [
    "こたつむり",
    "ハノコハノ",
    "轟車 “G-突”",
    "エグゼズ・ワイバーン",
    "大集結！ドングリ軍団",
    "マファリッヒ・タンク",
    "奇襲隊長ダブルレイザー",
    "トツゲキ戦車 バクゲットー",
]


@dataclass
class RefinedDeck:
    title: str
    deck: list[DeckCard]
    audit: dict[str, Any]
    changes: list[str]
    notes: list[str]
    archetype: str = "火自然アグロロック"


def load_catalog(db_path: Path) -> dict[str, Card]:
    return {card.name: card for card in load_cards(db_path)}


def load_rank1_deck(db_path: Path, results_path: Path = DEFAULT_NIGHT_RESULTS) -> tuple[str, list[DeckCard], dict[str, Any]]:
    catalog = load_catalog(db_path)
    data = json.loads(results_path.read_text(encoding="utf-8"))
    rank1 = data["top_candidates"][0]
    deck = []
    for row in rank1.get("deck", []):
        card = catalog.get(row["name"])
        if card:
            deck.append(DeckCard(int(row["count"]), card, "night-rank1"))
    return rank1.get("deck_name", "night rank1"), merge_deck(deck), rank1


def merge_deck(deck: list[DeckCard]) -> list[DeckCard]:
    merged: dict[str, DeckCard] = {}
    for entry in deck:
        if entry.card.name not in merged:
            merged[entry.card.name] = DeckCard(0, entry.card, entry.reason)
        merged[entry.card.name].count += entry.count
    return [entry for entry in merged.values() if entry.count > 0]


def run_refine(db_path: str | Path = DEFAULT_DB, out_dir: str | Path = DEFAULT_OUT) -> dict[str, Any]:
    db_path = Path(db_path)
    out_dir = Path(out_dir)
    rank_name, rank_deck, rank_payload = load_rank1_deck(db_path)
    original = build_original(rank_name, rank_deck, db_path)
    safe = build_safe_version(rank_deck, db_path)
    final_a = load_final_a_summary()
    payload = {
        "rank1_name": rank_name,
        "rank1_payload": rank_payload,
        "original": serialize_refined(original),
        "safe": serialize_refined(safe),
        "comparison": build_comparison(original, safe, final_a),
        "final_a": final_a,
        "test_plan": build_test_plan(),
    }
    write_outputs(payload, out_dir)
    return payload


def build_original(name: str, deck: list[DeckCard], db_path: Path) -> RefinedDeck:
    audit = audit_final_deck(FinalDeck("夜間研究Rank1そのまま版", "A", deck, "夜間研究Rank1をそのまま再監査"), db_path)
    notes = []
    notes.extend(minority_civ_notes(deck, audit))
    notes.extend(overtag_notes(deck))
    qqqx = qqqx_review(deck)
    if qqqx:
        notes.append(qqqx["summary"])
    return RefinedDeck("夜間研究Rank1そのまま版", deck, audit, [], notes, "火自然アグロロック")


def build_safe_version(rank_deck: list[DeckCard], db_path: Path) -> RefinedDeck:
    catalog = load_catalog(db_path)
    deck = [DeckCard(entry.count, entry.card, entry.reason) for entry in rank_deck]
    changes: list[str] = []
    notes: list[str] = []

    initial_audit = audit_final_deck(FinalDeck("tmp", "tmp", deck, "安全補正前の一時監査"), db_path)
    risky_civs = {
        risk["civilization"]
        for risk in minority_civ_risks(deck, initial_audit)
        if risk["civilization"] != "火" and risk["civilization"] != "自然" and risk["supply"] < 8
    }
    if "光" in risky_civs:
        removed = remove_cards(deck, lambda c: "光" in split_civs(c.civilization))
        if removed:
            changes.append("光有効供給8未満のため、光タッチカードを火/自然札へ差し替えました: " + " / ".join(removed))

    if any(entry.card.name == QQQX_NAME for entry in deck):
        removed = remove_cards(deck, lambda c: c.name == QQQX_NAME)
        changes.append(f"{QQQX_NAME} は高速火自然アグロロックの即時圧力と噛み合いが薄いため差し替えました。")

    removed_thin = remove_cards(deck, is_thin_attack_or_overtagged)
    if removed_thin:
        changes.append("攻撃札/複合役割として根拠が薄いカードを差し替えました: " + " / ".join(removed_thin))

    replacement_pool = build_replacement_pool(catalog)
    fill_deck(deck, replacement_pool, changes)
    deck = normalize_to_40(deck, replacement_pool, changes)
    audit = audit_final_deck(FinalDeck("夜間研究Rank1安全補正版", "B", deck, "少数文明と方針不一致カードを安全補正"), db_path)

    # If safety constraints still miss resource/defense, tune by replacing surplus attack.
    for _ in range(10):
        if safe_constraints_ok(audit):
            break
        tune_safe_deck(deck, replacement_pool, audit, changes)
        audit = audit_final_deck(FinalDeck("夜間研究Rank1安全補正版", "B", deck, "少数文明と方針不一致カードを安全補正"), db_path)

    for _ in range(6):
        secondary = audit.get("secondary_counts", {})
        if secondary.get("lock", 0) >= 8 and denjadeon_rate(audit.get("matchups", [])) >= 0.50:
            break
        if not add_lock_without_losing_safety(deck, replacement_pool, changes):
            break
        audit = audit_final_deck(FinalDeck("夜間研究Rank1安全補正版", "B", deck, "少数文明と方針不一致カードを安全補正"), db_path)

    overtagged_names = {row["name"] for row in audit.get("base_audit", {}).get("overtagged_cards", [])}
    if overtagged_names:
        removed = remove_cards(deck, lambda c: c.name in overtagged_names)
        changes.append("タグ過大評価警告を消すため差し替えました: " + " / ".join(removed))
        fill_deck(deck, [c for c in replacement_pool if c.name not in overtagged_names], changes)
        deck = normalize_to_40(deck, [c for c in replacement_pool if c.name not in overtagged_names], changes)
        audit = audit_final_deck(FinalDeck("夜間研究Rank1安全補正版", "B", deck, "少数文明と方針不一致カードを安全補正"), db_path)

    for _ in range(8):
        if safe_constraints_ok(audit):
            break
        tune_safe_deck(deck, replacement_pool, audit, changes)
        audit = audit_final_deck(FinalDeck("夜間研究Rank1安全補正版", "B", deck, "少数文明と方針不一致カードを安全補正"), db_path)

    notes.extend(minority_civ_notes(deck, audit))
    notes.extend(overtag_notes(deck))
    if not notes:
        notes.append("水要求なし、光タッチなし、DB未存在なし、タグ過大評価警告なしの安全寄せ候補です。")
    return RefinedDeck("夜間研究Rank1安全補正版", deck, audit, changes, notes, "火自然アグロロック")


def remove_cards(deck: list[DeckCard], predicate) -> list[str]:
    removed = []
    keep = []
    for entry in deck:
        if predicate(entry.card):
            removed.append(f"{entry.count} {entry.card.name}")
        else:
            keep.append(entry)
    deck[:] = keep
    return removed


def is_thin_attack_or_overtagged(card: Card) -> bool:
    if card.name in {"コモロキシ", "緑知銀 イーアル"}:
        return True
    text = card.text or ""
    if "攻撃できない" in text or "相手プレイヤーを攻撃できない" in text:
        return True
    roles = final_secondary_roles(card)
    return False


def build_replacement_pool(catalog: dict[str, Card]) -> list[Card]:
    pool = []
    for card in catalog.values():
        if is_external_or_zero(card):
            continue
        civs = split_civs(card.civilization)
        if "水" in civs or "光" in civs or "闇" in civs:
            continue
        if card.cost > 4:
            continue
        if card.name in {"コモロキシ", "緑知銀 イーアル", QQQX_NAME}:
            continue
        if is_thin_attack_or_overtagged(card) and "lock" not in final_secondary_roles(card):
            continue
        if likely_practical_overtagged(card):
            continue
        if final_primary_role(card) in {"attack", "lock", "defense", "resource"} or is_low_attack_card(card):
            pool.append(card)
    preferred_index = {name: index for index, name in enumerate(PREFERRED_SAFE_REPLACEMENTS)}
    pool.sort(key=lambda c: (1000 - preferred_index[c.name] if c.name in preferred_index else replacement_score(c)), reverse=True)
    return pool


def replacement_score(card: Card) -> float:
    score = 0.0
    if is_low_attack_card(card) or final_primary_role(card) == "attack":
        score += 8
    if is_lock_card(card) or final_primary_role(card) == "lock":
        score += 5
    if is_defense_card(card):
        score += 3
    if is_resource_card(card):
        score += 3
    if "自然" in split_civs(card.civilization):
        score += 1.5
    if "火" in split_civs(card.civilization):
        score += 1.5
    score += max(0, 5 - card.cost)
    if "攻撃できない" in (card.text or ""):
        score -= 20
    return score


def likely_practical_overtagged(card: Card) -> bool:
    roles = 0
    roles += 1 if is_low_attack_card(card) else 0
    roles += 1 if is_defense_card(card) else 0
    roles += 1 if is_resource_card(card) else 0
    roles += 1 if is_lock_card(card) else 0
    roles += 1 if "除去" in card.tags or "破壊" in card.tags or "バウンス" in card.tags else 0
    return roles >= 4


def fill_deck(deck: list[DeckCard], pool: list[Card], changes: list[str]) -> None:
    while total_count(deck) < 40:
        need = 40 - total_count(deck)
        counts = Counter()
        secondary = Counter()
        low_attack = 0
        for entry in deck:
            role = final_primary_role(entry.card)
            counts[role] += entry.count
            if role == "attack" and 2 <= entry.card.cost <= 4:
                low_attack += entry.count
            for role2 in final_secondary_roles(entry.card):
                secondary[role2] += entry.count
        if counts["attack"] < 28 or low_attack < 28:
            predicate = lambda c: (final_primary_role(c) == "attack" or is_low_attack_card(c)) and 2 <= c.cost <= 4
        elif secondary["defense"] < 10:
            predicate = lambda c: is_defense_card(c)
        elif secondary["resource"] < 10:
            predicate = lambda c: is_resource_card(c)
        else:
            predicate = lambda c: True
        card = next((c for c in pool if count_of(deck, c.name) < 4 and predicate(c)), None)
        if card is None:
            card = next((c for c in pool if count_of(deck, c.name) < 4), None)
        if not card:
            break
        add_count = min(4 - count_of(deck, card.name), need)
        add_card(deck, card, add_count, "rank1-safe-fill")
        changes.append(f"{add_count} {card.name} を安全補正枠として追加")


def normalize_to_40(deck: list[DeckCard], pool: list[Card], changes: list[str]) -> list[DeckCard]:
    deck = merge_deck(deck)
    while total_count(deck) > 40:
        target = sorted(deck, key=lambda e: removal_priority(e.card), reverse=True)[0]
        target.count -= 1
        changes.append(f"枚数調整で 1 {target.card.name} を削減")
        if target.count <= 0:
            deck.remove(target)
    fill_deck(deck, pool, changes)
    return merge_deck(deck)


def removal_priority(card: Card) -> float:
    score = card.cost
    if final_primary_role(card) not in {"attack", "lock", "defense", "resource"}:
        score += 5
    if "光" in split_civs(card.civilization) or "水" in split_civs(card.civilization):
        score += 8
    if card.name == QQQX_NAME:
        score += 10
    return score


def tune_safe_deck(deck: list[DeckCard], pool: list[Card], audit: dict[str, Any], changes: list[str]) -> None:
    secondary = audit.get("secondary_counts", {})
    desired = "defense" if secondary.get("defense", 0) < 10 else "resource" if secondary.get("resource", 0) < 10 else "attack"
    replacement = next(
        (
            c
            for c in pool
            if count_of(deck, c.name) < 4
            and (
                (desired == "defense" and is_defense_card(c))
                or (desired == "resource" and is_resource_card(c))
                or (desired == "attack" and final_primary_role(c) == "attack")
            )
        ),
        None,
    )
    if not replacement:
        return
    removable = sorted(
        [e for e in deck if e.count > 0 and final_primary_role(e.card) == "attack" and e.card.name != replacement.name],
        key=lambda e: (e.card.cost, e.count),
        reverse=True,
    )
    if not removable:
        return
    removable[0].count -= 1
    if removable[0].count <= 0:
        deck.remove(removable[0])
    add_card(deck, replacement, 1, f"rank1-safe-{desired}")
    changes.append(f"{desired}補正で 1 {replacement.name} を追加")


def add_lock_without_losing_safety(deck: list[DeckCard], pool: list[Card], changes: list[str]) -> bool:
    replacement = next(
        (
            c
            for c in pool
            if count_of(deck, c.name) < 4
            and "lock" in final_secondary_roles(c)
            and (is_defense_card(c) or final_primary_role(c) == "lock")
        ),
        None,
    )
    if not replacement:
        return False
    removable = sorted(
        [
            e
            for e in deck
            if e.count > 0
            and "lock" not in final_secondary_roles(e.card)
            and final_primary_role(e.card) in {"defense", "attack"}
            and not (final_primary_role(e.card) == "attack" and count_primary_attack(deck) <= 28)
        ],
        key=lambda e: (final_primary_role(e.card) != "defense", e.card.cost, e.count),
        reverse=True,
    )
    if not removable:
        return False
    target = removable[0]
    target.count -= 1
    if target.count <= 0:
        deck.remove(target)
    add_card(deck, replacement, 1, "rank1-safe-lock補正")
    changes.append(f"自然単デンジャデオン対面のロック密度補正で 1 {replacement.name} を追加")
    return True


def count_primary_attack(deck: list[DeckCard]) -> int:
    return sum(entry.count for entry in deck if final_primary_role(entry.card) == "attack")


def add_card(deck: list[DeckCard], card: Card, count: int, reason: str) -> None:
    for entry in deck:
        if entry.card.name == card.name:
            entry.count = min(4, entry.count + count)
            return
    deck.append(DeckCard(count, card, reason))


def count_of(deck: list[DeckCard], name: str) -> int:
    return sum(entry.count for entry in deck if entry.card.name == name)


def total_count(deck: list[DeckCard]) -> int:
    return sum(entry.count for entry in deck)


def safe_constraints_ok(audit: dict[str, Any], archetype: str = "火自然アグロロック") -> bool:
    return not safety_warnings(audit, archetype)


def safety_warnings(audit: dict[str, Any], archetype: str = "火自然アグロロック") -> list[str]:
    goals = ARCHETYPE_GOALS.get(archetype, ARCHETYPE_GOALS["火自然アグロロック"])
    base = audit.get("base_audit", {})
    stats = base.get("stats", {})
    primary = base.get("primary_counts", {})
    secondary = base.get("secondary_counts", {})
    supply = base.get("effective_supply", audit.get("effective_supply", {}))
    low_attack = base.get("low_primary_attack_count", audit.get("low_primary_attack_count", 0))
    warnings = []
    if stats.get("deck_size", audit.get("deck_size")) != 40:
        warnings.append("40枚ではありません。")
    if stats.get("avg_cost", audit.get("avg_cost", 99)) > goals["max_avg_cost"]:
        warnings.append(f"平均コストが{goals['max_avg_cost']}を超えています: {stats.get('avg_cost', audit.get('avg_cost'))}")
    if stats.get("high_cost", audit.get("high_cost_count", 0)) > goals["max_high_cost"]:
        warnings.append(f"7コスト以上が多いです: {stats.get('high_cost', audit.get('high_cost_count'))}")
    if primary.get("attack", 0) < goals["min_attack"]:
        warnings.append(f"primary attack不足: {primary.get('attack', 0)}")
    low_attack = base.get("low_primary_attack_count", audit.get("low_primary_attack_count", 0))
    if low_attack < goals["min_low_attack"]:
        warnings.append(f"2〜4 cost primary attack不足: {low_attack}")
    if secondary.get("defense", 0) < goals["min_defense"]:
        warnings.append(f"defense不足: {secondary.get('defense', 0)}")
    if secondary.get("resource", 0) < goals["min_resource"]:
        warnings.append(f"resource不足: {secondary.get('resource', 0)}")
    for civ, minimum in goals["min_effective_supply"].items():
        if supply.get(civ, 0) < minimum:
            warnings.append(f"{civ}有効供給不足: {supply.get(civ, 0)} / 目標 {minimum}")
    used_civs = {civ for civ, value in supply.items() if float(value or 0) > 0}
    allowed_civs = set(goals["required_civilizations"]) | set(goals["optional_civilizations"])
    if goals["required_civilizations"] and any(civ not in allowed_civs for civ in used_civs):
        warnings.append("想定外文明があります: " + " / ".join(sorted(civ for civ in used_civs if civ not in allowed_civs)))
    if goals.get("require_qqqx") and not audit_has_card(audit, QQQX_NAME):
        warnings.append(f"{archetype}では {QQQX_NAME} を評価対象に含めます。")
    if base.get("overtagged_cards"):
        warnings.append("タグ過大評価警告があります: " + " / ".join(row["name"] for row in base.get("overtagged_cards", [])))
    return warnings


def overtag_notes_from_audit(audit: dict[str, Any]) -> list[str]:
    # final audit itself does not store overtagged cards, so the safety warning is
    # generated from explicit deck notes in this module. Kept as a hook.
    return []


def audit_has_card(audit: dict[str, Any], card_name: str) -> bool:
    return any(row.get("name") == card_name for row in audit.get("card_checks", []))


def minority_civ_risks(deck: list[DeckCard], audit: dict[str, Any]) -> list[dict[str, Any]]:
    supply = audit.get("effective_supply", {})
    demand = Counter()
    cards = {civ: [] for civ in ["光", "水", "闇", "火", "自然"]}
    for entry in deck:
        for civ in split_civs(entry.card.civilization):
            demand[civ] += entry.count
            cards[civ].append(
                {
                    "name": entry.card.name,
                    "count": entry.count,
                    "role": final_primary_role(entry.card),
                    "cost": entry.card.cost,
                }
            )
    risks = []
    for civ, count in demand.items():
        effective = float(supply.get(civ, 0) or 0)
        if (1 <= count <= 3 and effective < 4) or (count >= 4 and effective < 8) or (count >= 8 and effective < 10):
            risks.append({"civilization": civ, "demand": count, "supply": effective, "cards": cards[civ]})
    return risks


def minority_civ_notes(deck: list[DeckCard], audit: dict[str, Any]) -> list[str]:
    notes = []
    for risk in minority_civ_risks(deck, audit):
        cards = " / ".join(f"{c['count']} {c['name']}({c['role']})" for c in risk["cards"])
        notes.append(
            f"{risk['civilization']}文明リスク: 要求{risk['demand']}枚 / 有効供給{risk['supply']}枚。対象: {cards}"
        )
    return notes


def overtag_notes(deck: list[DeckCard]) -> list[str]:
    notes = []
    for entry in deck:
        roles = final_secondary_roles(entry.card)
        if len(roles) >= 4 or is_thin_attack_or_overtagged(entry.card):
            notes.append(
                f"タグ過大評価候補: {entry.card.name} / primary={final_primary_role(entry.card)} / secondary={', '.join(sorted(roles)) or '-'}"
            )
    return notes


def qqqx_review(deck: list[DeckCard]) -> dict[str, Any] | None:
    entry = next((d for d in deck if d.card.name == QQQX_NAME), None)
    if not entry:
        return None
    roles = sorted(final_secondary_roles(entry.card))
    return {
        "name": entry.card.name,
        "count": entry.count,
        "primary_role": final_primary_role(entry.card),
        "secondary_roles": roles,
        "summary": (
            f"{QQQX_NAME}: primary={final_primary_role(entry.card)} / secondary={', '.join(roles) or '-'}。"
            "ロック/特殊勝利寄りのカードですが、火自然低カーブで5〜6ターン目に盾を詰める方針では即時打点として不安があります。"
        ),
        "fit": "安全補正版では、方針不一致候補として火/自然の低コスト圧力札へ差し替えます。",
    }


def load_final_a_summary() -> dict[str, Any]:
    if not DEFAULT_FINAL_REPORT.exists():
        return {}
    try:
        data = json.loads(DEFAULT_FINAL_REPORT.read_text(encoding="utf-8"))
        return data.get("recommended", data.get("decks", [{}])[0] if data.get("decks") else {})
    except Exception:
        return {}


def build_comparison(original: RefinedDeck, safe: RefinedDeck, final_a: dict[str, Any]) -> dict[str, Any]:
    def row(deck: RefinedDeck) -> dict[str, Any]:
        audit = deck.audit
        base = audit.get("base_audit", {})
        stats = base.get("stats", {})
        return {
            "title": deck.title,
            "avg_cost": stats.get("avg_cost", audit.get("avg_cost")),
            "primary_attack": base.get("primary_counts", {}).get("attack", audit.get("primary_counts", {}).get("attack", 0)),
            "low_primary_attack": base.get("low_primary_attack_count", audit.get("low_primary_attack_count", 0)),
            "defense": base.get("secondary_counts", {}).get("defense", audit.get("secondary_counts", {}).get("defense", 0)),
            "resource": base.get("secondary_counts", {}).get("resource", audit.get("secondary_counts", {}).get("resource", 0)),
            "lock": base.get("secondary_counts", {}).get("lock", audit.get("secondary_counts", {}).get("lock", 0)),
            "effective_supply": base.get("effective_supply", audit.get("effective_supply", {})),
            "denjadeon_rate": denjadeon_rate(audit.get("matchups", [])),
            "warnings": safety_warnings(audit, deck.archetype),
        }

    return {
        "original": row(original),
        "safe": row(safe),
        "final_a_note": "MANA推奨 実戦版Aは既存の最終候補として比較対象です。詳細は final_deck_report.json を参照してください。" if final_a else "MANA推奨 実戦版AのJSONを取得できませんでした。",
    }


def denjadeon_rate(matchups: list[dict[str, Any]]) -> float:
    row = next((m for m in matchups if "デンジャデオン" in str(m.get("opponent", ""))), None)
    return float(row.get("estimated_win_rate", 0)) if row else 0.0


def serialize_refined(deck: RefinedDeck) -> dict[str, Any]:
    return {
        "title": deck.title,
        "deck": [
            {
                "count": entry.count,
                "name": entry.card.name,
                "civilization": entry.card.civilization,
                "cost": entry.card.cost,
                "card_type": entry.card.card_type,
                "primary_role": final_primary_role(entry.card),
                "secondary_roles": sorted(final_secondary_roles(entry.card)),
            }
            for entry in deck.deck
        ],
        "audit": deck.audit,
        "changes": deck.changes,
        "notes": deck.notes,
        "archetype": deck.archetype,
        "archetype_goals": ARCHETYPE_GOALS.get(deck.archetype, {}),
        "qqqx_review": qqqx_review(deck.deck),
        "constraints_ok": safe_constraints_ok(deck.audit, deck.archetype),
        "safety_warnings": safety_warnings(deck.audit, deck.archetype),
    }


def build_test_plan() -> list[dict[str, str]]:
    opponents = ["自然単デンジャデオン", "自然単デンジャデオン", "自然単デンジャデオン", "火光レイド", "火水レイド"]
    return [
        {
            "match": str(index),
            "opponent": opponent,
            "record": "勝敗 / 先攻後攻 / 決着ターン / 4ターン目までに2体以上 / 6ターン目までに詰め切り / 光カード腐り / Q.Q.QX.適性 / 色事故 / 腐ったカード / 強かったカード",
        }
        for index, opponent in enumerate(opponents, start=1)
    ]


def write_outputs(payload: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rank1_safety_refine_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "rank1_safety_refine_report.md").write_text(to_markdown(payload), encoding="utf-8")


def to_markdown(payload: dict[str, Any]) -> str:
    lines = ["# Rank 1安全補正レポート", ""]
    lines.extend(deck_section("元Rank 1", payload["original"]))
    lines.extend(deck_section("安全補正版", payload["safe"]))
    lines.extend(["", "## 比較"])
    for key, row in payload["comparison"].items():
        if key == "final_a_note":
            lines.append(f"- MANA推奨 実戦版A: {row}")
            continue
        lines.append(
            f"- {row['title']}: avg_cost {row['avg_cost']} / primary attack {row['primary_attack']} / "
            f"2〜4攻撃 {row['low_primary_attack']} / defense {row['defense']} / resource {row['resource']} / "
            f"lock {row['lock']} / デンジャデオン {row['denjadeon_rate']:.1%} / warnings {len(row['warnings'])}"
        )
    lines.extend(["", "## 5戦テスト計画"])
    for row in payload["test_plan"]:
        lines.append(f"{row['match']}. {row['opponent']}: {row['record']}")
    lines.extend(
        [
            "",
            "## MANA上の評価",
            "安全補正版はスコア最大化ではなく、少数文明リスクとタグ過大評価を削り、火自然アグロロックとして試しやすい形に寄せた候補です。",
            "",
            "## 実戦上の未確認点",
            "代理評価は完全な実ルールシミュレーションではありません。特に、盾・初手・相手の除去タイミング・Q.Q.QX.の実効性は実戦ログで確認が必要です。",
            "",
            "## 人間が確認すべき点",
            "安全補正版で、4ターン目までに2体以上並ぶか、6ターン目までに詰め切れるか、抜いた光カード/Q.Q.QX.が本当に不要だったかを確認してください。",
        ]
    )
    return "\n".join(lines)


def deck_section(title: str, data: dict[str, Any]) -> list[str]:
    audit = data["audit"]
    base = audit.get("base_audit", {})
    stats = base.get("stats", {})
    primary = base.get("primary_counts", audit.get("primary_counts", {}))
    secondary = base.get("secondary_counts", audit.get("secondary_counts", {}))
    supply = base.get("effective_supply", audit.get("effective_supply", {}))
    avg_cost = stats.get("avg_cost", audit.get("avg_cost"))
    high_cost = stats.get("high_cost", audit.get("high_cost_count"))
    deck_size = stats.get("deck_size", audit.get("deck_size"))
    low_attack = base.get("low_primary_attack_count", audit.get("low_primary_attack_count", 0))
    lines = [
        "",
        f"## {title}",
        f"- deck_size: {deck_size}",
        f"- avg_cost: {avg_cost}",
        f"- high_cost: {high_cost}",
        f"- primary attack: {primary.get('attack', 0)}",
        f"- 2〜4 cost primary attack: {low_attack}",
        f"- defense: {secondary.get('defense', 0)}",
        f"- resource: {secondary.get('resource', 0)}",
        f"- lock: {secondary.get('lock', 0)}",
        f"- 色供給: {format_supply(supply)}",
        f"- 評価型: {data.get('archetype', '-')}",
        f"- constraints_ok: {data.get('constraints_ok')}",
        f"- safety_warnings: {', '.join(data.get('safety_warnings', [])) if data.get('safety_warnings') else 'なし'}",
        "- 注記: constraints_ok は評価型別の safety_warnings を基準にします。火自然アグロロックでは光文明とQ.Q.QX.を必須評価にしません。",
        "",
        "### 40枚リスト",
    ]
    for card in data["deck"]:
        lines.append(f"- {card['count']} {card['name']} [{card['civilization']} / {card['cost']}] primary={card['primary_role']}")
    lines.extend(["", "### 少数文明リスク・タグ過大評価リスク"])
    if data.get("notes"):
        lines.extend(f"- {note}" for note in data["notes"])
    else:
        lines.append("- なし")
    lines.extend(["", "### Q.Q.QX./終葬 5.S.D. 評価"])
    if data.get("qqqx_review"):
        q = data["qqqx_review"]
        lines.extend(
            [
                f"- primary_role: {q['primary_role']}",
                f"- secondary_roles: {', '.join(q['secondary_roles']) or '-'}",
                f"- 評価: {q['summary']}",
                f"- 方針: {q['fit']}",
            ]
        )
    else:
        lines.append("- この版には採用されていません。高速火自然アグロロックでは、採用する場合も即時圧力・腐りにくさを実戦で確認する必要があります。")
    lines.extend(["", "### 現在メタ5デッキ推定勝率"])
    for matchup in audit.get("matchups", []):
        lines.append(f"- {matchup.get('opponent')}: {float(matchup.get('estimated_win_rate', 0)):.1%} ({matchup.get('note', '-')})")
    if data.get("changes"):
        lines.extend(["", "### 差し替え内容"])
        lines.extend(f"- {change}" for change in data["changes"])
    return lines


def format_supply(supply: dict[str, Any]) -> str:
    return " / ".join(f"{key}{value}" for key, value in supply.items() if float(value or 0) > 0) or "-"


def main() -> None:
    parser = argparse.ArgumentParser(description="Refine latest night research rank 1 into a safer practical candidate.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    payload = run_refine(args.db, args.out)
    safe = payload["safe"]
    print(
        json.dumps(
            {
                "original": payload["original"]["title"],
                "safe": safe["title"],
                "safe_deck_size": safe["audit"]["deck_size"],
                "safe_avg_cost": safe["audit"]["avg_cost"],
                "safe_constraints_ok": safe["constraints_ok"],
                "report": str(Path(args.out) / "rank1_safety_refine_report.md"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

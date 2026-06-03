from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.current_meta_deck_regenerator import (
    CIVS,
    Card,
    DeckCard,
    deck_stats,
    is_attack_card,
    is_defense_card,
    is_defense_only,
    is_evolution,
    is_external_or_zero,
    is_lock_card,
    is_low_attack_card,
    is_removal_card,
    is_resource_card,
    load_cards,
    split_civs,
)
from src.current_meta_matchup_simulator import (
    DeckCard as MatchupDeckCard,
    estimate_matchup,
    load_card_info,
    load_current_meta_decks,
)


DEFAULT_DB = Path("data/cards.db")
DEFAULT_REGEN_JSON = Path("data/reports/current_meta_regeneration/current_meta_regenerated_decks.json")
DEFAULT_OUT = Path("data/reports/current_meta_practical_audit")
TARGET_PROFILE = "anti_denjadeon_fast_finish"
MAIN_CIVS = {"火", "光", "自然"}


@dataclass
class CandidateDeck:
    name: str
    profile: str
    deck: list[DeckCard]
    source_stats: dict[str, Any]


def load_regenerated_candidate(
    db_path: Path,
    regen_json_path: Path = DEFAULT_REGEN_JSON,
    profile: str = TARGET_PROFILE,
) -> CandidateDeck:
    cards_by_name = {card.name: card for card in load_cards(db_path)}
    data = json.loads(regen_json_path.read_text(encoding="utf-8"))
    row = next((item for item in data if item.get("profile") == profile), None)
    if row is None:
        raise RuntimeError(f"{profile} が {regen_json_path} に見つかりません。")

    deck = []
    for card_row in row.get("cards", []):
        card = cards_by_name.get(str(card_row.get("name", "")))
        if not card:
            continue
        deck.append(DeckCard(int(card_row.get("count") or 0), card, str(card_row.get("reason", ""))))
    return CandidateDeck(
        name=str(row.get("title") or profile),
        profile=profile,
        deck=deck,
        source_stats=row.get("stats", {}),
    )


def primary_role(card: Card) -> str:
    if is_defense_only(card):
        return "defense"
    if is_low_attack_card(card):
        return "attack"
    if is_attack_card(card):
        if card.cost >= 5 or card.tags & {"フィニッシャー", "フィニッシャー候補"}:
            return "finisher"
        return "attack"
    if is_lock_card(card):
        return "lock"
    if is_removal_card(card):
        return "removal"
    if is_resource_card(card):
        return "resource"
    if is_defense_card(card):
        return "defense"
    return "utility"


def secondary_roles(card: Card) -> set[str]:
    roles = set()
    if is_attack_card(card):
        roles.add("attack")
    if is_defense_card(card):
        roles.add("defense")
    if is_resource_card(card):
        roles.add("resource")
    if is_removal_card(card):
        roles.add("removal")
    if is_lock_card(card):
        roles.add("lock")
    if card.tags & {"フィニッシャー", "フィニッシャー候補"}:
        roles.add("finisher")
    return roles


def audit_deck(deck: list[DeckCard], db_path: Path) -> dict[str, Any]:
    stats = deck_stats(deck)
    primary_counts = Counter()
    secondary_counts = Counter()
    secondary_role_summary = Counter()
    overtagged_cards = []
    civ_supply = {civ: 0 for civ in CIVS}
    effective_supply = {civ: 0.0 for civ in CIVS}
    civ_demand = {civ: 0 for civ in CIVS}
    multicolor_cards = []
    denjadeon_cards = []
    warnings = []

    for entry in deck:
        card = entry.card
        role = primary_role(card)
        primary_counts[role] += entry.count
        roles = secondary_roles(card)
        for secondary in roles:
            secondary_counts[secondary] += entry.count
        secondary_role_summary[len(roles)] += entry.count
        if len(roles) >= 4:
            overtagged_cards.append(
                {
                    "name": card.name,
                    "count": entry.count,
                    "roles": sorted(roles),
                    "tags": sorted(card.tags),
                }
            )

        card_civs = split_civs(card.civilization)
        if len(card_civs) >= 2:
            multicolor_cards.append({"name": card.name, "count": entry.count, "civilization": card.civilization})
        for civ in card_civs:
            civ_supply[civ] += entry.count
            civ_demand[civ] += entry.count
            effective_supply[civ] += entry.count if len(card_civs) == 1 else entry.count * 0.5

        if _is_denjadeon_relevant(card):
            denjadeon_cards.append(
                {
                    "name": card.name,
                    "count": entry.count,
                    "role": role,
                    "cost": card.cost,
                    "reason": _denjadeon_reason(card),
                }
            )

    for civ in CIVS:
        demand = civ_demand[civ]
        supply = effective_supply[civ]
        if demand >= 8 and supply < 10:
            warnings.append(f"{civ}文明要求{demand}枚に対して有効供給{supply:.1f}枚です。10〜12枚を推奨します。")
        elif demand >= 4 and supply < 8:
            warnings.append(f"{civ}文明要求{demand}枚に対して有効供給{supply:.1f}枚です。最低8枚を推奨します。")

    if civ_demand["水"] > 0 and effective_supply["水"] < 8:
        water_cards = [
            f"{entry.count} {entry.card.name}"
            for entry in deck
            if "水" in split_civs(entry.card.civilization)
        ]
        warnings.append(f"水要求カードがありますが有効水供給が{effective_supply['水']:.1f}枚です: {' / '.join(water_cards)}")

    if stats["avg_cost"] > 4.2:
        warnings.append(f"平均コストが高めです: {stats['avg_cost']}")
    if stats["high_cost"] > 4:
        warnings.append(f"7コスト以上が多めです: {stats['high_cost']}")
    if primary_counts["attack"] < 20:
        warnings.append(f"primary attack不足: {primary_counts['attack']}")
    if _low_primary_attack_count(deck) < 16:
        warnings.append(f"2〜4コスト primary attack不足: {_low_primary_attack_count(deck)}")
    if primary_counts["defense"] < 8 and secondary_counts["defense"] < 8:
        warnings.append("受け札が実戦下限より少なめです。")
    if stats["evolution"] and stats["evolution_base"] < stats["evolution"] * 2:
        warnings.append(f"進化元不足: 進化{stats['evolution']} / 進化元候補{stats['evolution_base']}")
    if overtagged_cards:
        warnings.append(f"タグ過大評価の疑いがあるカードが{len(overtagged_cards)}種類あります。")

    matchups = estimate_deck_matchups(deck, db_path)
    return {
        "stats": stats,
        "primary_counts": dict(primary_counts),
        "secondary_counts": dict(secondary_counts),
        "secondary_role_summary": dict(secondary_role_summary),
        "low_primary_attack_count": _low_primary_attack_count(deck),
        "civ_supply": civ_supply,
        "effective_supply": {k: round(v, 1) for k, v in effective_supply.items()},
        "civ_demand": civ_demand,
        "multicolor_cards": multicolor_cards,
        "warnings": warnings,
        "overtagged_cards": overtagged_cards[:20],
        "denjadeon_cards": denjadeon_cards,
        "matchups": matchups,
        "denjadeon_rate": _denjadeon_rate(matchups),
    }


def build_improved_candidates(base: CandidateDeck, db_path: Path, limit: int = 3) -> list[dict[str, Any]]:
    all_cards = load_cards(db_path)
    variants = []
    strategies = [
        ("色事故除去・火光自然アグロロック", {"allow_water": False, "prefer_defense": True, "prefer_lock": True}),
        ("早期打点最大化", {"allow_water": False, "prefer_defense": False, "prefer_lock": True}),
        ("受け厚め高速圧力", {"allow_water": False, "prefer_defense": True, "prefer_lock": False}),
    ]
    for title, options in strategies[:limit]:
        deck = _improve_deck(base.deck, all_cards, options)
        audit = audit_deck(deck, db_path)
        variants.append(
            {
                "title": title,
                "deck": deck,
                "audit": audit,
                "comparison": compare_audits(audit_deck(base.deck, db_path), audit),
                "play_note": build_play_note(deck, audit),
                "first_five_matches": first_five_matches(audit),
            }
        )
    return variants


def _improve_deck(base_deck: list[DeckCard], all_cards: list[Card], options: dict[str, Any]) -> list[DeckCard]:
    deck: list[DeckCard] = []
    name_set = set()

    def add(card: Card, count: int, reason: str) -> None:
        if card.name in name_set or is_external_or_zero(card):
            return
        if not options.get("allow_water") and "水" in split_civs(card.civilization):
            return
        if not split_civs(card.civilization) <= MAIN_CIVS:
            return
        current = sum(d.count for d in deck)
        if current >= 40:
            return
        count = min(count, 40 - current, 4)
        if card.cost >= 7:
            count = min(count, 1)
        if count <= 0:
            return
        name_set.add(card.name)
        deck.append(DeckCard(count, card, reason))

    for entry in base_deck:
        card = entry.card
        if "水" in split_civs(card.civilization):
            continue
        if card.cost >= 7:
            continue
        if not split_civs(card.civilization) <= MAIN_CIVS:
            continue
        add(card, entry.count, "base keep")

    pool = sorted(all_cards, key=lambda c: _improvement_score(c, options), reverse=True)
    _fill_until(deck, pool, lambda c: primary_role(c) == "attack" and is_low_attack_card(c), 16, "low primary attack")
    _fill_until(deck, pool, lambda c: primary_role(c) == "attack", 20, "primary attack")
    _fill_until(deck, pool, lambda c: is_defense_card(c) and c.cost <= 6, 8, "defense")
    _fill_until(deck, pool, lambda c: is_resource_card(c) and c.cost <= 4, 8, "resource")
    if options.get("prefer_lock"):
        _fill_until(deck, pool, lambda c: is_lock_card(c) and c.cost <= 4, 6, "lock")

    for card in pool:
        if sum(d.count for d in deck) >= 40:
            break
        if card.name in {d.card.name for d in deck}:
            continue
        if not split_civs(card.civilization) <= MAIN_CIVS:
            continue
        if not options.get("allow_water") and "水" in split_civs(card.civilization):
            continue
        if card.cost > 6:
            continue
        add(card, 4 if card.cost <= 4 else 2, "fill practical")

    _fix_main_civ_supply(deck, pool)

    while sum(d.count for d in deck) > 40:
        target = max(deck, key=lambda d: (d.card.cost, d.count))
        target.count -= 1
        if target.count <= 0:
            deck.remove(target)
    return deck


def _fix_main_civ_supply(deck: list[DeckCard], pool: list[Card]) -> None:
    for civ in ["光", "自然"]:
        attempts = 0
        while _civ_demand(deck, civ) >= 4 and _effective_civ_supply(deck, civ) < 8 and attempts < 12:
            attempts += 1
            removed = _remove_one_for_civ_fix(deck, civ)
            if not removed:
                break
            if not _add_one_civ_card(deck, pool, civ):
                break


def _remove_one_for_civ_fix(deck: list[DeckCard], civ: str) -> bool:
    candidates = [
        entry
        for entry in deck
        if civ not in split_civs(entry.card.civilization)
        and "水" not in split_civs(entry.card.civilization)
    ]
    if not candidates:
        candidates = [entry for entry in deck if civ not in split_civs(entry.card.civilization)]
    if not candidates:
        return False
    target = sorted(candidates, key=lambda entry: (entry.card.cost, entry.count), reverse=True)[0]
    target.count -= 1
    if target.count <= 0:
        deck.remove(target)
    return True


def _add_one_civ_card(deck: list[DeckCard], pool: list[Card], civ: str) -> bool:
    current = {entry.card.name: entry for entry in deck}
    candidates = [
        card
        for card in pool
        if civ in split_civs(card.civilization)
        and "水" not in split_civs(card.civilization)
        and split_civs(card.civilization) <= MAIN_CIVS
        and card.cost <= 4
        and not is_external_or_zero(card)
        and (is_low_attack_card(card) or is_resource_card(card) or is_defense_card(card) or is_lock_card(card))
    ]
    candidates.sort(
        key=lambda card: (
            3 if split_civs(card.civilization) == {civ} else 1,
            _improvement_score(card, {"prefer_defense": True, "prefer_lock": True}),
        ),
        reverse=True,
    )
    for card in candidates:
        existing = current.get(card.name)
        if existing and existing.count < 4:
            existing.count += 1
            return True
        if not existing:
            deck.append(DeckCard(1, card, f"{civ}有効供給補正"))
            return True
    return False


def _effective_civ_supply(deck: list[DeckCard], civ: str) -> float:
    supply = 0.0
    for entry in deck:
        card_civs = split_civs(entry.card.civilization)
        if civ not in card_civs:
            continue
        supply += entry.count if len(card_civs) == 1 else entry.count * 0.5
    return supply


def _civ_demand(deck: list[DeckCard], civ: str) -> int:
    return sum(entry.count for entry in deck if civ in split_civs(entry.card.civilization))


def _fill_until(deck: list[DeckCard], pool: list[Card], predicate, target_count: int, reason: str) -> None:
    def current_count() -> int:
        total = 0
        for entry in deck:
            if predicate(entry.card):
                total += entry.count
        return total

    name_set = {d.card.name for d in deck}
    for card in pool:
        if current_count() >= target_count or sum(d.count for d in deck) >= 40:
            break
        if card.name in name_set or not predicate(card):
            continue
        if not split_civs(card.civilization) <= MAIN_CIVS or "水" in split_civs(card.civilization):
            continue
        count = min(4, 40 - sum(d.count for d in deck))
        name_set.add(card.name)
        deck.append(DeckCard(count, card, reason))


def _improvement_score(card: Card, options: dict[str, Any]) -> float:
    if is_external_or_zero(card):
        return -999
    if not split_civs(card.civilization) <= MAIN_CIVS:
        return -500
    if not options.get("allow_water") and "水" in split_civs(card.civilization):
        return -500
    score = 0.0
    if primary_role(card) == "attack":
        score += 80
    if is_low_attack_card(card):
        score += 50
    if is_lock_card(card):
        score += 22 if options.get("prefer_lock") else 12
    if is_defense_card(card):
        score += 18 if options.get("prefer_defense") else 8
    if is_resource_card(card):
        score += 16
    if is_removal_card(card):
        score += 10
    score += max(0, 6 - card.cost) * 3
    if card.cost >= 7:
        score -= 80
    if is_evolution(card):
        score -= 20
    return score


def compare_audits(base: dict[str, Any], improved: dict[str, Any]) -> dict[str, Any]:
    return {
        "avg_cost_delta": round(improved["stats"]["avg_cost"] - base["stats"]["avg_cost"], 2),
        "denjadeon_rate_delta": round(improved["denjadeon_rate"] - base["denjadeon_rate"], 4),
        "warning_delta": len(improved["warnings"]) - len(base["warnings"]),
        "base_denjadeon_rate": base["denjadeon_rate"],
        "improved_denjadeon_rate": improved["denjadeon_rate"],
    }


def estimate_deck_matchups(deck: list[DeckCard], db_path: Path) -> list[dict[str, Any]]:
    infos = load_card_info(db_path)
    metas = load_current_meta_decks(db_path)
    candidate = [MatchupDeckCard(entry.count, entry.card.name) for entry in deck]
    return [estimate_matchup(candidate, meta, infos) for meta in metas]


def build_play_note(deck: list[DeckCard], audit: dict[str, Any]) -> str:
    return (
        "2〜4ターン目はprimary attackを優先して盤面を作り、"
        "踏み倒しメタ/呪文制限でデンジャデオン側の大型着地を遅らせます。"
        "受け札は最低限に抑え、5〜6ターン目までにシールドを詰め切る想定です。"
    )


def first_five_matches(audit: dict[str, Any]) -> list[str]:
    return ["自然単デンジャデオン", "火光レイド", "火水レイド", "水単スコーラー", "光単裁きの紋章Z"]


def write_outputs(base: CandidateDeck, base_audit: dict[str, Any], improvements: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "current_meta_practical_audit.md"
    json_path = out_dir / "current_meta_practical_audit.json"
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "base_candidate": serialize_deck(base.deck),
        "base_audit": base_audit,
        "improvements": [
            {
                "title": item["title"],
                "deck": serialize_deck(item["deck"]),
                "audit": item["audit"],
                "comparison": item["comparison"],
                "play_note": item["play_note"],
                "first_five_matches": item["first_five_matches"],
            }
            for item in improvements
        ],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_markdown(base, base_audit, improvements), encoding="utf-8")
    print("markdown:", md_path)
    print("json:", json_path)


def build_markdown(base: CandidateDeck, base_audit: dict[str, Any], improvements: list[dict[str, Any]]) -> str:
    lines = ["# current meta practical audit", ""]
    lines.append(f"- 対象: {base.name}")
    lines.append(f"- profile: {base.profile}")
    lines.append("")
    lines.extend(audit_section("元候補2の監査結果", base.deck, base_audit))
    lines.append("")
    lines.append("## 改良候補")
    for index, item in enumerate(improvements, start=1):
        lines.append("")
        lines.append(f"### 改良候補{index}: {item['title']}")
        lines.append("")
        lines.extend(audit_section("監査", item["deck"], item["audit"], heading_level=4))
        comp = item["comparison"]
        lines.append("")
        lines.append("#### 候補2との比較")
        lines.append(f"- avg_cost_delta: {comp['avg_cost_delta']}")
        lines.append(f"- denjadeon_rate_delta: {comp['denjadeon_rate_delta']:+.1%}")
        lines.append(f"- warning_delta: {comp['warning_delta']}")
        lines.append("")
        lines.append("#### 実戦での回し方メモ")
        lines.append(item["play_note"])
        lines.append("")
        lines.append("#### 最初の5戦")
        for match in item["first_five_matches"]:
            lines.append(f"- {match}")
    return "\n".join(lines)


def audit_section(title: str, deck: list[DeckCard], audit: dict[str, Any], heading_level: int = 2) -> list[str]:
    h = "#" * heading_level
    s = audit["stats"]
    lines = [f"{h} {title}", ""]
    lines.append(f"- deck_size: {sum(d.count for d in deck)}")
    lines.append(f"- avg_cost: {s['avg_cost']}")
    lines.append(f"- 7コスト以上: {s['high_cost']}")
    lines.append(f"- primary_role_counts: {audit['primary_counts']}")
    lines.append(f"- 2〜4 cost primary attack: {audit['low_primary_attack_count']}")
    lines.append(f"- secondary_role_counts: {audit['secondary_counts']}")
    lines.append(f"- civilization_supply: {audit['civ_supply']}")
    lines.append(f"- effective_supply: {audit['effective_supply']}")
    lines.append(f"- civilization_demand: {audit['civ_demand']}")
    lines.append(f"- denjadeon_estimated_win_rate: {audit['denjadeon_rate']:.1%}")
    lines.append("")
    lines.append("### 色事故警告 / 実戦警告" if heading_level == 2 else "##### 色事故警告 / 実戦警告")
    if audit["warnings"]:
        for warning in audit["warnings"]:
            lines.append(f"- {warning}")
    else:
        lines.append("- 重大な警告はありません。")
    lines.append("")
    lines.append("### タグ過大評価の疑い" if heading_level == 2 else "##### タグ過大評価の疑い")
    if audit["overtagged_cards"]:
        for row in audit["overtagged_cards"][:8]:
            lines.append(f"- {row['count']} {row['name']}: roles={row['roles']}")
    else:
        lines.append("- 大きな過大評価候補はありません。")
    lines.append("")
    lines.append("### 自然単デンジャデオン対策カード" if heading_level == 2 else "##### 自然単デンジャデオン対策カード")
    for row in audit["denjadeon_cards"][:20]:
        lines.append(f"- {row['count']} {row['name']} [{row['role']} / cost {row['cost']}]: {row['reason']}")
    lines.append("")
    lines.append("### 現在メタ5デッキ代理相性" if heading_level == 2 else "##### 現在メタ5デッキ代理相性")
    lines.append("| opponent | estimated_win_rate | note | reasons |")
    lines.append("| --- | ---: | --- | --- |")
    for row in audit["matchups"]:
        lines.append(
            f"| {row.get('opponent')} | {float(row.get('estimated_win_rate') or 0):.1%} | {row.get('note')} | {' / '.join(row.get('reasons') or []) or '-'} |"
        )
    lines.append("")
    lines.append("### 40枚リスト" if heading_level == 2 else "##### 40枚リスト")
    for entry in deck:
        lines.append(f"- {entry.count} {entry.card.name} [{entry.card.civilization} / {entry.card.cost}] primary={primary_role(entry.card)}")
    return lines


def serialize_deck(deck: list[DeckCard]) -> list[dict[str, Any]]:
    return [
        {
            "count": entry.count,
            "name": entry.card.name,
            "civilization": entry.card.civilization,
            "cost": entry.card.cost,
            "primary_role": primary_role(entry.card),
            "secondary_roles": sorted(secondary_roles(entry.card)),
        }
        for entry in deck
    ]


def _is_denjadeon_relevant(card: Card) -> bool:
    return (
        is_low_attack_card(card)
        or bool(card.tags & {"踏み倒しメタ", "ロック", "呪文ロック", "攻撃制限", "シールド圧力"})
        or "コストを支払わず" in card.text
    )


def _denjadeon_reason(card: Card) -> str:
    reasons = []
    if is_low_attack_card(card):
        reasons.append("早期打点")
    for tag in ["踏み倒しメタ", "ロック", "呪文ロック", "攻撃制限", "シールド圧力"]:
        if tag in card.tags:
            reasons.append(tag)
    return " / ".join(reasons) or "状態干渉"


def _low_primary_attack_count(deck: list[DeckCard]) -> int:
    return sum(entry.count for entry in deck if primary_role(entry.card) == "attack" and 2 <= entry.card.cost <= 4)


def _denjadeon_rate(matchups: list[dict[str, Any]]) -> float:
    row = next((item for item in matchups if "デンジャデオン" in str(item.get("opponent", ""))), None)
    return float(row.get("estimated_win_rate") or 0) if row else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit current meta regenerated deck practicality.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--regen-json", default=str(DEFAULT_REGEN_JSON))
    parser.add_argument("--profile", default=TARGET_PROFILE)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    db_path = Path(args.db)
    base = load_regenerated_candidate(db_path, Path(args.regen_json), args.profile)
    base_audit = audit_deck(base.deck, db_path)
    improvements = build_improved_candidates(base, db_path, limit=3)
    write_outputs(base, base_audit, improvements, Path(args.out))


if __name__ == "__main__":
    main()

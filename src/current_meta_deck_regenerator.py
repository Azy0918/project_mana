from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data/cards.db")
DEFAULT_OUT = Path("data/reports/current_meta_regeneration")


CIVS = ["光", "水", "闇", "火", "自然"]

PROFILES = [
    {
        "name": "anti_current_meta_pressure",
        "title": "第36弾メタ対応・受け付き圧力",
        "civilizations": ["光", "火", "自然"],
        "target_tags": {
            "受け札": 1.8,
            "G・ストライク": 1.4,
            "S・トリガー": 1.0,
            "打点": 2.4,
            "フィニッシャー": 2.2,
            "フィニッシャー候補": 1.6,
            "即効性": 2.2,
            "除去": 1.6,
            "破壊": 1.2,
            "踏み倒しメタ": 2.2,
            "ロック": 1.8,
            "攻撃制限": 1.2,
            "リソース": 1.2,
            "サーチ候補": 1.0,
            "マナ加速": 1.0,
        },
        "avoid_tags": {"受け札だけ": 2.0},
        "min_attack": 14,
        "min_low_attack": 10,
        "min_defense": 10,
        "max_avg_cost": 4.2,
        "max_high_cost": 6,
    },
    {
        "name": "anti_denjadeon_fast_finish",
        "title": "自然単デンジャデオン対策・早期打点",
        "civilizations": ["火", "自然", "光"],
        "target_tags": {
            "打点": 3.2,
            "フィニッシャー": 2.8,
            "フィニッシャー候補": 2.2,
            "即効性": 2.8,
            "シールド圧力": 2.4,
            "踏み倒しメタ": 1.8,
            "ロック": 1.2,
            "除去": 1.4,
            "リソース": 1.0,
            "サーチ候補": 1.0,
            "マナ加速": 0.8,
            "受け札": 0.8,
        },
        "avoid_tags": {"受け札だけ": 2.4},
        "min_attack": 16,
        "min_low_attack": 12,
        "min_defense": 6,
        "max_defense": 10,
        "target_resource": 8,
        "max_avg_cost": 4.2,
        "max_high_cost": 6,
        "fast_finish": True,
    },
    {
        "name": "anti_raid_stabilizer",
        "title": "レイド系対策・受け除去ミッド",
        "civilizations": ["光", "自然", "火"],
        "target_tags": {
            "受け札": 2.5,
            "S・トリガー": 1.8,
            "G・ストライク": 1.8,
            "ブロッカー": 1.2,
            "除去": 2.2,
            "破壊": 1.5,
            "タップ": 1.2,
            "攻撃制限": 1.8,
            "踏み倒しメタ": 2.0,
            "打点": 1.7,
            "即効性": 1.2,
            "リソース": 1.0,
        },
        "avoid_tags": {},
        "min_attack": 12,
        "min_low_attack": 8,
        "min_defense": 14,
        "max_avg_cost": 4.2,
        "max_high_cost": 6,
    },
    {
        "name": "anti_scholar_spell_lock",
        "title": "水単スコーラー対策・呪文妨害",
        "civilizations": ["光", "自然", "水"],
        "target_tags": {
            "呪文ロック": 3.2,
            "ロック": 2.6,
            "攻撃制限": 1.5,
            "踏み倒しメタ": 1.8,
            "リソース": 1.5,
            "サーチ候補": 1.2,
            "ドロー": 1.2,
            "打点": 1.8,
            "フィニッシャー": 1.6,
            "受け札": 1.2,
            "除去": 1.0,
        },
        "avoid_tags": {},
        "min_attack": 10,
        "min_low_attack": 6,
        "min_defense": 8,
        "max_avg_cost": 4.2,
        "max_high_cost": 6,
    },
]


@dataclass
class Card:
    card_id: str
    name: str
    civilization: str
    cost: int
    card_type: str
    power: str
    race: str
    text: str
    tags: set[str]


@dataclass
class DeckCard:
    count: int
    card: Card
    reason: str


def safe_int(value: Any, default: int = 0) -> int:
    try:
        text = str(value).strip()
        if not text or text == "-":
            return default
        return int(float(text))
    except Exception:
        return default


def split_civs(value: str) -> set[str]:
    return {c for c in CIVS if c in str(value or "")}


ATTACK_TAGS = {"打点", "フィニッシャー", "フィニッシャー候補", "即効性", "シールド圧力"}
DEFENSE_TAGS = {"受け札", "S・トリガー", "G・ストライク", "ブロッカー"}
RESOURCE_TAGS = {"リソース", "ドロー", "サーチ候補", "マナ加速"}
REMOVAL_TAGS = {"除去", "破壊", "バウンス", "タップ", "パワー低下"}
LOCK_TAGS = {"ロック", "呪文ロック", "攻撃制限", "踏み倒しメタ"}
EXTERNAL_ZONE_WORDS = {"超次元", "サイキック", "ドラグハート", "龍魂", "覚醒", "禁断"}


def is_creature(card: Card) -> bool:
    return "クリーチャー" in card.card_type


def is_evolution(card: Card) -> bool:
    blob = f"{card.card_type} {card.text} {' '.join(card.tags)}"
    return "進化" in blob


def is_external_or_zero(card: Card) -> bool:
    blob = f"{card.name} {card.card_type} {card.race} {card.text} {' '.join(card.tags)}"
    return card.cost <= 0 or any(word in blob for word in EXTERNAL_ZONE_WORDS)


def has_breaker_or_pressure(card: Card) -> bool:
    text = card.text
    return (
        bool(card.tags & ATTACK_TAGS)
        or "スピードアタッカー" in text
        or "W・ブレイカー" in text
        or "T・ブレイカー" in text
        or "Q・ブレイカー" in text
        or "パワード・ブレイカー" in text
        or "アンブロッカブル" in text
    )


def is_defense_only(card: Card) -> bool:
    if not (card.tags & DEFENSE_TAGS):
        return False
    if has_breaker_or_pressure(card):
        return False
    if is_creature(card) and 2 <= card.cost <= 4 and "ブロッカー" not in card.tags:
        return False
    return True


def is_attack_card(card: Card, strict_fast: bool = False) -> bool:
    if is_external_or_zero(card):
        return False
    if not is_creature(card):
        return False
    if is_defense_only(card):
        return False
    if is_evolution(card):
        return has_breaker_or_pressure(card)
    if 2 <= card.cost <= 4 and "ブロッカー" not in card.tags:
        return True
    if has_breaker_or_pressure(card):
        return not (strict_fast and card.cost >= 7)
    return False


def is_low_attack_card(card: Card) -> bool:
    return is_attack_card(card, strict_fast=True) and 2 <= card.cost <= 4 and not is_evolution(card)


def is_resource_card(card: Card) -> bool:
    return bool(card.tags & RESOURCE_TAGS) and not is_defense_only(card)


def is_removal_card(card: Card) -> bool:
    return bool(card.tags & REMOVAL_TAGS)


def is_lock_card(card: Card) -> bool:
    return bool(card.tags & LOCK_TAGS)


def is_defense_card(card: Card) -> bool:
    return bool(card.tags & DEFENSE_TAGS)


def load_cards(db_path: Path) -> list[Card]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    tag_map: dict[str, set[str]] = {}
    for row in con.execute("SELECT c.card_id, t.tag FROM card_tags t JOIN cards c ON c.card_id=t.card_id").fetchall():
        tag_map.setdefault(row["card_id"], set()).add(row["tag"])

    rows = con.execute("SELECT card_id, name, civilization, cost, card_type, power, race, text FROM cards").fetchall()
    con.close()

    cards = []
    seen_names = set()
    for r in rows:
        name = str(r["name"] or "").strip()
        if not name:
            continue
        # 同名絵違いの重複を生成候補では1種類に寄せる
        if name in seen_names:
            continue
        seen_names.add(name)
        cards.append(
            Card(
                card_id=str(r["card_id"]),
                name=name,
                civilization=str(r["civilization"] or ""),
                cost=safe_int(r["cost"]),
                card_type=str(r["card_type"] or ""),
                power=str(r["power"] or ""),
                race=str(r["race"] or ""),
                text=str(r["text"] or ""),
                tags=tag_map.get(str(r["card_id"]), set()),
            )
        )
    return cards


def load_current_meta_names(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    names = set()
    try:
        for row in con.execute("SELECT card_name FROM meta_deck_cards").fetchall():
            names.add(str(row[0]))
    except Exception:
        pass
    con.close()
    return names


def card_score(card: Card, profile: dict[str, Any], meta_names: set[str]) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []

    if is_external_or_zero(card):
        return -999.0, ["外部ゾーン/0コスト除外"]

    wanted_civs = set(profile["civilizations"])
    card_civs = split_civs(card.civilization)

    if card_civs and not (card_civs & wanted_civs):
        return -999.0, ["文明外"]

    # 色の扱いやすさ
    if len(card_civs) == 1:
        score += 0.8
    elif len(card_civs) == 2:
        score += 0.2
    elif len(card_civs) >= 3:
        score -= 1.0
        reasons.append("多文明で色事故注意")

    # コスト
    if 0 < card.cost <= 2:
        score += 1.2
        reasons.append("軽量")
    elif card.cost <= 4:
        score += 1.0
    elif card.cost >= 7:
        score -= 2.0 if profile.get("fast_finish") else 1.0
        reasons.append("高コスト")

    # タグ
    for tag, weight in profile["target_tags"].items():
        if tag in card.tags:
            score += float(weight)
            reasons.append(tag)

    # 現環境で使われているカードは、単純にカードパワー/実績補正
    if card.name in meta_names:
        score += 1.5
        reasons.append("現環境採用実績")

    # テキスト補正
    text = card.text
    if "スピードアタッカー" in text:
        score += 1.6
        reasons.append("即時打点")
    if "W・ブレイカー" in text or "T・ブレイカー" in text or "Q・ブレイカー" in text:
        score += 1.0
        reasons.append("打点")
    if "呪文を唱え" in text and ("できない" in text or "られない" in text):
        score += 2.0
        reasons.append("呪文制限")
    if "コストを支払わず" in text or "バトルゾーンに出す" in text:
        score += 0.7
        reasons.append("踏み倒し/展開")

    if is_low_attack_card(card):
        score += 2.4 if profile.get("fast_finish") else 1.4
        reasons.append("2〜4コスト攻撃札")
    elif is_attack_card(card, strict_fast=bool(profile.get("fast_finish"))):
        score += 1.0
        reasons.append("実攻撃札")

    if is_defense_only(card):
        score -= 2.5
        reasons.append("防御専用")
    elif is_defense_card(card):
        score += 0.4

    # 進化クリーチャーは進化元チェック前なので控えめ
    if "進化" in card.card_type or "進化" in card.text:
        score -= 1.6
        reasons.append("進化条件注意")

    if profile.get("fast_finish"):
        if is_resource_card(card):
            score += 0.4
        if is_defense_only(card):
            score -= 1.2
        if card.cost >= 7 and not ("コストを支払わず" in text or "G・ゼロ" in text):
            score -= 1.5

    return score, reasons


def classify(card: Card) -> str:
    if is_attack_card(card):
        return "attack"
    if is_defense_card(card):
        return "defense"
    if is_resource_card(card):
        return "resource"
    if is_removal_card(card):
        return "removal"
    if is_lock_card(card):
        return "lock"
    return "other"


def deck_stats(deck: list[DeckCard]) -> dict[str, Any]:
    total = sum(d.count for d in deck)
    avg = sum(d.count * d.card.cost for d in deck) / total if total else 0
    counts = {"attack": 0, "defense": 0, "resource": 0, "removal": 0, "lock": 0, "other": 0}
    civs = {c: 0 for c in CIVS}
    low_attack = 0
    high_cost = 0
    evolution = 0
    evolution_base = 0

    for d in deck:
        matched = False
        if is_attack_card(d.card):
            counts["attack"] += d.count
            matched = True
        if is_defense_card(d.card):
            counts["defense"] += d.count
            matched = True
        if is_resource_card(d.card):
            counts["resource"] += d.count
            matched = True
        if is_removal_card(d.card):
            counts["removal"] += d.count
            matched = True
        if is_lock_card(d.card):
            counts["lock"] += d.count
            matched = True
        if not matched:
            counts["other"] += d.count
        if is_low_attack_card(d.card):
            low_attack += d.count
        if d.card.cost >= 7:
            high_cost += d.count
        if is_evolution(d.card):
            evolution += d.count
        elif is_creature(d.card):
            evolution_base += d.count
        for civ in split_civs(d.card.civilization):
            civs[civ] += d.count

    return {
        "deck_size": total,
        "avg_cost": round(avg, 2),
        **counts,
        "low_attack": low_attack,
        "high_cost": high_cost,
        "evolution": evolution,
        "evolution_base": evolution_base,
        "civilizations": civs,
    }


def choose_cards(cards: list[Card], profile: dict[str, Any], meta_names: set[str]) -> list[DeckCard]:
    scored = []
    for c in cards:
        score, reasons = card_score(c, profile, meta_names)
        if score <= -900:
            continue
        scored.append((score, c, reasons))
    scored.sort(key=lambda x: x[0], reverse=True)

    deck: list[DeckCard] = []
    name_set = set()
    max_high_cost = int(profile.get("max_high_cost", 6))

    def add_card(c: Card, count: int, reason: str) -> None:
        nonlocal deck
        if c.name in name_set:
            return
        if sum(d.count for d in deck) >= 40:
            return
        if is_external_or_zero(c):
            return
        current_high = sum(d.count for d in deck if d.card.cost >= 7)
        if c.cost >= 7:
            count = min(count, max(0, max_high_cost - current_high))
        if profile.get("fast_finish") and c.cost >= 7 and count > 1:
            count = 1
        count = min(count, 40 - sum(d.count for d in deck))
        if count <= 0:
            return
        name_set.add(c.name)
        deck.append(DeckCard(count, c, reason))

    # 役割ごとの候補
    buckets: dict[str, list[tuple[float, Card, list[str]]]] = {k: [] for k in ["attack", "defense", "resource", "removal", "lock", "other"]}
    for item in scored:
        buckets[classify(item[1])].append(item)

    # 早期打点は2〜4コストの非進化クリーチャーを先に確保する。
    low_attack_target = int(profile.get("min_low_attack", 0))
    current_low_attack = 0
    for score, c, reasons in [item for item in scored if is_low_attack_card(item[1])]:
        if current_low_attack >= low_attack_target:
            break
        add_card(c, 4, f"low-attack: {', '.join(reasons[:5])}")
        current_low_attack = deck_stats(deck)["low_attack"]

    target_plan = [
        ("attack", profile.get("min_attack", 14), 4),
        ("defense", profile.get("min_defense", 10), 3),
        ("resource", profile.get("target_resource", 8), 3),
        ("removal", 6, 2),
        ("lock", 4, 2),
    ]

    for role, target, default_count in target_plan:
        current = deck_stats(deck).get(role, 0)
        for score, c, reasons in buckets[role]:
            if current >= target:
                break
            if role == "attack" and not is_attack_card(c, strict_fast=bool(profile.get("fast_finish"))):
                continue
            if role == "defense" and profile.get("max_defense") and deck_stats(deck)["defense"] >= profile["max_defense"]:
                break
            # 軽量や環境実績カードは4、重いカードは2〜3
            count = default_count
            if c.cost >= 7:
                count = 1 if profile.get("fast_finish") else 2
            elif c.cost <= 2:
                count = 4
            add_card(c, count, f"{role}: {', '.join(reasons[:5])}")
            current = deck_stats(deck).get(role, 0)
            if sum(d.count for d in deck) >= 40:
                break

    # 足りない分は全体上位から補充。ただし平均コストを上げすぎない。
    for score, c, reasons in scored:
        if sum(d.count for d in deck) >= 40:
            break
        stats = deck_stats(deck)
        if stats["avg_cost"] > profile.get("max_avg_cost", 4.2) and c.cost > 3:
            continue
        if profile.get("fast_finish") and c.cost >= 7:
            continue
        count = 4 if c.cost <= 4 else 1
        add_card(c, count, f"fill: {', '.join(reasons[:5])}")

    # 40枚に届かない場合は低コスト上位で補充
    if sum(d.count for d in deck) < 40:
        low = [x for x in scored if x[1].cost <= 3]
        for score, c, reasons in low:
            if sum(d.count for d in deck) >= 40:
                break
            add_card(c, 4, f"low-fill: {', '.join(reasons[:5])}")

    return rebalance_deck(deck, scored, profile)


def rebalance_deck(
    deck: list[DeckCard],
    scored: list[tuple[float, Card, list[str]]],
    profile: dict[str, Any],
) -> list[DeckCard]:
    """Tighten practical constraints after role-based selection."""
    name_set = {d.card.name for d in deck}

    def total() -> int:
        return sum(d.count for d in deck)

    def remove_one(predicate) -> bool:
        candidates = [
            (idx, d)
            for idx, d in enumerate(deck)
            if d.count > 0 and predicate(d.card)
        ]
        if not candidates:
            return False
        idx, target = sorted(candidates, key=lambda x: (x[1].card.cost, x[1].count), reverse=True)[0]
        target.count -= 1
        if target.count <= 0:
            name_set.discard(target.card.name)
            deck.pop(idx)
        return True

    def add_best(predicate, reason: str, max_count: int = 4) -> bool:
        for _score, card, reasons in scored:
            if card.name in name_set:
                continue
            if not predicate(card):
                continue
            count = min(max_count, 40 - total())
            if count <= 0:
                return False
            name_set.add(card.name)
            deck.append(DeckCard(count, card, f"{reason}: {', '.join(reasons[:5])}"))
            return True
        return False

    # 高コスト過多と平均コストを先に締める。
    max_high_cost = int(profile.get("max_high_cost", 6))
    while deck_stats(deck)["high_cost"] > max_high_cost:
        if not remove_one(lambda c: c.cost >= 7):
            break
    while deck_stats(deck)["avg_cost"] > profile.get("max_avg_cost", 4.2):
        if not remove_one(lambda c: c.cost >= 5):
            break

    # 早期打点を優先。足りない場合は重いカード/過剰な受け札を削って入れ替える。
    while deck_stats(deck)["low_attack"] < profile.get("min_low_attack", 0):
        if total() >= 40:
            removed = remove_one(lambda c: c.cost >= 5 or is_defense_only(c) or not is_attack_card(c))
            if not removed:
                break
        if not add_best(lambda c: is_low_attack_card(c), "low-attack補正", max_count=4):
            break

    while deck_stats(deck)["attack"] < profile.get("min_attack", 14):
        if total() >= 40:
            removed = remove_one(lambda c: c.cost >= 5 or is_defense_only(c) or classify(c) == "other")
            if not removed:
                break
        if not add_best(lambda c: is_attack_card(c, strict_fast=bool(profile.get("fast_finish"))), "attack補正", max_count=4):
            break

    # 防御は必要数だけ。fast_finishでは過剰受けを削って攻撃/リソースへ寄せる。
    max_defense = profile.get("max_defense")
    if max_defense:
        while deck_stats(deck)["defense"] > int(max_defense):
            if not remove_one(lambda c: is_defense_card(c) and not is_attack_card(c)):
                break

    target_resource = int(profile.get("target_resource", 8))
    while deck_stats(deck)["resource"] < target_resource:
        if total() >= 40:
            remove_one(lambda c: c.cost >= 5 or classify(c) == "other")
        if not add_best(lambda c: is_resource_card(c) and c.cost <= 4, "resource補正", max_count=3):
            break

    # 文明供給不足は、指定文明を外すのではなく軽量実用札で増やす。
    for civ in profile["civilizations"]:
        attempts = 0
        while deck_stats(deck)["civilizations"].get(civ, 0) < 8 and attempts < 6:
            attempts += 1
            if total() >= 40:
                remove_one(lambda c, target=civ: target not in split_civs(c.civilization))
            if not add_best(
                lambda c, target=civ: target in split_civs(c.civilization)
                and c.cost <= 4
                and (is_attack_card(c) or is_resource_card(c) or is_defense_card(c)),
                f"{civ}文明供給補正",
                max_count=4,
            ):
                break

    # 40枚ぴったりへ戻す。
    while total() < 40:
        if not add_best(lambda c: c.cost <= 4 and not is_external_or_zero(c), "40枚補正", max_count=4):
            break
    while total() > 40:
        if not remove_one(lambda c: c.cost >= 5 or classify(c) == "other"):
            remove_one(lambda _c: True)

    return deck


def validate_deck(deck: list[DeckCard], profile: dict[str, Any]) -> list[str]:
    stats = deck_stats(deck)
    warnings = []
    if stats["deck_size"] != 40:
        warnings.append(f"40枚ではありません: {stats['deck_size']}")
    if stats["attack"] < profile.get("min_attack", 14):
        warnings.append(f"攻撃札不足: {stats['attack']}")
    if stats["low_attack"] < profile.get("min_low_attack", 0):
        warnings.append(f"2〜4コスト攻撃札不足: {stats['low_attack']}")
    if stats["defense"] < profile.get("min_defense", 8):
        warnings.append(f"受け札不足: {stats['defense']}")
    if profile.get("max_defense") and stats["defense"] > profile["max_defense"]:
        warnings.append(f"受け札過多: {stats['defense']} / 上限 {profile['max_defense']}")
    if stats["avg_cost"] > profile.get("max_avg_cost", 4.8):
        warnings.append(f"平均コスト高め: {stats['avg_cost']}")
    if stats["high_cost"] > profile.get("max_high_cost", 6):
        warnings.append(f"7コスト以上が多すぎます: {stats['high_cost']}")
    if stats["evolution"] and stats["evolution_base"] < stats["evolution"] * 2:
        warnings.append(f"進化元候補不足: 進化{stats['evolution']} / 進化元候補{stats['evolution_base']}")
    for civ in profile["civilizations"]:
        if stats["civilizations"].get(civ, 0) < 8:
            warnings.append(f"{civ}文明供給が実用下限未満: {stats['civilizations'].get(civ, 0)}")
    return warnings


def estimate_current_meta_matchups(deck: list[DeckCard], db_path: Path) -> list[dict[str, Any]]:
    try:
        from src.current_meta_matchup_simulator import (
            DeckCard as MatchupDeckCard,
            estimate_matchup,
            load_card_info,
            load_current_meta_decks,
        )

        infos = load_card_info(db_path)
        meta_decks = load_current_meta_decks(db_path)
        candidate = [MatchupDeckCard(d.count, d.card.name) for d in deck]
        return [estimate_matchup(candidate, meta, infos) for meta in meta_decks]
    except Exception as exc:
        return [
            {
                "opponent": "評価失敗",
                "estimated_win_rate": 0.0,
                "note": "未評価",
                "reasons": [str(exc)],
            }
        ]


def denjadeon_comment(matchups: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    den = next((m for m in matchups if "デンジャデオン" in str(m.get("opponent", ""))), None)
    if den is None:
        return "自然単デンジャデオンの代理評価が取得できませんでした。"
    rate = float(den.get("estimated_win_rate") or 0)
    comments = []
    if stats["avg_cost"] <= 4.2 and stats["low_attack"] >= 12 and stats["attack"] >= 16:
        comments.append("早期打点プランの最低条件は満たしています。")
    if stats["high_cost"] > 6:
        comments.append("大型が多く、デンジャデオンより先に詰める速度が落ちます。")
    if stats["low_attack"] < 12:
        comments.append("2〜4コスト攻撃札が不足し、序盤圧力が足りません。")
    if rate < 0.5:
        comments.append("代理評価ではまだ五分未満です。軽量打点または呪文/召喚制限を増やしてください。")
    else:
        comments.append("代理評価ではデンジャデオンへ五分以上を見込めます。")
    return " ".join(comments)


def write_outputs(results: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "current_meta_regenerated_decks.md"
    js = out_dir / "current_meta_regenerated_decks.json"
    csv_path = out_dir / "current_meta_regenerated_decks_summary.csv"

    serializable = []
    for r in results:
        serializable.append(
            {
                "profile": r["profile"],
                "title": r["title"],
                "stats": r["stats"],
                "warnings": r["warnings"],
                "matchups": r.get("matchups", []),
                "denjadeon_comment": r.get("denjadeon_comment", ""),
                "cards": [
                    {
                        "count": d.count,
                        "name": d.card.name,
                        "civilization": d.card.civilization,
                        "cost": d.card.cost,
                        "card_type": d.card.card_type,
                        "tags": sorted(d.card.tags),
                        "reason": d.reason,
                    }
                    for d in r["deck"]
                ],
            }
        )
    js.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "profile",
                "title",
                "deck_size",
                "avg_cost",
                "low_attack",
                "attack",
                "defense",
                "resource",
                "removal",
                "lock",
                "high_cost",
                "denjadeon_win_rate",
                "warning_count",
            ],
        )
        writer.writeheader()
        for r in results:
            s = r["stats"]
            writer.writerow(
                {
                    "profile": r["profile"],
                    "title": r["title"],
                    "deck_size": s["deck_size"],
                    "avg_cost": s["avg_cost"],
                    "low_attack": s["low_attack"],
                    "attack": s["attack"],
                    "defense": s["defense"],
                    "resource": s["resource"],
                    "removal": s["removal"],
                    "lock": s["lock"],
                    "high_cost": s["high_cost"],
                    "denjadeon_win_rate": _denjadeon_rate(r.get("matchups", [])),
                    "warning_count": len(r["warnings"]),
                }
            )

    lines = []
    lines.append("# current meta regenerated decks")
    lines.append("")
    lines.append("第36弾現在流行中メタを対象に、#45/#46の弱点だった自然単デンジャデオン不利を意識して再生成しました。")
    lines.append("")
    lines.append("| profile | deck_size | avg_cost | 2-4 attack | attack | defense | resource | removal | lock | high cost | denjadeon | warnings |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in results:
        s = r["stats"]
        lines.append(
            f"| {r['title']} | {s['deck_size']} | {s['avg_cost']} | {s['low_attack']} | {s['attack']} | {s['defense']} | {s['resource']} | {s['removal']} | {s['lock']} | {s['high_cost']} | {_denjadeon_rate(r.get('matchups', [])):.1%} | {len(r['warnings'])} |"
        )

    for idx, r in enumerate(results, start=1):
        lines.append("")
        lines.append(f"## {idx}. {r['title']}")
        lines.append("")
        s = r["stats"]
        lines.append(f"- profile: {r['profile']}")
        lines.append(f"- deck_size: {s['deck_size']}")
        lines.append(f"- avg_cost: {s['avg_cost']}")
        lines.append(f"- 2〜4コスト攻撃札: {s['low_attack']}")
        lines.append(f"- attack: {s['attack']}")
        lines.append(f"- defense: {s['defense']}")
        lines.append(f"- resource: {s['resource']}")
        lines.append(f"- removal: {s['removal']}")
        lines.append(f"- lock: {s['lock']}")
        lines.append(f"- 7コスト以上: {s['high_cost']}")
        lines.append(f"- civilizations: {s['civilizations']}")
        if r["warnings"]:
            lines.append("")
            lines.append("### warnings")
            for w in r["warnings"]:
                lines.append(f"- {w}")
        lines.append("")
        lines.append("### current meta proxy matchups")
        lines.append("| opponent | estimated_win_rate | note | reasons |")
        lines.append("| --- | ---: | --- | --- |")
        for m in r.get("matchups", []):
            lines.append(
                f"| {m.get('opponent', '-')} | {float(m.get('estimated_win_rate') or 0):.1%} | {m.get('note', '-')} | {' / '.join(m.get('reasons') or []) or '-'} |"
            )
        lines.append("")
        lines.append("### 自然単デンジャデオンへの改善コメント")
        lines.append(r.get("denjadeon_comment", ""))
        lines.append("")
        lines.append("### deck")
        for d in r["deck"]:
            lines.append(f"- {d.count} {d.card.name} [{d.card.civilization} / {d.card.cost}] - {d.reason}")

    md.write_text("\n".join(lines), encoding="utf-8")

    print("markdown:", md)
    print("json:", js)
    print("csv:", csv_path)


def _denjadeon_rate(matchups: list[dict[str, Any]]) -> float:
    row = next((m for m in matchups if "デンジャデオン" in str(m.get("opponent", ""))), None)
    return float(row.get("estimated_win_rate") or 0) if row else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate MANA candidate decks against the current Kamigame meta.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    db_path = Path(args.db)
    cards = load_cards(db_path)
    meta_names = load_current_meta_names(db_path)

    results = []
    for profile in PROFILES:
        deck = choose_cards(cards, profile, meta_names)
        stats = deck_stats(deck)
        warnings = validate_deck(deck, profile)
        matchups = estimate_current_meta_matchups(deck, db_path)
        results.append(
            {
                "profile": profile["name"],
                "title": profile["title"],
                "deck": deck,
                "stats": stats,
                "warnings": warnings,
                "matchups": matchups,
                "denjadeon_comment": denjadeon_comment(matchups, stats),
            }
        )

    write_outputs(results, Path(args.out))


if __name__ == "__main__":
    main()

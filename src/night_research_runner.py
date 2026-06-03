from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
import time
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.current_meta_deck_practical_auditor import audit_deck, primary_role
from src.current_meta_deck_regenerator import (
    Card,
    DeckCard,
    PROFILES,
    choose_cards,
    deck_stats,
    is_attack_card,
    is_defense_card,
    is_external_or_zero,
    is_lock_card,
    is_low_attack_card,
    is_removal_card,
    is_resource_card,
    load_cards,
    load_current_meta_names,
    split_civs,
)
from src.deck_sanity_checker import analyze_deck_sanity, analyze_theme_fit
from src.final_test_logger import summarize_matches
from src.meta_watchlist_store import load_queued_meta_research_seeds, seed_strategy_memo
from src.research_theme import build_theme_profiles, get_research_theme, list_research_themes


DEFAULT_DB = Path("data/cards.db")
DEFAULT_OUT = Path("data/reports/night_research")
BEST_DIR_NAME = "best_decks"


EXTRA_PROFILE_NAMES = [
    "balanced_current_meta",
    "low_curve_attack",
    "anti_big_mana_pressure",
]


@dataclass
class ResearchCandidate:
    deck_name: str
    profile_name: str
    deck: list[DeckCard]
    audit: dict[str, Any]
    score: float
    final_fitness: float
    base_score: float
    novelty_score: float
    meta_score: float
    sanity: dict[str, Any]
    theme_fit: dict[str, Any]
    role_snapshot: dict[str, int]
    youtube_knowledge_notes: list[str]
    strategy_memos: list[str]
    pass_required: bool
    reject_reasons: list[str]
    why_selected: str


def is_stable_mode(mode: str | None = None, stable: bool = False) -> bool:
    return stable or str(mode or "").lower() == "stable"


def normalize_deck_format(value: str | None) -> str:
    fmt = str(value or "AD").strip().upper()
    if fmt in {"ALL", "ALL_DIVISION", "ALLDIVISION", "A"}:
        return "AD"
    if fmt in {"NEW", "NEW_DIVISION", "NEWDIVISION", "N"}:
        return "ND"
    if fmt not in {"AD", "ND"}:
        raise ValueError(f"未知のフォーマットです: {value}")
    return fmt


def resolve_deck_format(format_name: str | None, research_theme: dict[str, Any] | None) -> str:
    if format_name:
        return normalize_deck_format(format_name)
    if research_theme:
        return normalize_deck_format(research_theme.get("format", "AD"))
    return "AD"


def format_target_matchups(research_theme: dict[str, Any] | None, deck_format: str) -> list[str]:
    """研究テーマの仮想敵をAD/NDごとに解決する。"""
    if not research_theme:
        return []
    deck_format = normalize_deck_format(deck_format)
    by_format = research_theme.get("target_matchups_by_format", {}) or {}
    if isinstance(by_format, dict) and deck_format in by_format:
        return [str(x) for x in (by_format.get(deck_format) or [])]
    return [str(x) for x in (research_theme.get("target_matchups", []) or [])]


def apply_format_to_research_theme(research_theme: dict[str, Any] | None, deck_format: str) -> dict[str, Any] | None:
    if research_theme is None:
        return None
    deck_format = normalize_deck_format(deck_format)
    research_theme["format"] = deck_format
    research_theme["effective_target_matchups"] = format_target_matchups(research_theme, deck_format)
    return research_theme


def filter_meta_names_by_format(meta_names: set[str], research_theme: dict[str, Any] | None, deck_format: str) -> set[str]:
    targets = set(format_target_matchups(research_theme, deck_format))
    if not targets:
        return meta_names
    compact_targets = {normalize_card_name(x) for x in targets}
    filtered = {
        name for name in meta_names
        if normalize_card_name(name) in compact_targets
        or any(normalize_card_name(name) in t or t in normalize_card_name(name) for t in compact_targets)
    }
    return filtered or meta_names


def filter_meta_seeds_by_format(seeds: list[dict[str, Any]], research_theme: dict[str, Any] | None, deck_format: str) -> list[dict[str, Any]]:
    targets = format_target_matchups(research_theme, deck_format)
    if not targets:
        return seeds
    compact_targets = [normalize_card_name(x) for x in targets]
    out: list[dict[str, Any]] = []
    for seed in seeds:
        text = " ".join(str(seed.get(k, "")) for k in ["source_name", "strategy_hint", "target", "memo", "mana_action"])
        compact_text = normalize_card_name(text)
        if any(t in compact_text for t in compact_targets):
            out.append(seed)
    return out or seeds


def read_manual_ad_only_cards(db_path: Path) -> set[str]:
    """NDで使えないカードを手動で除外するための軽量CSV。

    data/manual_ad_only_cards.csv に name または card_name 列を置く。
    DB側にフォーマット情報が無い場合でも、このCSVに入れたカードは
    --format ND で候補から除外される。
    """
    paths = [db_path.parent / "manual_ad_only_cards.csv", Path("data") / "manual_ad_only_cards.csv"]
    names: set[str] = set()
    for path in paths:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = str(row.get("name") or row.get("card_name") or "").strip()
                    if name and not name.startswith("#"):
                        names.add(normalize_card_name(name))
        except Exception:
            continue
    return names


def card_text_for_format_detection(card: Card) -> str:
    parts: list[str] = []
    for attr in [
        "format", "formats", "division", "divisions", "available_formats",
        "legal_formats", "legality", "regulation", "notes", "source", "pack",
    ]:
        value = getattr(card, attr, None)
        if value is None:
            continue
        if isinstance(value, (list, tuple, set)):
            parts.extend(str(v) for v in value)
        else:
            parts.append(str(value))
    tags = getattr(card, "tags", None)
    if tags:
        if isinstance(tags, (list, tuple, set)):
            parts.extend(str(v) for v in tags)
        else:
            parts.append(str(tags))
    return " ".join(parts)


def is_ad_only_card(card: Card, manual_ad_only: set[str]) -> bool:
    compact = normalize_card_name(card.name)
    if compact in manual_ad_only:
        return True
    blob = card_text_for_format_detection(card).upper().replace(" ", "")
    original_blob = card_text_for_format_detection(card)
    ad_only_markers = [
        "ADのみ", "AD専用", "ALLDIVISIONのみ", "ALLDIVISION専用",
        "ALL DIVISIONのみ", "ALL DIVISION専用", "NEW不可", "ND不可",
        "NEW DIVISION不可", "NEW DIVISION未対応",
    ]
    nd_markers = ["ND", "NEW", "NEW_DIVISION", "NEWDIVISION", "NEW DIVISION", "New Division", "ND可"]
    if any(marker.replace(" ", "").upper() in blob for marker in ad_only_markers):
        return True
    # ND対応の印が明示されている場合はAD専用ではない。
    if any(str(marker).replace(" ", "").upper() in blob for marker in nd_markers):
        return False
    # ADだけが明示されていてND系の印が無い場合はAD専用扱い。
    if ("AD" in blob or "ALLDIVISION" in blob) and not any(str(marker).replace(" ", "").upper() in blob for marker in nd_markers):
        return True
    return False


def filter_cards_by_deck_format(cards: list[Card], deck_format: str, db_path: Path) -> tuple[list[Card], dict[str, Any]]:
    deck_format = normalize_deck_format(deck_format)
    manual_ad_only = read_manual_ad_only_cards(db_path)
    if deck_format == "AD":
        return cards, {
            "format": "AD",
            "enabled": False,
            "input_count": len(cards),
            "output_count": len(cards),
            "excluded_count": 0,
            "excluded_ad_only_cards": [],
            "manual_ad_only_count": len(manual_ad_only),
        }

    kept: list[Card] = []
    excluded: list[str] = []
    for card in cards:
        if is_ad_only_card(card, manual_ad_only):
            excluded.append(card.name)
            continue
        kept.append(card)
    return kept, {
        "format": "ND",
        "enabled": True,
        "input_count": len(cards),
        "output_count": len(kept),
        "excluded_count": len(excluded),
        "excluded_ad_only_cards": sorted(set(excluded))[:100],
        "manual_ad_only_count": len(manual_ad_only),
    }


def configure_theme_from_battle_logs(
    research_theme: dict[str, Any] | None,
    battle_log_summary: dict[str, Any],
    stable_mode: bool,
) -> None:
    if not is_donjungle_theme(research_theme):
        return
    dead = normalize_card_count_items(battle_log_summary.get("dead_cards", []))
    donjungle_dead = matched_signal_count("ドンジャングルS7", dead)
    weak = normalize_card_count_items(battle_log_summary.get("weak_cards", []))
    strong = normalize_card_count_items(battle_log_summary.get("strong_cards", []))

    research_theme["_stable_mode"] = stable_mode
    research_theme["_donjungle_s7_dead_count"] = donjungle_dead
    research_theme["_allow_donjungle_s7_two"] = donjungle_dead >= 5
    research_theme["_prefer_donjungle_s7_count"] = 2 if donjungle_dead >= 10 else 3
    research_theme["_strong_yadok_count"] = matched_signal_count("ヤドック", strong)
    research_theme["_strong_trap_count"] = matched_signal_count("トラップ×トラップ", strong)
    research_theme["_weak_card_counts"] = weak


def build_night_profiles() -> list[dict[str, Any]]:
    profiles = [deepcopy(p) for p in PROFILES]
    profiles.extend(
        [
            {
                "name": "fire_nature_safe_pressure",
                "title": "夜間研究・火自然安全圧力",
                "civilizations": ["火", "自然"],
                "target_tags": {
                    "打点": 3.0,
                    "即効性": 2.5,
                    "シールド圧力": 2.2,
                    "踏み倒しメタ": 2.2,
                    "ロック": 2.0,
                    "攻撃制限": 1.5,
                    "除去": 1.2,
                    "リソース": 1.1,
                    "受け札": 0.9,
                },
                "avoid_tags": {"受け札だけ": 2.5},
                "min_attack": 22,
                "min_low_attack": 18,
                "min_defense": 6,
                "target_resource": 8,
                "max_avg_cost": 3.8,
                "max_high_cost": 2,
                "fast_finish": True,
            },
            {
                "name": "fire_nature_lock_race",
                "title": "夜間研究・火自然ロックレース",
                "civilizations": ["火", "自然"],
                "target_tags": {
                    "打点": 2.8,
                    "即効性": 2.2,
                    "踏み倒しメタ": 2.8,
                    "ロック": 2.5,
                    "攻撃制限": 2.0,
                    "リソース": 1.0,
                    "受け札": 0.8,
                },
                "avoid_tags": {"受け札だけ": 2.4},
                "min_attack": 20,
                "min_low_attack": 16,
                "min_defense": 6,
                "target_resource": 7,
                "max_avg_cost": 3.9,
                "max_high_cost": 2,
                "fast_finish": True,
            },
            {
                "name": "balanced_current_meta",
                "title": "夜間研究・現メタ総合バランス",
                "civilizations": ["火", "光", "自然"],
                "target_tags": {
                    "打点": 2.4,
                    "即効性": 2.0,
                    "受け札": 1.5,
                    "S・トリガー": 1.0,
                    "除去": 1.7,
                    "踏み倒しメタ": 2.0,
                    "ロック": 1.7,
                    "リソース": 1.2,
                    "サーチ候補": 1.0,
                },
                "avoid_tags": {"受け札だけ": 2.0},
                "min_attack": 18,
                "min_low_attack": 14,
                "min_defense": 8,
                "target_resource": 8,
                "max_avg_cost": 4.0,
                "max_high_cost": 4,
            },
            {
                "name": "low_curve_attack",
                "title": "夜間研究・低カーブ攻撃圧",
                "civilizations": ["火", "自然", "光"],
                "target_tags": {
                    "打点": 3.4,
                    "即効性": 3.0,
                    "シールド圧力": 2.6,
                    "フィニッシャー候補": 1.8,
                    "踏み倒しメタ": 1.8,
                    "ロック": 1.3,
                    "受け札": 0.9,
                    "リソース": 1.0,
                },
                "avoid_tags": {"受け札だけ": 2.8},
                "min_attack": 22,
                "min_low_attack": 18,
                "min_defense": 6,
                "target_resource": 6,
                "max_avg_cost": 3.8,
                "max_high_cost": 2,
                "fast_finish": True,
            },
            {
                "name": "anti_big_mana_pressure",
                "title": "夜間研究・ビッグマナ先詰め",
                "civilizations": ["火", "自然", "光"],
                "target_tags": {
                    "打点": 3.0,
                    "シールド圧力": 2.4,
                    "踏み倒しメタ": 2.4,
                    "ロック": 2.1,
                    "攻撃制限": 1.4,
                    "除去": 1.3,
                    "リソース": 1.0,
                    "受け札": 0.8,
                },
                "avoid_tags": {"受け札だけ": 2.5},
                "min_attack": 20,
                "min_low_attack": 16,
                "min_defense": 6,
                "target_resource": 7,
                "max_avg_cost": 3.9,
                "max_high_cost": 3,
                "fast_finish": True,
            },
        ]
    )
    return profiles


def apply_meta_seeds_to_profiles(profiles: list[dict[str, Any]], seeds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not seeds:
        return profiles
    out = [deepcopy(profile) for profile in profiles]
    for profile in out:
        target_tags = dict(profile.get("target_tags", {}))
        for seed in seeds[:10]:
            seed_type = str(seed.get("seed_type", ""))
            for tag in seed.get("required_tags", []) or []:
                target_tags[str(tag)] = target_tags.get(str(tag), 0.8) + seed_weight(seed)
            if seed_type == "matchup_counter":
                target_tags["メタ"] = target_tags.get("メタ", 0.8) + 1.0
                target_tags["除去"] = target_tags.get("除去", 1.0) + 0.4
                target_tags["ロック"] = target_tags.get("ロック", 1.0) + 0.4
            elif seed_type == "winrate_spike":
                target_tags["環境適性"] = target_tags.get("環境適性", 0.8) + 0.7
                target_tags["リソース"] = target_tags.get("リソース", 1.0) + 0.3
            elif seed_type == "rogue_deck_signal":
                target_tags["未知性"] = target_tags.get("未知性", 0.8) + 0.8
                target_tags["コンボ"] = target_tags.get("コンボ", 0.8) + 0.5
            elif seed_type == "paper_diff_hypothesis":
                target_tags["状態変換"] = target_tags.get("状態変換", 0.8) + 0.8
            elif seed_type == "external_zone_tech":
                profile["external_zone_seed_count"] = int(profile.get("external_zone_seed_count", 0)) + 1
        profile["target_tags"] = target_tags
        profile["meta_seed_count"] = len(seeds)
    return out


def seed_weight(seed: dict[str, Any]) -> float:
    priority = str(seed.get("priority", ""))
    confidence = float(seed.get("confidence", 0.5) or 0.5)
    base = 0.35
    if priority == "高":
        base += 0.45
    elif priority == "中":
        base += 0.25
    return round(base + confidence * 0.35, 2)


def run_night_research(
    db_path: str | Path = DEFAULT_DB,
    generations: int = 3,
    population: int = 20,
    hours: float | None = None,
    seed: int | None = None,
    out_dir: str | Path = DEFAULT_OUT,
    theme_name: str | None = None,
    format_name: str | None = None,
    mode: str = "normal",
    stable: bool = False,
) -> dict[str, Any]:
    db_path = Path(db_path)
    out_dir = Path(out_dir)
    rng = random.Random(seed)
    started = time.time()
    random_seed = seed if seed is not None else int(started)
    rng.seed(random_seed)
    stable_mode = is_stable_mode(mode, stable)

    cards = load_cards(db_path)
    meta_names = load_current_meta_names(db_path)
    research_theme = get_research_theme(theme_name)
    deck_format = resolve_deck_format(format_name, research_theme)
    research_theme = apply_format_to_research_theme(research_theme, deck_format)
    meta_names = filter_meta_names_by_format(meta_names, research_theme, deck_format)
    cards, format_filter_summary = filter_cards_by_deck_format(cards, deck_format, db_path)
    profiles = build_theme_profiles(research_theme, count=max(6, min(population, 12))) if research_theme else build_night_profiles()
    queued_meta_seeds = load_queued_meta_research_seeds(db_path, limit=30)
    queued_meta_seeds = filter_meta_seeds_by_format(queued_meta_seeds, research_theme, deck_format)
    profiles = apply_meta_seeds_to_profiles(profiles, queued_meta_seeds)
    battle_log_summary = load_battle_log_summary(db_path)
    video_learning_summary = load_youtube_research_summary(db_path)
    configure_theme_from_battle_logs(research_theme, battle_log_summary, stable_mode)

    current_population = build_initial_population(cards, meta_names, profiles, population, rng, research_theme)
    all_candidates: list[ResearchCandidate] = []
    reject_counter: Counter[str] = Counter()

    generation_index = 0
    deadline = started + (hours * 3600) if hours else None
    while True:
        if deadline and time.time() >= deadline:
            break
        if not deadline and generation_index >= max(1, generations):
            break
        evaluated = [
            evaluate_candidate(
                item["deck_name"],
                item["profile_name"],
                item["deck"],
                db_path,
                battle_log_summary,
                video_learning_summary,
                research_theme,
                queued_meta_seeds,
                stable_mode,
            )
            for item in current_population
        ]
        all_candidates.extend(evaluated)
        for cand in evaluated:
            if cand.reject_reasons:
                reject_counter.update(normalize_reject_reason(reason) for reason in cand.reject_reasons)

        elites = select_elites(evaluated, max(3, min(10, population // 4)))
        if deadline and time.time() >= deadline:
            break
        generation_index += 1
        if generation_index >= max(1, generations) and not deadline:
            break
        if deadline and time.time() >= deadline:
            break

        current_population = [{"deck_name": e.deck_name, "profile_name": e.profile_name, "deck": e.deck} for e in elites]
        while len(current_population) < population:
            parent = rng.choice(elites) if elites else rng.choice(evaluated)
            mutated = mutate_deck(parent.deck, cards, rng, research_theme)
            current_population.append(
                {
                    "deck_name": f"{parent.deck_name} mutation {generation_index}-{len(current_population) + 1}",
                    "profile_name": parent.profile_name,
                    "deck": mutated,
                }
            )
        if deadline and time.time() >= deadline:
            break

    unique = dedupe_candidates(all_candidates)
    ranked = sorted(unique, key=lambda c: (c.pass_required, c.final_fitness), reverse=True)
    if stable_mode:
        qualified = [
            cand for cand in ranked
            if cand.pass_required
            and cand.sanity.get("score", 0) >= 60
            and cand.theme_fit.get("score", 100) >= 55
            and not cand.sanity.get("fatal_issues")
            and cand.audit.get("stats", {}).get("deck_size") == 40
        ]
    else:
        qualified = [
            cand for cand in ranked
            if cand.pass_required
            and cand.sanity.get("score", 0) >= 70
            and cand.theme_fit.get("score", 100) >= 70
            and not cand.sanity.get("fatal_issues")
        ]
    top = qualified[:3]
    fallback_candidates: list[ResearchCandidate] = []
    if stable_mode and not top:
        fallback_candidates = select_stable_fallback_candidates(ranked, top, limit=3)
        top = fallback_candidates
    elapsed = round(time.time() - started, 2)

    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "conditions": {
            "db_path": str(db_path),
            "generations": generation_index if generation_index else max(1, generations),
            "population": population,
            "elapsed_time": elapsed,
            "random_seed": random_seed,
            "battle_log_used": battle_log_summary["total_matches"] > 0,
            "video_learning_used": video_learning_summary["log_count"] > 0,
            "theme_name": research_theme.get("name") if research_theme else "",
            "theme_enabled": research_theme is not None,
            "format": deck_format,
            "format_filter": format_filter_summary,
            "format_target_matchups": format_target_matchups(research_theme, deck_format),
            "mode": "stable" if stable_mode else "normal",
            "stable_mode": stable_mode,
        },
        "research_theme": research_theme or {},
        "format_filter": format_filter_summary,
        "meta_research_seeds": queued_meta_seeds[:10],
        "battle_log_summary": battle_log_summary,
        "video_learning_summary": video_learning_summary,
        "summary": build_summary(unique, top, reject_counter),
        "top_candidates": [serialize_candidate(c) for c in top],
        "fallback_candidates": [serialize_candidate(c) for c in fallback_candidates],
        "all_candidates": [serialize_candidate(c, include_deck=False) for c in ranked[:100]],
        "reject_reasons": [(reason, count) for reason, count in reject_counter.most_common() if reason != "通過"],
    }
    write_outputs(payload, out_dir)
    return payload


def build_initial_population(
    cards: list[Card],
    meta_names: set[str],
    profiles: list[dict[str, Any]],
    population: int,
    rng: random.Random,
    research_theme: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while len(out) < population:
        profile = deepcopy(profiles[len(out) % len(profiles)])
        if len(out) >= len(profiles):
            profile = jitter_profile(profile, rng)
        deck = choose_cards(cards, profile, meta_names)
        deck = apply_theme_constraints(deck, cards, research_theme, rng)
        out.append(
            {
                "deck_name": f"night {research_theme['name']} #{len(out) + 1}" if research_theme else f"night {profile['name']} #{len(out) + 1}",
                "profile_name": profile["name"],
                "deck": deck,
            }
        )
    return out


def jitter_profile(profile: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    profile = deepcopy(profile)
    target_tags = dict(profile.get("target_tags", {}))
    for key in list(target_tags):
        target_tags[key] = round(max(0.2, target_tags[key] + rng.uniform(-0.35, 0.45)), 2)
    profile["target_tags"] = target_tags
    profile["min_attack"] = int(profile.get("min_attack", 16)) + rng.choice([-1, 0, 1, 2])
    profile["min_low_attack"] = int(profile.get("min_low_attack", 12)) + rng.choice([-1, 0, 1, 2])
    profile["target_resource"] = max(5, int(profile.get("target_resource", 8)) + rng.choice([-1, 0, 1]))
    return profile


def mutate_deck(deck: list[DeckCard], cards: list[Card], rng: random.Random, research_theme: dict[str, Any] | None = None) -> list[DeckCard]:
    work = [DeckCard(d.count, d.card, d.reason) for d in deck]
    remove_names = {"コモロキシ", "緑知銀 イーアル"}
    mutation_count = rng.randint(1, 4)
    pool = [
        c for c in cards
        if not is_external_or_zero(c)
        and c.cost <= 5
        and is_allowed_by_theme(c, research_theme)
        and not is_forbidden_theme_card_name(c.name, research_theme)
    ]
    for _ in range(mutation_count):
        if not work:
            break
        target_index = choose_removal_index(work, rng, remove_names)
        target = work[target_index]
        remove_count = min(target.count, rng.randint(1, 2))
        target.count -= remove_count
        if target.count <= 0:
            work.pop(target_index)
        add_card = choose_replacement(pool, work, rng, research_theme)
        if add_card:
            add_or_increment(work, add_card, remove_count, "night-mutation")
    return apply_theme_constraints(normalize_deck(work, pool, rng, research_theme), cards, research_theme, rng)


def choose_removal_index(deck: list[DeckCard], rng: random.Random, remove_names: set[str]) -> int:
    weighted: list[int] = []
    for idx, entry in enumerate(deck):
        weight = 1
        if entry.card.name in remove_names:
            weight += 10
        if entry.card.cost >= 5:
            weight += 3
        if primary_role(entry.card) not in {"attack", "lock", "defense", "resource"}:
            weight += 2
        weighted.extend([idx] * weight)
    return rng.choice(weighted)


def choose_replacement(pool: list[Card], deck: list[DeckCard], rng: random.Random, research_theme: dict[str, Any] | None = None) -> Card | None:
    current_names = {d.card.name for d in deck if d.count >= 4}
    candidates = [
        c
        for c in pool
        if c.name not in current_names
        and is_allowed_by_theme(c, research_theme)
        and (is_low_attack_card(c) or is_lock_card(c) or is_defense_card(c) or is_resource_card(c))
        and (research_theme is not None or "水" not in split_civs(c.civilization))
    ]
    if not candidates:
        return None
    scored = []
    for c in candidates:
        score = 0.0
        if is_low_attack_card(c):
            score += 5
        if is_lock_card(c):
            score += 3
        if is_defense_card(c):
            score += 2
        if is_resource_card(c):
            score += 1.5
        if c.cost <= 3:
            score += 2
        if c.cost >= 5:
            score -= 2
        scored.append((score + rng.random(), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[min(rng.randrange(min(10, len(scored))), len(scored) - 1)][1]


def add_or_increment(deck: list[DeckCard], card: Card, count: int, reason: str) -> None:
    for entry in deck:
        if entry.card.name == card.name:
            entry.count = min(4, entry.count + count)
            return
    deck.append(DeckCard(min(4, count), card, reason))


def is_allowed_by_theme(card: Card, research_theme: dict[str, Any] | None) -> bool:
    if research_theme is None:
        return True
    allowed = set(research_theme.get("allowed_colors", []))
    if not allowed:
        return True
    civs = split_civs(card.civilization)
    return not civs or bool(civs & allowed) and civs <= allowed


def apply_theme_constraints(
    deck: list[DeckCard],
    cards: list[Card],
    research_theme: dict[str, Any] | None,
    rng: random.Random,
) -> list[DeckCard]:
    if research_theme is None:
        return deck

    required_counts: dict[str, int] = {
        str(name): int(count)
        for name, count in dict(research_theme.get("required_counts", {})).items()
    }
    required_names = set(research_theme.get("required_cards", []))
    recommended_names = set(research_theme.get("recommended_cards", []))
    card_by_name = {
        card.name: card
        for card in cards
        if is_allowed_by_theme(card, research_theme)
        and (not is_external_or_zero(card) or card.name in required_names or card.name in recommended_names)
    }

    work = [
        DeckCard(entry.count, entry.card, entry.reason)
        for entry in deck
        if is_allowed_by_theme(entry.card, research_theme)
        and not is_forbidden_theme_card_name(entry.card.name, research_theme)
    ]

    missing_required_in_db: list[str] = []
    available_required: list[str] = []
    for name in required_names:
        card = find_card_by_theme_name(name, card_by_name)
        if card is None:
            missing_required_in_db.append(name)
            continue
        available_required.append(name)
        target_count = max(1, min(4, required_counts.get(name, 2)))
        current = next((entry for entry in work if entry.card.name == card.name), None)
        if current is None:
            work.append(DeckCard(target_count, card, "theme-required"))
        elif current.count < target_count:
            current.count = target_count
    research_theme["_missing_required_in_db"] = missing_required_in_db
    research_theme["_available_required_cards"] = available_required

    for name in recommended_names:
        if sum(entry.count for entry in work) >= 40:
            break
        card = find_card_by_theme_name(name, card_by_name)
        if card is None or any(entry.card.name == card.name for entry in work):
            continue
        count = 1 if card.cost >= 7 else 2
        work.append(DeckCard(min(count, 40 - sum(entry.count for entry in work)), card, "theme-recommended"))

    pool = [
        card
        for card in cards
        if is_allowed_by_theme(card, research_theme)
        and not is_forbidden_theme_card_name(card.name, research_theme)
        and not is_external_or_zero(card)
        and card.cost <= 6
    ]
    work = reinforce_theme_main_colors(work, pool, research_theme, rng)

    while sum(entry.count for entry in work) > 40:
        idx = choose_theme_removal_index(work, required_counts, required_names, research_theme, rng)
        work[idx].count -= 1
        if work[idx].count <= 0:
            work.pop(idx)

    while sum(entry.count for entry in work) < 40:
        card = choose_theme_fill_card(pool, work, research_theme, rng)
        if card is None:
            break
        add_or_increment(work, card, 1 if card.cost >= 6 else min(4, 40 - sum(entry.count for entry in work)), "theme-fill")

    while sum(entry.count for entry in work) > 40:
        idx = choose_theme_removal_index(work, required_counts, required_names, research_theme, rng)
        work[idx].count -= 1
        if work[idx].count <= 0:
            work.pop(idx)

    work = reinforce_donjungle_requirements(work, cards, research_theme, rng)
    work = reinforce_tier_s_meta_control_requirements(work, cards, research_theme, rng)

    return [entry for entry in work if entry.count > 0]


def is_donjungle_theme(research_theme: dict[str, Any] | None) -> bool:
    return bool(research_theme and str(research_theme.get("name", "")) == "黒緑ドンジャングル")


def is_tier_s_meta_control_theme(research_theme: dict[str, Any] | None) -> bool:
    return bool(research_theme and str(research_theme.get("name", "")) == "黒緑TierSメタコントロール")


def tier_s_meta_minimums(research_theme: dict[str, Any] | None = None) -> dict[str, int]:
    if not research_theme:
        return {}
    return {
        "defense": int(dict(research_theme.get("required_roles", {})).get("defense", 10) or 10),
        "removal": int(dict(research_theme.get("required_roles", {})).get("removal", 8) or 8),
        "anti_cheat": int(dict(research_theme.get("required_roles", {})).get("anti_cheat", 7) or 7),
        "lock": int(dict(research_theme.get("required_roles", {})).get("lock", 5) or 5),
        "resource": int(dict(research_theme.get("required_roles", {})).get("resource", 14) or 14),
        "mana_boost": int(dict(research_theme.get("required_roles", {})).get("mana_boost", 10) or 10),
    }


def is_forbidden_theme_card_name(name: str, research_theme: dict[str, Any] | None) -> bool:
    if not research_theme:
        return False
    compact = normalize_card_name(name)
    for forbidden_name in research_theme.get("forbidden_cards", []) or []:
        target = normalize_card_name(str(forbidden_name))
        if compact == target or compact in target or target in compact:
            return True
    return False


def theme_card_count(deck: list[DeckCard], name: str) -> int:
    return count_card_by_name(deck, name)


def calculate_tier_s_second_resistance_score(role_snapshot: dict[str, int], deck: list[DeckCard], audit: dict[str, Any] | None = None) -> int:
    audit = audit or {}
    primary = audit.get("primary_counts", {}) or {}
    primary_attack = int(primary.get("attack", 0) or 0)
    score = 0
    if int(role_snapshot.get("defense", 0) or 0) >= 10:
        score += 20
    if int(role_snapshot.get("removal", 0) or 0) >= 8:
        score += 20
    if int(role_snapshot.get("anti_cheat", 0) or 0) >= 7:
        score += 20
    if int(role_snapshot.get("lock", 0) or 0) >= 5:
        score += 15
    if int(role_snapshot.get("mana_boost", 0) or 0) >= 10:
        score += 10
    if primary_attack <= 20:
        score += 10
    donjungle_count = count_card_by_name(deck, "ドンジャングルS7")
    if donjungle_count <= 1:
        score += 5
    if donjungle_count >= 2:
        score -= 15
    return int(max(0, min(100, score)))


def theme_required_count_reject_reasons(deck: list[DeckCard], research_theme: dict[str, Any] | None, stable_mode: bool = False) -> list[str]:
    if not research_theme:
        return []
    reasons: list[str] = []
    for name, required in dict(research_theme.get("required_counts", {})).items():
        required_count = int(required or 0)
        actual = count_card_by_name(deck, str(name))
        if actual >= required_count:
            continue
        # stableではエスカルデンだけ最低1まで緩和し、候補全滅を避ける。
        if stable_mode and "エスカルデン" in str(name) and actual >= 1:
            continue
        reasons.append(f"テーマ必須枚数不足: {name} {actual}/{required_count}")
    return reasons


def theme_penalty_adjustment(deck: list[DeckCard], audit: dict[str, Any], research_theme: dict[str, Any] | None, role_snapshot: dict[str, int] | None = None) -> float:
    if not research_theme:
        return 0.0
    role_snapshot = role_snapshot or build_role_snapshot(deck, audit)
    primary = audit.get("primary_counts", {}) or {}
    primary_attack = int(primary.get("attack", 0) or 0)
    adjustment = 0.0

    for entry in deck:
        name = entry.card.name
        count = int(entry.count or 0)
        if is_forbidden_theme_card_name(name, research_theme):
            adjustment -= 80.0
        for penalty_name, penalty_value in dict(research_theme.get("penalty_cards", {})).items():
            compact = normalize_card_name(str(penalty_name))
            actual = normalize_card_name(name)
            if compact == actual or compact in actual or actual in compact:
                if "ドンジャングルS7" in compact and count <= 1:
                    adjustment -= float(penalty_value) * count * 0.25
                else:
                    adjustment -= float(penalty_value) * count

    if is_tier_s_meta_control_theme(research_theme):
        minimums = tier_s_meta_minimums(research_theme)
        weights = {"defense": 3.0, "removal": 3.5, "anti_cheat": 4.0, "lock": 3.0, "resource": 1.2, "mana_boost": 1.5}
        for role, required in minimums.items():
            actual = int(role_snapshot.get(role, 0) or 0)
            if actual < required:
                adjustment -= (required - actual) * weights.get(role, 2.0)
            else:
                adjustment += min(actual - required, 4) * 0.8
        donjungle_count = count_card_by_name(deck, "ドンジャングルS7")
        if donjungle_count == 0:
            adjustment += 5.0
        elif donjungle_count == 1:
            adjustment += 1.0
        elif donjungle_count >= 2:
            adjustment -= 15.0 + (donjungle_count - 2) * 8.0
        if primary_attack <= 20:
            adjustment += 8.0
        else:
            adjustment -= (primary_attack - 20) * 1.7
        adjustment += calculate_tier_s_second_resistance_score(role_snapshot, deck, audit) * 0.12
    return round(adjustment, 2)


def choose_tier_s_meta_role_card(
    role: str,
    deck: list[DeckCard],
    candidate_pool: list[Card],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> Card | None:
    main_colors = set(research_theme.get("main_colors", []))
    required = set(research_theme.get("required_cards", []))
    recommended = set(research_theme.get("recommended_cards", []))
    scored: list[tuple[float, Card]] = []
    for card in candidate_pool:
        if current_card_count(deck, card) >= 4:
            continue
        if is_forbidden_theme_card_name(card.name, research_theme):
            continue
        if role != "any" and not card_contributes_to_role(card, role):
            continue
        blob = card_text_blob(card)
        civs = split_civs(card.civilization)
        score = 0.0
        if civs & main_colors:
            score += 4.0
        if any(normalize_card_name(card.name) == normalize_card_name(x) or normalize_card_name(x) in normalize_card_name(card.name) or normalize_card_name(card.name) in normalize_card_name(x) for x in required):
            score += 10.0
        if any(normalize_card_name(card.name) == normalize_card_name(x) or normalize_card_name(x) in normalize_card_name(card.name) or normalize_card_name(card.name) in normalize_card_name(x) for x in recommended):
            score += 5.0
        if card.cost <= 3:
            score += 3.0
        elif card.cost <= 5:
            score += 1.0
        else:
            score -= 3.0
        if card_contributes_to_role(card, "defense"):
            score += 4.5
        if card_contributes_to_role(card, "removal"):
            score += 4.5
        if card_contributes_to_role(card, "anti_cheat"):
            score += 5.0
        if card_contributes_to_role(card, "lock"):
            score += 4.5
        if card_contributes_to_role(card, "mana_boost"):
            score += 3.0
        if card_contributes_to_role(card, "resource"):
            score += 2.2
        if primary_role(card) == "attack" and not any(k in blob for k in ["踏み倒し", "攻撃できない", "除去", "S・トリガー", "トリガー"]):
            score -= 5.0
        if normalize_card_name(card.name) == normalize_card_name("ドンジャングルS7"):
            score -= 30.0
        scored.append((score + rng.random() * 0.01, card))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored else None


def choose_tier_s_meta_removal_index(
    deck: list[DeckCard],
    research_theme: dict[str, Any],
    protected_minimums: dict[str, int],
    role_needed: str,
    rng: random.Random,
) -> int | None:
    required_counts = {normalize_card_name(str(name)): int(count) for name, count in dict(research_theme.get("required_counts", {})).items()}
    current_counts = {role: deck_role_count(deck, role) for role in protected_minimums}
    scored: list[tuple[float, int]] = []
    for idx, entry in enumerate(deck):
        compact = normalize_card_name(entry.card.name)
        matching_required = next((req for req in required_counts if compact == req or compact in req or req in compact), "")
        if matching_required and int(entry.count or 0) <= required_counts.get(matching_required, 1):
            continue
        if role_needed != "any" and card_contributes_to_role(entry.card, role_needed):
            continue
        would_break = False
        for role, minimum in protected_minimums.items():
            if current_counts.get(role, 0) <= minimum and card_contributes_to_role(entry.card, role):
                would_break = True
                break
        if would_break:
            continue
        score = 0.0
        if is_forbidden_theme_card_name(entry.card.name, research_theme):
            score += 100.0
        if normalize_card_name(entry.card.name) == normalize_card_name("ドンジャングルS7"):
            score += 55.0
        if primary_role(entry.card) == "attack":
            score += 18.0
        if entry.card.cost >= 7:
            score += 16.0
        elif entry.card.cost >= 5:
            score += 6.0
        if int(entry.count or 0) == 1:
            score += 4.0
        if matching_required:
            score -= 35.0
        scored.append((score + rng.random() * 0.01, idx))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def reinforce_tier_s_meta_control_requirements(
    deck: list[DeckCard],
    cards: list[Card],
    research_theme: dict[str, Any] | None,
    rng: random.Random,
) -> list[DeckCard]:
    if not is_tier_s_meta_control_theme(research_theme):
        return deck

    work = [DeckCard(entry.count, entry.card, entry.reason) for entry in deck if entry.count > 0 and not is_forbidden_theme_card_name(entry.card.name, research_theme)]
    allowed_names = set(research_theme.get("required_cards", [])) | set(research_theme.get("recommended_cards", []))
    candidate_pool = [
        card
        for card in cards
        if is_allowed_by_theme(card, research_theme)
        and not is_forbidden_theme_card_name(card.name, research_theme)
        and (not is_external_or_zero(card) or card.name in allowed_names)
        and card.cost <= 6
    ]
    minimums = tier_s_meta_minimums(research_theme)

    # ドンジャングルS7は非依存化。2枚以上あれば軽量対策札へ置換する。
    attempts = 0
    while count_card_by_name(work, "ドンジャングルS7") > 1 and attempts < 8:
        attempts += 1
        target = next((entry for entry in work if normalize_card_name("ドンジャングルS7") in normalize_card_name(entry.card.name)), None)
        if target is None:
            break
        target.count -= 1
        if target.count <= 0:
            work = [entry for entry in work if entry is not target]
        replacement = choose_tier_s_meta_role_card("any", work, candidate_pool, research_theme, rng)
        if replacement is not None:
            add_or_increment(work, replacement, 1, "tier-s-meta-donjungle-replace")

    for role in ["anti_cheat", "defense", "removal", "lock", "mana_boost", "resource"]:
        attempts = 0
        while deck_role_count(work, role) < minimums.get(role, 0) and attempts < 36:
            attempts += 1
            card = choose_tier_s_meta_role_card(role, work, candidate_pool, research_theme, rng)
            if card is None:
                break
            if deck_total(work) >= 40:
                idx = choose_tier_s_meta_removal_index(work, research_theme, minimums, role, rng)
                if idx is None:
                    break
                work[idx].count -= 1
                if work[idx].count <= 0:
                    work.pop(idx)
            add_or_increment(work, card, 1, f"tier-s-meta-{role}")

    attempts = 0
    while deck_primary_attack_count(work) > 20 and attempts < 32:
        attempts += 1
        replacement = choose_tier_s_meta_role_card("any", work, candidate_pool, research_theme, rng)
        idx = choose_tier_s_meta_removal_index(work, research_theme, minimums, "any", rng)
        if replacement is None or idx is None:
            break
        if primary_role(work[idx].card) != "attack" and attempts < 20:
            continue
        work[idx].count -= 1
        if work[idx].count <= 0:
            work.pop(idx)
        add_or_increment(work, replacement, 1, "tier-s-meta-attack-trim")

    while deck_total(work) > 40:
        idx = choose_tier_s_meta_removal_index(work, research_theme, minimums, "any", rng)
        if idx is None:
            idx = choose_theme_removal_index(work, dict(research_theme.get("required_counts", {})), set(research_theme.get("required_cards", [])), research_theme, rng)
        work[idx].count -= 1
        if work[idx].count <= 0:
            work.pop(idx)

    while deck_total(work) < 40:
        card = choose_tier_s_meta_role_card("any", work, candidate_pool, research_theme, rng) or choose_theme_fill_card(candidate_pool, work, research_theme, rng)
        if card is None:
            break
        add_or_increment(work, card, 1, "tier-s-meta-fill")

    return [entry for entry in work if entry.count > 0]


def donjungle_s7_min_count(research_theme: dict[str, Any] | None = None) -> int:
    if not is_donjungle_theme(research_theme):
        return 3
    if research_theme.get("_allow_donjungle_s7_two") or research_theme.get("_stable_mode"):
        return 2
    return int(dict(research_theme.get("required_counts", {})).get("ドンジャングルS7", 2) or 2)


def donjungle_s7_preferred_count(research_theme: dict[str, Any] | None = None) -> int:
    if not is_donjungle_theme(research_theme):
        return 3
    return int(research_theme.get("_prefer_donjungle_s7_count") or dict(research_theme.get("preferred_counts", {})).get("ドンジャングルS7", 3) or 3)


def donjungle_s7_variant(count: int) -> str:
    if count == 0:
        return "ドンジャングルS7 0枚型"
    if count == 1:
        return "ドンジャングルS7 1枚型"
    if count == 2:
        return "ドンジャングルS7 2枚型"
    if count == 3:
        return "ドンジャングルS7 3枚型"
    return f"ドンジャングルS7 {count}枚型"


def donjungle_trap_x_trap_count(deck: list[DeckCard]) -> int:
    return sum(int(entry.count or 0) for entry in deck if normalize_card_name(entry.card.name) == normalize_card_name("トラップ×トラップ"))


def donjungle_minimums(research_theme: dict[str, Any] | None = None) -> dict[str, int]:
    return {
        "defense": 6,
        "resource": 6,
        "mana_boost": 4,
        "anti_cheat": 4,
        "hand_discard": 3,
        "donjungle_s7": donjungle_s7_min_count(research_theme),
    }


def donjungle_preferred_minimums(research_theme: dict[str, Any] | None = None) -> dict[str, int]:
    """Rank上位に乗せたい黒緑ドンジャングルの推奨ライン。

    最低条件は donjungle_minimums() に残しつつ、生成側では
    火光レイド後攻を意識して受け札8枚を強く目指す。
    """
    preferred = dict(donjungle_minimums(research_theme))
    preferred["defense"] = 8
    preferred["resource"] = 10
    # Tier S火光レイド/ブランドを意識した推奨ライン。
    # 最低条件ではなく、生成側で上位候補を寄せるための目標。
    preferred["removal"] = 6
    preferred["lock"] = 5
    return preferred


def deck_total(deck: list[DeckCard]) -> int:
    return sum(int(entry.count or 0) for entry in deck)


def card_contributes_to_role(card: Card, role: str) -> bool:
    if role == "donjungle_s7":
        return "ドンジャングルS7" in normalize_card_name(card.name)
    return count_role_cards([DeckCard(1, card, "role-check")], role) > 0


def is_protected_donjungle_card(card: Card, research_theme: dict[str, Any] | None) -> bool:
    if not is_donjungle_theme(research_theme):
        return False
    compact = normalize_card_name(card.name)
    protected_names = {
        normalize_card_name(name)
        for name in list(research_theme.get("required_cards", [])) + ["ドンジャングルS7"]
    }
    return any(compact == name or compact in name or name in compact for name in protected_names)


def is_low_quality_donjungle_attack_card(card: Card, research_theme: dict[str, Any] | None) -> bool:
    """黒緑ドンジャングルで穴埋めになりやすい低品質attack札を判定する。"""
    if not is_donjungle_theme(research_theme):
        return False
    if is_protected_donjungle_card(card, research_theme):
        return False
    if primary_role(card) != "attack":
        return False
    useful_roles = ["defense", "resource", "mana_boost", "anti_cheat", "hand_discard", "lock", "removal"]
    return not any(card_contributes_to_role(card, role) for role in useful_roles)


def deck_role_count(deck: list[DeckCard], role: str) -> int:
    if role == "donjungle_s7":
        return count_card_by_name(deck, "ドンジャングルS7")
    return count_role_cards(deck, role)


def current_card_count(deck: list[DeckCard], card: Card) -> int:
    compact = normalize_card_name(card.name)
    for entry in deck:
        if normalize_card_name(entry.card.name) == compact:
            return int(entry.count or 0)
    return 0


def deck_primary_attack_count(deck: list[DeckCard]) -> int:
    return sum(int(entry.count or 0) for entry in deck if primary_role(entry.card) == "attack")


def choose_tier_s_counter_card(
    deck: list[DeckCard],
    candidate_pool: list[Card],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> Card | None:
    """Tier S火光レイド/ブランドを見て、穴埋めattackより優先して足したいカードを選ぶ。"""
    main_colors = set(research_theme.get("main_colors", []))
    required = set(research_theme.get("required_cards", []))
    recommended = set(research_theme.get("recommended_cards", []))
    scored: list[tuple[float, Card]] = []

    for card in candidate_pool:
        if current_card_count(deck, card) >= 4:
            continue
        if is_donjungle_theme(research_theme) and normalize_card_name(card.name) == normalize_card_name("ドンジャングルS7"):
            if current_card_count(deck, card) >= donjungle_s7_preferred_count(research_theme):
                continue
        if is_low_quality_donjungle_attack_card(card, research_theme):
            continue

        contributes_defense = card_contributes_to_role(card, "defense")
        contributes_removal = card_contributes_to_role(card, "removal")
        contributes_lock = card_contributes_to_role(card, "lock")
        contributes_anti_cheat = card_contributes_to_role(card, "anti_cheat")
        contributes_resource = card_contributes_to_role(card, "resource")
        if not any([contributes_defense, contributes_removal, contributes_lock, contributes_anti_cheat, contributes_resource]):
            continue

        civs = split_civs(card.civilization)
        score = 0.0
        if civs & main_colors:
            score += 3.0
        if card.name in required:
            score += 8.0
        if card.name in recommended:
            score += 4.0
        if contributes_defense:
            score += 5.0
        if contributes_removal:
            score += 5.0
        if contributes_lock:
            score += 4.0
        if contributes_anti_cheat:
            score += 4.0
        if contributes_resource:
            score += 1.5
        if card.cost <= 4:
            score += 2.0
        elif card.cost >= 7:
            score -= 3.0
        if primary_role(card) == "attack" and not is_protected_donjungle_card(card, research_theme):
            score -= 4.0
        scored.append((score + rng.random() * 0.01, card))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored else None


def choose_donjungle_role_card(
    role: str,
    deck: list[DeckCard],
    candidate_pool: list[Card],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> Card | None:
    main_colors = set(research_theme.get("main_colors", []))
    recommended = set(research_theme.get("recommended_cards", []))
    required = set(research_theme.get("required_cards", []))
    scored: list[tuple[float, Card]] = []

    for card in candidate_pool:
        if current_card_count(deck, card) >= 4:
            continue
        if not card_contributes_to_role(card, role):
            continue

        blob = f"{card.name} {card.card_type} {card.race} {card.text} {' '.join(sorted(card.tags))}"
        civs = split_civs(card.civilization)
        score = 0.0

        if civs & main_colors:
            score += 5.0
        if card.name in required:
            score += 10.0
        if card.name in recommended:
            score += 4.0
        if card.cost <= 4:
            score += 3.0
        elif card.cost <= 6:
            score += 1.0
        else:
            score -= 2.0

        if role == "defense":
            if is_defense_card(card):
                score += 4.0
            if "S・トリガー" in blob or "Sトリガー" in blob:
                score += 3.0
            if is_removal_card(card):
                score += 1.5
        elif role == "resource":
            if is_resource_card(card):
                score += 4.0
            if any(k in blob for k in ["ドロー", "手札", "回収", "探索", "サーチ"]):
                score += 2.0
        elif role == "mana_boost":
            if any(k in blob for k in ["マナ加速", "ブースト", "マナゾーン", "チャージャー"]):
                score += 5.0
            if card.cost <= 3:
                score += 2.5
        elif role == "anti_cheat":
            if any(k in blob for k in ["踏み倒し", "コストを支払わず", "召喚できない", "出せない"]):
                score += 5.0
            if is_lock_card(card):
                score += 2.0
        elif role == "hand_discard":
            if any(k in blob for k in ["ハンデス", "手札破壊", "捨て", "相手の手札"]):
                score += 5.0
        elif role == "removal":
            if is_removal_card(card):
                score += 5.0
            if any(k in blob for k in ["破壊", "除去", "マナ送り", "パワー低下", "タップ", "山札の下"]):
                score += 3.0
            if card.cost <= 4:
                score += 1.5
        elif role == "lock":
            if is_lock_card(card):
                score += 5.0
            if any(k in blob for k in ["攻撃できない", "攻撃制限", "召喚できない", "出せない", "呪文を唱えられない"]):
                score += 3.0
            if card.cost <= 4:
                score += 1.5
        elif role == "donjungle_s7":
            score += 20.0

        scored.append((score + rng.random() * 0.01, card))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored else None


def choose_donjungle_removal_index(
    deck: list[DeckCard],
    research_theme: dict[str, Any],
    protected_minimums: dict[str, int],
    role_needed: str,
    rng: random.Random,
) -> int | None:
    required_names = set(research_theme.get("required_cards", []))
    required_counts = {
        normalize_card_name(name): int(count)
        for name, count in dict(research_theme.get("required_counts", {})).items()
    }
    required_counts[normalize_card_name("ドンジャングルS7")] = max(
        donjungle_s7_min_count(research_theme),
        required_counts.get(normalize_card_name("ドンジャングルS7"), 0),
    )
    required_compact = {normalize_card_name(name) for name in required_names}
    scored: list[tuple[float, int]] = []

    current_counts = {role: deck_role_count(deck, role) for role in protected_minimums}

    for idx, entry in enumerate(deck):
        compact = normalize_card_name(entry.card.name)
        matching_required = next((req for req in required_compact if compact == req or req in compact or compact in req), "")
        if matching_required and int(entry.count or 0) <= required_counts.get(matching_required, 1):
            continue

        # 不足している役割の札は、原則として抜かない。
        if card_contributes_to_role(entry.card, role_needed):
            continue

        would_break_required_role = False
        for role, minimum in protected_minimums.items():
            if current_counts.get(role, 0) <= minimum and card_contributes_to_role(entry.card, role):
                would_break_required_role = True
                break
        if would_break_required_role:
            continue

        score = 0.0
        if not is_allowed_by_theme(entry.card, research_theme):
            score += 100.0
        if primary_role(entry.card) not in {"attack", "lock", "defense", "resource", "removal"}:
            score += 20.0
        if is_low_quality_donjungle_attack_card(entry.card, research_theme):
            score += 22.0
        elif primary_role(entry.card) == "attack" and entry.card.cost <= 4 and not is_protected_donjungle_card(entry.card, research_theme):
            score += 8.0
        if entry.card.cost >= 7:
            score += 12.0
        elif entry.card.cost >= 5:
            score += 5.0
        if int(entry.count or 0) == 1:
            score += 5.0
        if matching_required:
            score -= 20.0
        if entry.card.name in research_theme.get("recommended_cards", []):
            score -= 6.0
        score += rng.random() * 0.01
        scored.append((score, idx))

    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def soften_donjungle_attack_density(
    deck: list[DeckCard],
    candidate_pool: list[Card],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> list[DeckCard]:
    """Tier S火光レイド/ブランド対策として、小型attack過多を生成側で少し抑える。

    評価ゲートで全滅させるのではなく、低品質attackを受け/除去/ロックへ置換して
    Rank上位をコントロール寄りにする。
    """
    work = [DeckCard(entry.count, entry.card, entry.reason) for entry in deck if entry.count > 0]
    preferred = donjungle_preferred_minimums(research_theme)
    attempts = 0

    while deck_primary_attack_count(work) > 22 and attempts < 28:
        attempts += 1
        replacement = choose_tier_s_counter_card(work, candidate_pool, research_theme, rng)
        if replacement is None:
            break
        idx = choose_donjungle_removal_index(work, research_theme, preferred, "tier_s_counter", rng)
        if idx is None:
            break
        # 攻撃札が多い時だけ置換したいので、非attackが選ばれたら無理に抜かない。
        if primary_role(work[idx].card) != "attack" and attempts < 20:
            continue
        work[idx].count -= 1
        if work[idx].count <= 0:
            work.pop(idx)
        add_or_increment(work, replacement, 1, "donjungle-tier-s-counter-fill")

    return [entry for entry in work if entry.count > 0]


def adjust_donjungle_s7_count_and_fill(
    deck: list[DeckCard],
    candidate_pool: list[Card],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> list[DeckCard]:
    work = [DeckCard(entry.count, entry.card, entry.reason) for entry in deck if entry.count > 0]
    target_count = donjungle_s7_preferred_count(research_theme)
    min_count = donjungle_s7_min_count(research_theme)

    while count_card_by_name(work, "ドンジャングルS7") > target_count:
        target = next((entry for entry in work if "ドンジャングルS7" in normalize_card_name(entry.card.name)), None)
        if target is None or count_card_by_name(work, "ドンジャングルS7") <= min_count:
            break
        target.count -= 1
        if target.count <= 0:
            work = [entry for entry in work if entry is not target]

        replacement = choose_tier_s_counter_card(work, candidate_pool, research_theme, rng)
        if replacement is None:
            replacement = choose_theme_fill_card(candidate_pool, work, research_theme, rng)
        if replacement is not None:
            add_or_increment(work, replacement, 1, "donjungle-s7-dead-slot-fill")

    return [entry for entry in work if entry.count > 0]


def reinforce_trap_x_trap(
    deck: list[DeckCard],
    candidate_pool: list[Card],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> list[DeckCard]:
    work = [DeckCard(entry.count, entry.card, entry.reason) for entry in deck if entry.count > 0]
    target = 3
    if float(research_theme.get("_strong_trap_count", 0) or 0) >= 8:
        target = 4
    trap_card = next((card for card in candidate_pool if normalize_card_name(card.name) == normalize_card_name("トラップ×トラップ")), None)
    if trap_card is None:
        return work

    preferred = donjungle_preferred_minimums(research_theme)
    attempts = 0
    while donjungle_trap_x_trap_count(work) < target and current_card_count(work, trap_card) < 4 and attempts < 8:
        attempts += 1
        if deck_total(work) >= 40:
            idx = choose_donjungle_removal_index(work, research_theme, preferred, "defense", rng)
            if idx is None:
                break
            work[idx].count -= 1
            if work[idx].count <= 0:
                work.pop(idx)
        add_or_increment(work, trap_card, 1, "strong-card-trap-x-trap")

    return [entry for entry in work if entry.count > 0]


def reinforce_donjungle_requirements(
    deck: list[DeckCard],
    cards: list[Card],
    research_theme: dict[str, Any] | None,
    rng: random.Random,
) -> list[DeckCard]:
    """
    黒緑ドンジャングル専用の生成側補強。
    評価で弾く前に、テーマ成立に必要な役割をDB内カードから優先的に埋める。
    """
    if not is_donjungle_theme(research_theme):
        return deck

    work = [DeckCard(entry.count, entry.card, entry.reason) for entry in deck if entry.count > 0]
    minimums = donjungle_minimums(research_theme)
    allowed_names = set(research_theme.get("required_cards", [])) | set(research_theme.get("recommended_cards", []))
    candidate_pool = [
        card
        for card in cards
        if is_allowed_by_theme(card, research_theme)
        and (not is_external_or_zero(card) or card.name in allowed_names)
        and (card.cost <= 7 or "ドンジャングルS7" in normalize_card_name(card.name))
    ]

    donjungle_card = next((card for card in candidate_pool if "ドンジャングルS7" in normalize_card_name(card.name)), None)
    target_donjungle_count = donjungle_s7_preferred_count(research_theme)
    if donjungle_card is not None:
        while count_card_by_name(work, "ドンジャングルS7") < target_donjungle_count and current_card_count(work, donjungle_card) < 4:
            if deck_total(work) >= 40:
                idx = choose_donjungle_removal_index(work, research_theme, minimums, "donjungle_s7", rng)
                if idx is None:
                    break
                work[idx].count -= 1
                if work[idx].count <= 0:
                    work.pop(idx)
            add_or_increment(work, donjungle_card, 1, "donjungle-required")

    # 重要度順。受けと踏み倒しメタを先に埋める。
    for role in ["defense", "anti_cheat", "resource", "mana_boost", "hand_discard"]:
        attempts = 0
        while deck_role_count(work, role) < minimums[role] and attempts < 24:
            attempts += 1
            card = choose_donjungle_role_card(role, work, candidate_pool, research_theme, rng)
            if card is None:
                break
            if deck_total(work) >= 40:
                idx = choose_donjungle_removal_index(work, research_theme, minimums, role, rng)
                if idx is None:
                    break
                work[idx].count -= 1
                if work[idx].count <= 0:
                    work.pop(idx)
            add_or_increment(work, card, 1, f"donjungle-{role}")

    # 実戦ログで火光レイド後攻に弱さが出たため、最低条件とは別に
    # Rank上位向けの推奨ラインとして受け/除去/ロックを目指す。
    preferred = donjungle_preferred_minimums(research_theme)
    for role in ["defense", "removal", "lock"]:
        attempts = 0
        while deck_role_count(work, role) < preferred[role] and attempts < 32:
            attempts += 1
            card = choose_donjungle_role_card(role, work, candidate_pool, research_theme, rng)
            if card is None:
                break
            if deck_total(work) >= 40:
                idx = choose_donjungle_removal_index(work, research_theme, preferred, role, rng)
                if idx is None:
                    break
                work[idx].count -= 1
                if work[idx].count <= 0:
                    work.pop(idx)
            add_or_increment(work, card, 1, f"donjungle-preferred-{role}")

    work = adjust_donjungle_s7_count_and_fill(work, candidate_pool, research_theme, rng)
    work = reinforce_trap_x_trap(work, candidate_pool, research_theme, rng)
    work = soften_donjungle_attack_density(work, candidate_pool, research_theme, rng)

    while deck_total(work) > 40:
        idx = choose_donjungle_removal_index(work, research_theme, minimums, "defense", rng)
        if idx is None:
            idx = choose_theme_removal_index(
                work,
                dict(research_theme.get("required_counts", {})),
                set(research_theme.get("required_cards", [])),
                research_theme,
                rng,
            )
        work[idx].count -= 1
        if work[idx].count <= 0:
            work.pop(idx)

    while deck_total(work) < 40:
        card = choose_theme_fill_card(candidate_pool, work, research_theme, rng)
        if card is None:
            break
        add_or_increment(work, card, 1, "donjungle-fill")

    return [entry for entry in work if entry.count > 0]


def reinforce_theme_main_colors(
    deck: list[DeckCard],
    pool: list[Card],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> list[DeckCard]:
    main_colors = set(research_theme.get("main_colors", []))
    splash_colors = set(research_theme.get("splash_colors", []))
    if not main_colors:
        return deck

    work = [DeckCard(entry.count, entry.card, entry.reason) for entry in deck]

    def civ_count(civ: str) -> int:
        return sum(entry.count for entry in work if civ in split_civs(entry.card.civilization))

    def total() -> int:
        return sum(entry.count for entry in work)

    for civ in main_colors:
        attempts = 0
        while civ_count(civ) < 10 and attempts < 12:
            attempts += 1
            removable = [
                (idx, entry)
                for idx, entry in enumerate(work)
                if split_civs(entry.card.civilization)
                and civ not in split_civs(entry.card.civilization)
                and (split_civs(entry.card.civilization) & splash_colors or not split_civs(entry.card.civilization) & main_colors)
            ]
            if removable:
                idx, entry = sorted(removable, key=lambda item: (item[1].card.cost, item[1].count), reverse=True)[0]
                entry.count -= 1
                if entry.count <= 0:
                    work.pop(idx)
            elif total() >= 40:
                break

            candidates = [
                card for card in pool
                if civ in split_civs(card.civilization)
                and card.name not in {entry.card.name for entry in work if entry.count >= 4}
                and (is_resource_card(card) or is_defense_card(card) or is_removal_card(card) or is_lock_card(card) or is_attack_card(card))
            ]
            if not candidates:
                break
            candidates.sort(
                key=lambda card: (
                    card.name in research_theme.get("required_cards", []),
                    card.name in research_theme.get("recommended_cards", []),
                    card.cost <= 4,
                    -card.cost,
                    rng.random(),
                ),
                reverse=True,
            )
            add_or_increment(work, candidates[0], 1, f"theme-main-color-{civ}")
    while total() > 40:
        idx = choose_theme_removal_index(work, dict(research_theme.get("required_counts", {})), set(research_theme.get("required_cards", [])), research_theme, rng)
        work[idx].count -= 1
        if work[idx].count <= 0:
            work.pop(idx)
    return work


def find_card_by_theme_name(name: str, card_by_name: dict[str, Card]) -> Card | None:
    if name in card_by_name:
        return card_by_name[name]
    compact = normalize_card_name(name)
    for card_name, card in card_by_name.items():
        if normalize_card_name(card_name) == compact or compact in normalize_card_name(card_name):
            return card
    return None


def normalize_card_name(name: str) -> str:
    return str(name).replace(" ", "").replace("　", "").strip()


def choose_theme_removal_index(
    deck: list[DeckCard],
    required_counts: dict[str, int],
    required_names: set[str],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> int:
    required_compact = {normalize_card_name(name) for name in required_names}
    required_count_by_compact = {normalize_card_name(name): int(count) for name, count in required_counts.items()}
    weighted: list[int] = []
    for idx, entry in enumerate(deck):
        weight = 1
        compact = normalize_card_name(entry.card.name)
        matching_required = next((req for req in required_compact if compact == req or req in compact or compact in req), "")
        if matching_required and entry.count <= required_count_by_compact.get(matching_required, 1):
            continue
        if matching_required:
            weight -= 1
        if not is_allowed_by_theme(entry.card, research_theme):
            weight += 20
        if entry.card.cost >= 7:
            weight += 5
        if entry.count == 1:
            weight += 3
        if primary_role(entry.card) not in {"attack", "lock", "defense", "resource", "removal"}:
            weight += 3
        weighted.extend([idx] * max(1, weight))
    return rng.choice(weighted) if weighted else 0


def choose_theme_fill_card(
    pool: list[Card],
    deck: list[DeckCard],
    research_theme: dict[str, Any],
    rng: random.Random,
) -> Card | None:
    current_names = {entry.card.name for entry in deck if entry.count >= 4}
    main_colors = set(research_theme.get("main_colors", []))
    deck_type = str(research_theme.get("deck_type", ""))
    scored: list[tuple[float, Card]] = []
    for card in pool:
        if card.name in current_names:
            continue
        if is_donjungle_theme(research_theme) and normalize_card_name(card.name) == normalize_card_name("ドンジャングルS7"):
            if current_card_count(deck, card) >= donjungle_s7_preferred_count(research_theme):
                continue
        score = 0.0
        civs = split_civs(card.civilization)
        if civs & main_colors:
            score += 3
        if card.name in research_theme.get("recommended_cards", []):
            score += 4
        if is_low_attack_card(card):
            score += 3 if any(k in deck_type for k in ["速攻", "中速"]) else 1
        if is_donjungle_theme(research_theme):
            if is_low_quality_donjungle_attack_card(card, research_theme):
                score -= 18.0
            if primary_role(card) == "attack" and card.cost <= 3 and not is_protected_donjungle_card(card, research_theme):
                score -= 5.0
            if primary_role(card) == "attack" and not any(
                card_contributes_to_role(card, role)
                for role in ["defense", "removal", "lock", "anti_cheat", "resource", "hand_discard"]
            ):
                score -= 6.0
            if card_contributes_to_role(card, "defense"):
                score += 5.5
            if card_contributes_to_role(card, "removal"):
                score += 6.0
            if card_contributes_to_role(card, "resource"):
                score += 1.8
            if card_contributes_to_role(card, "lock"):
                score += 5.0
            if card_contributes_to_role(card, "anti_cheat"):
                score += 3.0
        if is_resource_card(card):
            score += 3 if any(k in deck_type for k in ["コントロール", "コンボ", "中速"]) else 1
        if is_defense_card(card):
            score += 2 if "コントロール" in deck_type else 0.5
        if is_lock_card(card):
            score += 2
        if is_removal_card(card):
            score += 1.5
        if card.cost <= 4:
            score += 1.2
        if card.cost >= 7:
            score -= 3
        scored.append((score + rng.random() * 0.1, card))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored else None


def normalize_deck(deck: list[DeckCard], pool: list[Card], rng: random.Random, research_theme: dict[str, Any] | None = None) -> list[DeckCard]:
    deck = [d for d in deck if d.count > 0]
    while sum(d.count for d in deck) > 40:
        idx = choose_removal_index(deck, rng, {"コモロキシ", "緑知銀 イーアル"})
        deck[idx].count -= 1
        if deck[idx].count <= 0:
            deck.pop(idx)
    while sum(d.count for d in deck) < 40:
        card = choose_replacement(pool, deck, rng, research_theme)
        if card is None:
            break
        add_or_increment(deck, card, 1, "night-fill")
    return deck


def evaluate_candidate(
    deck_name: str,
    profile_name: str,
    deck: list[DeckCard],
    db_path: Path,
    battle_log_summary: dict[str, Any],
    video_learning_summary: dict[str, Any],
    research_theme: dict[str, Any] | None = None,
    queued_meta_seeds: list[dict[str, Any]] | None = None,
    stable_mode: bool = False,
) -> ResearchCandidate:
    audit = audit_deck(deck, db_path)
    sanity = analyze_deck_sanity(
        deck_to_sanity_input(deck),
        {
            "deck_type": research_theme.get("deck_type") if research_theme else profile_name,
            "concept": research_theme.get("name") if research_theme else profile_name,
        },
    )
    theme_fit = analyze_theme_fit(deck_to_sanity_input(deck), research_theme, sanity)
    role_snapshot = build_role_snapshot(deck, audit)
    if is_donjungle_theme(research_theme):
        theme_fit = normalize_donjungle_theme_fit_warnings(theme_fit, role_snapshot)
    strict_reasons, role_snapshot = strict_theme_gate_reasons(deck, audit, theme_fit, research_theme, battle_log_summary, stable_mode)
    reject_reasons = required_reject_reasons(deck, audit, sanity, research_theme)
    reject_reasons.extend(battle_log_reject_reasons(deck, battle_log_summary, research_theme, stable_mode))
    reject_reasons.extend(strict_reasons)
    reject_reasons = list(dict.fromkeys(reject_reasons))
    theme_fit = apply_theme_fit_penalty(theme_fit, reject_reasons)
    base_score = score_candidate(deck, audit, battle_log_summary, video_learning_summary, research_theme)
    stable_penalty, stable_warnings = stable_mode_penalty_and_warnings(deck, audit, battle_log_summary, research_theme, role_snapshot, stable_mode)
    base_score -= stable_penalty
    if stable_warnings:
        existing_control = list(theme_fit.get("control_quality_warnings", []) or [])
        for warning in stable_warnings:
            if warning not in existing_control:
                existing_control.append(warning)
        theme_fit["control_quality_warnings"] = existing_control
        theme_fit = apply_theme_fit_penalty(theme_fit, reject_reasons)
    meta_score = round(average_win_rate(audit.get("matchups", [])) * 100, 2)
    novelty_score = novelty_proxy_score(deck, sanity)
    final_fitness = combine_fitness(base_score, novelty_score, meta_score, sanity, theme_fit)
    youtube_notes = youtube_knowledge_notes(deck, video_learning_summary)
    strategy_memos = [seed_strategy_memo(seed) for seed in (queued_meta_seeds or [])[:3]]
    score = final_fitness
    theme_fit_floor = 62 if stable_mode else 70
    if research_theme and theme_fit.get("score", 100) < theme_fit_floor:
        if stable_mode and is_tier_s_meta_control_theme(research_theme):
            theme_fit.setdefault("control_quality_warnings", []).append(
                f"stable警告化: テーマらしさ不足 {theme_fit.get('score')}/{theme_fit_floor}"
            )
            theme_fit["score"] = max(float(theme_fit.get("score", 0) or 0), float(theme_fit_floor))
        else:
            reject_reasons.append(f"テーマらしさ不足: {theme_fit.get('score')}")
    pass_required = not reject_reasons
    why = build_why_selected(audit, score, pass_required, sanity, theme_fit)
    return ResearchCandidate(
        deck_name,
        profile_name,
        deck,
        audit,
        score,
        final_fitness,
        base_score,
        novelty_score,
        meta_score,
        sanity,
        theme_fit,
        role_snapshot,
        youtube_notes,
        strategy_memos,
        pass_required,
        reject_reasons,
        why,
    )


def deck_to_sanity_input(deck: list[DeckCard]) -> list[dict[str, Any]]:
    return [
        {
            "count": entry.count,
            "quantity": entry.count,
            "card_id": entry.card.card_id,
            "name": entry.card.name,
            "civilization": entry.card.civilization,
            "cost": entry.card.cost,
            "card_type": entry.card.card_type,
            "power": entry.card.power,
            "race": entry.card.race,
            "text": entry.card.text,
            "tags": sorted(entry.card.tags),
        }
        for entry in deck
    ]



def has_any_keyword(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def card_text_blob(card: Card) -> str:
    return " ".join(
        [
            str(card.name or ""),
            str(card.card_type or ""),
            str(card.race or ""),
            str(card.text or ""),
            " ".join(sorted(card.tags or [])),
        ]
    )


def count_role_cards(deck: list[DeckCard], role: str) -> int:
    """テーマ足切り用の役割枚数を、タグ・本文・既存判定関数から広めに数える。"""
    total = 0
    for entry in deck:
        card = entry.card
        blob = card_text_blob(card)
        matched = False
        if role == "defense":
            matched = is_defense_card(card) or has_any_keyword(
                blob,
                ["受け札", "防御", "S・トリガー", "Sトリガー", "シールド・トリガー", "トリガー", "除去"],
            )
        elif role == "resource":
            matched = is_resource_card(card) or has_any_keyword(
                blob,
                ["リソース", "ドロー", "カードを引", "手札", "墓地回収", "回収", "探索", "サーチ", "マナ回収"],
            )
        elif role == "mana_boost":
            matched = has_any_keyword(
                blob,
                ["マナ加速", "ブースト", "マナブースト", "マナゾーンに置", "マナゾーンへ置", "マナゾーンから", "チャージャー"],
            )
        elif role == "anti_cheat":
            matched = has_any_keyword(
                blob,
                ["踏み倒しメタ", "コストを支払わず", "召喚できない", "出せない", "バトルゾーンに出せない", "コスト踏み倒し", "メタ"],
            )
        elif role == "hand_discard":
            matched = has_any_keyword(
                blob,
                ["ハンデス", "手札破壊", "手札を", "捨て", "見ないで選び", "相手の手札"],
            )
        elif role == "removal":
            matched = is_removal_card(card) or has_any_keyword(
                blob,
                ["除去", "破壊", "マナ送り", "バウンス", "シールド送り", "山札の下", "パワー低下", "タップ"]
            )
        elif role == "lock":
            matched = is_lock_card(card) or has_any_keyword(
                blob,
                ["ロック", "攻撃できない", "攻撃制限", "召喚できない", "出せない", "呪文を唱えられない"],
            )
        if matched:
            total += int(entry.count or 0)
    return total


def count_card_by_name(deck: list[DeckCard], name_keyword: str) -> int:
    keyword = normalize_card_name(name_keyword)
    total = 0
    for entry in deck:
        name = normalize_card_name(entry.card.name)
        if keyword == name or keyword in name or name in keyword:
            total += int(entry.count or 0)
    return total


def build_role_snapshot(deck: list[DeckCard], audit: dict[str, Any] | None = None) -> dict[str, int]:
    audit = audit or {}
    secondary = audit.get("secondary_counts", {}) or {}
    primary = audit.get("primary_counts", {}) or {}
    snapshot = {
        "defense": max(int(secondary.get("defense", 0) or 0), count_role_cards(deck, "defense")),
        "resource": max(int(secondary.get("resource", 0) or 0), count_role_cards(deck, "resource")),
        "mana_boost": count_role_cards(deck, "mana_boost"),
        "anti_cheat": count_role_cards(deck, "anti_cheat"),
        "hand_discard": count_role_cards(deck, "hand_discard"),
        "removal": max(int(secondary.get("removal", 0) or 0), int(primary.get("removal", 0) or 0), count_role_cards(deck, "removal")),
        "lock": max(int(secondary.get("lock", 0) or 0), int(primary.get("lock", 0) or 0), count_role_cards(deck, "lock")),
        "donjungle_s7": count_card_by_name(deck, "ドンジャングルS7"),
    }
    return snapshot


def normalize_reject_reason(reason: str) -> str:
    text = str(reason).strip()
    if not text:
        return "不明"
    return text.split(":", 1)[0].strip()


def normalize_donjungle_theme_fit_warnings(
    theme_fit: dict[str, Any],
    role_snapshot: dict[str, int],
) -> dict[str, Any]:
    """
    黒緑ドンジャングル専用補正。
    analyze_theme_fit 側のタグ判定が 0/required になっていても、
    strict role_snapshot 側で必要枚数を満たしている場合は警告から外す。
    """
    adjusted = dict(theme_fit or {})
    warnings = list(adjusted.get("warnings", []) or [])

    requirements = {
        "受け札": ("defense", 6),
        "リソース": ("resource", 6),
        "マナ加速": ("mana_boost", 4),
        "踏み倒しメタ": ("anti_cheat", 4),
        "ハンデス": ("hand_discard", 3),
        "ドンジャングルS7": ("donjungle_s7", 2),
    }

    filtered: list[str] = []

    for warning in warnings:
        text = str(warning)
        should_remove = False

        for label, (role_key, required) in requirements.items():
            if label in text:
                actual = int(role_snapshot.get(role_key, 0) or 0)
                if actual >= required:
                    should_remove = True
                break

        if not should_remove:
            filtered.append(text)

    adjusted["warnings"] = filtered

    # 必須役割の誤警告が全て消えた場合は、テーマ成立ラインまで戻す。
    # 元の analyze_theme_fit の score は保持しつつ、strict gate の過剰減点を防ぐ。
    if not filtered and float(adjusted.get("score", 0) or 0) < 70:
        adjusted["score"] = 75.0

    return adjusted


def donjungle_control_quality_warnings(
    audit: dict[str, Any],
    role_snapshot: dict[str, int],
) -> tuple[list[str], list[str]]:
    """黒緑ドンジャングルをビート寄りにしすぎないための品質ゲート。"""
    primary = audit.get("primary_counts", {}) or {}
    primary_attack = int(primary.get("attack", 0) or 0)
    low_attack = int(audit.get("low_primary_attack_count", 0) or 0)
    defense = int(role_snapshot.get("defense", 0) or 0)
    removal = int(role_snapshot.get("removal", 0) or 0)
    resource = int(role_snapshot.get("resource", 0) or 0)
    lock = int(role_snapshot.get("lock", 0) or 0)

    reject_reasons: list[str] = []
    warnings: list[str] = []

    if primary_attack >= 28:
        reject_reasons.append(f"攻撃札過多: {primary_attack}/27")
    elif primary_attack >= 24:
        warnings.append(f"攻撃札多め: {primary_attack}/23")

    if low_attack >= 24:
        warnings.append(f"低コスト攻撃札過多: {low_attack}/23")
    if defense < 8:
        warnings.append(f"受け札やや薄い: {defense}/8")
        if defense <= 6:
            warnings.append(f"火光レイド後攻リスク: 受け札{defense}/8")
    if removal < 6:
        warnings.append(f"除去やや不足: {removal}/6")
    if resource < 10:
        warnings.append(f"リソース推奨未満: {resource}/10")

    # Tier S 火光レイド/ブランドを登録した後の専用ゲート。
    # ここは「落とす条件」ではなく、Rank内の並び替えに使う軽い警告に留める。
    # 強くしすぎると候補が全滅するため、閾値とペナルティを抑える。
    if primary_attack >= 24:
        warnings.append(f"Tier S対策不足: 小型attack寄り {primary_attack}/23")
    if low_attack >= 24:
        warnings.append(f"Tier S対策不足: 低コストattack過多 {low_attack}/23")
    if lock < 4:
        warnings.append(f"Tier S対策不足: 攻撃制限/ロック薄い {lock}/4")
    if removal < 6:
        warnings.append(f"Tier S対策不足: B我/ブランド除去薄い {removal}/6")

    return reject_reasons, warnings


def strict_theme_gate_reasons(
    deck: list[DeckCard],
    audit: dict[str, Any],
    theme_fit: dict[str, Any],
    research_theme: dict[str, Any] | None,
    battle_log_summary: dict[str, Any] | None = None,
    stable_mode: bool = False,
) -> tuple[list[str], dict[str, int]]:
    if research_theme is None:
        return [], build_role_snapshot(deck, audit)

    reasons: list[str] = []
    role_snapshot = build_role_snapshot(deck, audit)
    deck_type = str(research_theme.get("deck_type", ""))
    theme_name = str(research_theme.get("name", ""))
    warnings = theme_fit.get("warnings", []) or []
    if not isinstance(warnings, list):
        warnings = [str(warnings)]

    if deck_type == "コントロール":
        if role_snapshot["defense"] <= 0:
            reasons.append("受け札不足")
        if role_snapshot["resource"] <= 0:
            reasons.append("リソース不足")

    reasons.extend(theme_required_count_reject_reasons(deck, research_theme, stable_mode))

    if is_tier_s_meta_control_theme(research_theme):
        minimums = tier_s_meta_minimums(research_theme)
        for key, required in minimums.items():
            actual = int(role_snapshot.get(key, 0) or 0)
            if actual < required:
                if stable_mode:
                    theme_fit.setdefault("control_quality_warnings", []).append(f"stable警告化: Tier Sメタ役割不足: {key} {actual}/{required}")
                else:
                    reasons.append(f"Tier Sメタ役割不足: {key} {actual}/{required}")
        donjungle_count = count_card_by_name(deck, "ドンジャングルS7")
        if donjungle_count >= 2:
            if stable_mode:
                theme_fit.setdefault("control_quality_warnings", []).append(f"ドンジャングルS7 2枚以上: 高コスト到達不能リスク {donjungle_count}/1")
            else:
                reasons.append(f"ドンジャングルS7過多: {donjungle_count}/1")
        primary_attack = int((audit.get("primary_counts", {}) or {}).get("attack", 0) or 0)
        if primary_attack >= 24:
            if stable_mode:
                theme_fit.setdefault("control_quality_warnings", []).append(f"stable警告化: primary attack過多: {primary_attack}/23")
            else:
                reasons.append(f"primary attack過多: {primary_attack}/23")
        elif primary_attack > 20:
            theme_fit.setdefault("control_quality_warnings", []).append(f"primary attack推奨超過: {primary_attack}/20")
        resistance = calculate_tier_s_second_resistance_score(role_snapshot, deck, audit)
        theme_fit["tier_s_second_resistance_score"] = resistance
        if resistance < 60:
            theme_fit.setdefault("control_quality_warnings", []).append(f"Tier S後攻耐性スコア低め: {resistance}/100")

    if theme_name == "黒緑ドンジャングル":
        minimums = {
            "defense": (6, "受け札不足"),
            "resource": (6, "リソース不足"),
            "mana_boost": (4, "マナ加速不足"),
            "anti_cheat": (4, "踏み倒しメタ不足"),
            "hand_discard": (3, "ハンデス不足"),
            "donjungle_s7": (donjungle_s7_min_count(research_theme), "ドンジャングルS7不足"),
        }
        for key, (required, label) in minimums.items():
            actual = int(role_snapshot.get(key, 0) or 0)
            if actual < required:
                reasons.append(f"{label}: {actual}/{required}")

        control_rejects, control_warnings = donjungle_control_quality_warnings(audit, role_snapshot)
        if stable_mode:
            softened_rejects = []
            for reason in control_rejects:
                if "攻撃札過多" in reason:
                    control_warnings.append("stable減点: " + reason)
                else:
                    softened_rejects.append(reason)
            control_rejects = softened_rejects
        reasons.extend(control_rejects)
        if control_warnings:
            existing_control = list(theme_fit.get("control_quality_warnings", []) or [])
            for warning in control_warnings:
                if warning not in existing_control:
                    existing_control.append(warning)
            theme_fit["control_quality_warnings"] = existing_control

    if len(warnings) >= 3:
        if stable_mode and is_tier_s_meta_control_theme(research_theme):
            theme_fit.setdefault("control_quality_warnings", []).append(f"stable警告化: テーマ警告過多: {len(warnings)}件")
        else:
            reasons.append(f"テーマ警告過多: {len(warnings)}件")

    return reasons, role_snapshot


def apply_theme_fit_penalty(theme_fit: dict[str, Any], reject_reasons: list[str]) -> dict[str, Any]:
    adjusted = dict(theme_fit or {})
    original_score = float(adjusted.get("score", 100) or 0)
    penalty = 0.0
    for reason in reject_reasons:
        if "攻撃札過多" in reason:
            penalty += 22.0
        elif "不足" in reason:
            penalty += 18.0
        elif "警告過多" in reason:
            penalty += 12.0
    warning_count = len(adjusted.get("warnings", []) or [])
    control_warnings = list(adjusted.get("control_quality_warnings", []) or [])
    tier_s_warnings = [w for w in control_warnings if "Tier S対策不足" in str(w)]
    normal_control_warnings = [w for w in control_warnings if "Tier S対策不足" not in str(w)]

    penalty += warning_count * 4.0
    # 通常の品質警告は従来通り。Tier S警告は全滅防止のため軽く扱う。
    penalty += len(normal_control_warnings) * 3.0
    penalty += len(tier_s_warnings) * 0.8

    for warning in normal_control_warnings:
        text = str(warning)
        if "受け札やや薄い" in text:
            penalty += 4.0
        if "火光レイド後攻リスク" in text:
            penalty += 6.0

    for warning in tier_s_warnings:
        text = str(warning)
        if "小型attack寄り" in text or "低コストattack過多" in text:
            penalty += 0.4
        if "攻撃制限/ロック薄い" in text:
            penalty += 0.8
        if "B我/ブランド除去薄い" in text:
            penalty += 1.0
    adjusted["original_score"] = original_score
    adjusted["score"] = round(max(0.0, original_score - penalty), 2)
    adjusted["strict_gate_penalty"] = round(penalty, 2)
    return adjusted


def stable_mode_penalty_and_warnings(
    deck: list[DeckCard],
    audit: dict[str, Any],
    summary: dict[str, Any],
    research_theme: dict[str, Any] | None,
    role_snapshot: dict[str, int],
    stable_mode: bool,
) -> tuple[float, list[str]]:
    if not stable_mode:
        return 0.0, []

    penalty = 0.0
    warnings: list[str] = []
    primary = audit.get("primary_counts", {}) or {}
    primary_attack = int(primary.get("attack", 0) or 0)
    weak = normalize_card_count_items(summary.get("weak_cards", []))
    dead = normalize_card_count_items(summary.get("dead_cards", []))

    for item in card_count_items_in_deck(deck, weak, threshold=2.99):
        name = item["name"]
        count = float(item["count"])
        if count >= 5 and not is_battle_log_protected_card_name(name, research_theme):
            # 5回以上の非必須weakは battle_log_reject_reasons 側でreject。
            continue
        if count >= 3:
            card_penalty = count * float(item.get("deck_count", 1)) * 1.8
            penalty += card_penalty
            warnings.append(f"実戦ログ減点カード: {name}({int(count)}回)")

    for item in card_count_items_in_deck(deck, dead, threshold=4.99):
        name = item["name"]
        count = float(item["count"])
        if is_battle_log_protected_card_name(name, research_theme) or "ドンジャングルS7" in normalize_card_name(name):
            penalty += count * 1.2
            warnings.append(f"枚数調整候補: {name} dead_cards {int(count)}回")
            warnings.append(f"高コスト到達不能リスク: {name}")
        else:
            penalty += count * float(item.get("deck_count", 1)) * 1.5
            warnings.append(f"腐り減点カード: {name}({int(count)}回)")

    if primary_attack >= 26:
        penalty += 10.0
        warnings.append(f"primary attack強警告: {primary_attack}/25")
    elif primary_attack >= 24:
        penalty += 5.0
        warnings.append(f"primary attack警告: {primary_attack}/23")
    elif primary_attack >= 23:
        penalty += 2.5
        warnings.append(f"primary attack軽度減点: {primary_attack}/22")

    if is_donjungle_theme(research_theme):
        defense = int(role_snapshot.get("defense", 0) or 0)
        lock = int(role_snapshot.get("lock", 0) or 0)
        removal = int(role_snapshot.get("removal", 0) or 0)
        anti_cheat = int(role_snapshot.get("anti_cheat", 0) or 0)
        resource = int(role_snapshot.get("resource", 0) or 0)
        if defense < 8:
            penalty += (8 - defense) * 2.5
            warnings.append(f"Tier S後攻リスク: defense {defense}/8")
        if lock < 5:
            penalty += (5 - lock) * 2.0
            warnings.append(f"Tier S後攻リスク: lock {lock}/5")
        if removal < 6:
            penalty += (6 - removal) * 2.0
            warnings.append(f"Tier S後攻リスク: removal {removal}/6")
        if anti_cheat < 4:
            penalty += (4 - anti_cheat) * 3.0
            warnings.append(f"Tier S後攻リスク: anti_cheat {anti_cheat}/4")
        if resource < 10:
            warnings.append(f"リソース厚み確認: resource {resource}/10")

    if is_tier_s_meta_control_theme(research_theme):
        minimums = tier_s_meta_minimums(research_theme)
        for role, required in minimums.items():
            actual = int(role_snapshot.get(role, 0) or 0)
            if actual < required:
                penalty += (required - actual) * 1.6
                warnings.append(f"Tier S後攻リスク: {role} {actual}/{required}")
        resistance = calculate_tier_s_second_resistance_score(role_snapshot, deck, audit)
        if resistance < 70:
            penalty += (70 - resistance) * 0.25
            warnings.append(f"Tier S後攻耐性スコア低め: {resistance}/100")
        donjungle_count = count_card_by_name(deck, "ドンジャングルS7")
        if donjungle_count >= 2:
            penalty += 15.0
            warnings.append(f"高コスト到達不能リスク: ドンジャングルS7 {donjungle_count}/1")

    return round(penalty, 2), warnings


def required_reject_reasons(
    deck: list[DeckCard],
    audit: dict[str, Any],
    sanity: dict[str, Any],
    research_theme: dict[str, Any] | None = None,
) -> list[str]:
    stats = audit.get("stats", {})
    primary = audit.get("primary_counts", {})
    effective_supply = audit.get("effective_supply", {})
    matchups = audit.get("matchups", [])
    avg_meta = average_win_rate(matchups)
    den = denjadeon_rate(matchups)
    reasons: list[str] = []
    if stats.get("deck_size") != 40:
        reasons.append("40枚ではない")
    if stats.get("avg_cost", 99) > 4.2:
        reasons.append("重すぎる")
    if stats.get("high_cost", 99) > 4:
        reasons.append("高コスト過多")
    if effective_supply.get("水", 0) > 0 and effective_supply.get("水", 0) < 8:
        reasons.append("水文明色事故")
    for risk in minority_civilization_risks(deck, audit):
        if risk["demand"] >= 4 and risk["supply"] < 8:
            reasons.append(f"{risk['civilization']}文明供給不足")
        elif risk["demand"] <= 3 and risk["supply"] < 4 and risk["key_role"]:
            reasons.append(f"{risk['civilization']}タッチ必須札リスク")
    deck_type = str(research_theme.get("deck_type", "") if research_theme else "")
    is_aggressive_theme = any(key in deck_type for key in ["速攻", "アグロ", "ビート", "中速"])
    if research_theme is None or is_aggressive_theme:
        if primary.get("attack", 0) < 20:
            reasons.append("攻撃札不足")
        if audit.get("low_primary_attack_count", 0) < 16:
            reasons.append("2〜4コスト攻撃札不足")
    if max(effective_supply.values() or [0]) < 16:
        reasons.append("主文明供給不足")
    if research_theme is None and den < 0.50:
        reasons.append("デンジャデオン勝率不足")
    if research_theme is None and avg_meta < 0.55:
        reasons.append("メタ平均勝率不足")
    if db_missing_count(audit) > 0:
        reasons.append("DB未存在カード")
    if sanity.get("fatal_issues"):
        reasons.extend(f"成立性fatal: {issue}" for issue in sanity.get("fatal_issues", []))
    if sanity.get("score", 0) < 70:
        reasons.append(f"成立性スコア不足: {sanity.get('score', 0)}")
    metrics = sanity.get("metrics", {})
    if not metrics.get("main_axis_cards"):
        reasons.append("主軸カード不足")
    if metrics.get("color_count", 0) >= 4:
        reasons.append("文明過多")
    reasons.extend(theme_reject_reasons(deck, sanity, research_theme))
    return reasons


def theme_reject_reasons(deck: list[DeckCard], sanity: dict[str, Any], research_theme: dict[str, Any] | None) -> list[str]:
    if research_theme is None:
        return []
    reasons: list[str] = []
    allowed = set(research_theme.get("allowed_colors", []))
    main = set(research_theme.get("main_colors", []))
    metrics = sanity.get("metrics", {})
    if allowed:
        off_theme = [
            entry.card.name
            for entry in deck
            if split_civs(entry.card.civilization) and not split_civs(entry.card.civilization) <= allowed
        ]
        if off_theme:
            reasons.append("テーマ外文明カード混入: " + "、".join(off_theme[:5]))
    for civ in main:
        if float(metrics.get("effective_supply", {}).get(civ, 0) or 0) < 8:
            reasons.append(f"テーマ主文明供給不足: {civ}")

    present = {normalize_card_name(entry.card.name): entry.count for entry in deck}
    missing_required: list[str] = []
    for name in research_theme.get("_available_required_cards", research_theme.get("required_cards", [])):
        compact = normalize_card_name(name)
        if not any(compact == present_name or compact in present_name or present_name in compact for present_name in present):
            missing_required.append(name)
    if missing_required:
        reasons.append("テーマ必須カード不足: " + "、".join(missing_required[:5]))

    forbidden_card_hits = [entry.card.name for entry in deck if is_forbidden_theme_card_name(entry.card.name, research_theme)]
    if forbidden_card_hits:
        reasons.append("テーマ禁止カード混入: " + "、".join(forbidden_card_hits[:5]))

    forbidden = set(research_theme.get("forbidden_patterns", []))
    if "文明過多" in forbidden and metrics.get("color_count", 0) > len(allowed or main):
        reasons.append("テーマ禁止条件: 文明過多")
    if "主軸なし" in forbidden and not metrics.get("main_axis_cards"):
        reasons.append("テーマ禁止条件: 主軸なし")
    if "ピン挿し過多" in forbidden and int(metrics.get("one_of_count", 0) or 0) > 10:
        reasons.append("テーマ禁止条件: ピン挿し過多")
    if "重すぎる" in forbidden and metrics.get("high_cost_count", 0) > 4:
        reasons.append("テーマ禁止条件: 重すぎる")
    return reasons


def novelty_proxy_score(deck: list[DeckCard], sanity: dict[str, Any]) -> float:
    metrics = sanity.get("metrics", {})
    one_of = int(metrics.get("one_of_count", 0) or 0)
    color_count = int(metrics.get("color_count", 0) or 0)
    axis_count = len(metrics.get("main_axis_cards", []) or [])
    score = 55 + min(20, axis_count * 4)
    score += min(10, len({entry.card.name for entry in deck if entry.card.cost <= 3}))
    score -= max(0, one_of - 10) * 1.5
    score -= max(0, color_count - 3) * 8
    return round(max(0, min(100, score)), 2)


def combine_fitness(
    base_score: float,
    novelty_score: float,
    meta_score: float,
    sanity: dict[str, Any],
    theme_fit: dict[str, Any] | None = None,
) -> float:
    sanity_score = float(sanity.get("score", 0) or 0)
    theme_fit_score = float((theme_fit or {}).get("score", 100) or 0)
    normalized_base = max(0.0, min(100.0, base_score))
    fitness = (
        normalized_base * 0.25
        + novelty_score * 0.10
        + meta_score * 0.20
        + sanity_score * 0.25
        + theme_fit_score * 0.20
    )
    if sanity.get("fatal_issues") or sanity_score < 60 or theme_fit_score < 60:
        fitness = min(fitness, sanity_score, theme_fit_score)
    return round(max(0.0, min(100.0, fitness)), 2)


def score_candidate(
    deck: list[DeckCard],
    audit: dict[str, Any],
    battle_log_summary: dict[str, Any],
    video_learning_summary: dict[str, Any],
    research_theme: dict[str, Any] | None = None,
) -> float:
    stats = audit.get("stats", {})
    primary = audit.get("primary_counts", {})
    secondary = audit.get("secondary_counts", {})
    matchups = audit.get("matchups", [])
    avg_meta = average_win_rate(matchups)
    min_meta = min_win_rate(matchups)
    den = denjadeon_rate(matchups)
    raid = average_for_opponents(matchups, ["レイド"])
    scholar = average_for_opponents(matchups, ["スコーラー"])
    warning_count = len(audit.get("warnings", []))
    color_issue_count = sum(1 for w in audit.get("warnings", []) if "文明" in w or "水要求" in w)
    overtagged_count = len(audit.get("overtagged_cards", []))
    high_cost_penalty = max(0, stats.get("high_cost", 0) - 2) * 3
    score = (
        saturated_rate_score(avg_meta) * 60
        + saturated_rate_score(min_meta) * 40
        + saturated_rate_score(den) * 20
        + saturated_rate_score(raid) * 10
        + saturated_rate_score(scholar) * 10
        + min(primary.get("attack", 0), 30) * 0.6
        + min(audit.get("low_primary_attack_count", 0), 28) * 0.5
        + min(secondary.get("defense", 0), 16) * 0.35
        + min(secondary.get("resource", 0), 14) * 0.25
        + min(secondary.get("lock", 0), 14) * 0.25
        - warning_count * 5
        - color_issue_count * 8
        - db_missing_count(audit) * 20
        - high_cost_penalty
        - overtagged_count * 1.5
        - max(0, stats.get("avg_cost", 0) - 3.8) * 10
    )
    for risk in minority_civilization_risks(deck, audit):
        if risk["demand"] <= 3 and risk["supply"] < 4:
            score -= 10 if risk["key_role"] else 4
        elif risk["demand"] >= 4 and risk["supply"] < 8:
            score -= 18
        elif risk["demand"] >= 8 and risk["supply"] < 10:
            score -= 6
    score += battle_log_adjustment_for_deck(deck, battle_log_summary, research_theme)
    score += video_learning_adjustment(deck, video_learning_summary)
    score += theme_penalty_adjustment(deck, audit, research_theme)
    if is_donjungle_theme(research_theme):
        attack_count = int(primary.get("attack", 0) or 0)
        if attack_count <= 21:
            score += 2.0
        elif attack_count >= 26:
            score -= 22.0
        elif attack_count >= 24:
            score -= 12.0
        elif attack_count >= 23:
            score -= 7.0
        else:
            score -= 3.0
        trap_count = donjungle_trap_x_trap_count(deck)
        if trap_count <= 2:
            score -= (3 - trap_count) * 8.0
        donjungle_count = count_card_by_name(deck, "ドンジャングルS7")
        donjungle_dead = float(research_theme.get("_donjungle_s7_dead_count", 0) or 0)
        if donjungle_dead >= 10 and donjungle_count >= 3:
            score -= 9.0
        if donjungle_count <= 1:
            score -= 40.0
    return round(score, 2)


def normalize_card_count_items(items: Any) -> dict[str, float]:
    """
    final_test_logger の集計形式差を吸収する。
    対応形式:
    - [{"name": "...", "count": 3}]
    - [["...", 3]]
    - [("...", 3)]
    """
    out: dict[str, float] = {}
    for item in items or []:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            count = float(item.get("count", 0) or 0)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            name = str(item[0]).strip()
            count = float(item[1] or 0)
        else:
            continue
        if name:
            out[name] = out.get(name, 0.0) + count
    return out


def matched_signal_count(card_name: str, counts: dict[str, float]) -> float:
    compact = normalize_card_name(card_name)
    total = 0.0
    for name, count in counts.items():
        other = normalize_card_name(name)
        if compact == other or compact in other or other in compact:
            total += float(count or 0)
    return total


def card_count_items_in_deck(deck: list[DeckCard], counts: dict[str, float], threshold: float = 0.0) -> list[dict[str, Any]]:
    rows = []
    seen: set[str] = set()
    for entry in deck:
        value = matched_signal_count(entry.card.name, counts)
        if value <= threshold:
            continue
        if entry.card.name in seen:
            continue
        seen.add(entry.card.name)
        rows.append({"name": entry.card.name, "count": int(value) if float(value).is_integer() else value, "deck_count": entry.count})
    return sorted(rows, key=lambda item: (-float(item["count"]), item["name"]))


def is_battle_log_protected_card_name(name: str, research_theme: dict[str, Any] | None) -> bool:
    """実戦ログで弱くても、テーマ必須カードは自動除外しない。"""
    if not research_theme:
        return False
    compact = normalize_card_name(name)
    extra_protected = ["ドンジャングルS7"] if is_donjungle_theme(research_theme) else []
    protected = {
        normalize_card_name(card_name)
        for card_name in list(research_theme.get("required_cards", [])) + extra_protected
    }
    return any(compact == item or compact in item or item in compact for item in protected)


def battle_log_excluded_card_counts(
    summary: dict[str, Any],
    research_theme: dict[str, Any] | None,
    threshold: float = 5.0,
) -> dict[str, float]:
    """weak_cards に一定回数以上出た非必須カードを、上位候補から除外する。

    9戦ログ以降は 3回以上を即rejectにすると探索空間が全滅しやすい。
    5回以上は実戦弱カードとして除外し、3〜4回のカードは
    battle_log_adjustment_for_deck() のスコア減点に任せる。
    """
    weak = normalize_card_count_items(summary.get("weak_cards", []))
    excluded: dict[str, float] = {}
    for name, count in weak.items():
        if count >= threshold and not is_battle_log_protected_card_name(name, research_theme):
            excluded[name] = count
    return excluded


def battle_log_excluded_card_items(
    summary: dict[str, Any],
    research_theme: dict[str, Any] | None,
    threshold: float = 5.0,
) -> list[dict[str, Any]]:
    excluded = battle_log_excluded_card_counts(summary, research_theme, threshold)
    return [
        {"name": name, "count": int(count) if float(count).is_integer() else count}
        for name, count in sorted(excluded.items(), key=lambda item: (-item[1], item[0]))
    ]


def battle_log_penalty_card_items(
    summary: dict[str, Any],
    research_theme: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    weak = normalize_card_count_items(summary.get("weak_cards", []))
    rows = []
    for name, count in weak.items():
        if 3 <= count < 5 or (count >= 3 and is_battle_log_protected_card_name(name, research_theme)):
            rows.append({"name": name, "count": int(count) if float(count).is_integer() else count})
    return sorted(rows, key=lambda item: (-float(item["count"]), item["name"]))


def dead_card_adjustment_items(
    summary: dict[str, Any],
    research_theme: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    dead = normalize_card_count_items(summary.get("dead_cards", []))
    rows = []
    for name, count in dead.items():
        if count >= 5 and (is_battle_log_protected_card_name(name, research_theme) or "ドンジャングルS7" in normalize_card_name(name)):
            rows.append({"name": name, "count": int(count) if float(count).is_integer() else count})
    return sorted(rows, key=lambda item: (-float(item["count"]), item["name"]))


def tier_s_second_play_risk_text(summary: dict[str, Any]) -> str:
    risks = []
    for row in summary.get("by_opponent", []) or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", ""))
        matches = int(row.get("matches", 0) or 0)
        wins = int(row.get("wins", 0) or 0)
        if ("火光レイド" in key or "ブランド" in key or "Tier S" in key) and matches >= 3 and wins == 0:
            risks.append(f"{key}: 0勝{matches}敗")
    for row in summary.get("by_play_order", []) or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", ""))
        matches = int(row.get("matches", 0) or 0)
        wins = int(row.get("wins", 0) or 0)
        if "後攻" in key and matches >= 3 and wins == 0:
            risks.append(f"{key}: 0勝{matches}敗")
    return " / ".join(risks) if risks else "明確な0勝リスクなし"


def battle_log_reject_reasons(
    deck: list[DeckCard],
    summary: dict[str, Any],
    research_theme: dict[str, Any] | None,
    stable_mode: bool = False,
) -> list[str]:
    """実戦で5回以上弱かった非必須カードを含む候補は、Rank上位から外す。

    3〜4回の弱カードは完全除外せず、スコア減点で順位を下げる。
    これにより暗黒獣ヤミノシーザー/ラピスのような3回弱カードで
    夜間耐久が全滅するのを防ぐ。
    """
    if summary.get("total_matches", 0) <= 0:
        return []
    excluded = battle_log_excluded_card_counts(summary, research_theme)
    if not excluded:
        return []

    reasons: list[str] = []
    deck_counts = {normalize_card_name(entry.card.name): entry.card.name for entry in deck if int(entry.count or 0) > 0}
    for weak_name, weak_count in excluded.items():
        weak_compact = normalize_card_name(weak_name)
        matched = next(
            (
                original_name
                for compact_name, original_name in deck_counts.items()
                if weak_compact == compact_name or weak_compact in compact_name or compact_name in weak_compact
            ),
            "",
        )
        if matched:
            reasons.append(f"実戦弱カード混入: {matched}({int(weak_count)}回)")
    return reasons


def battle_log_adjustment(audit: dict[str, Any], summary: dict[str, Any]) -> float:
    """後方互換用。監査結果に含まれる候補カードだけを見る旧式の補正。"""
    if summary.get("total_matches", 0) <= 0:
        return 0.0
    names = set()
    for row in audit.get("denjadeon_cards", []):
        names.add(row.get("name", ""))
    adjustment = 0.0
    strong = normalize_card_count_items(summary.get("strong_cards", []))
    weak = normalize_card_count_items(summary.get("weak_cards", []))
    dead = normalize_card_count_items(summary.get("dead_cards", []))
    for name in names:
        adjustment += strong.get(name, 0) * 1.0
        adjustment -= weak.get(name, 0) * 1.5
        adjustment -= dead.get(name, 0) * 2.0
    adjustment -= float(summary.get("mana_color_issue_rate", 0) or 0) * 5
    return adjustment


def battle_log_adjustment_for_deck(
    deck: list[DeckCard],
    summary: dict[str, Any],
    research_theme: dict[str, Any] | None = None,
) -> float:
    """
    実戦ログを候補デッキ全体へ直接反映する。
    weak/dead に出たカードを含む候補は強めに下げ、strong に出たカードを含む候補は上げる。
    """
    if summary.get("total_matches", 0) <= 0:
        return 0.0

    strong = normalize_card_count_items(summary.get("strong_cards", []))
    weak = normalize_card_count_items(summary.get("weak_cards", []))
    dead = normalize_card_count_items(summary.get("dead_cards", []))

    adjustment = 0.0
    for entry in deck:
        name = entry.card.name
        count = min(int(entry.count or 0), 4)
        strong_count = matched_signal_count(name, strong)
        weak_count = matched_signal_count(name, weak)
        dead_count = matched_signal_count(name, dead)
        protected = is_battle_log_protected_card_name(name, research_theme) or "ドンジャングルS7" in normalize_card_name(name)

        adjustment += strong_count * count * 1.2
        if weak_count >= 5:
            adjustment -= weak_count * count * 3.4
        elif weak_count >= 3:
            adjustment -= weak_count * count * 2.6
        else:
            adjustment -= weak_count * count * 1.6

        if dead_count >= 5 and protected:
            adjustment -= dead_count * count * 0.8
        else:
            adjustment -= dead_count * count * 2.0

    # レイド対面、とくに後攻で負けが重なっている場合は、受け札不足をさらに重く見る。
    by_opponent = summary.get("by_opponent", []) or []
    raid_loss_signal = False
    for row in by_opponent:
        if isinstance(row, dict):
            key = str(row.get("key", ""))
            matches = int(row.get("matches", 0) or 0)
            win_rate = float(row.get("win_rate", 100) or 0)
        elif isinstance(row, (list, tuple)) and len(row) >= 4:
            key = str(row[0])
            matches = int(row[1] or 0)
            win_rate = float(row[3] or 0)
        else:
            continue
        if "レイド" in key and matches >= 2 and win_rate < 50:
            raid_loss_signal = True
            break
    if raid_loss_signal:
        defense_count = count_role_cards(deck, "defense")
        if defense_count < 8:
            adjustment -= (8 - defense_count) * 4.0

    adjustment -= float(summary.get("mana_color_issue_rate", 0) or 0) * 5
    return adjustment


def video_learning_adjustment(deck: list[DeckCard], summary: dict[str, Any]) -> float:
    if summary.get("log_count", 0) <= 0:
        return 0.0
    strong = summary.get("strong_card_scores", {})
    weak = summary.get("weak_card_scores", {})
    dead = summary.get("dead_card_scores", {})
    keep = summary.get("keep_card_scores", {})
    adjustment = 0.0
    for entry in deck:
        name = entry.card.name
        adjustment += float(strong.get(name, 0)) * min(entry.count, 4) * 0.7
        adjustment += float(keep.get(name, 0)) * min(entry.count, 4) * 0.4
        adjustment -= float(weak.get(name, 0)) * min(entry.count, 4) * 0.8
        adjustment -= float(dead.get(name, 0)) * min(entry.count, 4) * 1.2
    return adjustment


def db_missing_count(_audit: dict[str, Any]) -> int:
    # 候補はDBから作るため通常0。将来の外部インポートに備えた拡張点。
    return 0


def average_win_rate(matchups: list[dict[str, Any]]) -> float:
    rates = [float(m.get("estimated_win_rate", 0)) for m in matchups]
    return sum(rates) / len(rates) if rates else 0.0


def min_win_rate(matchups: list[dict[str, Any]]) -> float:
    rates = [float(m.get("estimated_win_rate", 0)) for m in matchups]
    return min(rates) if rates else 0.0


def saturated_rate_score(rate: float) -> float:
    """Diminish extra credit from proxy win rates that hit the 80% display cap."""
    rate = max(0.0, min(1.0, rate))
    if rate <= 0.75:
        return rate
    return 0.75 + (rate - 0.75) * 0.25


def minority_civilization_risks(deck: list[DeckCard], audit: dict[str, Any]) -> list[dict[str, Any]]:
    effective = audit.get("effective_supply", {})
    demand = {civ: 0 for civ in ["光", "水", "闇", "火", "自然"]}
    cards_by_civ: dict[str, list[dict[str, Any]]] = {civ: [] for civ in demand}
    for entry in deck:
        civs = split_civs(entry.card.civilization)
        for civ in civs:
            demand[civ] += entry.count
            role = primary_role(entry.card)
            cards_by_civ[civ].append(
                {
                    "name": entry.card.name,
                    "count": entry.count,
                    "role": role,
                    "cost": entry.card.cost,
                    "key_role": role in {"attack", "lock", "finisher"} or is_low_attack_card(entry.card) or is_lock_card(entry.card),
                }
            )
    risks = []
    for civ, count in demand.items():
        if count <= 0:
            continue
        supply = float(effective.get(civ, 0) or 0)
        key_role = any(card["key_role"] for card in cards_by_civ[civ])
        if (1 <= count <= 3 and supply < 4) or (count >= 4 and supply < 8) or (count >= 8 and supply < 10):
            risks.append(
                {
                    "civilization": civ,
                    "demand": count,
                    "supply": supply,
                    "key_role": key_role,
                    "cards": cards_by_civ[civ],
                }
            )
    return risks


def denjadeon_rate(matchups: list[dict[str, Any]]) -> float:
    row = next((m for m in matchups if "デンジャデオン" in str(m.get("opponent", ""))), None)
    return float(row.get("estimated_win_rate", 0)) if row else 0.0


def average_for_opponents(matchups: list[dict[str, Any]], keywords: list[str]) -> float:
    rows = [m for m in matchups if any(k in str(m.get("opponent", "")) for k in keywords)]
    return average_win_rate(rows)


def build_why_selected(
    audit: dict[str, Any],
    score: float,
    pass_required: bool,
    sanity: dict[str, Any],
    theme_fit: dict[str, Any],
) -> str:
    stats = audit.get("stats", {})
    primary = audit.get("primary_counts", {})
    return (
        f"MANA上の最終fitness {score}、成立性スコア{sanity.get('score')}、"
        f"テーマらしさ{theme_fit.get('score', 100)}。"
        f"平均コスト{stats.get('avg_cost')}、primary attack {primary.get('attack', 0)}、"
        f"2〜4コストprimary attack {audit.get('low_primary_attack_count', 0)}、"
        f"デンジャデオン推定勝率{denjadeon_rate(audit.get('matchups', [])):.1%}。"
        + ("必須条件を通過しています。" if pass_required else "必須条件未満のため参考候補です。")
    )


def select_elites(candidates: list[ResearchCandidate], elite_count: int) -> list[ResearchCandidate]:
    ranked = sorted(candidates, key=lambda c: (c.pass_required, c.final_fitness), reverse=True)
    return ranked[:elite_count]


def dedupe_candidates(candidates: list[ResearchCandidate]) -> list[ResearchCandidate]:
    best: dict[str, ResearchCandidate] = {}
    for cand in candidates:
        key = deck_signature(cand.deck)
        if key not in best or cand.final_fitness > best[key].final_fitness:
            best[key] = cand
    return list(best.values())


def deck_signature(deck: list[DeckCard]) -> str:
    return "|".join(f"{d.card.name}:{d.count}" for d in sorted(deck, key=lambda x: x.card.name))


def load_battle_log_summary(db_path: Path) -> dict[str, Any]:
    try:
        return summarize_matches(db_path)
    except Exception as exc:
        return {
            "total_matches": 0,
            "win_rate": 0.0,
            "strong_cards": [],
            "weak_cards": [],
            "dead_cards": [],
            "mana_color_issue_rate": 0.0,
            "error": str(exc),
        }


def load_video_learning_summary(db_path: Path) -> dict[str, Any]:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT strong_cards_json, weak_cards_json, dead_cards_json, keep_advice, matchup_notes, meta_notes
            FROM video_learning_logs
            ORDER BY id DESC
            """
        ).fetchall()
        conn.close()
    except Exception as exc:
        return {
            "log_count": 0,
            "strong_card_scores": {},
            "weak_card_scores": {},
            "dead_card_scores": {},
            "keep_card_scores": {},
            "matchup_notes": {},
            "error": str(exc),
        }

    strong = Counter()
    weak = Counter()
    dead = Counter()
    keep = Counter()
    matchup_notes: dict[str, list[str]] = {}
    meta_keywords = ["自然単デンジャデオン", "火光レイド", "火水レイド", "水単スコーラー", "光単裁きの紋章Z"]
    for row in rows:
        for name in json.loads(row["strong_cards_json"] or "[]"):
            strong[name] += 1
        for name in json.loads(row["weak_cards_json"] or "[]"):
            weak[name] += 1
        for name in json.loads(row["dead_cards_json"] or "[]"):
            dead[name] += 1
        keep_text = str(row["keep_advice"] or "")
        for name in strong:
            if name and name in keep_text:
                keep[name] += 1
        notes = " / ".join(str(row[key] or "") for key in ["matchup_notes", "meta_notes"])
        for keyword in meta_keywords:
            if keyword in notes:
                matchup_notes.setdefault(keyword, []).append(notes[:160])
    return {
        "log_count": len(rows),
        "strong_card_scores": dict(strong),
        "weak_card_scores": dict(weak),
        "dead_card_scores": dict(dead),
        "keep_card_scores": dict(keep),
        "strong_cards": [{"name": k, "count": v} for k, v in strong.most_common(10)],
        "weak_cards": [{"name": k, "count": v} for k, v in weak.most_common(10)],
        "dead_cards": [{"name": k, "count": v} for k, v in dead.most_common(10)],
        "matchup_notes": {k: v[:3] for k, v in matchup_notes.items()},
    }


def load_youtube_research_summary(db_path: Path) -> dict[str, Any]:
    """Read both the older video_learning_logs and the newer transcript research DB."""
    base = load_video_learning_summary(db_path)
    strong = Counter(base.get("strong_card_scores", {}))
    weak = Counter(base.get("weak_card_scores", {}))
    dead = Counter(base.get("dead_card_scores", {}))
    keep = Counter(base.get("keep_card_scores", {}))
    matchup_notes: dict[str, list[str]] = dict(base.get("matchup_notes", {}) or {})
    deck_cautions: list[str] = []
    play_patterns: list[str] = []
    transcript_count = 0

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        if "card_insights" in tables:
            rows = conn.execute(
                """
                SELECT card_name, role, reason, related_matchup, sentiment, confidence
                FROM card_insights
                ORDER BY id DESC
                LIMIT 500
                """
            ).fetchall()
            transcript_count += len(rows)
            for row in rows:
                name = str(row["card_name"] or "").strip()
                if not name:
                    continue
                sentiment = str(row["sentiment"] or "")
                role = str(row["role"] or "")
                confidence = float(row["confidence"] or 0.5)
                weight = max(0.5, confidence)
                if any(key in sentiment for key in ["強", "有効", "positive", "good", "keep"]) or any(key in role for key in ["強", "キープ", "メタ"]):
                    strong[name] += weight
                if any(key in sentiment for key in ["弱", "微妙", "negative", "bad"]):
                    weak[name] += weight
                if any(key in sentiment for key in ["腐", "dead"]):
                    dead[name] += weight
                if any(key in role for key in ["キープ", "初動"]):
                    keep[name] += weight
                matchup = str(row["related_matchup"] or "").strip()
                reason = str(row["reason"] or "").strip()
                if matchup and reason:
                    matchup_notes.setdefault(matchup, []).append(reason[:160])
        if "deck_knowledge" in tables:
            rows = conn.execute(
                """
                SELECT deck_name, main_plan, color_balance_notes, caution_points
                FROM deck_knowledge
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
            transcript_count += len(rows)
            for row in rows:
                for key in ["color_balance_notes", "caution_points", "main_plan"]:
                    text = str(row[key] or "").strip()
                    if text:
                        deck_cautions.append(f"{row['deck_name']}: {text[:160]}")
        if "matchup_insights" in tables:
            rows = conn.execute(
                """
                SELECT deck_name, opponent_deck, evaluation, game_plan, caution_points
                FROM matchup_insights
                ORDER BY id DESC
                LIMIT 200
                """
            ).fetchall()
            transcript_count += len(rows)
            for row in rows:
                opponent = str(row["opponent_deck"] or "").strip()
                note = " / ".join(
                    str(row[key] or "").strip()
                    for key in ["evaluation", "game_plan", "caution_points"]
                    if str(row[key] or "").strip()
                )
                if opponent and note:
                    matchup_notes.setdefault(opponent, []).append(note[:160])
        if "play_patterns" in tables:
            rows = conn.execute(
                """
                SELECT deck_name, pattern_name, description, turn_range, required_cards
                FROM play_patterns
                ORDER BY id DESC
                LIMIT 100
                """
            ).fetchall()
            transcript_count += len(rows)
            for row in rows:
                text = f"{row['deck_name']} {row['pattern_name']}: {row['description']} {row['required_cards']}".strip()
                if text:
                    play_patterns.append(text[:180])
        conn.close()
    except Exception as exc:
        base["transcript_error"] = str(exc)

    log_count = int(base.get("log_count", 0) or 0) + transcript_count
    return {
        "log_count": log_count,
        "legacy_log_count": base.get("log_count", 0),
        "transcript_knowledge_count": transcript_count,
        "strong_card_scores": dict(strong),
        "weak_card_scores": dict(weak),
        "dead_card_scores": dict(dead),
        "keep_card_scores": dict(keep),
        "strong_cards": [{"name": k, "count": round(v, 2)} for k, v in strong.most_common(10)],
        "weak_cards": [{"name": k, "count": round(v, 2)} for k, v in weak.most_common(10)],
        "dead_cards": [{"name": k, "count": round(v, 2)} for k, v in dead.most_common(10)],
        "matchup_notes": {k: v[:3] for k, v in matchup_notes.items()},
        "deck_cautions": deck_cautions[:10],
        "play_patterns": play_patterns[:10],
        "connection_status": {
            "mana_research_status": "fallback内蔵",
            "youtube_knowledge": "connected" if transcript_count or base.get("log_count", 0) else "no_data",
            "candidate_search": "night_research_runner",
        },
        **({"transcript_error": base["transcript_error"]} if base.get("transcript_error") else {}),
    }


def youtube_knowledge_notes(deck: list[DeckCard], summary: dict[str, Any]) -> list[str]:
    if summary.get("log_count", 0) <= 0:
        return []
    strong = summary.get("strong_card_scores", {})
    weak = summary.get("weak_card_scores", {})
    dead = summary.get("dead_card_scores", {})
    notes: list[str] = []
    for entry in deck:
        name = entry.card.name
        if strong.get(name):
            notes.append(f"{name}: 動画/文字起こし知識で有効カードとして言及")
        if weak.get(name):
            notes.append(f"{name}: 動画/文字起こし知識で弱い・注意カードとして言及")
        if dead.get(name):
            notes.append(f"{name}: 動画/文字起こし知識で腐りやすいカードとして言及")
    for caution in summary.get("deck_cautions", [])[:3]:
        if "色" in caution or "マナ" in caution:
            notes.append(caution)
    return list(dict.fromkeys(notes))[:8]


def infer_seed_candidate_origin(strategy_memos: list[str]) -> str:
    text = "\n".join(strategy_memos)
    if "external_zone_tech" in text:
        return "external_zone_based"
    if "overseas_meta" in text:
        return "overseas_based"
    if "paper_diff_hypothesis" in text:
        return "paper_diff_based"
    if "matchup_counter" in text or "winrate_spike" in text or "high_rate_recipe" in text or "tournament_result" in text:
        return "meta_counter_based"
    if "rogue_deck_signal" in text:
        return "rogue_signal_based"
    return "tag_based"


def select_stable_fallback_candidates(
    ranked: list[ResearchCandidate],
    existing_top: list[ResearchCandidate],
    limit: int = 3,
) -> list[ResearchCandidate]:
    selected_ids = {id(candidate) for candidate in existing_top}
    fallback: list[ResearchCandidate] = []
    for candidate in ranked:
        if id(candidate) in selected_ids:
            continue
        if candidate.sanity.get("fatal_issues"):
            continue
        stats = candidate.audit.get("stats", {}) or {}
        if stats.get("deck_size") != 40:
            continue
        if any("テーマ外文明" in reason or "DB未存在カード" in reason or "40枚ではない" in reason for reason in candidate.reject_reasons):
            continue
        candidate = deepcopy_candidate_for_fallback(candidate)
        fallback.append(candidate)
        if len(fallback) >= limit:
            break
    return fallback


def deepcopy_candidate_for_fallback(candidate: ResearchCandidate) -> ResearchCandidate:
    copied = deepcopy(candidate)
    if "stable fallback: 再調整候補" not in copied.reject_reasons:
        copied.reject_reasons.append("stable fallback: 再調整候補")
    copied.pass_required = False
    copied.why_selected = copied.why_selected + " stableモードの再調整候補です。実戦投入前に弱点を再確認してください。"
    return copied


def build_summary(candidates: list[ResearchCandidate], top: list[ResearchCandidate], reject_counter: Counter[str]) -> dict[str, Any]:
    pass_count = sum(1 for c in candidates if c.pass_required)
    scores = [c.final_fitness for c in candidates]
    normalized_counter: Counter[str] = Counter()
    for cand in candidates:
        for reason in cand.reject_reasons:
            normalized_counter[normalize_reject_reason(reason)] += 1
    if not normalized_counter:
        normalized_counter.update({k: v for k, v in reject_counter.items() if k != "通過"})
    return {
        "generated_candidate_count": len(candidates),
        "passed_count": pass_count,
        "rejected_count": len(candidates) - pass_count,
        "best_score": max(scores) if scores else 0,
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "top_candidate_count": len(top),
        "candidate_extinction_risk": pass_count == 0,
        "reject_reason_ranking": normalized_counter.most_common(10),
    }


def serialize_candidate(candidate: ResearchCandidate, include_deck: bool = True) -> dict[str, Any]:
    audit = candidate.audit
    sanity_metrics = candidate.sanity.get("metrics", {})
    donjungle_count = count_card_by_name(candidate.deck, "ドンジャングルS7")
    trap_count = donjungle_trap_x_trap_count(candidate.deck)
    yadok_count = count_card_by_name(candidate.deck, "獣軍隊 ヤドック")
    donjungle_fill_cards = [
        {"count": entry.count, "name": entry.card.name, "reason": entry.reason}
        for entry in candidate.deck
        if "donjungle-s7-dead-slot-fill" in str(entry.reason)
    ]
    tier_s_second_resistance = calculate_tier_s_second_resistance_score(candidate.role_snapshot, candidate.deck, audit)
    out = {
        "deck_name": candidate.deck_name,
        "profile_name": candidate.profile_name,
        "score": candidate.score,
        "final_fitness": candidate.final_fitness,
        "base_score": candidate.base_score,
        "novelty_score": candidate.novelty_score,
        "meta_score": candidate.meta_score,
        "pass_required": candidate.pass_required,
        "reject_reasons": candidate.reject_reasons,
        "rejected_reason": "; ".join(candidate.reject_reasons),
        "why_selected": candidate.why_selected,
        "sanity": candidate.sanity,
        "sanity_score": candidate.sanity.get("score", 0),
        "sanity_warnings": candidate.sanity.get("warnings", []),
        "fatal_issues": candidate.sanity.get("fatal_issues", []),
        "theme_fit": candidate.theme_fit,
        "theme_fit_score": candidate.theme_fit.get("score", 100),
        "theme_fit_score_original": candidate.theme_fit.get("original_score", candidate.theme_fit.get("score", 100)),
        "theme_fit_strict_gate_penalty": candidate.theme_fit.get("strict_gate_penalty", 0),
        "theme_fit_warnings": candidate.theme_fit.get("warnings", []),
        "control_quality_warnings": candidate.theme_fit.get("control_quality_warnings", []),
        "role_snapshot": candidate.role_snapshot,
        "strategy_memos": candidate.strategy_memos,
        "candidate_origin": infer_seed_candidate_origin(candidate.strategy_memos),
        "civilization_counts": sanity_metrics.get("civilization_counts", {}),
        "main_colors": sanity_metrics.get("main_colors", []),
        "splash_colors": sanity_metrics.get("splash_colors", []),
        "main_axis_cards": sanity_metrics.get("main_axis_cards", []),
        "one_of_count": sanity_metrics.get("one_of_count", 0),
        "youtube_knowledge_notes": candidate.youtube_knowledge_notes,
        "stats": audit.get("stats", {}),
        "primary_counts": audit.get("primary_counts", {}),
        "secondary_counts": audit.get("secondary_counts", {}),
        "low_primary_attack_count": audit.get("low_primary_attack_count", 0),
        "effective_supply": audit.get("effective_supply", {}),
        "warnings": audit.get("warnings", []),
        "matchups": audit.get("matchups", []),
        "denjadeon_rate": denjadeon_rate(audit.get("matchups", [])),
        "average_meta_win_rate": average_win_rate(audit.get("matchups", [])),
        "donjungle_s7_count": donjungle_count,
        "donjungle_s7_variant": donjungle_s7_variant(donjungle_count),
        "trap_x_trap_count": trap_count,
        "yadok_count": yadok_count,
        "strong_card_retention": {
            "獣軍隊 ヤドック": yadok_count,
            "トラップ×トラップ": trap_count,
        },
        "donjungle_s7_dead_slot_fill_cards": donjungle_fill_cards,
        "tier_s_second_resistance_score": tier_s_second_resistance,
    }
    if include_deck:
        out["deck"] = serialize_deck(candidate.deck)
    return out


def serialize_deck(deck: list[DeckCard]) -> list[dict[str, Any]]:
    return [
        {
            "count": d.count,
            "name": d.card.name,
            "civilization": d.card.civilization,
            "cost": d.card.cost,
            "card_type": d.card.card_type,
            "primary_role": primary_role(d.card),
            "reason": d.reason,
        }
        for d in deck
    ]


def write_outputs(payload: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    best_dir = out_dir / BEST_DIR_NAME
    best_dir.mkdir(parents=True, exist_ok=True)
    for old_rank in best_dir.glob("rank_*.md"):
        old_rank.unlink()
    (out_dir / "night_research_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary_csv(payload, out_dir / "night_research_summary.csv")
    (out_dir / "night_research_report.md").write_text(to_markdown(payload), encoding="utf-8")
    for idx, candidate in enumerate(payload.get("top_candidates", []), start=1):
        (best_dir / f"rank_{idx:02d}.md").write_text(candidate_markdown(idx, candidate), encoding="utf-8")


def write_summary_csv(payload: dict[str, Any], path: Path) -> None:
    rows = payload.get("all_candidates", [])
    fieldnames = [
        "deck_name",
        "profile_name",
        "score",
        "final_fitness",
        "base_score",
        "novelty_score",
        "meta_score",
        "sanity_score",
        "theme_fit_score",
        "control_quality_warnings",
        "pass_required",
        "avg_cost",
        "primary_attack",
        "low_primary_attack",
        "defense",
        "resource",
        "lock",
        "mana_boost",
        "anti_cheat",
        "hand_discard",
        "donjungle_s7",
        "donjungle_s7_variant",
        "trap_x_trap_count",
        "yadok_count",
        "tier_s_second_resistance_score",
        "high_cost",
        "average_meta_win_rate",
        "denjadeon_rate",
        "main_colors",
        "splash_colors",
        "main_axis_cards",
        "one_of_count",
        "sanity_warnings",
        "theme_fit_warnings",
        "fatal_issues",
        "youtube_knowledge_notes",
        "candidate_origin",
        "strategy_memos",
        "reject_reasons",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            stats = row.get("stats", {})
            primary = row.get("primary_counts", {})
            secondary = row.get("secondary_counts", {})
            writer.writerow(
                {
                    "deck_name": row.get("deck_name"),
                    "profile_name": row.get("profile_name"),
                    "score": row.get("score"),
                    "final_fitness": row.get("final_fitness"),
                    "base_score": row.get("base_score"),
                    "novelty_score": row.get("novelty_score"),
                    "meta_score": row.get("meta_score"),
                    "sanity_score": row.get("sanity_score"),
                    "theme_fit_score": row.get("theme_fit_score"),
                    "control_quality_warnings": "; ".join(row.get("control_quality_warnings", [])),
                    "pass_required": row.get("pass_required"),
                    "avg_cost": stats.get("avg_cost"),
                    "primary_attack": primary.get("attack", 0),
                    "low_primary_attack": row.get("low_primary_attack_count", 0),
                    "defense": secondary.get("defense", 0),
                    "resource": secondary.get("resource", 0),
                    "lock": (row.get("role_snapshot", {}) or {}).get("lock", secondary.get("lock", 0)),
                    "mana_boost": (row.get("role_snapshot", {}) or {}).get("mana_boost", 0),
                    "anti_cheat": (row.get("role_snapshot", {}) or {}).get("anti_cheat", 0),
                    "hand_discard": (row.get("role_snapshot", {}) or {}).get("hand_discard", 0),
                    "donjungle_s7": (row.get("role_snapshot", {}) or {}).get("donjungle_s7", 0),
                    "donjungle_s7_variant": row.get("donjungle_s7_variant", ""),
                    "trap_x_trap_count": row.get("trap_x_trap_count", 0),
                    "yadok_count": row.get("yadok_count", 0),
                    "tier_s_second_resistance_score": row.get("tier_s_second_resistance_score", 0),
                    "high_cost": stats.get("high_cost"),
                    "average_meta_win_rate": row.get("average_meta_win_rate"),
                    "denjadeon_rate": row.get("denjadeon_rate"),
                    "main_colors": "/".join(row.get("main_colors", [])),
                    "splash_colors": "/".join(row.get("splash_colors", [])),
                    "main_axis_cards": "; ".join(f"{x.get('name')}x{x.get('count')}" for x in row.get("main_axis_cards", [])),
                    "one_of_count": row.get("one_of_count", 0),
                    "sanity_warnings": "; ".join(row.get("sanity_warnings", [])),
                    "theme_fit_warnings": "; ".join(row.get("theme_fit_warnings", [])),
                    "fatal_issues": "; ".join(row.get("fatal_issues", [])),
                    "youtube_knowledge_notes": "; ".join(row.get("youtube_knowledge_notes", [])),
                    "candidate_origin": row.get("candidate_origin", ""),
                    "strategy_memos": " || ".join(row.get("strategy_memos", [])),
                    "reject_reasons": "; ".join(row.get("reject_reasons", [])),
                }
            )


def to_markdown(payload: dict[str, Any]) -> str:
    conditions = payload["conditions"]
    summary = payload["summary"]
    battle = payload["battle_log_summary"]
    video = payload.get("video_learning_summary", {})
    lines = [
        "# Project MANA 夜間研究レポート",
        "",
        "## 実行条件",
        f"- generations: {conditions['generations']}",
        f"- population: {conditions['population']}",
        f"- elapsed_time: {conditions['elapsed_time']}秒",
        f"- random_seed: {conditions['random_seed']}",
        f"- research_theme: {conditions.get('theme_name') or 'なし'}",
        f"- 使用フォーマット: {conditions.get('format', 'AD')}",
        f"- フォーマット別仮想敵: {' / '.join(conditions.get('format_target_matchups', []) or []) or '未指定'}",
        f"- stableモード: {'あり' if conditions.get('stable_mode') else 'なし'}",
        f"- 実戦ログ使用有無: {'あり' if conditions['battle_log_used'] else 'なし'}",
        f"- 動画学習使用有無: {'あり' if conditions.get('video_learning_used') else 'なし'}",
        f"- フォーマット除外: {format_filter_report_text(conditions.get('format_filter', {}))}",
        "",
        "## 実戦ログ反映",
        f"- 実戦ログ件数: {battle.get('total_matches', 0)}",
        f"- 実戦ログを評価に使ったか: {'はい' if conditions['battle_log_used'] else 'いいえ'}",
        f"- 強かったカード上位: {format_counter_items(battle.get('strong_cards', []))}",
        f"- 弱かったカード上位: {format_counter_items(battle.get('weak_cards', []))}",
        f"- 実戦ログ除外カード: {format_counter_items(battle_log_excluded_card_items(battle, payload.get('research_theme', {})))}",
        f"- 実戦ログ減点カード: {format_counter_items(battle_log_penalty_card_items(battle, payload.get('research_theme', {})))}",
        f"- 腐ったカード上位: {format_counter_items(battle.get('dead_cards', []))}",
        f"- dead_cardsによる枚数調整候補: {format_counter_items(dead_card_adjustment_items(battle, payload.get('research_theme', {})))}",
        f"- 色事故率: {battle.get('mana_color_issue_rate', 0):.1%}",
        f"- Tier S後攻リスク: {tier_s_second_play_risk_text(battle)}",
        f"- 候補全滅リスク: {'あり' if summary.get('candidate_extinction_risk') else 'なし'}",
        "",
        "## YouTube動画学習反映",
        f"- 動画学習ログ件数: {video.get('log_count', 0)}",
        f"- 文字起こし研究DB件数: {video.get('transcript_knowledge_count', 0)}",
        f"- 夜間研究に反映したか: {'はい' if conditions.get('video_learning_used') else 'いいえ'}",
        f"- 加点カード上位: {format_counter_items(video.get('strong_cards', []))}",
        f"- 減点カード上位: {format_counter_items(video.get('weak_cards', []))}",
        f"- 腐りカード上位: {format_counter_items(video.get('dead_cards', []))}",
        f"- 対面別学習メモ: {format_matchup_notes(video.get('matchup_notes', {}))}",
        f"- 構築上の注意: {format_text_items(video.get('deck_cautions', []))}",
        "",
        "## 制約付き研究テーマ",
        f"- テーマ指定: {conditions.get('theme_name') or 'なし'}",
        f"- target_matchups({conditions.get('format', 'AD')}): {' / '.join(payload.get('research_theme', {}).get('effective_target_matchups', []) or conditions.get('format_target_matchups', []) or []) or '-'}",
        f"- deck_type: {payload.get('research_theme', {}).get('deck_type', '-')}",
        f"- format: {payload.get('research_theme', {}).get('format', conditions.get('format', 'AD'))}",
        f"- main_colors: {'/'.join(payload.get('research_theme', {}).get('main_colors', [])) or '-'}",
        f"- allowed_colors: {'/'.join(payload.get('research_theme', {}).get('allowed_colors', [])) or '-'}",
        f"- required_cards: {', '.join(payload.get('research_theme', {}).get('required_cards', [])) or '-'}",
        f"- DB未発見のrequired_cards: {', '.join(payload.get('research_theme', {}).get('_missing_required_in_db', [])) or 'なし'}",
        "",
        "## 外部観測seed反映",
        f"- queued seed件数: {len(payload.get('meta_research_seeds', []))}",
    ]
    for seed in payload.get("meta_research_seeds", [])[:5]:
        lines.append(
            f"- seed_id={seed.get('id')} / {seed.get('seed_type')} / {seed.get('priority')} / "
            f"{seed.get('source_name') or seed.get('source_type')} / {seed.get('strategy_hint')}"
        )
    lines.extend(
        [
            "",
        "## 探索結果サマリー",
        f"- 生成候補数: {summary['generated_candidate_count']}",
        f"- 監査通過数: {summary['passed_count']}",
        f"- 破棄候補数: {summary['rejected_count']}",
        f"- 最高スコア: {summary['best_score']}",
        f"- 平均スコア: {summary['average_score']}",
        f"- 上位候補数: {summary['top_candidate_count']}",
        f"- fallback候補数: {len(payload.get('fallback_candidates', []))}",
        "",
        "## 通過候補と破棄候補の内訳",
        "",
        "### 通過候補",
        ]
    )
    passed_rows = [c for c in payload.get("all_candidates", []) if c.get("pass_required")]
    rejected_rows = [c for c in payload.get("all_candidates", []) if not c.get("pass_required")]
    if passed_rows:
        for candidate in passed_rows[:10]:
            role = candidate.get("role_snapshot", {}) or {}
            lines.append(
                f"- {candidate.get('deck_name')}: fitness={candidate.get('final_fitness')} / "
                f"受け={role.get('defense', 0)} リソース={role.get('resource', 0)} "
                f"マナ加速={role.get('mana_boost', 0)} 踏み倒しメタ={role.get('anti_cheat', 0)} "
                f"ハンデス={role.get('hand_discard', 0)} "
                f"Tier S後攻耐性={candidate.get('tier_s_second_resistance_score', 0)} "
                f"{candidate.get('donjungle_s7_variant', 'ドンジャングルS7型不明')} "
                f"トラップ×トラップ={candidate.get('trap_x_trap_count', 0)}"
            )
    else:
        lines.append("- なし")
    lines.extend(["", "### 破棄候補"] )
    if rejected_rows:
        for candidate in rejected_rows[:20]:
            role = candidate.get("role_snapshot", {}) or {}
            lines.append(
                f"- {candidate.get('deck_name')}: {candidate.get('rejected_reason') or '理由不明'} / "
                f"受け={role.get('defense', 0)} リソース={role.get('resource', 0)} "
                f"マナ加速={role.get('mana_boost', 0)} 踏み倒しメタ={role.get('anti_cheat', 0)} "
                f"ハンデス={role.get('hand_discard', 0)} "
                f"Tier S後攻耐性={candidate.get('tier_s_second_resistance_score', 0)} "
                f"{candidate.get('donjungle_s7_variant', 'ドンジャングルS7型不明')} "
                f"トラップ×トラップ={candidate.get('trap_x_trap_count', 0)}"
            )
    else:
        lines.append("- なし")
    lines.extend(
        [
        "",
        "## 今日試すべきデッキ Top 3",
        ]
    )
    top_candidates = payload.get("top_candidates", [])
    if top_candidates:
        for idx, candidate in enumerate(top_candidates, start=1):
            lines.extend(candidate_markdown_lines(idx, candidate, include_plan=False))
        lines.extend(
            [
                "",
                "## 最有力候補",
            ]
        )
        lines.extend(candidate_markdown_lines(1, payload["top_candidates"][0], include_plan=True))
    else:
        lines.extend(
            [
                "",
                "今回の探索では実戦投入可能候補なし。",
                "",
                "棄却理由:",
            ]
        )
    fallback = payload.get("fallback_candidates", [])
    if fallback:
        lines.extend(
            [
                "",
                "## stable fallback 再調整候補",
                "",
                "passed_count が不足したため、fatalではない候補を再調整候補として提示します。実戦投入候補ではありません。",
            ]
        )
        for idx, candidate in enumerate(fallback, start=1):
            lines.extend(candidate_markdown_lines(idx, candidate, include_plan=False))
        for reason, count in summary.get("reject_reason_ranking", [])[:6]:
            lines.append(f"- {reason}: {count}")
        lines.extend(
            [
                "",
                "次回の探索条件:",
                "- 2色以下を優先する",
                "- 主軸カード3枚以上を必須にする",
                "- 1枚差し最大10種類を目標にする",
                "- 特殊ゾーン/禁断系カードを通常40枚候補から除外する",
            ]
        )
    lines.extend(
        [
            "",
            "## 候補別成立性チェック上位サンプル",
            "",
            "| deck_name | final_fitness | base_score | novelty_score | meta_score | sanity_score | theme_fit_score | fatal_issues | rejected_reason | main_colors | splash_colors | main_axis_cards | one_of_count | youtube_knowledge_notes |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- | --- | ---: | --- |",
        ]
    )
    for candidate in payload.get("all_candidates", [])[:10]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(candidate.get("deck_name", "-")).replace("|", "/"),
                    str(candidate.get("final_fitness", "-")),
                    str(candidate.get("base_score", "-")),
                    str(candidate.get("novelty_score", "-")),
                    str(candidate.get("meta_score", "-")),
                    str(candidate.get("sanity_score", "-")),
                    str(candidate.get("theme_fit_score", "-")),
                    format_table_cell("; ".join(candidate.get("fatal_issues", [])) or "なし"),
                    format_table_cell(candidate.get("rejected_reason") or "なし"),
                    format_table_cell("/".join(candidate.get("main_colors", [])) or "-"),
                    format_table_cell("/".join(candidate.get("splash_colors", [])) or "-"),
                    format_table_cell(format_axis_cards(candidate.get("main_axis_cards", []))),
                    str(candidate.get("one_of_count", 0)),
                    format_table_cell(format_text_items(candidate.get("youtube_knowledge_notes", []))),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## 棄却理由ランキング",
        ]
    )
    for reason, count in summary.get("reject_reason_ranking", []):
        lines.append(f"- {reason}: {count}")
    lines.extend(
        [
            "",
            "## MANA上の評価",
            "既存の候補生成、実戦監査、現在メタ代理評価を組み合わせ、実戦で試す価値が高そうな候補を順位付けしました。",
            "",
            "## 実戦上の未確認点",
            "この結果は完全なデュエプレ実ルールシミュレーションではありません。初手、盾、実際のプレイ順、相手の妨害までは未確定です。",
            "",
            "## 人間が確認すべき点",
            "Top 3のうちrank_01から5戦テストし、色事故、4ターン目圧力、6ターン目詰め切り、腐ったカードを記録してください。",
            "",
            "## 次の改善条件",
            "実戦ログで弱かったカード・腐ったカード・色事故率を確認し、次回の夜間研究スコアに反映します。",
        ]
    )
    return "\n".join(lines)


def candidate_markdown(rank: int, candidate: dict[str, Any]) -> str:
    return "\n".join(candidate_markdown_lines(rank, candidate, include_plan=True))


def candidate_markdown_lines(rank: int, candidate: dict[str, Any], include_plan: bool) -> list[str]:
    stats = candidate.get("stats", {})
    primary = candidate.get("primary_counts", {})
    secondary = candidate.get("secondary_counts", {})
    supply = candidate.get("effective_supply", {})
    role_snapshot = candidate.get("role_snapshot", {}) or {}
    fill_cards = candidate.get("donjungle_s7_dead_slot_fill_cards", []) or []
    fill_text = (
        " / ".join(f"{item.get('name')}x{item.get('count')}" for item in fill_cards)
        if fill_cards
        else "トラップ×トラップ / 軽量除去 / 受け札 / ロック / 踏み倒しメタ / リソース札を優先"
    )
    strong_retention = candidate.get("strong_card_retention", {}) or {}
    lines = [
        "",
        f"### Rank {rank}: {candidate.get('deck_name')}",
        f"- final_fitness: {candidate.get('final_fitness', candidate.get('score'))}",
        f"- base_score: {candidate.get('base_score')}",
        f"- novelty_score: {candidate.get('novelty_score')}",
        f"- meta_score: {candidate.get('meta_score')}",
        f"- sanity_score: {candidate.get('sanity_score')}",
        f"- theme_fit_score: {candidate.get('theme_fit_score')}",
        f"- 必須条件通過: {'Yes' if candidate.get('pass_required') else 'No'}",
        f"- avg_cost: {stats.get('avg_cost')}",
        f"- primary attack: {primary.get('attack', 0)}",
        f"- 2〜4 cost primary attack: {candidate.get('low_primary_attack_count', 0)}",
        f"- defense: {role_snapshot.get('defense', secondary.get('defense', 0))}",
        f"- resource: {role_snapshot.get('resource', secondary.get('resource', 0))}",
        f"- lock: {role_snapshot.get('lock', secondary.get('lock', 0))}",
        f"- removal: {role_snapshot.get('removal', secondary.get('removal', 0))}",
        f"- マナ加速: {role_snapshot.get('mana_boost', 0)}",
        f"- 踏み倒しメタ: {role_snapshot.get('anti_cheat', 0)}",
        f"- ハンデス: {role_snapshot.get('hand_discard', 0)}",
        f"- ドンジャングルS7: {role_snapshot.get('donjungle_s7', 0)}",
        f"- ドンジャングルS7型: {candidate.get('donjungle_s7_variant', '不明')}",
        f"- Tier S後攻耐性スコア: {candidate.get('tier_s_second_resistance_score', 0)}",
        f"- dead_cards枚数調整理由: 黒緑TierSメタコントロールではドンジャングルS7を非依存化し、0〜1枚を優先します。",
        f"- 空いた枠の補充先: {fill_text}",
        f"- トラップ×トラップ枚数: {candidate.get('trap_x_trap_count', 0)}",
        f"- strong_cards維持状況: ヤドック={strong_retention.get('獣軍隊 ヤドック', candidate.get('yadok_count', 0))} / トラップ×トラップ={strong_retention.get('トラップ×トラップ', candidate.get('trap_x_trap_count', 0))}",
        "- Tier S後攻リスク: 火光レイド/ブランド Tier S 0勝8敗・後攻0勝11敗を前提に、rejectではなく減点と警告で反映",
        f"- theme_fit_score_original: {candidate.get('theme_fit_score_original')}",
        f"- theme_fit_strict_gate_penalty: {candidate.get('theme_fit_strict_gate_penalty')}",
        f"- high cost: {stats.get('high_cost')}",
        f"- 色供給: {format_supply(supply)}",
        f"- 文明数: {candidate.get('civilization_counts', {})}",
        f"- main_colors: {'/'.join(candidate.get('main_colors', [])) or '-'}",
        f"- splash_colors: {'/'.join(candidate.get('splash_colors', [])) or '-'}",
        f"- main_axis_cards: {format_axis_cards(candidate.get('main_axis_cards', []))}",
        f"- one_of_count: {candidate.get('one_of_count', 0)}",
        f"- 警告: {', '.join(candidate.get('warnings', [])) if candidate.get('warnings') else 'なし'}",
        f"- sanity_warnings: {', '.join(candidate.get('sanity_warnings', [])) if candidate.get('sanity_warnings') else 'なし'}",
        f"- theme_fit_warnings: {', '.join(candidate.get('theme_fit_warnings', [])) if candidate.get('theme_fit_warnings') else 'なし'}",
        f"- control_quality_warnings: {', '.join(candidate.get('control_quality_warnings', [])) if candidate.get('control_quality_warnings') else 'なし'}",
        f"- fatal_issues: {', '.join(candidate.get('fatal_issues', [])) if candidate.get('fatal_issues') else 'なし'}",
        f"- rejected_reason: {candidate.get('rejected_reason') or 'なし'}",
        f"- candidate_origin: {candidate.get('candidate_origin') or 'night_research'}",
        f"- strategy_memos: {format_text_items(candidate.get('strategy_memos', []))}",
        f"- youtube_knowledge_notes: {format_text_items(candidate.get('youtube_knowledge_notes', []))}",
        f"- なぜ選ばれたか: {candidate.get('why_selected')}",
        "- 現在メタ5デッキ推定勝率:",
    ]
    for matchup in candidate.get("matchups", []):
        lines.append(f"  - {matchup.get('opponent')}: {float(matchup.get('estimated_win_rate', 0)):.1%} ({matchup.get('note', '-')})")
    lines.append("- 40枚リスト:")
    for card in candidate.get("deck", []):
        lines.append(f"  - {card['count']} {card['name']} [{card['civilization']} / {card['cost']}] primary={card['primary_role']}")
    lines.extend(
        [
            "- 実戦上の未確認点: 代理評価上の候補です。実際の初手、盾、相手の干渉、プレイ順は未検証です。",
        ]
    )
    if include_plan:
        lines.extend(
            [
                "",
                "#### 対面別プラン",
                "- 自然単デンジャデオン: 2〜4ターン目に低コスト打点を展開し、踏み倒しメタ/ロックで大型着地前に盾を詰めます。",
                "- 火光レイド / 火水レイド: 受け札を1枚抱えつつ、盤面を取り返される前に早期打点を維持します。",
                "- 水単スコーラー: 呪文ロック/踏み倒しメタを優先し、相手のリソース連鎖前に詰めます。",
                "- 光単裁きの紋章Z: 長期戦に寄せすぎず、ロック札と打点でシールド追加前に圧をかけます。",
                "",
                "#### 最初の5戦テスト計画",
                "1. 自然単デンジャデオン",
                "2. 自然単デンジャデオン",
                "3. 自然単デンジャデオン",
                "4. 火光レイド",
                "5. 火水レイド",
                "",
                "#### ログ入力コマンド例",
                '```powershell',
                'python -m src.final_test_logger --deck "' + str(candidate.get("deck_name")) + '" --opponent "自然単デンジャデオン" --result win --finish-turn 6 --play-order first --pressure-by-turn4 yes --finish-by-turn6 yes --notes "夜間研究rank_01の初回テスト"',
                '```',
            ]
        )
    return lines


def format_filter_report_text(summary: dict[str, Any]) -> str:
    if not summary:
        return "なし"
    fmt = summary.get("format", "AD")
    if fmt == "AD":
        return "AD指定のため除外なし"
    excluded = int(summary.get("excluded_count", 0) or 0)
    manual = int(summary.get("manual_ad_only_count", 0) or 0)
    names = summary.get("excluded_ad_only_cards", []) or []
    name_text = " / ".join(map(str, names[:10])) if names else "なし"
    more = "" if len(names) <= 10 else f" 他{len(names) - 10}件"
    return f"ND指定: AD専用候補を{excluded}枚除外 / manual_ad_only={manual} / 除外例: {name_text}{more}"


def format_supply(supply: dict[str, Any]) -> str:
    return " / ".join(f"{k}{v}" for k, v in supply.items() if float(v or 0) > 0) or "-"


def format_counter_items(items: Any) -> str:
    if not items:
        return "なし"
    formatted: list[str] = []
    for item in list(items)[:5]:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            count = item.get("count", 0)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            name = str(item[0]).strip()
            count = item[1]
        else:
            continue
        if name:
            formatted.append(f"{name}: {count}")
    return " / ".join(formatted) if formatted else "なし"


def format_matchup_notes(notes: dict[str, list[str]]) -> str:
    if not notes:
        return "なし"
    return " / ".join(f"{key}: {len(value)}件" for key, value in notes.items())


def format_text_items(items: list[str]) -> str:
    if not items:
        return "なし"
    return " / ".join(str(item).replace("\r", " ").replace("\n", " | ") for item in items[:5])


def format_axis_cards(items: list[dict[str, Any]]) -> str:
    if not items:
        return "なし"
    return " / ".join(f"{item.get('name')}x{item.get('count')}" for item in items[:8])


def format_table_cell(value: str) -> str:
    return str(value).replace("|", "/").replace("\n", " ")

def normalize_theme_fit_warnings_by_role_snapshot(candidate: ResearchCandidate) -> ResearchCandidate:
    """
    theme_fit_warnings がカードタグ不足で 0/required と出ていても、
    strict role_snapshot 側で実際に必要枚数を満たしている場合は警告から外す。
    """
    role = getattr(candidate, "role_snapshot", None)
    if role is None:
        role = extract_donjungle_role_snapshot(candidate.deck)

    minimums = {
        "踏み倒しメタ": ("anti_cheat", 4),
        "ハンデス": ("hand_discard", 3),
        "リソース": ("resource", 6),
        "マナ加速": ("mana_boost", 4),
        "受け札": ("defense", 6),
        "ドンジャングルS7": ("donjungle_s7", 2),
    }

    theme_fit = dict(candidate.theme_fit or {})
    warnings = list(theme_fit.get("warnings", []) or [])

    filtered = []
    for warning in warnings:
        text = str(warning)

        removed = False
        for label, (role_key, required) in minimums.items():
            if label in text:
                actual = int(role.get(role_key, 0) or 0)
                if actual >= required:
                    removed = True
                break

        if not removed:
            filtered.append(warning)

    theme_fit["warnings"] = filtered
    candidate.theme_fit = theme_fit
    return candidate

def main() -> None:
    parser = argparse.ArgumentParser(description="Run Project MANA overnight autonomous research.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--generations", type=int, default=3)
    parser.add_argument("--population", type=int, default=20)
    parser.add_argument("--hours", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--theme", choices=list_research_themes(), default=None, help="制約付き研究テーマ")
    parser.add_argument("--format", choices=["AD", "ND"], default=None, help="使用フォーマット。省略時は研究テーマのformat、未指定テーマはAD")
    parser.add_argument("--mode", choices=["normal", "stable"], default="normal")
    parser.add_argument("--stable", action="store_true", help="候補全滅を避ける安定探索モード")
    args = parser.parse_args()

    payload = run_night_research(
        db_path=args.db,
        generations=args.generations,
        population=args.population,
        hours=args.hours,
        seed=args.seed,
        out_dir=args.out,
        theme_name=args.theme,
        format_name=args.format,
        mode=args.mode,
        stable=args.stable,
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    print(f"wrote: {Path(args.out) / 'night_research_report.md'}")


if __name__ == "__main__":
    main()

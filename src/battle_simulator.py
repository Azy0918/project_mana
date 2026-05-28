from __future__ import annotations

import random
from typing import Any

from src.evaluate_deck import evaluate_deck


META_TAGS = {"メタ", "ロック", "ハンデス"}
REMOVAL_TAGS = {"除去", "バウンス", "タップ"}
RESOURCE_TAGS = {"ドロー", "リソース", "マナ加速"}


def _tag_count(summary: dict[str, Any], tags: set[str]) -> int:
    tag_counts = summary["tag_counts"]
    return sum(int(tag_counts.get(tag, 0)) for tag in tags)


def _cost_count(summary: dict[str, Any], low: int, high: int | None = None) -> int:
    total = 0
    for cost, count in summary["cost_curve"].items():
        cost_int = int(cost)
        if high is None:
            if cost_int >= low:
                total += int(count)
        elif low <= cost_int <= high:
            total += int(count)
    return total


def _features(deck: list[dict[str, Any]]) -> dict[str, Any]:
    summary = evaluate_deck(deck)
    role_counts = summary["role_counts"]
    total = max(1, summary["total_cards"])
    low_cost = _cost_count(summary, 0, 3)
    high_cost = _cost_count(summary, 7, None)
    removal = _tag_count(summary, REMOVAL_TAGS)
    resource = _tag_count(summary, RESOURCE_TAGS)
    meta = _tag_count(summary, META_TAGS)

    speed = min(1.0, (role_counts["初動"] + low_cost) / 24)
    ramp = min(1.0, role_counts["マナ加速"] / 10)
    defense = min(1.0, role_counts["受け札"] / 14)
    finisher = min(1.0, (role_counts["フィニッシャー"] + high_cost) / 12)
    resource_index = min(1.0, resource / 14)
    removal_index = min(1.0, removal / 10)
    meta_index = min(1.0, meta / 8)
    curve_index = min(1.0, low_cost / max(1, total * 0.45))

    return {
        "summary": summary,
        "speed": speed,
        "ramp": ramp,
        "defense": defense,
        "finisher": finisher,
        "resource": resource_index,
        "removal": removal_index,
        "meta": meta_index,
        "curve": curve_index,
        "total_score": summary["score"] / 100,
        "novelty": summary["novelty_score"] / 100,
        "meta_score": summary["meta_score"] / 100,
    }


def _power(features: dict[str, Any], opponent: dict[str, Any]) -> float:
    proactive = (
        features["speed"] * 0.18
        + features["ramp"] * 0.12
        + features["finisher"] * 0.16
        + features["resource"] * 0.12
        + features["curve"] * 0.08
    )
    reactive = (
        features["defense"] * 0.13
        + features["removal"] * 0.10
        + features["meta"] * 0.08
    )
    quality = features["total_score"] * 0.12 + features["meta_score"] * 0.08 + features["novelty"] * 0.01
    matchup_bonus = 0.0
    matchup_bonus += features["defense"] * opponent["speed"] * 0.08
    matchup_bonus += features["removal"] * opponent["finisher"] * 0.06
    matchup_bonus += features["meta"] * opponent["resource"] * 0.06
    matchup_bonus += features["resource"] * opponent["defense"] * 0.05
    return proactive + reactive + quality + matchup_bonus


def _finish_turn(winner: dict[str, Any], loser: dict[str, Any], rng: random.Random) -> int:
    pressure = winner["speed"] * 1.8 + winner["finisher"] * 1.5 + winner["ramp"] * 0.9
    resistance = loser["defense"] * 1.4 + loser["removal"] * 0.8 + loser["resource"] * 0.5
    estimate = 8.5 - pressure + resistance + rng.uniform(-1.2, 1.2)
    return max(4, min(12, round(estimate)))


def _factor_lines(features: dict[str, Any], opponent: dict[str, Any], label: str) -> tuple[list[str], list[str]]:
    favorable = []
    unfavorable = []

    if features["speed"] >= 0.7:
        favorable.append(f"{label}は初動速度が高く、序盤の主導権を取りやすいです。")
    elif opponent["speed"] >= 0.7:
        unfavorable.append(f"{label}は相手の速い展開に対して出遅れる可能性があります。")

    if features["ramp"] >= 0.6:
        favorable.append(f"{label}はマナ加速で中盤以降の押し付けを早められます。")
    if features["defense"] >= 0.7:
        favorable.append(f"{label}は受け札が厚く、相手の攻撃を耐える余地があります。")
    elif opponent["finisher"] >= 0.7:
        unfavorable.append(f"{label}は相手のフィニッシャーに対する受けが薄めです。")

    if features["resource"] >= 0.6:
        favorable.append(f"{label}はドロー/リソースで長期戦の息切れを抑えられます。")
    elif opponent["defense"] >= 0.7:
        unfavorable.append(f"{label}は受けの厚い相手に長引かされると息切れしやすいです。")

    if features["removal"] >= 0.6:
        favorable.append(f"{label}は除去札で相手の勝ち筋に干渉できます。")
    if features["meta"] >= 0.3:
        favorable.append(f"{label}はメタカード要素で相手の動きを制限できます。")

    return favorable[:5], unfavorable[:5]


def simulate_battle(
    deck_a: list[dict[str, Any]],
    deck_b: list[dict[str, Any]],
    trials: int = 500,
    seed: int | None = None,
) -> dict[str, Any]:
    trials = max(1, min(1000, int(trials)))
    rng = random.Random(seed)
    features_a = _features(deck_a)
    features_b = _features(deck_b)
    base_a = _power(features_a, features_b)
    base_b = _power(features_b, features_a)

    wins_a = 0
    wins_b = 0
    finish_turns = []

    for _ in range(trials):
        roll_a = base_a + rng.gauss(0, 0.09)
        roll_b = base_b + rng.gauss(0, 0.09)
        if roll_a >= roll_b:
            wins_a += 1
            finish_turns.append(_finish_turn(features_a, features_b, rng))
        else:
            wins_b += 1
            finish_turns.append(_finish_turn(features_b, features_a, rng))

    favorable_a, unfavorable_a = _factor_lines(features_a, features_b, "デッキA")
    favorable_b, unfavorable_b = _factor_lines(features_b, features_a, "デッキB")

    return {
        "trials": trials,
        "deck_a_win_rate": wins_a / trials,
        "deck_b_win_rate": wins_b / trials,
        "deck_a_wins": wins_a,
        "deck_b_wins": wins_b,
        "average_finish_turn": sum(finish_turns) / len(finish_turns),
        "deck_a": {
            "summary": features_a["summary"],
            "base_power": round(base_a, 3),
            "favorable_factors": favorable_a,
            "unfavorable_factors": unfavorable_a,
        },
        "deck_b": {
            "summary": features_b["summary"],
            "base_power": round(base_b, 3),
            "favorable_factors": favorable_b,
            "unfavorable_factors": unfavorable_b,
        },
    }

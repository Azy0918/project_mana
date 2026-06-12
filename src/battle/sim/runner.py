from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from src.battle.kernel.cards import BattleCard, battle_deck_from_dicts
from src.battle.kernel.engine import DEFAULT_MAX_TURNS, DuelEngine
from src.battle.kernel.policy import GreedyPolicy, Policy

# 「エンジンが回った」とみなす効果op(墓地エンジン系。発火率の観測対象)
ENGINE_OPS = ("cast_from_grave", "summon_from_grave")


@dataclass
class SimulationSummary:
    games: int
    wins_a: int
    wins_b: int
    draws: int
    win_rate_a: float
    win_rate_b: float
    ci95_low_a: float
    ci95_high_a: float
    average_turns: float
    finish_reasons: dict[str, int]
    engine_fire_rate_a: float = 0.0  # デッキAのエンジン系効果が1回以上成立した試合の割合
    sample_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "games": self.games,
            "wins_a": self.wins_a,
            "wins_b": self.wins_b,
            "draws": self.draws,
            "win_rate_a": self.win_rate_a,
            "win_rate_b": self.win_rate_b,
            "ci95_low_a": self.ci95_low_a,
            "ci95_high_a": self.ci95_high_a,
            "average_turns": self.average_turns,
            "finish_reasons": dict(self.finish_reasons),
            "engine_fire_rate_a": self.engine_fire_rate_a,
        }


def _wilson_interval(wins: int, games: int) -> tuple[float, float]:
    if games <= 0:
        return 0.0, 0.0
    z = 1.96
    p = wins / games
    denominator = 1 + z * z / games
    center = (p + z * z / (2 * games)) / denominator
    margin = z * math.sqrt(p * (1 - p) / games + z * z / (4 * games * games)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def simulate_matches(
    deck_a: list[dict[str, Any]] | list[BattleCard],
    deck_b: list[dict[str, Any]] | list[BattleCard],
    games: int = 200,
    seed: int | None = None,
    max_turns: int = DEFAULT_MAX_TURNS,
    policy_a: Policy | None = None,
    policy_b: Policy | None = None,
    effects: dict[str, list[dict[str, Any]]] | None = None,
) -> SimulationSummary:
    """デッキ同士をN試合シミュレーションし、勝率と95%信頼区間を返す。

    先攻有利の偏りを避けるため、試合ごとに先攻デッキを入れ替える。
    effects には承認済みEffectScriptのマップ(card_id -> abilities)を渡す。
    """
    cards_a = deck_a if deck_a and isinstance(deck_a[0], BattleCard) else battle_deck_from_dicts(deck_a)  # type: ignore[arg-type]
    cards_b = deck_b if deck_b and isinstance(deck_b[0], BattleCard) else battle_deck_from_dicts(deck_b)  # type: ignore[arg-type]
    rng = random.Random(seed)
    policy_a = policy_a or GreedyPolicy()
    policy_b = policy_b or GreedyPolicy()

    wins_a = 0
    wins_b = 0
    draws = 0
    total_turns = 0
    engine_fired_games = 0
    finish_reasons: Counter[str] = Counter()
    sample_log: list[dict[str, Any]] = []

    for game_index in range(games):
        a_first = game_index % 2 == 0
        decks = (cards_a, cards_b) if a_first else (cards_b, cards_a)
        policies = (policy_a, policy_b) if a_first else (policy_b, policy_a)
        engine = DuelEngine(
            decks[0],
            decks[1],
            policies[0],
            policies[1],
            rng=random.Random(rng.random()),
            max_turns=max_turns,
            keep_log=game_index == 0,
            effects=effects,
        )
        result = engine.run()
        total_turns += result.turns
        finish_reasons[result.reason] += 1
        a_index = 0 if a_first else 1
        if any(engine.op_success_counts[a_index][op] for op in ENGINE_OPS):
            engine_fired_games += 1
        if game_index == 0:
            sample_log = result.log

        if result.winner is None:
            draws += 1
        elif (result.winner == 0) == a_first:
            wins_a += 1
        else:
            wins_b += 1

    ci_low, ci_high = _wilson_interval(wins_a, games)
    return SimulationSummary(
        games=games,
        wins_a=wins_a,
        wins_b=wins_b,
        draws=draws,
        win_rate_a=wins_a / games if games else 0.0,
        win_rate_b=wins_b / games if games else 0.0,
        ci95_low_a=ci_low,
        ci95_high_a=ci_high,
        average_turns=total_turns / games if games else 0.0,
        finish_reasons=dict(finish_reasons),
        engine_fire_rate_a=engine_fired_games / games if games else 0.0,
        sample_log=sample_log,
    )

from __future__ import annotations

import copy
import random
from typing import TYPE_CHECKING

from src.battle.kernel.policy import AttackChoice, GreedyPolicy

if TYPE_CHECKING:
    from src.battle.kernel.engine import DuelEngine
    from src.battle.kernel.state import GameState, PlayerState


def evaluate_state(state: "GameState", player_index: int) -> float:
    """プレイヤー視点の盤面評価値。勝敗確定時は±1000。"""
    if state.finished:
        if state.winner == player_index:
            return 1000.0
        if state.winner == 1 - player_index:
            return -1000.0
        return 0.0

    def side_value(player: "PlayerState") -> float:
        board_power = sum(creature.card.power for creature in player.battle_zone) / 1000
        return (
            len(player.shields) * 4.0
            + len(player.hand) * 1.5
            + len(player.battle_zone) * 1.2
            + board_power
            + len(player.mana_zone) * 0.4
        )

    me = state.players[player_index]
    opponent = state.players[1 - player_index]
    return side_value(me) - side_value(opponent)


class LookaheadPolicy(GreedyPolicy):
    """攻撃宣言を1手読みで選ぶ方策。

    相手の非公開ゾーン(山札・シールド)をシャッフルして仮の世界を作り
    (determinization)、攻撃を仮実行した後の盤面評価値で行動を選ぶ。
    「攻撃しない」選択肢も評価し、期待値を下げる攻撃は行わない。
    チャージ・召喚・ブロックはGreedyPolicyの基準を引き継ぐ。
    """

    def __init__(
        self,
        rng: random.Random | None = None,
        rollouts: int = 2,
        max_candidates: int = 8,
    ) -> None:
        self.rng = rng or random.Random()
        self.rollouts = max(1, rollouts)
        self.max_candidates = max(1, max_candidates)
        self._engine: "DuelEngine | None" = None

    def bind(self, engine: object) -> None:
        self._engine = engine  # type: ignore[assignment]

    def choose_attack(
        self, state: "GameState", player: "PlayerState", choices: list[AttackChoice]
    ) -> AttackChoice | None:
        if self._engine is None or not choices:
            return super().choose_attack(state, player, choices)

        my_index = state.players.index(player)
        stop_value = evaluate_state(state, my_index)
        best_choice: AttackChoice | None = None
        best_value = stop_value
        for choice in choices[: self.max_candidates]:
            total = 0.0
            for _ in range(self.rollouts):
                total += self._simulate_attack(choice, my_index)
            value = total / self.rollouts
            if value > best_value + 1e-9:
                best_choice = choice
                best_value = value
        return best_choice

    def _simulate_attack(self, choice: AttackChoice, my_index: int) -> float:
        from src.battle.kernel.engine import DuelEngine

        assert self._engine is not None
        state_copy = copy.deepcopy(self._engine.state)
        self._determinize(state_copy, 1 - my_index)
        scratch = DuelEngine(
            [],
            [],
            GreedyPolicy(),
            GreedyPolicy(),
            rng=random.Random(self.rng.random()),
            keep_log=False,
            effects=self._engine.executor.effects,
            state=state_copy,
        )
        attacking_player = state_copy.players[state_copy.active_index]
        if choice.attacker_index >= len(attacking_player.battle_zone):
            return float("-inf")
        scratch._resolve_attack(attacking_player, choice)
        return evaluate_state(scratch.state, my_index)

    def _determinize(self, state: "GameState", hidden_player_index: int) -> None:
        """相手の非公開情報(山札・シールドの中身)を覗かないよう、シャッフルして配り直す。"""
        player = state.players[hidden_player_index]
        pool = player.deck + player.shields
        self.rng.shuffle(pool)
        shield_count = len(player.shields)
        player.shields = pool[:shield_count]
        player.deck = pool[shield_count:]

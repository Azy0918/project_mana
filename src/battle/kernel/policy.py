from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.battle.kernel.state import CreatureInstance, GameState, PlayerState


@dataclass(frozen=True)
class AttackChoice:
    attacker_index: int
    target_creature_index: int | None  # Noneはプレイヤー(シールド)攻撃


class Policy:
    """行動選択インターフェース。エンジンが列挙した合法手から選ぶ。"""

    def bind(self, engine: object) -> None:
        """エンジン構築時に呼ばれる。先読み方策が状態複製に使う(既定は何もしない)。"""

    def choose_effect_target(
        self,
        state: "GameState",
        player: "PlayerState",
        op: str,
        candidates: list["CreatureInstance"],
    ) -> int | None:
        """効果の対象クリーチャーを選ぶ。Noneなら実行器の既定(最大パワー)に任せる。"""
        return None

    def choose_charge(self, state: "GameState", player: "PlayerState") -> int | None:
        raise NotImplementedError

    def choose_main_action(self, state: "GameState", player: "PlayerState", playable: list[int]) -> int | None:
        raise NotImplementedError

    def choose_attack(self, state: "GameState", player: "PlayerState", choices: list[AttackChoice]) -> AttackChoice | None:
        raise NotImplementedError

    def choose_blocker(
        self,
        state: "GameState",
        player: "PlayerState",
        attack: AttackChoice,
        blockers: list["CreatureInstance"],
    ) -> int | None:
        raise NotImplementedError


class RandomPolicy(Policy):
    """動作検証用のランダム方策。"""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def choose_charge(self, state: "GameState", player: "PlayerState") -> int | None:
        if not player.hand:
            return None
        return self.rng.randrange(len(player.hand))

    def choose_main_action(self, state: "GameState", player: "PlayerState", playable: list[int]) -> int | None:
        if not playable or self.rng.random() < 0.1:
            return None
        return self.rng.choice(playable)

    def choose_attack(self, state: "GameState", player: "PlayerState", choices: list[AttackChoice]) -> AttackChoice | None:
        if not choices or self.rng.random() < 0.1:
            return None
        return self.rng.choice(choices)

    def choose_blocker(
        self,
        state: "GameState",
        player: "PlayerState",
        attack: AttackChoice,
        blockers: list["CreatureInstance"],
    ) -> int | None:
        if not blockers or self.rng.random() < 0.5:
            return None
        return self.rng.randrange(len(blockers))


class GreedyPolicy(Policy):
    """単純な貪欲方策。マナを伸ばし、出せる最大コストを出し、常に攻撃する。"""

    def choose_charge(self, state: "GameState", player: "PlayerState") -> int | None:
        if not player.hand:
            return None
        # 現在のマナで出せない最高コストのカードをチャージに回す
        mana_count = len(player.mana_zone) + 1
        unplayable = [i for i, card in enumerate(player.hand) if card.cost > mana_count]
        candidates = unplayable or list(range(len(player.hand)))
        return max(candidates, key=lambda i: player.hand[i].cost)

    def choose_main_action(self, state: "GameState", player: "PlayerState", playable: list[int]) -> int | None:
        creatures = [i for i in playable if player.hand[i].is_creature]
        candidates = creatures or playable
        if not candidates:
            return None
        return max(candidates, key=lambda i: (player.hand[i].cost, player.hand[i].power))

    def choose_attack(self, state: "GameState", player: "PlayerState", choices: list[AttackChoice]) -> AttackChoice | None:
        if not choices:
            return None
        # 勝てるクリーチャー戦を優先し、なければシールドを攻撃する
        opponent = state.opponent
        for choice in choices:
            if choice.target_creature_index is None:
                continue
            attacker = player.battle_zone[choice.attacker_index]
            target = opponent.battle_zone[choice.target_creature_index]
            if attacker.card.power > target.card.power:
                return choice
        player_attacks = [choice for choice in choices if choice.target_creature_index is None]
        return player_attacks[0] if player_attacks else None

    def choose_blocker(
        self,
        state: "GameState",
        player: "PlayerState",
        attack: AttackChoice,
        blockers: list["CreatureInstance"],
    ) -> int | None:
        # シールドが少ないときのみ、生き残れる(または相打ちの)最大パワーのブロッカーで守る
        if len(player.shields) > 2:
            return None
        attacker_power = state.active_player.battle_zone[attack.attacker_index].card.power
        survivors = [i for i, blocker in enumerate(blockers) if blocker.card.power >= attacker_power]
        if survivors:
            return max(survivors, key=lambda i: blockers[i].card.power)
        if not player.shields:
            return max(range(len(blockers)), key=lambda i: blockers[i].card.power)
        return None

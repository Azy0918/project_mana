from __future__ import annotations

from typing import TYPE_CHECKING

from src.battle.kernel.engine import effective_cost
from src.battle.kernel.policy import GreedyPolicy

if TYPE_CHECKING:
    from src.battle.kernel.state import GameState, PlayerState


class ComboPolicy(GreedyPolicy):
    """G・ゼロ条件の達成を狙うコンボ方策。

    手札にG・ゼロカードがある間は、安い呪文から順に唱えて呪文カウントを稼ぎ、
    条件を満たしたG・ゼロカードを即座にプレイする。
    G・ゼロカードがなければ貪欲方策と同じ。
    """

    def choose_main_action(self, state: "GameState", player: "PlayerState", playable: list[int]) -> int | None:
        g_zero_in_hand = [
            index for index, card in enumerate(player.hand) if card.g_zero_spell_count is not None
        ]
        if g_zero_in_hand:
            # 条件達成済みのG・ゼロカードがあれば最優先で出す(最大コスト=最大の踏み倒し)
            ready = [
                index
                for index in playable
                if player.hand[index].g_zero_spell_count is not None
                and effective_cost(player, player.hand[index]) == 0
            ]
            if ready:
                return max(ready, key=lambda index: player.hand[index].cost)
            # 呪文カウントを稼ぐため、安い呪文から唱える
            spells = [index for index in playable if player.hand[index].is_spell]
            if spells:
                return min(spells, key=lambda index: player.hand[index].cost)
        return super().choose_main_action(state, player, playable)

    def choose_charge(self, state: "GameState", player: "PlayerState") -> int | None:
        if not player.hand:
            return None
        # G・ゼロカードはコストを支払わないので、出せない扱いでマナに埋めない
        g_zero = {index for index, card in enumerate(player.hand) if card.g_zero_spell_count is not None}
        candidates = [index for index in range(len(player.hand)) if index not in g_zero]
        if not candidates:
            return None
        mana_count = len(player.mana_zone) + 1
        unplayable = [index for index in candidates if player.hand[index].cost > mana_count]
        pool = unplayable or candidates
        return max(pool, key=lambda index: player.hand[index].cost)

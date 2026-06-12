from __future__ import annotations

from typing import TYPE_CHECKING

from src.battle.kernel.engine import effective_cost
from src.battle.kernel.policy import GreedyPolicy

if TYPE_CHECKING:
    from src.battle.kernel.state import GameState, PlayerState


class ComboPolicy(GreedyPolicy):
    """G・ゼロ条件の達成とMRC型エンジンの組立を狙うコンボ方策。

    - G・ゼロ: 安い呪文から連打して条件達成→0コスト召喚
    - MRC型: 墓地適性カード(攻撃時詠唱エンジン/墓地から詠唱できる呪文)を
      選んで捨て、エンジン本体はチャージに埋めない
    該当カードがなければ貪欲方策と同じ。

    チャージ保護をエンジンに限定するのは測定結果による: 墓地適性カード全体を
    保護すると、保護カードだけが手札に溜まってマナが止まる選択効果が起き、
    強さが43.0→28.4まで悪化した(エンジン限定+全保護時の貪欲退避なら45.8)。
    """

    def __init__(self) -> None:
        self._grave_good: set[str] = set()
        self._engines: set[str] = set()

    def bind(self, engine: object) -> None:
        # 効果マップから「墓地に置く価値があるカード」を割り出す
        effects = getattr(getattr(engine, "executor", None), "effects", {}) or {}
        engines = set()
        spells_castable = set()
        for card_id, abilities in effects.items():
            for ability in abilities:
                for action in ability.get("actions", []):
                    if ability.get("trigger") == "on_attack" and action.get("op") == "cast_from_grave":
                        engines.add(card_id)
                    if ability.get("trigger") == "on_cast" and action.get("op") == "summon_from_grave":
                        spells_castable.add(card_id)
        # エンジンが存在する世界では、蘇生呪文と(蘇生対象になる)エンジン自身が墓地適性
        self._engines = engines
        self._grave_good = (engines | spells_castable) if engines else set()

    def choose_discard(self, state, player, hand):
        # 墓地適性カードを優先して捨てる(エンジンの弾込め)
        candidates = [i for i, card in enumerate(hand) if card.card_id in self._grave_good]
        if candidates:
            return max(candidates, key=lambda i: hand[i].cost)
        return None

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
        # G・ゼロカードとエンジン本体はマナに埋めない(蘇生呪文の弾は保護しない)
        protected = {
            index for index, card in enumerate(player.hand)
            if card.g_zero_spell_count is not None or card.card_id in self._engines
        }
        candidates = [index for index in range(len(player.hand)) if index not in protected]
        if not candidates:
            # 手札が保護対象だけならマナ詰まり回避を優先して貪欲に従う
            return super().choose_charge(state, player)
        mana_count = len(player.mana_zone) + 1
        unplayable = [index for index in candidates if player.hand[index].cost > mana_count]
        pool = unplayable or candidates
        return max(pool, key=lambda index: player.hand[index].cost)

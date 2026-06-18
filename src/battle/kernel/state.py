from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.battle.kernel.cards import BattleCard


@dataclass
class ManaCard:
    card: BattleCard
    tapped: bool = False


def make_mana_card(card: BattleCard) -> ManaCard:
    """マナゾーンに置くカードを作る。多色カードはタップして置かれる。"""
    return ManaCard(card=card, tapped=card.is_multicolor)


@dataclass
class CreatureInstance:
    card: BattleCard
    tapped: bool = False
    summoned_turn: int = 0
    temporary: bool = False  # B・A・D等: ターン終了時に破壊される
    granted_speed: bool = False  # 効果による一時的なスピードアタッカー付与
    power_modifier: int = 0  # 効果による一時的なパワー増減(ターン終了時リセット)

    @property
    def current_power(self) -> int:
        """一時修整込みの現在パワー(戦闘・破壊判定用)。"""
        return self.card.power + self.power_modifier

    @property
    def current_attack_power(self) -> int:
        return self.card.attack_power + self.power_modifier

    def can_attack(self, current_turn: int) -> bool:
        if self.tapped:
            return False
        if self.summoned_turn < current_turn:
            return True
        return self.card.is_speed_attacker or self.card.is_evolution or self.granted_speed

    def can_attack_creature(self, current_turn: int) -> bool:
        if self.card.cannot_attack_creature:
            return False
        # マッハファイターは出たターンでもクリーチャーには攻撃できる
        return self.can_attack(current_turn) or (not self.tapped and self.card.is_mach_fighter)


@dataclass
class PlayerState:
    name: str
    deck: list[BattleCard] = field(default_factory=list)
    hand: list[BattleCard] = field(default_factory=list)
    mana_zone: list[ManaCard] = field(default_factory=list)
    battle_zone: list[CreatureInstance] = field(default_factory=list)
    shields: list[BattleCard] = field(default_factory=list)
    graveyard: list[BattleCard] = field(default_factory=list)
    spells_cast_this_turn: int = 0
    extra_turns_taken: int = 0
    strigger_disabled: bool = False

    def untapped_mana(self) -> list[ManaCard]:
        return [mana for mana in self.mana_zone if not mana.tapped]

    def untap_all(self) -> None:
        for mana in self.mana_zone:
            mana.tapped = False
        for creature in self.battle_zone:
            # 「アンタップしない」弱点を持つクリーチャーはタップしたまま(text 由来・常時)
            if creature.card.no_untap:
                continue
            creature.tapped = False

    def has_keyword(self, creature: CreatureInstance, keyword: str) -> bool:
        """静的キーワード or 自分のバトルゾーンのオーラ付与で、creatureがkeywordを持つか。"""
        card = creature.card
        if keyword == "ブロッカー" and card.is_blocker:
            return True
        if keyword == "スピードアタッカー" and card.is_speed_attacker:
            return True
        if keyword == "スレイヤー" and card.is_slayer:
            return True
        if keyword == "マッハファイター" and card.is_mach_fighter:
            return True
        for src in self.battle_zone:
            for kw, race in src.card.keyword_grants:
                if kw == keyword and (race is None or (race and race in card.race)):
                    return True
        return False

    def untapped_blockers(self) -> list[CreatureInstance]:
        return [c for c in self.battle_zone if self.has_keyword(c, "ブロッカー") and not c.tapped]

    def guardman_creatures(self) -> list[CreatureInstance]:
        return [c for c in self.battle_zone if c.card.is_guardman and not c.tapped]


@dataclass
class GameState:
    players: tuple[PlayerState, PlayerState]
    turn: int = 0
    active_index: int = 0
    winner: int | None = None
    finished: bool = False
    extra_turn_pending: bool = False
    # 「ターンの残りをとばす」: アクティブプレイヤーの残りフェイズを中断する。
    # 各ターン開始時に必ず False にリセットされ、当該ターン内でのみ有効。
    skip_active_turn: bool = False
    # (controller_index, 発生源カード, action) のターン終了時遅延効果
    deferred_end_of_turn: list[Any] = field(default_factory=list)
    finish_reason: str = ""
    log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def active_player(self) -> PlayerState:
        return self.players[self.active_index]

    @property
    def opponent_index(self) -> int:
        return 1 - self.active_index

    @property
    def opponent(self) -> PlayerState:
        return self.players[self.opponent_index]

    def record(self, action: str, **detail: Any) -> None:
        entry: dict[str, Any] = {"turn": self.turn, "player": self.active_player.name, "action": action}
        entry.update(detail)
        self.log.append(entry)

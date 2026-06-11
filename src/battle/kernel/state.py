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

    def can_attack(self, current_turn: int) -> bool:
        if self.tapped:
            return False
        return self.summoned_turn < current_turn or self.card.is_speed_attacker

    def can_attack_creature(self, current_turn: int) -> bool:
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

    def untapped_mana(self) -> list[ManaCard]:
        return [mana for mana in self.mana_zone if not mana.tapped]

    def untap_all(self) -> None:
        for mana in self.mana_zone:
            mana.tapped = False
        for creature in self.battle_zone:
            creature.tapped = False

    def untapped_blockers(self) -> list[CreatureInstance]:
        return [creature for creature in self.battle_zone if creature.card.is_blocker and not creature.tapped]


@dataclass
class GameState:
    players: tuple[PlayerState, PlayerState]
    turn: int = 0
    active_index: int = 0
    winner: int | None = None
    finished: bool = False
    extra_turn_pending: bool = False
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

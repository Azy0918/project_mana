from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


def _parse_power(value: Any) -> int:
    text = str(value or "").strip()
    match = re.search(r"\d+", text)
    if match:
        return int(match.group())
    return 0


def _split_civilizations(value: Any) -> tuple[str, ...]:
    return tuple(civ.strip() for civ in str(value or "").split("/") if civ.strip())


def _split_tags(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(tag for tag in value if tag)
    return tuple(tag.strip() for tag in str(value).split(";") if tag.strip())


@dataclass(frozen=True)
class BattleCard:
    card_id: str
    name: str
    civilizations: tuple[str, ...]
    cost: int
    card_type: str
    power: int
    text: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_creature(self) -> bool:
        return "クリーチャー" in self.card_type

    @property
    def is_spell(self) -> bool:
        return "呪文" in self.card_type

    @property
    def is_blocker(self) -> bool:
        return "ブロッカー" in self.tags or "ブロッカー" in self.text

    @property
    def breaker_count(self) -> int:
        haystack = self.text + ";".join(self.tags)
        if "T・ブレイカー" in haystack:
            return 3
        if "W・ブレイカー" in haystack:
            return 2
        return 1


def battle_card_from_dict(card: dict[str, Any]) -> BattleCard:
    return BattleCard(
        card_id=str(card.get("card_id", "")),
        name=str(card.get("name", "")),
        civilizations=_split_civilizations(card.get("civilization")),
        cost=int(card.get("cost") or 0),
        card_type=str(card.get("card_type", "")),
        power=_parse_power(card.get("power")),
        text=str(card.get("text", "") or ""),
        tags=_split_tags(card.get("tags")),
    )


def battle_deck_from_dicts(deck: list[dict[str, Any]]) -> list[BattleCard]:
    cards: list[BattleCard] = []
    for entry in deck:
        quantity = int(entry.get("quantity", 1))
        card = battle_card_from_dict(entry)
        cards.extend([card] * quantity)
    return cards

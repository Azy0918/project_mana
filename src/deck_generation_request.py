from __future__ import annotations

from dataclasses import dataclass


def parse_tag_input(value: str) -> list[str]:
    if not value:
        return []

    tags = []
    for tag in value.replace(",", ";").replace("、", ";").split(";"):
        tag = tag.strip()
        if tag and tag not in tags:
            tags.append(tag)

    return tags


@dataclass
class DeckGenerationRequest:
    deck_name: str
    civilizations: list[str]
    deck_type: str
    focus_tags: list[str]
    avoid_tags: list[str]
    strategy_note: str
    deck_size: int
    early_ratio: int = 30
    defense_ratio: int = 30
    finisher_ratio: int = 20

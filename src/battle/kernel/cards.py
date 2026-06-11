from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_G_ZERO_PATTERN = re.compile(r"G・ゼロ\s*[:：]\s*.*?呪文を(\d+)枚以上唱えたターン")
_G_ZERO_GRAVE_PATTERN = re.compile(r"G・ゼロ\s*[:：]\s*.*?墓地に.*?(\d+)枚以上")
_COST_REDUCTION_PATTERN = re.compile(r"コストを(\d+)少なくする")
_BAD_PATTERN = re.compile(r"B・A・D(?:・S)?\s*(\d+)")


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
        if "クリーチャー" in self.card_type:
            return True
        # ツインパクトはパワーを持てばクリーチャー面で運用する
        return "ツインパクト" in self.card_type and self.power > 0

    @property
    def is_spell(self) -> bool:
        return "呪文" in self.card_type

    @property
    def is_blocker(self) -> bool:
        return "ブロッカー" in self.tags or "ブロッカー" in self.text

    @property
    def is_speed_attacker(self) -> bool:
        return "スピードアタッカー" in self.tags or "スピードアタッカー" in self.text

    @property
    def is_mach_fighter(self) -> bool:
        return "マッハファイター" in self.tags or "マッハファイター" in self.text

    @property
    def cannot_attack_player(self) -> bool:
        return "プレイヤーを攻撃できない" in self.text

    @property
    def cannot_attack(self) -> bool:
        # 「相手プレイヤーを攻撃できない」は部分制限なので全面攻撃禁止とは区別する
        if self.cannot_attack_player:
            return False
        return "攻撃できない" in self.text

    @property
    def is_unblockable(self) -> bool:
        return "ブロックされない" in self.text

    @property
    def is_multicolor(self) -> bool:
        return len(self.civilizations) > 1

    @property
    def g_zero_spell_count(self) -> int | None:
        """G・ゼロ条件(このターン唱えた呪文の枚数)。なければNone。"""
        match = _G_ZERO_PATTERN.search(self.text)
        if match:
            return int(match.group(1))
        return None

    @property
    def g_zero_grave_count(self) -> int | None:
        """G・ゼロ条件(自分の墓地の枚数)。なければNone。"""
        match = _G_ZERO_GRAVE_PATTERN.search(self.text)
        if match:
            return int(match.group(1))
        return None

    @property
    def bad_discount(self) -> int:
        """B・A・D(コストN軽減で使えるが、ターン終了時に破壊される)。なければ0。"""
        match = _BAD_PATTERN.search(self.text)
        if match:
            return int(match.group(1))
        return 0

    @property
    def summon_cost_reduction(self) -> int:
        """バトルゾーンにいる間、自分のクリーチャー召喚コストを下げる量(近似)。

        種族・条件指定は無視した常時オーラとして扱う。
        """
        if not self.is_creature:
            return 0
        match = _COST_REDUCTION_PATTERN.search(self.text)
        if match:
            return int(match.group(1))
        return 0

    @property
    def power_attacker_bonus(self) -> int:
        match = re.search(r"パワーアタッカー\s*\+\s*(\d+)", self.text)
        if match:
            return int(match.group(1))
        return 0

    @property
    def attack_power(self) -> int:
        """攻撃時の実効パワー(パワーアタッカー込み)。"""
        return self.power + self.power_attacker_bonus

    @property
    def breaker_count(self) -> int:
        haystack = self.text + ";".join(self.tags)
        if "T・ブレイカー" in haystack:
            return 3
        if "W・ブレイカー" in haystack:
            return 2
        if "パワード・ブレイカー" in haystack:
            # パワー6000につき1枚ブレイク(切り上げ)の近似
            return max(1, (self.power + 5999) // 6000)
        return 1

    @property
    def is_charger(self) -> bool:
        """チャージャー呪文: 唱えた後、墓地ではなくマナゾーンに置く。"""
        return self.is_spell and "チャージャー" in self.text

    @property
    def is_slayer(self) -> bool:
        """スレイヤー: バトルした相手クリーチャーをパワーに関係なく破壊する。"""
        return "スレイヤー" in self.text or "スレイヤー" in self.tags

    @property
    def enters_tapped(self) -> bool:
        return "タップしてバトルゾーンに出る" in self.text

    @property
    def is_shield_burner(self) -> bool:
        """ブレイクしたシールドを手札に加えさせず墓地に置かせる。"""
        return "手札に加えるかわりに墓地に置く" in self.text

    @property
    def is_evolution(self) -> bool:
        """進化クリーチャー: 召喚酔いしない(進化元の条件は無視する近似)。"""
        return "進化" in self.card_type or bool(re.search(r"進化\s*[:：]", self.text))


def battle_card_from_dict(card: dict[str, Any]) -> BattleCard:
    card_type = str(card.get("card_type", ""))
    power = _parse_power(card.get("power"))
    cost = int(card.get("cost") or 0)
    # データ品質対策: コスト0登録のツインパクトはパワーからコストを推定する
    # (実カードにコスト0は存在せず、放置すると毎ターン無償プレイになるため)
    if cost <= 0 and "ツインパクト" in card_type:
        cost = max(2, power // 1000)
    return BattleCard(
        card_id=str(card.get("card_id", "")),
        name=str(card.get("name", "")),
        civilizations=_split_civilizations(card.get("civilization")),
        cost=cost,
        card_type=card_type,
        power=power,
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

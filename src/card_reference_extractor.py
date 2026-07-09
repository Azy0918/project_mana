from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CIVS = ["光", "水", "闇", "火", "自然"]

# 展開元ゾーン→バトルゾーンの踏み倒し構文
_DEPLOY_RE = re.compile(
    r"(?P<zone>手札|マナゾーン|墓地|山札)(?:の中|の上|の一番上)?から(?P<desc>[^。]{0,60}?)を?バトルゾーンに出"
)
_COST_CAP_RE = re.compile(r"コスト(?:の合計が)?(?P<value>\d+)以下")
_POWER_CAP_RE = re.compile(r"パワー(?P<value>\d+)以下")
_CHANGE_RE = re.compile(r"革命チェンジ[：:](?P<desc>[^。\n■]+)")
_INVASION_RE = re.compile(r"■侵略[：:](?P<desc>[^。\n■]+)")
_EVOLUTION_RE = re.compile(r"■(?:NEO)?進化[：:](?P<desc>[^。\n■]+)")
_COST_MIN_RE = re.compile(r"コスト(?P<value>\d+)以上")


@dataclass
class DeploySpec:
    zone: str
    civs: list[str] = field(default_factory=list)
    cost_cap: int | None = None
    power_cap: int | None = None
    race_terms: list[str] = field(default_factory=list)
    evolution_excluded: bool = False
    target_type: str = "クリーチャー"


@dataclass
class ChangeCondition:
    """革命チェンジ/侵略/進化元のような「特定条件のクリーチャーを踏み台にする」条件。"""

    civs: list[str] = field(default_factory=list)
    cost_min: int | None = None
    needs_dragon: bool = False
    race_terms: list[str] = field(default_factory=list)


@dataclass
class ReferenceProfile:
    """カードが「何を出せるか」「どんな条件でチェンジできるか」「自分がどう出されうるか」。"""

    deploys: list[DeploySpec] = field(default_factory=list)
    change_condition: ChangeCondition | None = None
    invasion_condition: ChangeCondition | None = None
    evolution_condition: ChangeCondition | None = None
    is_madness: bool = False
    discards_own_hand: bool = False


# 種族語はカードDBのrace列が未整備のため、テキスト/名前との照合に使う既知種族の暫定リスト。
KNOWN_RACE_TERMS = [
    "ドラゴン",
    "コマンド",
    "ビートジョッキー",
    "マフィ・ギャング",
    "グランセクト",
    "ムートピア",
    "メタリカ",
    "ジョーカーズ",
    "スノーフェアリー",
    "ビーストフォーク",
    "ドリームメイト",
    "魔導具",
    "サバイバー",
    "イニシエート",
    "リキッド・ピープル",
    "サイバーロード",
    "ガーディアン",
    "デーモン・コマンド",
    "エンジェル・コマンド",
    "アーマロイド",
    "ヒューマノイド",
]


def _split_sentences(text: str) -> list[str]:
    return [sentence for sentence in re.split(r"[。\n]", str(text or "")) if sentence]


def _parse_deploy_desc(desc: str) -> tuple[list[str], int | None, int | None, list[str], bool, str]:
    civs = [civ for civ in CIVS if f"{civ}の" in desc]
    cost_cap_match = _COST_CAP_RE.search(desc)
    power_cap_match = _POWER_CAP_RE.search(desc)
    races = [race for race in KNOWN_RACE_TERMS if race in desc]
    evolution_excluded = "進化でない" in desc
    target_type = "呪文" if "呪文" in desc else "クリーチャー"
    return (
        civs,
        int(cost_cap_match.group("value")) if cost_cap_match else None,
        int(power_cap_match.group("value")) if power_cap_match else None,
        races,
        evolution_excluded,
        target_type,
    )


def _parse_ride_condition(match: re.Match[str] | None) -> ChangeCondition | None:
    if match is None:
        return None
    desc = match.group("desc")
    cost_min_match = _COST_MIN_RE.search(desc)
    return ChangeCondition(
        civs=[civ for civ in CIVS if civ in desc],
        cost_min=int(cost_min_match.group("value")) if cost_min_match else None,
        needs_dragon="ドラゴン" in desc or "龍" in desc,
        race_terms=[race for race in KNOWN_RACE_TERMS if race != "ドラゴン" and race in desc],
    )


def extract_reference_profile(text: str) -> ReferenceProfile:
    profile = ReferenceProfile()
    text = str(text or "")

    for match in _DEPLOY_RE.finditer(text):
        desc = match.group("desc")
        # 「バトルゾーンに出た時」等の誘発や、「捨てられる時、かわりに出す」型の
        # 自己展開(マッドネス)は他カードの踏み倒しではないため除外
        if any(keyword in desc for keyword in ["出た時", "捨てられ", "かわりに"]):
            continue
        civs, cost_cap, power_cap, races, evo_excluded, target_type = _parse_deploy_desc(desc)
        profile.deploys.append(
            DeploySpec(
                zone=match.group("zone"),
                civs=civs,
                cost_cap=cost_cap,
                power_cap=power_cap,
                race_terms=races,
                evolution_excluded=evo_excluded,
                target_type=target_type,
            )
        )

    profile.change_condition = _parse_ride_condition(_CHANGE_RE.search(text))
    profile.invasion_condition = _parse_ride_condition(_INVASION_RE.search(text))
    profile.evolution_condition = _parse_ride_condition(_EVOLUTION_RE.search(text))

    for sentence in _split_sentences(text):
        if "捨てられる時" in sentence and "バトルゾーンに出" in sentence:
            profile.is_madness = True
        if "自分の手札" in sentence and any(keyword in sentence for keyword in ["捨てる", "捨てて"]):
            profile.discards_own_hand = True

    return profile


def _is_creature_type(card_type: str) -> bool:
    return "クリーチャー" in card_type or "ツインパクト" in card_type


def _card_is_dragon(name: str, text: str, race: str) -> bool:
    blob = f"{name} {race}"
    return "ドラゴン" in f"{race} {text}" or "龍" in blob


def _card_matches_race_terms(race_terms: list[str], name: str, text: str, race: str) -> bool:
    if not race_terms:
        return True
    blob = f"{name} {text} {race}"
    return any(term in blob for term in race_terms)


def deploy_link(
    enabler: ReferenceProfile,
    target_civ: str,
    target_cost: int | None,
    target_power: int | None,
    target_type: str,
    target_name: str = "",
    target_text: str = "",
    target_race: str = "",
    target_is_evolution: bool = False,
) -> bool:
    """enablerの展開条件をtargetカードが満たすか(=enablerがtargetを踏み倒せるか)。"""
    for spec in enabler.deploys:
        # ツインパクトはクリーチャー面と呪文面を両方持つ
        if spec.target_type == "クリーチャー" and not _is_creature_type(target_type):
            continue
        if spec.target_type == "呪文" and not ("呪文" in target_type or "ツインパクト" in target_type):
            continue
        if spec.civs and not any(civ in target_civ for civ in spec.civs):
            continue
        if spec.cost_cap is not None and (target_cost is None or target_cost > spec.cost_cap):
            continue
        if spec.power_cap is not None and (target_power is None or target_power > spec.power_cap):
            continue
        if spec.evolution_excluded and target_is_evolution:
            continue
        if not _card_matches_race_terms(spec.race_terms, target_name, target_text, target_race):
            continue
        return True
    return False


def ride_condition_link(
    condition: ChangeCondition | None,
    source_civ: str,
    source_cost: int | None,
    source_type: str,
    source_name: str = "",
    source_text: str = "",
    source_race: str = "",
) -> bool:
    """革命チェンジ/侵略/進化元の条件をsourceカード(踏み台側)が満たすか。"""
    if condition is None:
        return False
    if not _is_creature_type(source_type):
        return False
    if condition.civs and not any(civ in source_civ for civ in condition.civs):
        return False
    if condition.cost_min is not None and (source_cost is None or source_cost < condition.cost_min):
        return False
    if condition.needs_dragon and not _card_is_dragon(source_name, source_text, source_race):
        return False
    if condition.race_terms and not _card_matches_race_terms(
        condition.race_terms, source_name, source_text, source_race
    ):
        return False
    return True


def change_link(
    payoff: ReferenceProfile,
    source_civ: str,
    source_cost: int | None,
    source_type: str,
    source_name: str = "",
    source_text: str = "",
    source_race: str = "",
) -> bool:
    """payoffの革命チェンジ条件をsourceカード(チェンジ元)が満たすか。"""
    return ride_condition_link(
        payoff.change_condition,
        source_civ,
        source_cost,
        source_type,
        source_name,
        source_text,
        source_race,
    )


def madness_link(madness_card: ReferenceProfile, discarder: ReferenceProfile) -> bool:
    """マッドネス(捨てられる時に出る)と自分の手札を捨てる効果の接続。"""
    return madness_card.is_madness and discarder.discards_own_hand

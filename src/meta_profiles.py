from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetaProfile:
    name: str
    required_tags: set[str]
    speed: int
    defense: int
    resource: int
    finish_speed: int
    description: str


META_PROFILES: dict[str, MetaProfile] = {
    "速攻": MetaProfile(
        name="速攻",
        required_tags={"初動", "ビートダウン", "S・トリガー", "受け札", "除去"},
        speed=5,
        defense=2,
        resource=2,
        finish_speed=5,
        description="低コスト展開で早期決着を狙う仮想環境デッキ。",
    ),
    "中速": MetaProfile(
        name="中速",
        required_tags={"初動", "マナ加速", "除去", "リソース", "フィニッシャー"},
        speed=3,
        defense=3,
        resource=3,
        finish_speed=3,
        description="初動、除去、展開、フィニッシュをバランスよく持つ仮想環境デッキ。",
    ),
    "コントロール": MetaProfile(
        name="コントロール",
        required_tags={"受け札", "除去", "防御", "ハンデス", "リソース", "フィニッシャー"},
        speed=2,
        defense=5,
        resource=5,
        finish_speed=2,
        description="受けとリソースで長期戦を狙う仮想環境デッキ。",
    ),
    "コンボ": MetaProfile(
        name="コンボ",
        required_tags={"初動", "マナ加速", "ドロー", "リソース", "ロック", "フィニッシャー"},
        speed=3,
        defense=2,
        resource=5,
        finish_speed=4,
        description="必要札を集めて特定ターンに強い勝ち筋を通す仮想環境デッキ。",
    ),
    "受け特化": MetaProfile(
        name="受け特化",
        required_tags={"受け札", "S・トリガー", "防御", "タップ", "除去", "フィニッシャー"},
        speed=1,
        defense=5,
        resource=3,
        finish_speed=2,
        description="防御札を厚く取り、相手の攻めを受け切る仮想環境デッキ。",
    ),
}

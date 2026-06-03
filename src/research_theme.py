from __future__ import annotations

from copy import deepcopy
from typing import Any


RESEARCH_THEMES: dict[str, dict[str, Any]] = {
    "黒緑ドンジャングル": {
        "deck_type": "コントロール",
        "main_colors": ["闇", "自然"],
        "allowed_colors": ["闇", "自然"],
        "splash_colors": [],
        "required_cards": [
            "ドンジャングルS7",
            "ヤドック",
            "刻解人形ジェニー・ジェーン",
            "ライフプラン・チャージャー",
            "龍罠 エスカルデン/マクスカルゴ・トラップ",
        ],
        "required_counts": {
            "ドンジャングルS7": 2,
            "ヤドック": 4,
            "刻解人形ジェニー・ジェーン": 3,
            "ライフプラン・チャージャー": 4,
            "龍罠 エスカルデン/マクスカルゴ・トラップ": 3,
        },
        "preferred_counts": {
            "ドンジャングルS7": 3,
            "トラップ×トラップ": 3,
        },
        "recommended_cards": ["スペル・デル・フィン", "ニコル・ボーラス", "ソーナンデス"],
        "forbidden_patterns": ["文明過多", "主軸なし", "ピン挿し過多"],
        "required_tags": {"踏み倒しメタ": 4, "ハンデス": 3, "リソース": 6, "マナ加速": 4},
        "required_roles": {"defense": 6, "resource": 8, "removal": 6, "lock": 3, "finisher": 2},
        "forbidden_role_patterns": ["attack_only_control", "no_resource", "no_removal", "no_finisher"],
        "target_matchups": ["赤系レイド", "青単スコーラー"],
        "youtube_keywords": ["ドンジャングル", "ヤドック", "ジェニー", "ジェニージェン", "レイド", "スコーラー"],
        "profile": {
            "target_tags": {
                "受け札": 2.0,
                "除去": 2.2,
                "ハンデス": 2.2,
                "踏み倒しメタ": 2.4,
                "ロック": 2.0,
                "リソース": 2.1,
                "マナ加速": 2.0,
                "フィニッシャー": 1.4,
            },
            "min_attack": 8,
            "min_low_attack": 4,
            "min_defense": 10,
            "target_resource": 10,
            "max_avg_cost": 4.6,
            "max_high_cost": 6,
        },
    },
    "黒緑TierSメタコントロール": {
        "format": "AD",
        "deck_type": "コントロール",
        "main_colors": ["闇", "自然"],
        "allowed_colors": ["闇", "自然"],
        "splash_colors": [],
        "required_cards": [
            "獣軍隊 ヤドック",
            "トラップ×トラップ",
            "ライフプラン・チャージャー",
            "龍罠 エスカルデン/マクスカルゴ・トラップ",
        ],
        "required_counts": {
            "獣軍隊 ヤドック": 4,
            "トラップ×トラップ": 4,
            "ライフプラン・チャージャー": 4,
            "龍罠 エスカルデン/マクスカルゴ・トラップ": 2,
        },
        "preferred_counts": {
            "ドンジャングルS7": 0,
        },
        "recommended_cards": [
            "獣軍隊 ヤドック",
            "トラップ×トラップ",
            "ライフプラン・チャージャー",
            "龍罠 エスカルデン/マクスカルゴ・トラップ",
        ],
        "forbidden_cards": [
            "ニャンダフル・ニャン",
            "自動車男",
        ],
        "penalty_cards": {
            "暗黒獣ヤミノシーザー": 18,
            "虚像の大富豪 ラピス・ラズリ": 18,
            "ドンジャングルS7": 12,
        },
        "soft_limits": {
            "ドンジャングルS7": {
                "max_preferred": 1,
                "penalty_if_at_least": 2,
                "penalty": 15,
            },
            "primary_attack": {
                "max_preferred": 20,
                "penalty": 2,
            },
        },
        "forbidden_patterns": ["文明過多", "ピン挿し過多"],
        "required_tags": {"踏み倒しメタ": 7, "リソース": 14, "マナ加速": 10, "除去": 8, "受け札": 10, "ロック": 5},
        "required_roles": {"defense": 10, "resource": 14, "removal": 8, "lock": 5, "mana_boost": 10, "anti_cheat": 7},
        "recommended_max_roles": {"primary_attack": 20},
        "forbidden_role_patterns": ["attack_only_control", "no_resource", "no_removal", "no_lock"],
        "target_matchups": ["火光レイド/ブランド Tier S", "火光レイド", "火水レイド", "赤単ブランド"],
        "target_matchups_by_format": {
            "AD": ["火光レイド/ブランド Tier S", "火光レイド", "火水レイド", "赤単ブランド", "水単スコーラー", "自然単デンジャデオン"],
            "ND": ["火光レイド", "火水レイド", "赤単ブランド", "水単スコーラー", "自然単デンジャデオン"],
        },
        "youtube_keywords": ["黒緑", "ヤドック", "トラップ×トラップ", "火光レイド", "ブランド", "踏み倒しメタ"],
        "profile": {
            "target_tags": {
                "受け札": 3.0,
                "除去": 3.0,
                "踏み倒しメタ": 3.2,
                "ロック": 2.7,
                "リソース": 2.6,
                "マナ加速": 2.7,
                "ハンデス": 1.4,
                "フィニッシャー": 0.8,
                "打点": 0.4,
            },
            "min_attack": 4,
            "min_low_attack": 0,
            "min_defense": 12,
            "target_resource": 14,
            "max_avg_cost": 4.2,
            "max_high_cost": 4,
        },
        "notes": [
            "黒緑ドンジャングルから派生するが、ドンジャングルS7には依存しない",
            "Tier S火光レイド/ブランド後攻を止めるため、受け・軽量除去・踏み倒しメタ・ロックを厚くする",
            "ヤドック4、トラップ×トラップ4を固定主軸にする",
        ],
    },
    "赤白レイド": {
        "deck_type": "速攻",
        "main_colors": ["火", "光"],
        "allowed_colors": ["火", "光"],
        "splash_colors": [],
        "required_cards": [],
        "required_counts": {},
        "recommended_cards": ["マグナム・チュリス", "早撃人形マグナム", "ミラクルストップ"],
        "forbidden_patterns": ["文明過多", "重すぎる", "ピン挿し過多"],
        "required_tags": {"打点": 12, "即効性": 6, "シールド圧力": 4},
        "required_roles": {"early": 12, "attack": 22, "defense": 4},
        "forbidden_role_patterns": ["no_finisher"],
        "target_matchups": ["自然単デンジャデオン", "青単スコーラー"],
        "youtube_keywords": ["レイド", "赤白", "火光", "早期打点"],
        "profile": {
            "target_tags": {"打点": 3.2, "即効性": 2.8, "シールド圧力": 2.4, "受け札": 1.2, "ロック": 1.6, "除去": 1.2},
            "min_attack": 22,
            "min_low_attack": 18,
            "min_defense": 6,
            "target_resource": 5,
            "max_avg_cost": 3.8,
            "max_high_cost": 2,
            "fast_finish": True,
        },
    },
    "青単スコーラー": {
        "deck_type": "コンボ",
        "main_colors": ["水"],
        "allowed_colors": ["水"],
        "splash_colors": [],
        "required_cards": ["次元の嵐 スコーラー"],
        "required_counts": {"次元の嵐 スコーラー": 3},
        "recommended_cards": [],
        "forbidden_patterns": ["文明過多", "主軸なし"],
        "required_tags": {"ドロー": 8, "リソース": 10, "コンボ": 3},
        "required_roles": {"resource": 12, "defense": 4, "finisher": 2},
        "forbidden_role_patterns": ["no_resource", "no_finisher"],
        "target_matchups": ["赤系レイド", "白単サバキZ"],
        "youtube_keywords": ["スコーラー", "青単", "水単", "呪文連打"],
        "profile": {
            "target_tags": {"ドロー": 3.0, "リソース": 2.6, "コンボ": 2.4, "呪文": 2.2, "受け札": 1.2, "フィニッシャー": 1.4},
            "min_attack": 4,
            "min_low_attack": 0,
            "min_defense": 6,
            "target_resource": 14,
            "max_avg_cost": 4.2,
            "max_high_cost": 4,
        },
    },
    "黒単デスザーク": {
        "deck_type": "コントロール",
        "main_colors": ["闇"],
        "allowed_colors": ["闇"],
        "splash_colors": [],
        "required_cards": ["卍 デ・スザーク 卍"],
        "required_counts": {"卍 デ・スザーク 卍": 3},
        "recommended_cards": [],
        "forbidden_patterns": ["文明過多", "主軸なし", "ピン挿し過多"],
        "required_tags": {"墓地利用": 6, "除去": 6, "ロック": 3},
        "required_roles": {"defense": 6, "removal": 8, "resource": 5, "lock": 3, "finisher": 2},
        "forbidden_role_patterns": ["attack_only_control", "no_removal", "no_resource", "no_finisher"],
        "target_matchups": ["赤系レイド", "青単スコーラー"],
        "youtube_keywords": ["デスザーク", "黒単", "魔導具"],
        "profile": {
            "target_tags": {"墓地利用": 2.6, "除去": 2.2, "ハンデス": 1.8, "受け札": 1.6, "ロック": 2.2, "フィニッシャー": 1.8},
            "min_attack": 6,
            "min_low_attack": 0,
            "min_defense": 8,
            "target_resource": 8,
            "max_avg_cost": 4.4,
            "max_high_cost": 5,
        },
    },
    "白単サバキZ": {
        "deck_type": "コントロール",
        "main_colors": ["光"],
        "allowed_colors": ["光"],
        "splash_colors": [],
        "required_cards": [],
        "required_counts": {},
        "recommended_cards": [],
        "forbidden_patterns": ["文明過多", "主軸なし"],
        "required_tags": {"受け札": 10, "シールド追加": 4, "裁き": 4, "ロック": 2},
        "required_roles": {"defense": 10, "resource": 4, "removal": 4, "lock": 2, "finisher": 2},
        "forbidden_role_patterns": ["attack_only_control", "attack_overload", "no_defense", "no_resource", "no_lock"],
        "target_matchups": ["赤系レイド", "青単スコーラー"],
        "youtube_keywords": ["サバキZ", "裁き", "白単", "光単"],
        "profile": {
            "target_tags": {"受け札": 2.6, "シールド追加": 2.4, "裁き": 2.6, "ロック": 1.8, "除去": 1.6, "フィニッシャー": 1.4},
            "min_attack": 6,
            "min_low_attack": 0,
            "min_defense": 12,
            "target_resource": 6,
            "max_avg_cost": 4.5,
            "max_high_cost": 5,
        },
    },
    "アナカラーQQQX": {
        "deck_type": "中速",
        "main_colors": ["水", "闇", "自然"],
        "allowed_colors": ["水", "闇", "自然"],
        "splash_colors": [],
        "required_cards": ["Q.Q.QX./終葬 5.S.D."],
        "required_counts": {"Q.Q.QX./終葬 5.S.D.": 3},
        "recommended_cards": [],
        "forbidden_patterns": ["文明過多", "ピン挿し過多"],
        "required_tags": {"山札操作": 4, "特殊勝利": 2, "リソース": 6},
        "required_roles": {"resource": 8, "defense": 6, "removal": 4, "finisher": 2},
        "forbidden_role_patterns": ["no_resource", "no_finisher"],
        "target_matchups": ["自然単デンジャデオン", "赤系レイド"],
        "youtube_keywords": ["QQQX", "終葬", "アナカラー", "山札"],
        "profile": {
            "target_tags": {"山札操作": 2.6, "特殊勝利": 2.6, "リソース": 2.2, "除去": 1.8, "受け札": 1.4, "ロック": 1.6},
            "min_attack": 8,
            "min_low_attack": 4,
            "min_defense": 8,
            "target_resource": 10,
            "max_avg_cost": 4.4,
            "max_high_cost": 5,
        },
    },
}


def list_research_themes() -> list[str]:
    return list(RESEARCH_THEMES)


def get_research_theme(name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    if name not in RESEARCH_THEMES:
        raise ValueError(f"未知の研究テーマです: {name}")
    theme = deepcopy(RESEARCH_THEMES[name])
    theme["name"] = name
    theme["format"] = str(theme.get("format", "AD") or "AD").upper()
    return theme


def theme_to_profile(theme: dict[str, Any], index: int = 1) -> dict[str, Any]:
    profile = deepcopy(theme.get("profile", {}))
    profile.setdefault("target_tags", {})
    profile["name"] = f"theme_{_safe_key(theme['name'])}_{index}"
    profile["title"] = f"制約付き夜間研究・{theme['name']} #{index}"
    profile["civilizations"] = list(theme.get("allowed_colors") or theme.get("main_colors") or [])
    profile["theme_name"] = theme["name"]
    profile["main_colors"] = list(theme.get("main_colors", []))
    profile["allowed_colors"] = list(theme.get("allowed_colors", []))
    profile["splash_colors"] = list(theme.get("splash_colors", []))
    profile["format"] = str(theme.get("format", "AD") or "AD").upper()
    profile["required_cards"] = list(theme.get("required_cards", []))
    profile["recommended_cards"] = list(theme.get("recommended_cards", []))
    profile["format"] = str(theme.get("format", "AD") or "AD").upper()
    target_by_format = theme.get("target_matchups_by_format", {}) or {}
    profile["target_matchups"] = list(target_by_format.get(profile["format"], theme.get("target_matchups", [])))
    profile["target_matchups_by_format"] = deepcopy(target_by_format)
    return profile


def build_theme_profiles(theme: dict[str, Any], count: int = 6) -> list[dict[str, Any]]:
    profiles = []
    for index in range(1, max(1, count) + 1):
        profile = theme_to_profile(theme, index)
        profile["target_tags"] = deepcopy(profile.get("target_tags", {}))
        if index % 2 == 0:
            profile["target_tags"]["リソース"] = profile["target_tags"].get("リソース", 1.0) + 0.4
            profile["target_resource"] = int(profile.get("target_resource", 8)) + 1
        if index % 3 == 0:
            profile["target_tags"]["受け札"] = profile["target_tags"].get("受け札", 1.0) + 0.35
            profile["min_defense"] = int(profile.get("min_defense", 6)) + 1
        if index % 4 == 0:
            profile["target_tags"]["打点"] = profile["target_tags"].get("打点", 1.0) + 0.3
            profile["min_attack"] = int(profile.get("min_attack", 8)) + 1
        profiles.append(profile)
    return profiles


def _safe_key(value: str) -> str:
    return (
        value.replace("黒", "b")
        .replace("緑", "g")
        .replace("赤", "r")
        .replace("白", "w")
        .replace("青", "u")
        .replace("単", "mono")
        .replace(" ", "_")
    )

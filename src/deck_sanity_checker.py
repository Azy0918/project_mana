from __future__ import annotations

import re
from collections import Counter
from typing import Any


CIVILIZATIONS = ["光", "水", "闇", "火", "自然"]
SPECIAL_ZONE_WORDS = {
    "サイキック",
    "ドラグハート",
    "禁断",
    "禁断フィールド",
    "ゲーム開始時",
    "超次元",
    "覚醒",
    "龍魂",
    "FORBIDDEN STAR",
    "世界最後の日",
}

EARLY_TAGS = {"初動", "低コスト", "マナ加速", "チャージャー"}
ATTACK_TAGS = {"打点", "即効性", "シールド圧力", "フィニッシャー候補", "W・ブレイカー", "スピードアタッカー"}
DEFENSE_TAGS = {"受け札", "S・トリガー", "G・ストライク", "ブロッカー", "防御"}
REMOVAL_TAGS = {"除去", "破壊", "バウンス", "タップ", "パワー低下"}
RESOURCE_TAGS = {"リソース", "ドロー", "サーチ候補", "マナ加速", "墓地回収", "回収"}
FINISHER_TAGS = {"フィニッシャー", "フィニッシャー候補", "特殊勝利", "ロック", "T・ブレイカー", "Q・ブレイカー"}
LOCK_TAGS = {"ロック", "呪文ロック", "攻撃制限", "踏み倒しメタ"}


def analyze_deck_sanity(deck: list[dict[str, Any]], request: dict[str, Any] | None = None) -> dict[str, Any]:
    request = request or {}
    expanded = _expand_deck(deck)
    total_cards = len(expanded)
    name_counts = Counter(_normalize_name(_card_name(card)) for card in expanded)
    display_names = {_normalize_name(_card_name(card)): _card_name(card) for card in expanded}
    one_of_count = sum(1 for count in name_counts.values() if count == 1)
    main_axis_cards = [
        {"name": display_names.get(name, name), "count": count}
        for name, count in name_counts.most_common()
        if count >= 3
    ]

    civ_counts: Counter[str] = Counter()
    effective_supply: Counter[str] = Counter()
    civ_demands: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    high_cost_count = 0
    special_cards: list[str] = []
    broken_names: list[str] = []

    for card in expanded:
        civs = _civilizations(card)
        for civ in civs:
            civ_counts[civ] += 1
            civ_demands[civ] += 1
            effective_supply[civ] += 0.5 if len(civs) > 1 else 1.0
        cost = _safe_int(card.get("cost"), 0)
        if cost >= 7:
            high_cost_count += 1
        for role in _roles(card):
            role_counts[role] += 1
        if _is_special_zone_card(card):
            special_cards.append(_card_name(card))
        if _looks_broken_name(_card_name(card)):
            broken_names.append(_card_name(card))

    main_colors = [
        civ for civ in CIVILIZATIONS
        if effective_supply.get(civ, 0) >= 8 or civ_counts.get(civ, 0) >= 8
    ]
    splash_colors = [
        civ for civ in CIVILIZATIONS
        if civ_demands.get(civ, 0) > 0 and civ not in main_colors
    ]
    color_count = len([civ for civ in CIVILIZATIONS if civ_demands.get(civ, 0) > 0])
    deck_type = str(request.get("deck_type") or request.get("archetype") or request.get("concept") or "").strip()
    if not deck_type:
        deck_type = _infer_deck_type(role_counts, high_cost_count)

    warnings: list[str] = []
    fatal_issues: list[str] = []
    score = 100

    if total_cards != 40:
        fatal_issues.append(f"デッキ枚数が40枚ではありません: {total_cards}枚")
        score -= min(50, abs(40 - total_cards) * 4 + 20)

    over_limit = [display_names.get(name, name) for name, count in name_counts.items() if count > 4]
    if over_limit:
        fatal_issues.append("同名4枚制限を超えています: " + "、".join(over_limit[:8]))
        score -= 25 + min(25, len(over_limit) * 5)

    if special_cards:
        fatal_issues.append("通常40枚デッキ枠に特殊ゾーン/禁断系カードが混入しています: " + "、".join(sorted(set(special_cards))[:8]))
        score -= 30

    if broken_names:
        warnings.append("壊れた可能性のあるカード名があります: " + "、".join(sorted(set(broken_names))[:8]))
        score -= min(15, len(set(broken_names)) * 5)

    if color_count >= 6:
        fatal_issues.append("文明が6種以上に散っています。通常デッキとして文明基盤が破綻しています。")
        score -= 35
    elif color_count >= 4 and not _is_five_color_strategy(request, expanded):
        warnings.append(f"4文明以上ですが5c戦略として明示されていません: {color_count}文明")
        score -= 25
    elif color_count == 3:
        score -= 5

    for civ in main_colors:
        if effective_supply.get(civ, 0) < 8:
            warnings.append(f"{civ}文明の有効供給が不足気味です: {effective_supply.get(civ, 0):.1f}")
            score -= 8
    for civ in splash_colors:
        demand = civ_demands.get(civ, 0)
        supply = effective_supply.get(civ, 0)
        if demand >= 4 and supply < 8:
            warnings.append(f"{civ}文明要求{demand}枚に対して有効供給{supply:.1f}枚です。色事故リスクが高いです。")
            score -= 18
        elif demand <= 3 and supply < 4:
            warnings.append(f"{civ}文明はタッチ扱いですが有効供給{supply:.1f}枚です。必須札なら不安定です。")
            score -= 10
    if len(splash_colors) >= 3:
        warnings.append(f"タッチ文明が多すぎます: {'、'.join(splash_colors)}")
        score -= 12

    if not main_axis_cards:
        warnings.append("3枚以上採用された主軸候補がありません。デッキの一貫性が弱いです。")
        score -= 25
    if one_of_count >= 20:
        warnings.append(f"1枚差しが多すぎます: {one_of_count}種類")
        score -= 25
    elif one_of_count >= 14:
        warnings.append(f"1枚差しが多めです: {one_of_count}種類")
        score -= 12

    score += _role_balance_delta(deck_type, role_counts, high_cost_count, warnings)

    score = max(0, min(100, int(round(score))))
    ok = not fatal_issues and score >= 60

    return {
        "ok": ok,
        "score": score,
        "warnings": warnings,
        "fatal_issues": fatal_issues,
        "metrics": {
            "total_cards": total_cards,
            "civilization_counts": dict(civ_counts),
            "effective_supply": {k: round(v, 1) for k, v in effective_supply.items()},
            "civilization_demands": dict(civ_demands),
            "main_colors": main_colors,
            "splash_colors": splash_colors,
            "color_count": color_count,
            "main_axis_cards": main_axis_cards,
            "one_of_count": one_of_count,
            "role_counts": dict(role_counts),
            "high_cost_count": high_cost_count,
            "deck_type": deck_type,
            "special_cards": sorted(set(special_cards)),
            "broken_names": sorted(set(broken_names)),
        },
    }


def analyze_theme_fit(
    deck: list[dict[str, Any]],
    theme: dict[str, Any] | None,
    sanity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not theme:
        return {
            "score": 100,
            "warnings": [],
            "metrics": {"tag_hits": {}, "role_counts": {}, "forbidden_hits": []},
        }

    expanded = _expand_deck(deck)
    sanity = sanity or analyze_deck_sanity(deck, {"deck_type": theme.get("deck_type", "")})
    role_counts = Counter(sanity.get("metrics", {}).get("role_counts", {}))
    tag_hits: Counter[str] = Counter()
    for card in expanded:
        for tag in _split_tags(card.get("tags")):
            tag_hits[tag] += 1

    score = 100
    warnings: list[str] = []
    forbidden_hits: list[str] = []

    required_tags = _normalize_required_mapping(theme.get("required_tags", {}), default_minimum=1)
    tag_penalty = 0
    for tag, minimum in required_tags.items():
        actual = tag_hits.get(tag, 0)
        if actual < minimum:
            warnings.append(f"テーマ必須タグ不足: {tag} {actual} / {minimum}")
            tag_penalty += min(12, (minimum - actual) * 3)
    score -= min(25, tag_penalty)

    required_roles = _normalize_required_mapping(theme.get("required_roles", {}), default_minimum=1)
    for role, minimum in required_roles.items():
        actual = role_counts.get(role, 0)
        if actual < minimum:
            warnings.append(f"テーマ必須役割不足: {role} {actual} / {minimum}")
            score -= min(30, (minimum - actual) * 5)

    patterns = set(theme.get("forbidden_role_patterns", []))
    attack = role_counts.get("attack", 0)
    defense = role_counts.get("defense", 0)
    resource = role_counts.get("resource", 0)
    removal = role_counts.get("removal", 0)
    lock = role_counts.get("lock", 0)
    finisher = role_counts.get("finisher", 0)

    if "attack_only_control" in patterns and attack >= 28 and (defense < 6 or resource < 4 or lock < 2):
        forbidden_hits.append("attack_only_control")
        warnings.append("攻撃札に偏りすぎており、テーマの制御要素が不足しています。")
        score -= 35
    if "attack_overload" in patterns and attack >= 32:
        forbidden_hits.append("attack_overload")
        warnings.append(f"攻撃札過多です: {attack}")
        score -= 20
    if "no_defense" in patterns and defense <= 0:
        forbidden_hits.append("no_defense")
        warnings.append("受け札が0枚です。")
        score -= 25
    if "no_resource" in patterns and resource <= 0:
        forbidden_hits.append("no_resource")
        warnings.append("リソース札が0枚です。")
        score -= 25
    if "no_lock" in patterns and lock <= 0:
        forbidden_hits.append("no_lock")
        warnings.append("ロック/制限要素が0枚です。")
        score -= 20
    if "no_removal" in patterns and removal <= 0:
        forbidden_hits.append("no_removal")
        warnings.append("除去要素が0枚です。")
        score -= 18
    if "no_finisher" in patterns and finisher <= 0:
        forbidden_hits.append("no_finisher")
        warnings.append("勝ち筋になるカードが0枚です。")
        score -= 18

    score = max(0, min(100, int(round(score))))
    return {
        "score": score,
        "warnings": warnings,
        "metrics": {
            "tag_hits": dict(tag_hits),
            "role_counts": dict(role_counts),
            "forbidden_hits": forbidden_hits,
            "required_tags": required_tags,
            "required_roles": required_roles,
        },
    }


def _expand_deck(deck: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for card in deck:
        count = _safe_int(card.get("count", card.get("quantity", 1)), 1)
        for _ in range(max(0, count)):
            expanded.append(card)
    return expanded


def _card_name(card: dict[str, Any]) -> str:
    return str(card.get("name") or card.get("card_name") or "").strip()


def _normalize_name(name: str) -> str:
    text = re.sub(r"\s+", "", str(name))
    text = text.replace("　", "")
    return text


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        text = str(value).strip()
        if not text or text == "-":
            return default
        return int(float(text))
    except Exception:
        return default


def _split_tags(value: Any) -> set[str]:
    if isinstance(value, set):
        return {str(v).strip() for v in value if str(v).strip()}
    if isinstance(value, list):
        return {str(v).strip() for v in value if str(v).strip()}
    return {tag.strip() for tag in str(value or "").replace(",", ";").replace("、", ";").split(";") if tag.strip()}


def _civilizations(card: dict[str, Any]) -> list[str]:
    text = str(card.get("civilization", "") or "")
    return [civ for civ in CIVILIZATIONS if civ in text]


def _roles(card: dict[str, Any]) -> set[str]:
    tags = _split_tags(card.get("tags"))
    text = str(card.get("text", "") or "")
    roles: set[str] = set()
    if tags & EARLY_TAGS or _safe_int(card.get("cost"), 99) <= 2:
        roles.add("early")
    if tags & ATTACK_TAGS or any(word in text for word in ["スピードアタッカー", "W・ブレイカー", "T・ブレイカー", "シールドを"]):
        roles.add("attack")
    if tags & DEFENSE_TAGS or any(word in text for word in ["S・トリガー", "G・ストライク", "ブロッカー"]):
        roles.add("defense")
    if tags & REMOVAL_TAGS or any(word in text for word in ["破壊する", "手札に戻す", "タップする", "パワーを"]):
        roles.add("removal")
    if tags & RESOURCE_TAGS or any(word in text for word in ["カードを引", "山札を見る", "手札に加える", "マナゾーンに置く"]):
        roles.add("resource")
    if tags & FINISHER_TAGS or any(word in text for word in ["ゲームに勝つ", "追加ターン", "攻撃できない", "呪文を唱えられない"]):
        roles.add("finisher")
    if tags & LOCK_TAGS or any(word in text for word in ["攻撃できない", "呪文を唱えられない", "召喚できない", "出せない"]):
        roles.add("lock")
    return roles


def _normalize_required_mapping(value: Any, default_minimum: int = 1) -> dict[str, int]:
    if isinstance(value, dict):
        return {str(key): int(count) for key, count in value.items()}
    if isinstance(value, (list, tuple, set)):
        return {str(key): default_minimum for key in value}
    return {}


def _is_special_zone_card(card: dict[str, Any]) -> bool:
    blob = " ".join(
        [
            _card_name(card),
            str(card.get("card_type", "") or ""),
            str(card.get("text", "") or ""),
            ";".join(_split_tags(card.get("tags"))),
        ]
    )
    return any(word in blob for word in SPECIAL_ZONE_WORDS)


def _looks_broken_name(name: str) -> bool:
    if len(name) >= 55:
        return True
    if name.count("【") >= 3 or name.count("】") >= 3:
        return True
    if name.count("【／") >= 2:
        return True
    compact = _normalize_name(name)
    return bool(re.search(r"(.{3,})\1\1", compact))


def _infer_deck_type(role_counts: Counter[str], high_cost_count: int) -> str:
    if role_counts.get("attack", 0) >= 20 and high_cost_count <= 4:
        return "速攻"
    if role_counts.get("defense", 0) >= 10 and role_counts.get("removal", 0) >= 8:
        return "コントロール"
    if role_counts.get("resource", 0) >= 10 and high_cost_count >= 6:
        return "ランプ"
    return "中速"


def _is_five_color_strategy(request: dict[str, Any], expanded: list[dict[str, Any]]) -> bool:
    text = " ".join(str(request.get(key, "")) for key in ["deck_type", "archetype", "concept", "strategy_note"])
    if "5c" in text.lower() or "5色" in text or "五色" in text:
        return True
    return any("5c" in tag.lower() or "5色" in tag for card in expanded for tag in _split_tags(card.get("tags")))


def _role_balance_delta(deck_type: str, role_counts: Counter[str], high_cost_count: int, warnings: list[str]) -> int:
    deck_type_text = deck_type or "中速"
    delta = 0

    def require(role: str, minimum: int, label: str, penalty: int = 5) -> None:
        nonlocal delta
        actual = role_counts.get(role, 0)
        if actual < minimum:
            warnings.append(f"{label}が不足しています: {actual} / 目標 {minimum}")
            delta -= (minimum - actual) * penalty

    if any(key in deck_type_text for key in ["速攻", "アグロ", "ビート"]):
        require("early", 12, "初動/低コスト")
        require("attack", 18, "攻撃札")
        if high_cost_count > 4:
            warnings.append(f"速攻系にしては高コストが多いです: {high_cost_count}")
            delta -= (high_cost_count - 4) * 5
    elif "コントロール" in deck_type_text or "耐久" in deck_type_text:
        require("defense", 10, "受け札")
        require("removal", 8, "除去")
        require("resource", 8, "リソース")
        require("finisher", 2, "フィニッシャー", penalty=8)
    elif "ランプ" in deck_type_text:
        require("resource", 10, "マナ加速/リソース")
        require("finisher", 4, "大型フィニッシャー", penalty=7)
    elif "コンボ" in deck_type_text:
        require("resource", 8, "コンボ到達用リソース")
        require("finisher", 2, "勝利出力", penalty=8)
    else:
        require("early", 8, "初動/低コスト")
        require("defense", 6, "受け札")
        require("resource", 6, "リソース")
        require("finisher", 2, "フィニッシャー", penalty=7)
    return delta

from __future__ import annotations

from typing import Any


ZONE_KEYWORDS = {
    "hand": ["手札", "カードを引", "ドロー", "加える"],
    "mana": ["マナゾーン", "マナ加速", "チャージャー", "マナ"],
    "graveyard": ["墓地", "墓地肥やし", "墓地利用", "破壊"],
    "battle_zone": ["バトルゾーン", "出す", "召喚", "クリーチャー"],
    "shield": ["シールド", "S・トリガー", "盾"],
    "deck": ["山札", "デッキ"],
    "extra_deck": ["超次元", "超GR", "ドラグハート"],
}


def infer_effect_semantics(card: dict[str, Any]) -> dict[str, Any]:
    text = str(card.get("text", "") or "")
    tags = _split_tags(card.get("tags", ""))
    semantics = {
        "card_id": card.get("card_id", ""),
        "name": card.get("name", ""),
        "raw_text": text,
        "state_delta": infer_state_deltas(text, tags),
        "zones": infer_zones(text, tags),
        "constraint_breaks": infer_constraint_breaks(text, tags),
        "terminal_effects": infer_terminal_effects(text, tags),
        "special_mechanics": infer_special_mechanics(text, tags),
    }
    semantics["comments"] = summarize_effect_semantics(semantics)
    return semantics


def infer_state_deltas(text: str, tags: list[str]) -> dict[str, int]:
    haystack = _haystack(text, tags)
    delta = {"hand": 0, "mana": 0, "graveyard": 0, "board": 0, "shield": 0}

    if any(keyword in haystack for keyword in ["カードを引", "ドロー", "手札に加える", "手札に戻す", "回収"]):
        delta["hand"] += 1
    if any(keyword in haystack for keyword in ["マナゾーンに置", "マナ加速", "チャージャー", "マナを増や"]):
        delta["mana"] += 1
    if any(keyword in haystack for keyword in ["墓地に置", "墓地肥やし", "山札の上から", "捨てる"]):
        delta["graveyard"] += 1
    if any(keyword in haystack for keyword in ["バトルゾーンに出", "召喚", "踏み倒し", "リアニメイト"]):
        delta["board"] += 1
    if any(keyword in haystack for keyword in ["シールド化", "シールドに加える", "シールドを追加", "シールドゾーンに置"]):
        delta["shield"] += 1

    if any(keyword in haystack for keyword in ["破壊", "すべて破壊", "バトルゾーンから離"]):
        delta["board"] -= 1
    if any(keyword in haystack for keyword in ["手札を捨て", "ハンデス"]):
        delta["hand"] -= 1
    if any(keyword in haystack for keyword in ["シールドを墓地", "シールドをブレイク"]):
        delta["shield"] -= 1

    return delta


def infer_constraint_breaks(text: str, tags: list[str]) -> list[str]:
    haystack = _haystack(text, tags)
    breaks = []
    if any(keyword in haystack for keyword in ["コストを支払わず", "踏み倒し", "無料", "ただで"]):
        breaks.append("cost_bypass")
    if "G・ゼロ" in haystack or "Gゼロ" in haystack:
        breaks.extend(["cost_bypass", "condition_based_free_cast"])
    if any(keyword in haystack for keyword in ["超次元ゾーンから出", "超次元", "超GR"]):
        breaks.append("zone_bypass")
    if any(keyword in haystack for keyword in ["召喚酔い", "スピードアタッカー", "アンタップしているクリーチャーを攻撃"]):
        breaks.append("timing_or_attack_restriction_break")
    if any(keyword in haystack for keyword in ["かわりに", "置換", "離れない", "破壊されない"]):
        breaks.append("replacement_or_immunity")
    return _unique(breaks)


def infer_terminal_effects(text: str, tags: list[str]) -> list[str]:
    haystack = _haystack(text, tags)
    effects = []
    if any(keyword in haystack for keyword in ["ゲームに勝つ", "自分はゲームに勝つ", "勝利する"]):
        effects.append("extra_win")
    if any(keyword in haystack for keyword in ["山札の最後", "山札がなくなるかわり", "山札が0"]):
        effects.append("extra_win_deck_drawout")
    if "シールドが10枚以上" in haystack or "シールド10枚以上" in haystack:
        effects.append("extra_win_shield_count")
    if "手札が10枚以上" in haystack or "手札10枚以上" in haystack:
        effects.append("extra_win_hand_count")
    if any(keyword in haystack for keyword in ["クリーチャーが11体以上", "クリーチャーが18体以上", "11体以上", "18体以上"]):
        effects.append("extra_win_creature_count")
    if any(keyword in haystack for keyword in ["ターンを追加", "追加ターン", "もう一度自分のターン"]):
        effects.append("extra_turn")
    if any(keyword in haystack for keyword in ["すべて破壊", "すべて墓地", "すべて山札", "すべて手札"]):
        effects.append("reset_effect")
    return _unique(effects)


def infer_special_mechanics(text: str, tags: list[str]) -> list[str]:
    haystack = _haystack(text, tags)
    mechanics = []
    if "進化" in haystack:
        mechanics.append("evolution")
    if any(keyword in haystack for keyword in ["進化クリーチャーの下", "下に置", "下から", "一番上"]):
        mechanics.extend(["evolution_stack", "devolution_candidate"])
    if any(keyword in haystack for keyword in ["退化", "一番上を墓地", "一番上のカードを"]):
        mechanics.append("devolution_candidate")
    if any(keyword in haystack for keyword in ["墓地進化", "墓地から進化"]):
        mechanics.append("graveyard_evolution")
    if any(keyword in haystack for keyword in ["墓地退化", "墓地から出", "墓地から進化クリーチャー"]):
        mechanics.append("graveyard_devolution_candidate")
    if any(keyword in haystack for keyword in ["手札に戻す", "墓地から手札", "マナゾーンから手札", "回収"]):
        mechanics.append("recursion_candidate")
    if any(keyword in haystack for keyword in ["アンタップする", "もう一度使", "唱えてもよい", "再び", "ループ"]):
        mechanics.append("loop_candidate")
    if any(keyword in haystack for keyword in ["超次元", "超GR", "ドラグハート"]):
        mechanics.append("external_zone_access")
    if any(keyword in haystack for keyword in ["オールデリート", "すべて破壊", "すべて墓地", "リセット"]):
        mechanics.append("reset_combo_candidate")
    return _unique(mechanics)


def infer_zones(text: str, tags: list[str]) -> list[str]:
    haystack = _haystack(text, tags)
    zones = []
    for zone, keywords in ZONE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            zones.append(zone)
    return zones


def summarize_effect_semantics(semantics: dict[str, Any]) -> list[str]:
    comments = []
    delta = semantics.get("state_delta", {})
    positive = [zone for zone, value in delta.items() if value > 0]
    negative = [zone for zone, value in delta.items() if value < 0]
    if positive:
        comments.append("リソース増加候補: " + " / ".join(positive))
    if negative:
        comments.append("リソース減少または除去候補: " + " / ".join(negative))
    if semantics.get("constraint_breaks"):
        comments.append("通常のコスト・ゾーン・タイミング制約を外す候補があります。")
    if semantics.get("terminal_effects"):
        comments.append("特殊勝利、追加ターン、全体リセットなど終端効果の候補があります。")
    mechanics = semantics.get("special_mechanics", [])
    if any(item in mechanics for item in ["loop_candidate", "recursion_candidate"]):
        comments.append("再利用またはループに接続する仮説があります。")
    if any(item in mechanics for item in ["devolution_candidate", "graveyard_devolution_candidate"]):
        comments.append("進化元やカードの重なりを利用する退化系の仮説があります。")
    if not comments:
        comments.append("現段階の簡易推定では、特殊な構造は強く検出されていません。")
    return comments


def _split_tags(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    return [tag.strip() for tag in str(value).replace(",", ";").replace("、", ";").split(";") if tag.strip()]


def _haystack(text: str, tags: list[str]) -> str:
    return f"{text} {' '.join(tags)}"


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

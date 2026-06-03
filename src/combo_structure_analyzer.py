from __future__ import annotations

from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_DB_PATH
from src.search_cards import search_cards


PATTERN_RULES = [
    ("墓地蓄積 -> 墓地利用 -> 大型展開", ["墓地", "墓地利用", "リアニメイト"]),
    ("マナ加速 -> コスト変換 -> 大型展開", ["マナ加速", "ランプ", "踏み倒し"]),
    ("小型展開 -> 攻撃条件 -> 入れ替え", ["侵略", "革命チェンジ", "速攻"]),
    ("呪文連打 -> コスト軽減 -> 追加展開", ["呪文", "ドロー", "コンボ"]),
    ("シールド追加 -> 耐久 -> 制圧", ["シールド", "受け札", "ロック"]),
    ("ハンデス -> リソース差 -> ロック", ["ハンデス", "コントロール", "ロック"]),
    ("種族展開 -> 参照条件 -> 大量展開", ["種族", "進化", "展開"]),
]


def split_values(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    items: list[str] = []
    for item in str(value).replace(",", ";").replace("、", ";").replace("\n", ";").split(";"):
        item = item.strip()
        if item and item not in items:
            items.append(item)
    return items


def analyze_known_combo(combo: dict[str, Any]) -> dict[str, Any]:
    text_blob = " ".join(str(combo.get(key, "")) for key in combo)
    core_cards = split_values(combo.get("core_cards"))
    starter_cards = split_values(combo.get("starter_cards"))
    support_cards = split_values(combo.get("support_cards"))
    payoff_cards = split_values(combo.get("payoff_cards"))
    related_tags = split_values(combo.get("related_tags"))

    pattern_type = combo.get("pattern_type") or infer_combo_pattern(text_blob, related_tags)
    phases = [
        {"段階": "起点", "内容": _phase_text(starter_cards, "初動・条件作成カード")},
        {"段階": "条件", "内容": combo.get("required_conditions") or _infer_condition(text_blob)},
        {"段階": "変換", "内容": _infer_conversion(text_blob, related_tags)},
        {"段階": "連鎖", "内容": combo.get("main_sequence") or "起点からサポートカードへつなぎ、勝ち筋へ到達する。"},
        {"段階": "勝ち筋", "内容": combo.get("win_condition") or _phase_text(payoff_cards, "フィニッシュカード")},
        {"段階": "弱点", "内容": combo.get("weaknesses") or _infer_weakness(text_blob)},
    ]

    structure_score = 0
    structure_score += 15 if core_cards else 0
    structure_score += 15 if starter_cards else 0
    structure_score += 15 if payoff_cards else 0
    structure_score += 15 if combo.get("required_conditions") else 0
    structure_score += 20 if combo.get("main_sequence") else 0
    structure_score += 10 if combo.get("weaknesses") else 0
    structure_score += 10 if related_tags else 0

    return {
        "combo_name": combo.get("combo_name", ""),
        "format": combo.get("format", ""),
        "pattern_type": pattern_type,
        "core_cards": core_cards,
        "starter_cards": starter_cards,
        "support_cards": support_cards,
        "payoff_cards": payoff_cards,
        "related_tags": related_tags,
        "phases": phases,
        "structure_score": min(100, structure_score),
        "summary": build_combo_summary(combo, pattern_type),
    }


def infer_combo_pattern(text_blob: str, related_tags: list[str] | None = None) -> str:
    haystack = text_blob + " " + " ".join(related_tags or [])
    for label, keywords in PATTERN_RULES:
        if any(keyword in haystack for keyword in keywords):
            return label
    return "起点 -> 条件達成 -> 勝ち筋"


def build_combo_summary(combo: dict[str, Any], pattern_type: str) -> str:
    name = combo.get("combo_name", "既知コンボ")
    condition = combo.get("required_conditions") or "条件を作る"
    sequence = combo.get("main_sequence") or "中核カードを順に使う"
    win = combo.get("win_condition") or "勝ち筋へ到達する"
    return f"{name} は「{pattern_type}」型です。{condition} から {sequence} を通して、{win} ことを狙います。"


def find_combo_variants(
    combo: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
    limit: int = 20,
) -> list[dict[str, Any]]:
    analysis = analyze_known_combo(combo)
    tags = analysis["related_tags"] or _pattern_to_tags(analysis["pattern_type"])
    cards = search_cards(db_path)
    scored = []
    known_names = set(analysis["core_cards"] + analysis["starter_cards"] + analysis["support_cards"] + analysis["payoff_cards"])

    for card in cards:
        name = str(card.get("name", ""))
        if name in known_names:
            continue
        card_tags = set(split_values(card.get("tags")))
        text = str(card.get("text", ""))
        score = 0
        matched = []
        for tag in tags:
            if tag in card_tags or tag in text or tag in name:
                score += 12
                matched.append(tag)
        score += _effect_keyword_score(text, analysis["pattern_type"])
        if score <= 0:
            continue
        scored.append(
            {
                "カード名": name,
                "文明": card.get("civilization", ""),
                "コスト": card.get("cost", ""),
                "種類": card.get("card_type", ""),
                "候補スコア": score,
                "一致要素": ";".join(matched) if matched else "効果文",
                "想定役割": _infer_variant_role(card, analysis["pattern_type"]),
                "タグ": card.get("tags", ""),
            }
        )

    return sorted(scored, key=lambda row: row["候補スコア"], reverse=True)[:limit]


def _phase_text(cards: list[str], fallback: str) -> str:
    return " / ".join(cards) if cards else fallback


def _infer_condition(text_blob: str) -> str:
    if "墓地" in text_blob:
        return "墓地枚数または墓地に置かれたカードを条件にする。"
    if "マナ" in text_blob:
        return "マナ枚数またはマナゾーンのカードを条件にする。"
    if "攻撃" in text_blob or "侵略" in text_blob or "革命チェンジ" in text_blob:
        return "攻撃可能なクリーチャーを用意する。"
    if "呪文" in text_blob:
        return "呪文を唱える回数または手札の呪文を条件にする。"
    return "必要カードと必要ゾーンをそろえる。"


def _infer_conversion(text_blob: str, tags: list[str]) -> str:
    haystack = text_blob + " " + " ".join(tags)
    if "踏み倒し" in haystack or "コストを支払わず" in haystack:
        return "条件達成を、コストを支払わない展開へ変換する。"
    if "リアニメイト" in haystack or "墓地" in haystack:
        return "墓地リソースを盤面または手札へ変換する。"
    if "マナ加速" in haystack:
        return "マナ差を高コストカードの早期使用へ変換する。"
    if "ドロー" in haystack or "リソース" in haystack:
        return "手札補充で連鎖に必要な札へ到達する。"
    return "条件達成をテンポ、盤面、手札、打点のいずれかへ変換する。"


def _infer_weakness(text_blob: str) -> str:
    if "墓地" in text_blob:
        return "墓地リセット、速攻、ハンデスに弱い可能性があります。"
    if "呪文" in text_blob:
        return "呪文ロック、ハンデス、早期打点に弱い可能性があります。"
    if "マナ" in text_blob:
        return "初動不発、速攻、ランデスに弱い可能性があります。"
    return "必要札への依存、序盤干渉、特定メタカードを確認してください。"


def _pattern_to_tags(pattern_type: str) -> list[str]:
    if "墓地" in pattern_type:
        return ["墓地利用", "墓地肥やし", "リアニメイト", "フィニッシャー"]
    if "マナ" in pattern_type:
        return ["マナ加速", "踏み倒し", "フィニッシャー", "大型"]
    if "攻撃" in pattern_type or "入れ替え" in pattern_type:
        return ["速攻", "侵略", "革命チェンジ", "低コスト"]
    if "呪文" in pattern_type:
        return ["呪文", "ドロー", "リソース", "コンボ"]
    if "シールド" in pattern_type:
        return ["受け札", "S・トリガー", "ロック", "フィニッシャー"]
    return ["コンボ", "リソース", "フィニッシャー"]


def _effect_keyword_score(text: str, pattern_type: str) -> int:
    keywords = _pattern_to_tags(pattern_type) + ["コストを支払わず", "出す", "加える", "墓地", "マナ", "攻撃", "唱える"]
    return min(30, sum(5 for keyword in keywords if keyword in text))


def _infer_variant_role(card: dict[str, Any], pattern_type: str) -> str:
    tags = str(card.get("tags", ""))
    cost = _safe_int(card.get("cost"))
    if "フィニッシャー" in tags or cost >= 7:
        return "勝ち筋候補"
    if "初動" in tags or "マナ加速" in tags or cost <= 3:
        return "起点候補"
    if "ドロー" in tags or "リソース" in tags or "サーチ" in tags:
        return "連鎖補助"
    if "除去" in tags or "受け札" in tags:
        return "防御・妨害補助"
    return "構造類似候補"


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0

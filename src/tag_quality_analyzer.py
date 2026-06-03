from __future__ import annotations

from collections import Counter
from typing import Any


IMPORTANT_ROLE_TAGS = {
    "受け札",
    "初動",
    "マナ加速",
    "フィニッシャー",
    "除去",
    "軽量除去",
    "ロック",
    "呪文ロック",
    "踏み倒し",
    "墓地利用",
    "ドロー",
    "リソース",
    "ハンデス",
    "ブロッカー",
    "攻撃制限",
    "シールド追加",
}


TAG_EVIDENCE_KEYWORDS = {
    "受け札": ["S・トリガー", "G・ストライク", "ブロッカー", "攻撃できない", "シールド", "選ばれた時"],
    "初動": ["2コスト", "コスト2", "マナゾーンに置", "カードを引", "手札に加え", "山札を見る"],
    "マナ加速": ["マナゾーンに置", "マナに置", "チャージャー", "マナゾーンから"],
    "フィニッシャー": ["T・ブレイカー", "Q・ブレイカー", "ワールド・ブレイカー", "ゲームに勝つ", "追加ターン", "スピードアタッカー"],
    "除去": ["破壊", "手札に戻", "山札の下", "墓地に置", "マナゾーンに置", "バトル"],
    "軽量除去": ["破壊", "手札に戻", "コスト3以下", "コスト4以下"],
    "ロック": ["できない", "唱えられない", "召喚できない", "攻撃できない", "出せない"],
    "呪文ロック": ["呪文を唱えられない", "呪文を唱えることができない", "唱えられない"],
    "踏み倒し": ["コストを支払わず", "バトルゾーンに出", "召喚してもよい", "唱えてもよい"],
    "墓地利用": ["墓地から", "墓地にある", "墓地に置", "墓地のカード"],
    "ドロー": ["カードを引", "ドロー"],
    "リソース": ["カードを引", "手札に加え", "山札を見る", "マナゾーンに置"],
    "ハンデス": ["手札を捨て", "相手の手札"],
    "ブロッカー": ["ブロッカー"],
    "攻撃制限": ["攻撃できない", "攻撃することができない"],
    "シールド追加": ["シールド化", "シールドに加え", "シールドゾーンに置"],
}


DECK_ROLE_WARNING_THRESHOLDS = {
    "受け札": 30,
    "初動": 20,
    "マナ加速": 25,
    "フィニッシャー": 20,
    "除去": 22,
    "ロック": 18,
    "踏み倒し": 18,
    "墓地利用": 18,
}


def analyze_card_tag_quality(card: dict[str, Any]) -> dict[str, Any]:
    tags = _split_tags(str(card.get("tags", "")))
    role_tags = [tag for tag in tags if tag in IMPORTANT_ROLE_TAGS]
    text = _card_haystack(card)
    suspicious = [
        tag
        for tag in role_tags
        if not _has_evidence(tag, text, card)
    ]
    over_tagged = len(role_tags) >= 6 or len(suspicious) >= 3

    return {
        "card_id": card.get("card_id", ""),
        "name": card.get("name", ""),
        "role_tag_count": len(role_tags),
        "role_tags": role_tags,
        "suspicious_tags": suspicious,
        "over_tagged": over_tagged,
        "confidence": _confidence(len(role_tags), len(suspicious)),
        "comment": _card_comment(role_tags, suspicious, over_tagged),
    }


def analyze_deck_tag_quality(deck: list[dict[str, Any]]) -> dict[str, Any]:
    role_counts: Counter[str] = Counter()
    suspicious_counts: Counter[str] = Counter()
    over_tagged_cards = []
    low_confidence_cards = []

    for card in deck:
        quantity = _quantity(card)
        card_quality = analyze_card_tag_quality(card)
        for tag in card_quality["role_tags"]:
            role_counts[tag] += quantity
        for tag in card_quality["suspicious_tags"]:
            suspicious_counts[tag] += quantity
        if card_quality["over_tagged"]:
            over_tagged_cards.append(
                {
                    "カード名": card.get("name", ""),
                    "枚数": quantity,
                    "重要役割タグ数": card_quality["role_tag_count"],
                    "疑わしいタグ": ";".join(card_quality["suspicious_tags"]),
                }
            )
        if card_quality["confidence"] < 70:
            low_confidence_cards.append(
                {
                    "カード名": card.get("name", ""),
                    "信頼度": card_quality["confidence"],
                    "疑わしいタグ": ";".join(card_quality["suspicious_tags"]),
                }
            )

    warnings = []
    for tag, threshold in DECK_ROLE_WARNING_THRESHOLDS.items():
        count = role_counts.get(tag, 0)
        if count >= threshold:
            warnings.append(f"{tag} が {count}枚相当あります。タグ過剰により評価が高く出ている可能性があります。")

    if len(over_tagged_cards) >= 5:
        warnings.append(f"重要役割タグが多すぎるカードが {len(over_tagged_cards)} 種あります。")
    if sum(suspicious_counts.values()) >= 20:
        warnings.append("根拠が薄い役割タグが多く、一人回し結果や条件適合スコアを過信しないでください。")

    return {
        "role_counts": dict(role_counts),
        "suspicious_tag_counts": dict(suspicious_counts),
        "over_tagged_cards": over_tagged_cards,
        "low_confidence_cards": low_confidence_cards,
        "warnings": warnings,
        "has_warning": bool(warnings),
        "comment": _deck_comment(warnings),
    }


def _split_tags(value: str) -> list[str]:
    tags = []
    for tag in value.replace(",", ";").replace("、", ";").split(";"):
        tag = tag.strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _quantity(card: dict[str, Any]) -> int:
    try:
        return int(card.get("quantity", 1))
    except Exception:
        return 1


def _card_haystack(card: dict[str, Any]) -> str:
    return " ".join(
        str(card.get(key, "") or "")
        for key in ["name", "card_type", "race", "text"]
    )


def _has_evidence(tag: str, text: str, card: dict[str, Any]) -> bool:
    if tag == "初動":
        try:
            if int(float(str(card.get("cost", "") or 99))) <= 3:
                return True
        except Exception:
            pass
    if tag == "フィニッシャー":
        try:
            if int(float(str(card.get("cost", "") or 0))) >= 7:
                return True
        except Exception:
            pass
    return any(keyword in text for keyword in TAG_EVIDENCE_KEYWORDS.get(tag, []))


def _confidence(role_count: int, suspicious_count: int) -> int:
    score = 100
    if role_count >= 6:
        score -= (role_count - 5) * 8
    score -= suspicious_count * 15
    return max(0, min(100, score))


def _card_comment(role_tags: list[str], suspicious: list[str], over_tagged: bool) -> str:
    if over_tagged:
        return "重要役割タグが多く、カード評価を過剰に押し上げている可能性があります。"
    if suspicious:
        return "一部の役割タグは本文上の根拠が薄い可能性があります。"
    if role_tags:
        return "役割タグは概ね本文と対応しています。"
    return "重要役割タグは少なめです。"


def _deck_comment(warnings: list[str]) -> str:
    if warnings:
        return "この評価はタグ過剰により高く出ている可能性があります。初動成功率や受け札確認率を過信しないでください。"
    return "デッキ全体の役割タグ数に大きな過剰傾向は見つかっていません。"

from __future__ import annotations


TAG_RULES = [
    ("S・トリガー", ["S・トリガー", "受け札"]),
    ("マナゾーン", ["マナ加速"]),
    ("カードを引く", ["ドロー"]),
    ("破壊", ["除去"]),
    ("スピードアタッカー", ["速攻"]),
    ("ブロッカー", ["ブロッカー", "受け札"]),
    ("進化", ["進化"]),
    ("手札を捨てる", ["ハンデス"]),
    ("山札から", ["サーチ候補"]),
]


def suggest_tags(text: str) -> list[str]:
    suggestions = []
    for keyword, tags in TAG_RULES:
        if keyword in text:
            for tag in tags:
                if tag not in suggestions:
                    suggestions.append(tag)
    return suggestions


def suggest_tags_from_text(text: str) -> list[str]:
    return suggest_tags(text)


def suggest_missing_tags(text: str, existing_tags: str | list[str] | None = None) -> list[str]:
    existing = set()
    if isinstance(existing_tags, str):
        existing = {tag.strip() for tag in existing_tags.split(";") if tag.strip()}
    elif existing_tags:
        existing = {tag.strip() for tag in existing_tags if tag.strip()}
    return [tag for tag in suggest_tags(text) if tag not in existing]

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.search_cards import DEFAULT_DB_PATH, search_cards


DEFAULT_MODEL = "gpt-5-mini"
MAX_CANDIDATES = 80


def _split_input(value: str) -> list[str]:
    parts = value.replace("\n", ",").replace("、", ",").split(",")
    return [part.strip() for part in parts if part.strip()]


def _civilization_matches(card: dict[str, Any], civilizations: list[str]) -> bool:
    if not civilizations:
        return True
    card_civs = [civ.strip() for civ in card["civilization"].split("/") if civ.strip()]
    return any(civ in card_civs for civ in civilizations)


def _keyword_score(card: dict[str, Any], keywords: list[str]) -> int:
    text = " ".join(
        [
            card["name"],
            card["civilization"],
            card["card_type"],
            card.get("race") or "",
            card["text"],
            card["tags"],
        ]
    )
    return sum(1 for keyword in keywords if keyword and keyword in text)


def extract_candidate_cards(
    db_path: Path = DEFAULT_DB_PATH,
    civilizations: list[str] | None = None,
    concept: str = "",
    required_cards: str = "",
    target_opponent: str = "",
    limit: int = MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    cards = search_cards(db_path)
    civilizations = civilizations or []
    required_names = set(_split_input(required_cards))
    keywords = _split_input(concept) + _split_input(target_opponent)

    scored = []
    for card in cards:
        is_required = card["name"] in required_names or card["card_id"] in required_names
        if not is_required and not _civilization_matches(card, civilizations):
            continue

        score = 0
        score += 100 if is_required else 0
        score += 20 if _civilization_matches(card, civilizations) else 0
        score += _keyword_score(card, keywords) * 5
        score += 2 if "初動" in card["tags"] or "マナ加速" in card["tags"] else 0
        score += 2 if "受け札" in card["tags"] or "S・トリガー" in card["tags"] else 0
        score += 2 if "フィニッシャー" in card["tags"] or "W・ブレイカー" in card["tags"] else 0
        scored.append((score, int(card["cost"]), card["name"], card))

    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [card for _score, _cost, _name, card in scored[:limit]]


def _format_candidates(cards: list[dict[str, Any]]) -> str:
    lines = []
    for card in cards:
        power = card["power"] if card["power"] is not None else "-"
        lines.append(
            (
                f'- {card["card_id"]} | {card["name"]} | 文明:{card["civilization"]} | '
                f'コスト:{card["cost"]} | 種類:{card["card_type"]} | パワー:{power} | '
                f'種族:{card.get("race") or "-"} | タグ:{card["tags"]} | テキスト:{card["text"]}'
            )
        )
    return "\n".join(lines)


def build_ai_deck(
    db_path: Path = DEFAULT_DB_PATH,
    format_name: str = "",
    civilizations: list[str] | None = None,
    concept: str = "",
    required_cards: str = "",
    target_opponent: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(".env に OPENAI_API_KEY を設定してください。")

    candidates = extract_candidate_cards(
        db_path=db_path,
        civilizations=civilizations,
        concept=concept,
        required_cards=required_cards,
        target_opponent=target_opponent,
    )
    if not candidates:
        raise ValueError("候補カードがありません。文明や条件を広げてください。")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    selected_model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    civ_text = " / ".join(civilizations or []) or "指定なし"

    instructions = """
あなたはデュエル・マスターズ プレイスのデッキ研究者です。
既存テンプレートの焼き直しに寄せすぎず、未知アーキタイプ候補として検証価値のあるデッキを日本語で提案してください。
必ず提示された候補カードだけを使い、40枚ちょうど、同名カードは最大4枚にしてください。
カード名は候補リストにある表記を厳密に使ってください。
強さを断定せず、仮説とテスト項目として説明してください。
""".strip()

    prompt = f"""
入力条件:
- フォーマット: {format_name or "指定なし"}
- 文明: {civ_text}
- コンセプト: {concept or "指定なし"}
- 必ず使いたいカード: {required_cards or "指定なし"}
- 対策したい相手: {target_opponent or "指定なし"}

候補カード:
{_format_candidates(candidates)}

以下の見出しで出力してください。

## デッキ名
## 40枚リスト
枚数 カード名 の形式で、合計40枚。
## 基本戦略
## 採用理由
主要カードごとに簡潔に。
## 弱点
## 改造候補
候補カード内から差し替え案を出す。
## 未知性スコア
1から100。高いほど未知アーキタイプ寄り。理由も書く。
## 実戦テスト項目
一人回しや対戦で確認する観点。
""".strip()

    response = client.responses.create(
        model=selected_model,
        instructions=instructions,
        input=prompt,
        max_output_tokens=4000,
    )

    return {
        "model": selected_model,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "text": response.output_text,
    }

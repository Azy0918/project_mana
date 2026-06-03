from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from src.effect_semantics import infer_effect_semantics
from src.import_cards import DEFAULT_DB_PATH
from src.search_cards import search_cards


STATE_DELTA_KEYS = ["hand", "mana", "graveyard", "board", "shield"]
GENERIC_TERMS = {
    "火",
    "水",
    "自然",
    "光",
    "闇",
    "無色",
    "ND",
    "AD",
    "S",
    "A",
    "速攻",
    "中速",
    "コントロール",
    "コンボ",
    "ビート",
}


def analyze_meta_deck_structure(
    meta_deck: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
    max_key_cards: int = 12,
) -> dict[str, Any]:
    """環境デッキの主要カードから、デッキ単位の効果構造を簡易推定する。"""
    db_path = Path(db_path)
    key_terms = _split_terms(meta_deck.get("key_cards", ""))
    search_terms = [term for term in key_terms if _is_searchable_term(term)]

    matched_cards: list[dict[str, Any]] = []
    unmatched_terms: list[str] = []
    state_delta_total = {key: 0 for key in STATE_DELTA_KEYS}
    zones: list[str] = []
    constraint_breaks: list[str] = []
    terminal_effects: list[str] = []
    special_mechanics: list[str] = []

    for term in search_terms[:max_key_cards]:
        card = _find_best_card(term, db_path)
        if not card:
            unmatched_terms.append(term)
            continue

        semantics = infer_effect_semantics(card)
        for key in STATE_DELTA_KEYS:
            state_delta_total[key] += int(semantics.get("state_delta", {}).get(key, 0))
        zones = _unique([*zones, *semantics.get("zones", [])])
        constraint_breaks = _unique([*constraint_breaks, *semantics.get("constraint_breaks", [])])
        terminal_effects = _unique([*terminal_effects, *semantics.get("terminal_effects", [])])
        special_mechanics = _unique([*special_mechanics, *semantics.get("special_mechanics", [])])
        matched_cards.append(
            {
                "検索語": term,
                "カードID": card.get("card_id", ""),
                "カード名": card.get("name", ""),
                "文明": card.get("civilization", ""),
                "コスト": card.get("cost", ""),
                "種類": card.get("card_type", ""),
                "構造コメント": " / ".join(semantics.get("comments", [])),
            }
        )

    comments = _build_structure_comments(
        meta_deck=meta_deck,
        matched_count=len(matched_cards),
        state_delta_total=state_delta_total,
        constraint_breaks=constraint_breaks,
        terminal_effects=terminal_effects,
        special_mechanics=special_mechanics,
    )

    return {
        "deck_name": meta_deck.get("deck_name", ""),
        "format": meta_deck.get("format", ""),
        "tier": meta_deck.get("tier", ""),
        "deck_type": meta_deck.get("deck_type", ""),
        "game_plan": _infer_game_plan(meta_deck),
        "matched_key_cards": matched_cards,
        "unmatched_key_cards": unmatched_terms,
        "state_delta_total": state_delta_total,
        "zones": zones,
        "constraint_breaks": constraint_breaks,
        "terminal_effects": terminal_effects,
        "special_mechanics": special_mechanics,
        "comments": comments,
        "research_questions": _build_research_questions(meta_deck, comments),
    }


def _split_terms(value: Any) -> list[str]:
    raw = str(value or "")
    parts = re.split(r"[;\n,、/]+", raw)
    return _unique([part.strip() for part in parts if part.strip()])


def _is_searchable_term(term: str) -> bool:
    normalized = term.strip()
    return len(normalized) >= 2 and normalized not in GENERIC_TERMS


def _find_best_card(term: str, db_path: Path) -> dict[str, Any] | None:
    cards = search_cards(db_path=db_path, keyword=term)
    if not cards:
        return None

    normalized = term.strip()
    exact = [card for card in cards if str(card.get("name", "")).strip() == normalized]
    if exact:
        return exact[0]

    contains = [card for card in cards if normalized in str(card.get("name", ""))]
    if contains:
        return contains[0]

    return cards[0]


def _infer_game_plan(meta_deck: dict[str, Any]) -> str:
    text = _meta_haystack(meta_deck)
    if any(keyword in text for keyword in ["速攻", "ブランド", "ビート", "アグロ"]):
        return "序盤から打点を作り、相手の準備前に押し切る速度型の仮説です。"
    if any(keyword in text for keyword in ["コントロール", "耐久", "ロック", "ハンデス"]):
        return "除去・妨害・受け札でゲームを長引かせ、相手の勝ち筋を細くする制圧型の仮説です。"
    if any(keyword in text for keyword in ["墓地", "リアニメイト", "魔導具"]):
        return "墓地や呪文連鎖をリソース源にして、中盤以降の再利用や連鎖で勝つ仮説です。"
    if any(keyword in text for keyword in ["ランプ", "マナ", "自然"]):
        return "マナを伸ばして高コスト札や制約解除札へ早く到達する加速型の仮説です。"
    if any(keyword in text for keyword in ["コンボ", "ループ", "退化", "踏み倒し"]):
        return "特定条件を満たして通常より大きな出力を得るコンボ型の仮説です。"
    return "登録情報と主要カードから、勝ち筋構造を追加確認する段階です。"


def _build_structure_comments(
    meta_deck: dict[str, Any],
    matched_count: int,
    state_delta_total: dict[str, int],
    constraint_breaks: list[str],
    terminal_effects: list[str],
    special_mechanics: list[str],
) -> list[str]:
    comments: list[str] = []
    text = _meta_haystack(meta_deck)

    if matched_count == 0:
        comments.append("主要カードを実カードDBへ照合できませんでした。主要カード欄を具体的なカード名で補強すると解析精度が上がります。")
    if state_delta_total.get("hand", 0) > 0:
        comments.append("手札補充・回収によるリソース維持が構造上の強み候補です。")
    if state_delta_total.get("mana", 0) > 0:
        comments.append("マナ増加を起点に、相手より早い高コスト行動へ接続する構造候補があります。")
    if state_delta_total.get("graveyard", 0) > 0 or "墓地" in text:
        comments.append("墓地をリソースまたは条件として使う構造候補があります。墓地メタへの耐性確認が必要です。")
    if constraint_breaks:
        comments.append("コスト・ゾーン・タイミング制約を外すカードがあり、通常テンポを超える動きの候補です。")
    if terminal_effects:
        comments.append("特殊勝利、追加ターン、リセットなどゲーム終端へ直結する効果候補があります。")
    if any(item in special_mechanics for item in ["loop_candidate", "recursion_candidate"]):
        comments.append("再利用やループに接続する候補があります。成立条件と妨害耐性を個別に確認する価値があります。")
    if any(item in special_mechanics for item in ["devolution_candidate", "graveyard_devolution_candidate"]):
        comments.append("進化元・退化・墓地退化に関わる特殊構造候補があります。タグ集計だけでは見落としやすい領域です。")
    if not comments:
        comments.append("現段階では特殊構造は強く出ていません。環境デッキの基本速度・受け・リソース量を比較対象として扱います。")
    return comments


def _build_research_questions(meta_deck: dict[str, Any], comments: list[str]) -> list[str]:
    deck_name = str(meta_deck.get("deck_name", "") or "この環境デッキ")
    questions = [
        f"{deck_name}の主勝ち筋に対して、MANA候補は何ターン目までに干渉できますか。",
        "この構造を対策するだけでなく、未知候補側へ転用できるカード関係はありますか。",
    ]
    if any("制約" in comment for comment in comments):
        questions.append("制約解除の起点カードを止めた場合と通した場合で、勝ち筋到達率はどれだけ変わりますか。")
    if any("墓地" in comment for comment in comments):
        questions.append("墓地メタを採用した場合、こちらの研究候補の自分の動きは弱くなりませんか。")
    return questions


def _meta_haystack(meta_deck: dict[str, Any]) -> str:
    keys = ["deck_name", "deck_type", "key_cards", "civilizations", "notes"]
    return " ".join(str(meta_deck.get(key, "") or "") for key in keys)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

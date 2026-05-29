from __future__ import annotations

from typing import Any

from src.card_csv_validator import validate_cards_csv
from src.db_bootstrap import ensure_cards_db_from_csv
from src.deck_builder import build_deck_for_request
from src.deck_condition_analyzer import analyze_deck_condition
from src.deck_generation_request import DeckGenerationRequest, parse_tag_input
from src.evaluate_deck import evaluate_deck
from src.generated_deck_analyzer import generated_decks_to_csv
from src.generated_deck_store import ensure_generated_decks_table, load_generated_decks
from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH
from src.search_cards import list_civilizations, list_tags, search_cards


def _row(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {
        "項目": name,
        "判定": "OK" if ok else "NG",
        "詳細": detail,
    }


def run_smoke_tests() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    validation = validate_cards_csv(DEFAULT_CSV_PATH)
    rows.append(
        _row(
            "CSVバリデーション",
            len(validation["errors"]) == 0,
            f"エラー {len(validation['errors'])} / 警告 {len(validation['warnings'])}",
        )
    )

    imported_count = ensure_cards_db_from_csv()
    rows.append(_row("CSV→DB反映", imported_count >= 1000, f"{imported_count}枚"))

    cards = search_cards(DEFAULT_DB_PATH)
    rows.append(_row("カード検索", len(cards) >= 1000, f"{len(cards)}枚取得"))

    civilizations = list_civilizations(DEFAULT_DB_PATH)
    rows.append(_row("文明一覧", len(civilizations) >= 5, " / ".join(civilizations[:10])))

    tags = list_tags(DEFAULT_DB_PATH)
    rows.append(_row("タグ一覧", len(tags) > 0, f"{len(tags)}件"))

    request = DeckGenerationRequest(
        deck_name="スモークテスト",
        civilizations=["火", "自然"],
        deck_type="ランプ",
        focus_tags=parse_tag_input("マナ加速;フィニッシャー;除去;受け札"),
        avoid_tags=parse_tag_input("ハンデス"),
        strategy_note="スモークテスト用の生成条件です。",
        deck_size=40,
        early_ratio=30,
        defense_ratio=30,
        finisher_ratio=20,
    )
    deck = build_deck_for_request(request, DEFAULT_DB_PATH, seed=1)
    deck_size = sum(int(card.get("quantity", 1)) for card in deck)
    rows.append(_row("条件付きデッキ生成", deck_size == 40, f"{deck_size}枚"))

    analysis = analyze_deck_condition(
        deck_cards=deck,
        civilizations=request.civilizations,
        focus_tags=request.focus_tags,
        avoid_tags=request.avoid_tags,
        target_starter_count=12,
        target_defense_count=12,
        target_finisher_count=8,
    )
    rows.append(_row("生成条件適合度", analysis.condition_score >= 70, f"{analysis.condition_score} / 100"))

    evaluation = evaluate_deck(deck)
    rows.append(_row("デッキ評価", evaluation["total_cards"] == 40, f"評価スコア {evaluation['score']}"))

    ensure_generated_decks_table(DEFAULT_DB_PATH)
    saved_df = load_generated_decks(DEFAULT_DB_PATH)
    csv_bytes = generated_decks_to_csv(saved_df)
    rows.append(_row("保存済み生成デッキ一覧", csv_bytes.startswith(b"\xef\xbb\xbf"), f"{len(saved_df)}件"))

    failed = [row for row in rows if row["判定"] != "OK"]
    return {
        "ok": not failed,
        "status": "OK" if not failed else "NG",
        "passed": len(rows) - len(failed),
        "failed": len(failed),
        "rows": rows,
    }

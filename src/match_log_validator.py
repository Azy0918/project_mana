from __future__ import annotations

from typing import Any


VALID_PLAY_ORDERS = ["先攻", "後攻"]
VALID_RESULTS = ["勝ち", "負け"]


def validate_match_log(log: dict[str, Any]) -> list[str]:
    errors = []

    if not str(log.get("deck_name", "")).strip():
        errors.append("使用デッキ名は必須です。")
    if not str(log.get("opponent_deck_type", "")).strip():
        errors.append("相手デッキタイプは必須です。")
    if log.get("play_order") not in VALID_PLAY_ORDERS:
        errors.append("先攻/後攻を選択してください。")
    if log.get("result") not in VALID_RESULTS:
        errors.append("勝敗を選択してください。")

    finish_turn = log.get("finish_turn")
    try:
        finish_turn_int = int(finish_turn)
        if finish_turn_int <= 0:
            errors.append("決着ターンは1以上で入力してください。")
    except (TypeError, ValueError):
        errors.append("決着ターンは数値で入力してください。")

    return errors

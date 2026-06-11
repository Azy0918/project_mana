from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.battle.rating.store import DEFAULT_DB_PATH, save_sim_battle_log, save_sim_rating
from src.battle.sim.runner import simulate_matches

# メタデッキのカード名がカードDBと一致した割合がこれ未満のデッキは対戦相手から除外する
DEFAULT_MIN_COVERAGE = 0.6


def load_meta_battle_decks(
    db_path: Path = DEFAULT_DB_PATH,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> tuple[list[dict[str, Any]], list[str]]:
    """meta_deck_cardsをカードDBと名前で結合し、カーネル実行可能なメタデッキを返す。

    戻り値は (デッキ一覧, 警告一覧)。カード名が一致しない分は除外し、
    coverage(一致枚数率)が低いデッキは警告を出してスキップする。
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT deck_name, card_name, count FROM meta_deck_cards ORDER BY deck_name, id"
        ).fetchall()

        decks: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            decks.setdefault(row["deck_name"], []).append(row)

        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        for deck_name, entries in decks.items():
            cards: list[dict[str, Any]] = []
            matched = 0
            total = 0
            for entry in entries:
                quantity = int(entry["count"] or 1)
                total += quantity
                card_row = conn.execute(
                    "SELECT card_id, name, civilization, cost, card_type, power, text FROM cards WHERE name = ?",
                    (entry["card_name"],),
                ).fetchone()
                if card_row is None:
                    continue
                matched += quantity
                card = dict(card_row)
                card["quantity"] = quantity
                cards.append(card)
            coverage = matched / total if total else 0.0
            if coverage < min_coverage:
                warnings.append(
                    f"{deck_name}: カードDBと一致したのは{matched}/{total}枚({coverage:.0%})のため対戦相手から除外"
                )
                continue
            results.append(
                {
                    "deck_name": deck_name,
                    "cards": cards,
                    "coverage": coverage,
                    "total_cards": matched,
                }
            )
    return results, warnings


def add_deck_to_meta_pool(
    deck: list[dict[str, Any]],
    deck_name: str,
    db_path: Path = DEFAULT_DB_PATH,
    source_name: str = "self_play",
) -> int:
    """デッキを対戦相手プール(meta_deck_cards)に登録する。

    探索で発見した強デッキを相手プールへ昇格させる自己対戦型メタ拡充に使う。
    同名デッキが既に登録済みなら何もしない。戻り値は登録したカード行数。
    """
    with sqlite3.connect(db_path) as conn:
        exists = conn.execute(
            "SELECT COUNT(*) FROM meta_deck_cards WHERE deck_name = ?", (deck_name,)
        ).fetchone()[0]
        if exists:
            return 0
        inserted = 0
        for card in deck:
            conn.execute(
                """
                INSERT INTO meta_deck_cards (deck_name, format, source_url, card_name, count, raw_line, imported_at)
                VALUES (?, 'SIM', ?, ?, ?, '', datetime('now'))
                """,
                (deck_name, source_name, card["name"], int(card.get("quantity", 1))),
            )
            inserted += 1
        return inserted


def rate_deck_against_meta(
    deck: list[dict[str, Any]],
    deck_name: str,
    db_path: Path = DEFAULT_DB_PATH,
    games_per_pair: int = 100,
    seed: int | None = None,
    effects: dict[str, list[dict[str, Any]]] | None = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    save: bool = True,
) -> dict[str, Any]:
    """メタデッキ総当たりで絶対強さスコア(平均勝率×100)を算出する。

    対戦結果は sim_battle_logs、集計は sim_ratings に保存する。
    """
    meta_decks, warnings = load_meta_battle_decks(db_path, min_coverage=min_coverage)
    if not meta_decks:
        return {
            "deck_name": deck_name,
            "strength_score": None,
            "win_rate": None,
            "details": [],
            "warnings": warnings + ["対戦可能なメタデッキがありません。メタデッキ収集を先に実行してください。"],
        }

    details: list[dict[str, Any]] = []
    for index, meta_deck in enumerate(meta_decks):
        pair_seed = None if seed is None else seed + index
        summary = simulate_matches(
            deck,
            meta_deck["cards"],
            games=games_per_pair,
            seed=pair_seed,
            effects=effects,
        )
        if save:
            save_sim_battle_log(deck_name, meta_deck["deck_name"], summary, pair_seed, db_path=db_path)
        details.append(
            {
                "opponent": meta_deck["deck_name"],
                "coverage": meta_deck["coverage"],
                "games": summary.games,
                "wins": summary.wins_a,
                "win_rate": summary.win_rate_a,
                "ci95_low": summary.ci95_low_a,
                "ci95_high": summary.ci95_high_a,
                "average_turns": summary.average_turns,
            }
        )

    games_total = sum(detail["games"] for detail in details)
    wins_total = sum(detail["wins"] for detail in details)
    win_rate = wins_total / games_total if games_total else 0.0
    if save:
        save_sim_rating(deck_name, "meta_decks", details, db_path=db_path)

    return {
        "deck_name": deck_name,
        "strength_score": round(win_rate * 100, 1),
        "win_rate": win_rate,
        "games_total": games_total,
        "details": details,
        "warnings": warnings,
    }

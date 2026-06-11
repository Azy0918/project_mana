from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from src.battle.effects.store import (
    approve_clean_drafts,
    coverage_summary,
    generate_drafts_for_missing_cards,
    load_approved_effects_map,
)
from src.battle.kernel.cards import BattleCard, battle_deck_from_dicts
from src.battle.kernel.lookahead import LookaheadPolicy
from src.battle.kernel.policy import GreedyPolicy, Policy
from src.battle.rating.meta_rating import load_meta_battle_decks, rate_deck_against_meta
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.runner import simulate_matches

DEFAULT_REPORT_DIR = Path("data/reports/sim")

POLICY_FACTORIES: dict[str, Callable[[], Policy]] = {
    "greedy": GreedyPolicy,
    "lookahead": LookaheadPolicy,
}


def run_round_robin(
    decks: list[dict[str, Any]],
    games_per_pair: int = 100,
    seed: int | None = None,
    effects: dict[str, list[dict[str, Any]]] | None = None,
    policy_name: str = "greedy",
) -> dict[str, Any]:
    """デッキ群の総当たり戦。戻り値は勝率マトリクスと平均勝率ランキング。

    decks の各要素は {"deck_name": str, "cards": list[dict] | list[BattleCard]}。
    """
    names = [deck["deck_name"] for deck in decks]
    matrix: dict[str, dict[str, float]] = {name: {} for name in names}
    pair_index = 0
    for i, deck_a in enumerate(decks):
        for j, deck_b in enumerate(decks):
            if j <= i:
                continue
            pair_seed = None if seed is None else seed + pair_index
            pair_index += 1
            summary = simulate_matches(
                deck_a["cards"],
                deck_b["cards"],
                games=games_per_pair,
                seed=pair_seed,
                effects=effects,
                policy_a=POLICY_FACTORIES[policy_name](),
                policy_b=POLICY_FACTORIES[policy_name](),
            )
            matrix[deck_a["deck_name"]][deck_b["deck_name"]] = summary.win_rate_a
            matrix[deck_b["deck_name"]][deck_a["deck_name"]] = summary.win_rate_b

    rankings = sorted(
        (
            {
                "deck_name": name,
                "average_win_rate": sum(row.values()) / len(row) if row else 0.0,
                "matchups": row,
            }
            for name, row in matrix.items()
        ),
        key=lambda entry: -entry["average_win_rate"],
    )
    return {
        "games_per_pair": games_per_pair,
        "policy": policy_name,
        "decks": names,
        "matrix": matrix,
        "rankings": rankings,
    }


def benchmark_policies(
    deck: list[dict[str, Any]] | list[BattleCard],
    games: int = 100,
    seed: int | None = None,
    effects: dict[str, list[dict[str, Any]]] | None = None,
    policy_a: str = "lookahead",
    policy_b: str = "greedy",
) -> dict[str, Any]:
    """同一デッキのミラーマッチで方策同士を対戦させ、方策の強さを測る。"""
    summary = simulate_matches(
        deck,
        deck,
        games=games,
        seed=seed,
        effects=effects,
        policy_a=POLICY_FACTORIES[policy_a](),
        policy_b=POLICY_FACTORIES[policy_b](),
    )
    return {
        "policy_a": policy_a,
        "policy_b": policy_b,
        "games": summary.games,
        "win_rate_a": summary.win_rate_a,
        "ci95_low_a": summary.ci95_low_a,
        "ci95_high_a": summary.ci95_high_a,
        "draws": summary.draws,
        "average_turns": summary.average_turns,
    }


def write_report(payload: dict[str, Any], name: str, report_dir: Path = DEFAULT_REPORT_DIR) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"{name}_{timestamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_deck_file(path: Path) -> list[dict[str, Any]]:
    """JSONデッキファイル(カードdictのリスト)を読み込む。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "cards" in data:
        data = data["cards"]
    if not isinstance(data, list):
        raise ValueError(f"{path}: カードdictのリスト、または {{'cards': [...]}} 形式で指定してください")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.battle.research",
        description="ヘッドレス対戦シミュレーション研究ツール",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="カードDBのパス")
    parser.add_argument("--games", type=int, default=100, help="ペアあたりの試合数")
    parser.add_argument("--seed", type=int, default=None, help="乱数シード")
    parser.add_argument("--policy", choices=sorted(POLICY_FACTORIES), default="greedy", help="使用する方策")
    parser.add_argument("--no-effects", action="store_true", help="承認済みEffectScriptを使わない")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("meta-tournament", help="収集済みメタデッキ同士の総当たり戦")
    sub.add_parser("prepare-effects", help="EffectScript下書き生成と完全変換ぶんの一括承認")

    rate_parser = sub.add_parser("rate", help="デッキをメタデッキ総当たりで強さ判定")
    rate_parser.add_argument("deck_file", type=Path, help="デッキJSONファイル")
    rate_parser.add_argument("--name", default=None, help="デッキ名(省略時はファイル名)")

    bench_parser = sub.add_parser("benchmark-policies", help="ミラーマッチで方策同士を比較")
    bench_parser.add_argument("--deck-file", type=Path, default=None, help="デッキJSON(省略時は最初のメタデッキ)")
    bench_parser.add_argument("--policy-a", choices=sorted(POLICY_FACTORIES), default="lookahead")
    bench_parser.add_argument("--policy-b", choices=sorted(POLICY_FACTORIES), default="greedy")

    args = parser.parse_args(argv)

    if args.command == "prepare-effects":
        created = generate_drafts_for_missing_cards(args.db)
        approved = approve_clean_drafts(args.db)
        summary = coverage_summary(args.db)
        print(f"下書き生成: {created}件 / 一括承認: {approved}件")
        print(
            f'登録率: {summary["registered_rate"]:.1%} / 承認済み率: {summary["approved_rate"]:.1%} '
            f'(全{summary["total_cards"]}カード, 状態内訳: {summary["status_counts"]})'
        )
        return 0

    effects = None if args.no_effects else load_approved_effects_map(args.db)

    if args.command == "meta-tournament":
        decks, warnings = load_meta_battle_decks(args.db)
        for warning in warnings:
            print(f"warning: {warning}")
        if len(decks) < 2:
            print("総当たりに必要なメタデッキが2つ未満です。")
            return 1
        result = run_round_robin(decks, games_per_pair=args.games, seed=args.seed, effects=effects, policy_name=args.policy)
        path = write_report(result, "meta_tournament", args.report_dir)
        print(f"report: {path}")
        for rank, entry in enumerate(result["rankings"], start=1):
            print(f'{rank}. {entry["deck_name"]}: 平均勝率 {entry["average_win_rate"]:.1%}')
        return 0

    if args.command == "rate":
        deck = _load_deck_file(args.deck_file)
        deck_name = args.name or args.deck_file.stem
        result = rate_deck_against_meta(
            deck, deck_name, db_path=args.db, games_per_pair=args.games, seed=args.seed, effects=effects
        )
        path = write_report(result, f"rate_{deck_name}", args.report_dir)
        print(f"report: {path}")
        print(f'絶対強さスコア: {result["strength_score"]}')
        for detail in result["details"]:
            print(f'  vs {detail["opponent"]}: {detail["win_rate"]:.1%}')
        for warning in result["warnings"]:
            print(f"warning: {warning}")
        return 0

    if args.command == "benchmark-policies":
        if args.deck_file is not None:
            deck = _load_deck_file(args.deck_file)
        else:
            decks, _warnings = load_meta_battle_decks(args.db)
            if not decks:
                print("デッキ指定がなく、メタデッキもありません。")
                return 1
            deck = decks[0]["cards"]
            print(f'deck: {decks[0]["deck_name"]}(先頭のメタデッキ)')
        result = benchmark_policies(
            deck, games=args.games, seed=args.seed, effects=effects, policy_a=args.policy_a, policy_b=args.policy_b
        )
        path = write_report(result, "policy_benchmark", args.report_dir)
        print(f"report: {path}")
        print(
            f'{result["policy_a"]} vs {result["policy_b"]}: '
            f'勝率 {result["win_rate_a"]:.1%} [{result["ci95_low_a"]:.1%}-{result["ci95_high_a"]:.1%}] '
            f'引き分け{result["draws"]} ({result["games"]}試合, 平均{result["average_turns"]:.1f}ターン)'
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from src.battle.effects.store import (
    apply_curated_scripts,
    approve_clean_drafts,
    coverage_summary,
    generate_drafts_for_missing_cards,
    load_approved_effects_map,
    regenerate_unapproved_drafts,
)
from src.battle.kernel.cards import BattleCard, battle_deck_from_dicts
from src.battle.kernel.combo import ComboPolicy
from src.battle.kernel.lookahead import LookaheadPolicy
from src.battle.kernel.policy import GreedyPolicy, Policy
from src.battle.rating.meta_rating import load_meta_battle_decks, rate_deck_against_meta
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.runner import simulate_matches

DEFAULT_REPORT_DIR = Path("data/reports/sim")

POLICY_FACTORIES: dict[str, Callable[[], Policy]] = {
    "greedy": GreedyPolicy,
    "lookahead": LookaheadPolicy,
    "combo": ComboPolicy,
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

    rate_gen_parser = sub.add_parser("rate-generated", help="保存済み生成デッキをメタ総当たりで強さ判定")
    rate_gen_parser.add_argument("--id", type=int, default=None, help="generated_decksのID(省略時は一覧を表示)")

    evolve_parser = sub.add_parser("evolve-rate", help="進化探索の上位候補を厳密レーティングに流す")
    evolve_parser.add_argument("--generations", type=int, default=8)
    evolve_parser.add_argument("--population", type=int, default=12)
    evolve_parser.add_argument("--focus", default="バランス", help="進化探索の重みプリセット")
    evolve_parser.add_argument("--civilizations", default=None, help="カンマ区切りの文明フィルタ")

    hybrid_parser = sub.add_parser("hybrid-search", help="世代内選別に厳密シミュレーションを使う進化探索")
    hybrid_parser.add_argument("--generations", type=int, default=8)
    hybrid_parser.add_argument("--population", type=int, default=12)
    hybrid_parser.add_argument("--sim-games", type=int, default=30, help="世代内選別での相手ごとの試合数")
    hybrid_parser.add_argument("--sim-opponents", type=int, default=3, help="世代内選別で使うメタデッキ数")
    hybrid_parser.add_argument("--sim-weight", type=float, default=0.7, help="シミュレーション勝率の比重(0-1)")
    hybrid_parser.add_argument("--civilizations", default=None, help="カンマ区切りの文明フィルタ")
    hybrid_parser.add_argument("--no-rotate", action="store_true", help="選別相手の世代ローテーションを無効化(固定相手)")
    hybrid_parser.add_argument("--rotation-period", type=int, default=3, help="選別相手を入れ替える世代間隔")
    hybrid_parser.add_argument("--no-save", action="store_true", help="成果デッキをgenerated_decksに保存しない")
    hybrid_parser.add_argument("--max-card-types", type=int, default=16, help="デッキ内カード種類数のソフト上限")

    expand_parser = sub.add_parser("meta-expand", help="探索勝者を相手プールへ昇格させる自己対戦型メタ拡充(PSRO方式)")
    expand_parser.add_argument("--rounds", type=int, default=3, help="拡充ラウンド数")
    expand_parser.add_argument("--threshold", type=float, default=55.0, help="昇格に必要な絶対強さスコア")
    expand_parser.add_argument("--generations", type=int, default=10)
    expand_parser.add_argument("--population", type=int, default=14)

    mine_parser = sub.add_parser("combo-mine", help="カード固有の相互作用からコンボ候補を発掘・検証")
    mine_parser.add_argument("--max-proposals", type=int, default=30)
    mine_parser.add_argument("--trials", type=int, default=300, help="チェーン成立検証の一人回し試行数")
    mine_parser.add_argument("--max-turns", type=int, default=8, help="成立期限ターン")
    mine_parser.add_argument("--rate-top", type=int, default=3, help="メタ判定まで行う上位件数")
    mine_parser.add_argument("--evolve", action="store_true", help="最良コンボをシードにハイブリッド探索で周辺を最適化")

    loop_parser = sub.add_parser("loop-find", help="サガ型(相互/自己蘇生)ループの静的検出+動的検証")
    loop_parser.add_argument("--verify-top", type=int, default=20, help="動的検証する候補数")

    sub.add_parser("sanity-check", help="実戦ログなしでシミュレーターの方向性妥当性を検証")

    sub.add_parser("validate-ratings", help="実戦ログの勝率とシミュレーション強さの相関を検証")

    bench_parser = sub.add_parser("benchmark-policies", help="ミラーマッチで方策同士を比較")
    bench_parser.add_argument("--deck-file", type=Path, default=None, help="デッキJSON(省略時は最初のメタデッキ)")
    bench_parser.add_argument("--policy-a", choices=sorted(POLICY_FACTORIES), default="lookahead")
    bench_parser.add_argument("--policy-b", choices=sorted(POLICY_FACTORIES), default="greedy")

    args = parser.parse_args(argv)

    if args.command == "prepare-effects":
        created = generate_drafts_for_missing_cards(args.db)
        regenerated = regenerate_unapproved_drafts(args.db)
        approved = approve_clean_drafts(args.db)
        curated, missing = apply_curated_scripts(db_path=args.db)
        summary = coverage_summary(args.db)
        print(f"下書き生成: {created}件 / 再生成: {regenerated}件 / 一括承認: {approved}件 / キュレーション適用: {curated}件")
        for name in missing:
            print(f"warning: キュレーション対象が見つかりません: {name}")
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
            deck, deck_name, db_path=args.db, games_per_pair=args.games, seed=args.seed, effects=effects,
            policy_factory=POLICY_FACTORIES[args.policy], policy_name=args.policy,
        )
        path = write_report(result, f"rate_{deck_name}", args.report_dir)
        print(f"report: {path}")
        print(f'絶対強さスコア: {result["strength_score"]}')
        for detail in result["details"]:
            print(f'  vs {detail["opponent"]}: {detail["win_rate"]:.1%}')
        for warning in result["warnings"]:
            print(f"warning: {warning}")
        return 0

    if args.command == "rate-generated":
        import sqlite3

        with sqlite3.connect(args.db) as conn:
            conn.row_factory = sqlite3.Row
            if args.id is None:
                rows = conn.execute(
                    "SELECT id, deck_name, created_at, evaluation_score FROM generated_decks ORDER BY id DESC LIMIT 30"
                ).fetchall()
                if not rows:
                    print("保存済みの生成デッキがありません。")
                    return 1
                for row in rows:
                    print(f'id={row["id"]} {row["deck_name"]} (評価{row["evaluation_score"]}, {row["created_at"]})')
                print("\n--id を指定すると強さ判定を実行します。")
                return 0
            row = conn.execute(
                "SELECT deck_name, deck_cards_json FROM generated_decks WHERE id = ?", (args.id,)
            ).fetchone()
        if row is None:
            print(f"id={args.id} の生成デッキが見つかりません。")
            return 1
        deck = json.loads(row["deck_cards_json"] or "[]")
        if not deck:
            print(f"id={args.id} のデッキリストが空です。")
            return 1
        result = rate_deck_against_meta(
            deck, row["deck_name"], db_path=args.db, games_per_pair=args.games, seed=args.seed, effects=effects,
            policy_factory=POLICY_FACTORIES[args.policy], policy_name=args.policy,
        )
        path = write_report(result, f'rate_generated_{args.id}', args.report_dir)
        print(f"report: {path}")
        print(f'絶対強さスコア: {result["strength_score"]}(方策: {args.policy})')
        for detail in result["details"]:
            print(f'  vs {detail["opponent"]}: {detail["win_rate"]:.1%}')
        for warning in result["warnings"]:
            print(f"warning: {warning}")
        return 0

    if args.command == "evolve-rate":
        from src.evolutionary_search import run_evolutionary_search

        civilizations = [c.strip() for c in (args.civilizations or "").split(",") if c.strip()] or None
        search = run_evolutionary_search(
            db_path=args.db,
            generations=args.generations,
            population_size=args.population,
            civilizations=civilizations,
            focus=args.focus,
            seed=args.seed,
        )
        candidates = []
        for label in ["best_overall", "best_novelty", "best_meta"]:
            entry = search.get(label)
            if entry and entry.get("deck"):
                candidates.append((label, entry))
        if not candidates:
            print("進化探索が候補を返しませんでした。")
            return 1
        results = []
        for label, entry in candidates:
            deck_name = f"進化探索_{args.focus}_{label}"
            rating = rate_deck_against_meta(
                entry["deck"], deck_name, db_path=args.db, games_per_pair=args.games, seed=args.seed, effects=effects
            )
            results.append(
                {
                    "label": label,
                    "deck_name": deck_name,
                    "heuristic_fitness": entry.get("fitness"),
                    "strength_score": rating["strength_score"],
                    "details": rating["details"],
                    "warnings": rating["warnings"],
                }
            )
            print(
                f'{label}: ヒューリスティック適応度 {entry.get("fitness")} / '
                f'厳密強さスコア {rating["strength_score"]}'
            )
        path = write_report({"focus": args.focus, "results": results}, "evolve_rate", args.report_dir)
        print(f"report: {path}")
        return 0

    if args.command == "hybrid-search":
        from src.battle.hybrid_search import run_hybrid_search

        civilizations = [c.strip() for c in (args.civilizations or "").split(",") if c.strip()] or None
        search = run_hybrid_search(
            db_path=args.db,
            generations=args.generations,
            population_size=args.population,
            civilizations=civilizations,
            seed=args.seed,
            sim_games=args.sim_games,
            sim_opponents=args.sim_opponents,
            sim_weight=args.sim_weight,
            rotate_opponents=not args.no_rotate,
            rotation_period=args.rotation_period,
            max_card_types=args.max_card_types,
        )
        for warning in search.get("warnings", []):
            print(f"warning: {warning}")
        best = search.get("best")
        if best is None:
            return 1
        for entry in search["history"]:
            print(
                f'世代{entry["generation"]}: 合成 {entry["best_combined"]} '
                f'(勝率 {entry["best_sim_win_rate"]:.1%} / ヒューリスティック {entry["best_heuristic"]}) '
                f'相手: {", ".join(entry["opponents"])}'
            )
        rotation_label = "ローテーション" if search.get("rotate_opponents") else "固定"
        print(f'選別相手({rotation_label}): {", ".join(search["opponents"])}')
        deck_name = "ハイブリッド探索_best"
        rating = rate_deck_against_meta(
            best["deck"], deck_name, db_path=args.db, games_per_pair=args.games, seed=args.seed, effects=effects
        )
        print(f'最終候補の全メタ判定: 絶対強さスコア {rating["strength_score"]}')
        for detail in rating["details"]:
            print(f'  vs {detail["opponent"]}: {detail["win_rate"]:.1%}')
        payload = {
            "history": search["history"],
            "opponents": search["opponents"],
            "sim_weight": search["sim_weight"],
            "best_deck": [
                {"name": card["name"], "quantity": card.get("quantity", 1)} for card in best["deck"]
            ],
            "best_heuristic": best["heuristic_score"],
            "final_rating": rating["strength_score"],
            "matchups": rating["details"],
        }
        path = write_report(payload, "hybrid_search", args.report_dir)
        print(f"report: {path}")
        if not args.no_save:
            from src.battle.hybrid_search import save_to_generated_decks

            matchup_lines = "、".join(
                f'{detail["opponent"]} {detail["win_rate"]:.0%}' for detail in rating["details"]
            )
            note = (
                f'ハイブリッド探索(世代{args.generations}×{args.population}体, '
                f'sim比重{args.sim_weight})の最良候補。'
                f'絶対強さスコア {rating["strength_score"]}。相性: {matchup_lines}'
            )
            timestamp = datetime.now().strftime("%m/%d %H:%M")
            deck_id = save_to_generated_decks(
                best["deck"],
                f"ハイブリッド探索 {timestamp} (強さ{rating['strength_score']})",
                note,
                db_path=args.db,
            )
            print(f"generated_decksに保存しました: id={deck_id}(アプリの生成デッキ一覧 / rate-generated --id {deck_id} で参照可)")
        return 0

    if args.command == "meta-expand":
        from src.battle.hybrid_search import run_hybrid_search, save_to_generated_decks
        from src.battle.rating.meta_rating import add_deck_to_meta_pool

        for round_index in range(1, args.rounds + 1):
            pool, _w = load_meta_battle_decks(args.db)
            print(f"\n=== ラウンド{round_index}: 相手プール {len(pool)}デッキ ===")
            round_seed = None if args.seed is None else args.seed + round_index * 1000
            search = run_hybrid_search(
                db_path=args.db,
                generations=args.generations,
                population_size=args.population,
                seed=round_seed,
            )
            best = search.get("best")
            if best is None:
                print("探索が候補を返しませんでした。中断します。")
                return 1
            rating = rate_deck_against_meta(
                best["deck"], f"自己対戦R{round_index}", db_path=args.db,
                games_per_pair=args.games, seed=round_seed, effects=effects, save=False,
            )
            score = rating["strength_score"]
            print(f"勝者の絶対強さスコア: {score}(昇格閾値 {args.threshold})")
            if score is None or score < args.threshold:
                print("閾値未満のため昇格せず終了します(メタが探索に対して飽和)。")
                break
            deck_name = f"自己対戦デッキR{round_index} (強さ{score})"
            added = add_deck_to_meta_pool(best["deck"], deck_name, db_path=args.db)
            save_to_generated_decks(
                best["deck"], deck_name,
                f"meta-expandラウンド{round_index}の昇格デッキ。昇格時スコア {score}",
                db_path=args.db,
            )
            print(f"相手プールへ昇格: {deck_name}({added}種)")
        pool, _w = load_meta_battle_decks(args.db)
        print(f"\n最終的な相手プール: {len(pool)}デッキ: {', '.join(d['deck_name'] for d in pool)}")
        return 0

    if args.command == "combo-mine":
        from src.battle.combo_mine import mine_combos

        result = mine_combos(
            db_path=args.db,
            max_proposals=args.max_proposals,
            trials=args.trials,
            max_turns=args.max_turns,
            games=args.games,
            seed=args.seed,
            rate_top=args.rate_top,
        )
        print(f'チェーン提案: {result["proposals"]}件 / デッキ構築・検証済み: {len(result["validated"])}件\n')
        for entry in result["validated"][:10]:
            line = (
                f'[{entry["kind"]}] {" → ".join(entry["names"])}: '
                f'成立率 {entry["success_rate"]:.1%}'
            )
            if "strength_score" in entry:
                line += f' / 対メタ強さ {entry["strength_score"]}'
            print(line)
            if entry.get("completion_turns"):
                print(f'    成立ターン分布: {entry["completion_turns"]}')
        payload = {
            "proposals": result["proposals"],
            "validated": [
                {key: value for key, value in entry.items() if key != "deck"}
                for entry in result["validated"]
            ],
        }
        path = write_report(payload, "combo_mine", args.report_dir)
        print(f"\nreport: {path}")

        if args.evolve and result["validated"] and result["validated"][0]["success_rate"] > 0:
            from src.battle.hybrid_search import run_hybrid_search, save_to_generated_decks

            best_combo = result["validated"][0]
            print(f'\n=== 最良コンボをシードに進化: {" → ".join(best_combo["names"])} ===')
            search = run_hybrid_search(
                db_path=args.db, generations=10, population_size=14,
                seed=args.seed, seed_deck=best_combo["deck"],
                locked_card_ids=best_combo["chain"], chain=best_combo["chain"],
            )
            if search.get("best"):
                final_assembly = search["best"].get("assembly_rate", 0.0)
                print(f'進化後のコンボ成立率: {final_assembly:.1%}(発掘時 {best_combo["success_rate"]:.1%})')
                rating = rate_deck_against_meta(
                    search["best"]["deck"], "コンボ進化", db_path=args.db,
                    games_per_pair=args.games, seed=args.seed, effects=effects,
                )
                print(f'進化後の対メタ強さ: {rating["strength_score"]}(シード時 {best_combo.get("strength_score")})')
                deck_id = save_to_generated_decks(
                    search["best"]["deck"],
                    f'コンボ進化 {best_combo["names"][-1][:12]} (強さ{rating["strength_score"]})',
                    f'combo-mine --evolve の成果。コンボ骨格: {" → ".join(best_combo["names"])}。'
                    f'成立率{best_combo["success_rate"]:.0%}、進化後強さ{rating["strength_score"]}',
                    db_path=args.db,
                )
                print(f"generated_decksに保存: id={deck_id}")
        return 0

    if args.command == "loop-find":
        from src.battle.loop_finder import mine_loops

        result = mine_loops(db_path=args.db, verify_top=args.verify_top)
        print(f'静的候補: {result["static_candidates"]}件 / 動的検証: {len(result["verified"])}件\n')
        for entry in result["verified"][:12]:
            if entry.get("one_turn_kill"):
                mark = f'★1ターンキル(詠唱{entry.get("cast_count", 0)}回・シールド{entry.get("shields_taken", 0)}枚)'
            elif entry["hits_cap"]:
                mark = "★ループ署名"
            else:
                mark = f'蘇生{entry["revive_count"]}回'
            print(f'[{entry["kind"]}] {" + ".join(entry["names"])}: {mark}')
            if entry["revived_names"]:
                print(f'    連鎖: {" → ".join(str(n) for n in entry["revived_names"][:6])}')
        path = write_report(
            {"static_candidates": result["static_candidates"], "verified": result["verified"]},
            "loop_find", args.report_dir,
        )
        print(f"\nreport: {path}")
        return 0

    if args.command == "sanity-check":
        from src.battle.sim.sanity import run_sanity_checks

        checks = run_sanity_checks(games=args.games, seed=args.seed or 1)
        failed = [check for check in checks if not check["passed"]]
        for check in checks:
            mark = "OK " if check["passed"] else "NG "
            print(f'{mark} {check["name"]}: 勝率 {check["win_rate_a"]:.1%}(期待 {check["expect"]})')
        path = write_report({"checks": checks, "failed": len(failed)}, "sanity_check", args.report_dir)
        print(f"\n{len(checks) - len(failed)}/{len(checks)} 件合格 / report: {path}")
        return 1 if failed else 0

    if args.command == "validate-ratings":
        import sqlite3
        from statistics import correlation

        with sqlite3.connect(args.db) as conn:
            rows = conn.execute(
                """
                SELECT deck_name,
                       SUM(CASE WHEN result LIKE '%勝%' THEN 1 ELSE 0 END) AS wins,
                       COUNT(*) AS games
                FROM real_match_logs GROUP BY deck_name HAVING games >= 5
                """
            ).fetchall()
            sim_rows = conn.execute(
                "SELECT deck_name, MAX(id), win_rate FROM sim_ratings GROUP BY deck_name"
            ).fetchall()
        sim_by_name = {name: win_rate for name, _id, win_rate in sim_rows}
        pairs = [
            (wins / games, sim_by_name[name])
            for name, wins, games in rows
            if name in sim_by_name
        ]
        if len(pairs) < 3:
            print(
                f"相関検証に必要なデータが不足しています(実戦5試合以上のデッキ {len(rows)}件、"
                f"シミュレーション判定済みと一致 {len(pairs)}件、必要3件以上)。"
            )
            print("実戦ログを記録し、同名デッキを rate / rate-generated で判定してから再実行してください。")
            return 0
        real_rates = [p[0] for p in pairs]
        sim_rates = [p[1] for p in pairs]
        r = correlation(real_rates, sim_rates)
        payload = {
            "decks": len(pairs),
            "pearson_r": r,
            "pairs": [{"real": a, "sim": b} for a, b in pairs],
        }
        path = write_report(payload, "rating_validation", args.report_dir)
        print(f"実勝率 vs シミュレーション勝率 (n={len(pairs)}): Pearson r = {r:.3f}")
        print(f"report: {path}")
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

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import importlib
import json
import sqlite3
from typing import Any

import pandas as pd

from src.dashboard import collect_dashboard_data
from src.deck_explorer import run_deck_exploration
import src.generated_deck_store as generated_deck_store
from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH
from src.combo_knowledge_base import summarize_known_combos
from src.meta_deck_store import summarize_meta_decks
from src.simulate_goldfish import simulate_goldfish


RESEARCH_CYCLE_VERSION = 3
generated_deck_store = importlib.reload(generated_deck_store)
save_generated_deck = generated_deck_store.save_generated_deck
load_generated_deck_detail = generated_deck_store.load_generated_deck_detail
load_generated_decks = generated_deck_store.load_generated_decks


def collect_mana_research_brief(
    db_path: Path = DEFAULT_DB_PATH,
    csv_path: Path = DEFAULT_CSV_PATH,
) -> dict[str, Any]:
    dashboard = collect_dashboard_data(db_path, csv_path)
    generated_decks = load_generated_decks(db_path)
    meta_summary = summarize_meta_decks(db_path)
    combo_summary = summarize_known_combos(db_path)

    top_generated = _top_generated_decks(generated_decks)
    weak_generated = _weak_generated_decks(generated_decks)
    untagged_cards = prioritize_untagged_cards(db_path)
    next_test_decks = select_next_test_decks(db_path)
    next_research_actions = _build_research_actions(
        dashboard,
        generated_decks,
        top_generated,
        weak_generated,
        meta_summary,
        combo_summary,
    )
    mana_judgement = build_mana_judgement(
        dashboard,
        generated_decks,
        untagged_cards,
        next_test_decks,
        meta_summary,
        combo_summary,
    )

    return {
        "dashboard": dashboard,
        "meta_summary": meta_summary,
        "combo_summary": combo_summary,
        "generated_deck_count": len(generated_decks),
        "top_generated_decks": top_generated,
        "weak_generated_decks": weak_generated,
        "untagged_cards": untagged_cards,
        "next_test_decks": next_test_decks,
        "next_research_actions": next_research_actions,
        "research_status": _research_status(dashboard, generated_decks),
        "mana_judgement": mana_judgement,
    }


def build_mana_judgement(
    dashboard: dict[str, Any],
    generated_decks: pd.DataFrame,
    untagged_cards: list[dict[str, Any]],
    next_test_decks: list[dict[str, Any]],
    meta_summary: dict[str, Any] | None = None,
    combo_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card_stats = dashboard["card_stats"]
    lines = []
    if card_stats["card_count"] >= 5000:
        lines.append("カードDB基盤は完成しています。")
    elif card_stats["card_count"] >= 1000:
        lines.append("カードDB基盤は研究可能な水準です。")
    else:
        lines.append("カードDB基盤はまだ拡充が必要です。")

    if not untagged_cards:
        lines.append("タグ空欄は0枚です。")
        lines.append("次の研究段階は効果構造理解 v1 です。")
    else:
        lines.append(f"タグ空欄が{len(untagged_cards)}枚あります。補完を優先してください。")
    if meta_summary and meta_summary.get("count", 0) > 0:
        lines.append(f"環境デッキDBは{meta_summary['count']}件登録済みです。")
    else:
        lines.append("環境デッキDBは未登録です。現環境の登録を推奨します。")
    if combo_summary and combo_summary.get("count", 0) > 0:
        lines.append(f"既知コンボDBは{combo_summary['count']}件登録済みです。")
    else:
        lines.append("既知コンボDBは未登録です。コンボ研究の登録を推奨します。")

    if not untagged_cards:
        next_subject = "効果構造解析を開始し、特殊勝利・ループ・退化・制約解除の候補を確認します。"
    elif len(generated_decks) == 0:
        next_subject = "探索候補の生成に進みます。"
    elif not next_test_decks:
        next_subject = "探索候補の安定性検査に進みます。"
    else:
        next_subject = "実戦検証候補の比較に進みます。"

    recommendations = [
        "MANAに候補を20件探索させる",
        "上位10件に一人回し検査を実行する",
        "条件を満たした候補だけ保存する",
        "実戦候補を3件選ぶ",
    ]

    return {
        "判定": lines,
        "次の研究課題": next_subject,
        "今日の推奨": recommendations,
    }


def prioritize_untagged_cards(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """タグ未設定カードを、研究上の重要度順に並べる。"""
    if not Path(db_path).exists():
        return []

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT c.*
            FROM cards c
            WHERE NOT EXISTS (
                SELECT 1
                FROM card_tags ct
                WHERE ct.card_id = c.card_id
            )
            """
        ).fetchall()

    cards = []
    for row in rows:
        card = dict(row)
        importance = _untagged_importance(card)
        card.update(
            {
                "重要度": importance,
                "補完優先理由": _untagged_reason(card),
            }
        )
        cards.append(card)
    return sorted(cards, key=lambda card: card["重要度"], reverse=True)


def run_candidate_safety_checks(deck: list[dict[str, Any]]) -> dict[str, Any]:
    """候補デッキに一人回し・役割不足・平均コストなどの追加検査を行う。"""
    goldfish = simulate_goldfish(deck, trials=200, max_turns=5, seed=20260530)
    role_counts = _role_counts(deck)
    average_cost = _average_cost(deck)
    deck_size = sum(_quantity(card) for card in deck)

    warnings: list[str] = []
    if deck_size != 40:
        warnings.append(f"デッキ枚数が40枚ではありません: {deck_size}")
    if role_counts["初動"] < 8:
        warnings.append(f"初動が少なめです: {role_counts['初動']}枚")
    if role_counts["受け札"] < 6:
        warnings.append(f"受け札が少なめです: {role_counts['受け札']}枚")
    if role_counts["フィニッシャー"] < 3:
        warnings.append(f"フィニッシャーが少なめです: {role_counts['フィニッシャー']}枚")
    if average_cost > 5.0:
        warnings.append(f"平均コストが高めです: {average_cost}")
    if goldfish["early_success_rate"] < 0.65:
        warnings.append(f"一人回し初動成功率が低めです: {goldfish['early_success_rate']:.1%}")

    passed = not warnings
    safety_score = 100
    safety_score -= max(0, 8 - role_counts["初動"]) * 4
    safety_score -= max(0, 6 - role_counts["受け札"]) * 4
    safety_score -= max(0, 3 - role_counts["フィニッシャー"]) * 5
    safety_score -= 15 if average_cost > 5.0 else 0
    safety_score -= 20 if goldfish["early_success_rate"] < 0.65 else 0
    safety_score = max(0, min(100, round(safety_score)))

    return {
        "passed": passed,
        "safety_score": safety_score,
        "deck_size": deck_size,
        "average_cost": average_cost,
        "role_counts": role_counts,
        "goldfish": goldfish,
        "warnings": warnings,
    }


def run_candidate_goldfish_checks(
    candidates: list[dict[str, Any]],
    trials: int = 500,
    max_turns: int = 5,
) -> list[dict[str, Any]]:
    """MANA探索候補に一人回し検査を追加する。"""
    checked = []
    for index, candidate in enumerate(candidates):
        deck = candidate.get("deck", [])
        goldfish = simulate_goldfish(deck, trials=trials, max_turns=max_turns, seed=20260530 + index)
        enriched = dict(candidate)
        enriched["goldfish"] = goldfish
        enriched["deck_size"] = sum(_quantity(card) for card in deck)
        enriched["same_name_limit_ok"] = _same_name_limit_ok(deck)
        enriched["safety_checks"] = run_candidate_safety_checks(deck)
        checked.append(enriched)
    return checked


def filter_research_candidates(
    candidates: list[dict[str, Any]],
    novelty_mode: bool = False,
) -> list[dict[str, Any]]:
    """初動成功率、受け札確認率、評価スコアなどで保存前に足切りする。"""
    passed = []
    for candidate in candidates:
        goldfish = candidate.get("goldfish") or simulate_goldfish(candidate.get("deck", []), trials=500, max_turns=5)
        condition_score = float(candidate.get("condition_score", 0))
        evaluation_score = float(candidate.get("evaluation_score", 0))
        novelty_score = float(candidate.get("novelty_score", 0))
        deck_size = int(candidate.get("deck_size") or sum(_quantity(card) for card in candidate.get("deck", [])))
        same_name_ok = bool(candidate.get("same_name_limit_ok", _same_name_limit_ok(candidate.get("deck", []))))

        base_pass = (
            condition_score >= 60
            and evaluation_score >= 40
            and float(candidate.get("candidate_score", 0)) >= 90
            and goldfish["early_success_rate"] >= 0.65
            and goldfish["defense_seen_rate"] >= 0.45
            and deck_size == 40
            and same_name_ok
        )
        novelty_pass = (
            novelty_mode
            and condition_score >= 60
            and novelty_score >= 75
            and evaluation_score >= 25
            and float(candidate.get("candidate_score", 0)) >= 85
            and goldfish["early_success_rate"] >= 0.60
            and goldfish["defense_seen_rate"] >= 0.45
            and deck_size == 40
            and same_name_ok
        )

        if base_pass or novelty_pass:
            enriched = dict(candidate)
            enriched["research_filter_mode"] = "未知性重視" if novelty_pass and not base_pass else "通常"
            enriched["research_filter_passed"] = True
            enriched["research_filter_reason"] = _candidate_filter_reason(enriched)
            passed.append(enriched)

    return sorted(
        passed,
        key=lambda item: (
            float(item.get("candidate_score", 0)),
            float(item.get("condition_score", 0)),
            float(item.get("novelty_score", 0)),
        ),
        reverse=True,
    )


def select_next_test_decks(
    db_path: Path = DEFAULT_DB_PATH,
    limit: int = 5,
    novelty_mode: bool = False,
) -> list[dict[str, Any]]:
    """保存済み生成デッキから実戦待ち候補を選ぶ。"""
    saved = load_generated_decks(db_path)
    if saved.empty:
        return []

    work = saved.copy()
    for column in ["condition_score", "evaluation_score", "starter_count", "defense_count", "finisher_count"]:
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce").fillna(0)

    rows = []
    for _, row in work.iterrows():
        detail = load_generated_deck_detail(int(row["id"]), db_path)
        if not detail:
            continue
        safety = run_candidate_safety_checks(detail.get("deck_cards", []))
        condition_score = float(row.get("condition_score", 0))
        evaluation_score = float(row.get("evaluation_score", 0))
        novelty_score = float(row.get("novelty_score", 0))
        normal_pass = (
            condition_score >= 60
            and evaluation_score >= 40
            and safety["goldfish"]["early_success_rate"] >= 0.65
            and safety["goldfish"]["defense_seen_rate"] >= 0.45
            and safety["deck_size"] == 40
            and _same_name_limit_ok(detail.get("deck_cards", []))
        )
        novelty_pass = (
            novelty_mode
            and condition_score >= 60
            and novelty_score >= 75
            and evaluation_score >= 25
            and safety["goldfish"]["early_success_rate"] >= 0.60
            and safety["goldfish"]["defense_seen_rate"] >= 0.45
            and safety["deck_size"] == 40
            and _same_name_limit_ok(detail.get("deck_cards", []))
        )
        if not (normal_pass or novelty_pass):
            continue
        research_score = (
            condition_score * 0.40
            + evaluation_score * 0.30
            + novelty_score * 0.10
            + safety["safety_score"] * 0.20
        )
        rows.append(
            {
                "ID": int(row["id"]),
                "デッキ名": row.get("deck_name", ""),
                "形式": row.get("format", "ND"),
                "タイプ": row.get("deck_type", ""),
                "研究優先度": round(research_score, 1),
                "安全性": safety["safety_score"],
                "条件適合": row.get("condition_score", 0),
                "評価": row.get("evaluation_score", 0),
                "初動成功率": f'{safety["goldfish"]["early_success_rate"]:.1%}',
                "受け札確認率": f'{safety["goldfish"]["defense_seen_rate"]:.1%}',
                "推奨理由": "保存前足切り条件を通過し、実戦検証に回せる候補です。",
            }
        )

    return sorted(rows, key=lambda item: item["研究優先度"], reverse=True)[:limit]


def save_mana_research_cycle(
    db_path: Path,
    brief: dict[str, Any],
    candidates: list[dict[str, Any]],
    saved_rows: list[dict[str, Any]],
) -> int:
    """MANA研究サイクルのログを保存する。"""
    result = {
        "candidate_count": len(candidates),
        "saved_count": len(saved_rows),
        "top_candidates": [
            {
                "pattern_name": candidate.get("pattern_name", ""),
                "candidate_score": candidate.get("candidate_score", 0),
                "condition_score": candidate.get("condition_score", 0),
                "evaluation_score": candidate.get("evaluation_score", 0),
                "novelty_score": candidate.get("novelty_score", 0),
                "early_success_rate": candidate.get("goldfish", {}).get("early_success_rate"),
                "defense_seen_rate": candidate.get("goldfish", {}).get("defense_seen_rate"),
            }
            for candidate in candidates[:10]
        ],
        "saved_rows": saved_rows,
    }
    return save_research_cycle_log(db_path, brief, result)


def run_today_research_cycle(
    db_path: Path = DEFAULT_DB_PATH,
    format: str = "ND",
    deck_size: int = 40,
    seeds_per_pattern: int = 2,
    inspect_top_n: int = 10,
    save_top_n: int = 10,
    next_test_limit: int = 3,
    novelty_mode: bool = True,
    save_results: bool = True,
    save_log: bool = True,
) -> dict[str, Any]:
    brief = collect_mana_research_brief(db_path)
    recovery_mode = "未知性重視" if novelty_mode else "指定条件"
    auto_next_actions: list[str] = []
    exploration_attempts: list[dict[str, Any]] = []

    def run_attempt(label: str, attempt_seeds: int, attempt_inspect_top_n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        exploration = run_deck_exploration(
            db_path=db_path,
            seeds_per_pattern=attempt_seeds,
            deck_size=deck_size,
            format=format,
        )
        checked_candidates = run_candidate_goldfish_checks(exploration["candidates"])
        inspected = checked_candidates[:attempt_inspect_top_n]
        passed = filter_research_candidates(inspected, novelty_mode=novelty_mode)
        exploration_attempts.append(
            {
                "試行": label,
                "探索候補": len(exploration["candidates"]),
                "検査候補": len(inspected),
                "通過候補": len(passed),
                "各パターン試行数": attempt_seeds,
            }
        )
        return inspected, passed

    top_checked, passed_candidates = run_attempt("初回探索", seeds_per_pattern, inspect_top_n)
    if not passed_candidates:
        auto_next_actions.append("初回探索で保存基準を満たす候補が0件だったため、落選理由を見て自動再探索します。")
        retry_seeds = max(seeds_per_pattern + 2, 4)
        retry_inspect_top_n = max(inspect_top_n * 2, 20)
        top_checked, passed_candidates = run_attempt("自動再探索", retry_seeds, retry_inspect_top_n)
        recovery_mode = "自動再探索"

    if passed_candidates and save_results:
        auto_next_actions.append("保存基準を満たす候補が見つかったため、通過候補だけを保存します。")
    elif passed_candidates:
        auto_next_actions.append("保存基準を満たす候補が見つかりました。司令室では自動保存せず、候補として表示します。")
    else:
        recovery_mode = "仮説棄却"
        auto_next_actions.append("自動再探索でも通過候補が0件でした。保存せず、今回の仮説群は棄却します。")

    improvement_candidates = _build_improvement_candidates(top_checked, limit=3)
    rejected_rows = _build_rejected_rows(top_checked, novelty_mode=novelty_mode)

    saved_rows = []
    save_candidates = passed_candidates[:save_top_n]
    for rank, candidate in enumerate(save_candidates, start=1):
        request = candidate["request"]
        saved_id = 0
        if save_results:
            saved_id = save_generated_deck(
                deck_name=f"MANA今日の候補{rank}({getattr(request, 'format', format)}): {request.deck_name}",
                civilizations=request.civilizations,
                deck_type=request.deck_type,
                focus_tags=request.focus_tags,
                avoid_tags=request.avoid_tags,
                strategy_note=request.strategy_note
                + "\n\n"
                + candidate.get("research_filter_reason", "")
                + f"\n自動判定: {recovery_mode}",
                deck_cards=candidate["deck"],
                analysis=candidate["analysis"],
                evaluation=candidate["evaluation"],
                format=getattr(request, "format", "ND"),
                candidate_origin="tag_based",
                db_path=db_path,
            )
        saved_rows.append(
            {
                "保存ID": saved_id if save_results else "未保存",
                "順位": rank,
                "形式": getattr(request, "format", "ND"),
                "候補": candidate["pattern_name"],
                "足切り": candidate.get("research_filter_mode", "通常"),
                "自動判定": recovery_mode,
                "狙い目スコア": candidate["candidate_score"],
                "初動成功率": f'{candidate["goldfish"]["early_success_rate"]:.1%}',
                "受け札確認率": f'{candidate["goldfish"]["defense_seen_rate"]:.1%}',
            }
        )

    next_test_decks = select_next_test_decks(db_path, limit=next_test_limit, novelty_mode=novelty_mode)
    cycle_result = {
        "cycle_version": RESEARCH_CYCLE_VERSION,
        "explored_count": sum(attempt["探索候補"] for attempt in exploration_attempts),
        "inspected_count": sum(attempt["検査候補"] for attempt in exploration_attempts),
        "passed_count": len(passed_candidates),
        "saved_count": len(saved_rows) if save_results else 0,
        "saved_rows": saved_rows,
        "rejected_rows": rejected_rows,
        "auto_next_actions": auto_next_actions,
        "exploration_attempts": exploration_attempts,
        "recovery_mode": recovery_mode,
        "improvement_candidates": improvement_candidates,
        "next_test_decks": next_test_decks,
        "novelty_mode": novelty_mode,
        "save_results": save_results,
    }
    log_id = save_mana_research_cycle(db_path, brief, top_checked, saved_rows) if save_log else 0
    cycle_result["log_id"] = log_id
    return cycle_result


def save_research_cycle_log(
    db_path: Path,
    brief: dict[str, Any],
    result: dict[str, Any],
) -> int:
    """MANA研究サイクルの結果を保存する。"""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mana_research_cycle_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                research_status TEXT,
                card_count INTEGER,
                generated_deck_count INTEGER,
                next_actions_json TEXT,
                result_json TEXT
            )
            """
        )
        cur = conn.execute(
            """
            INSERT INTO mana_research_cycle_logs (
                created_at,
                research_status,
                card_count,
                generated_deck_count,
                next_actions_json,
                result_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                brief.get("research_status", ""),
                brief.get("dashboard", {}).get("card_stats", {}).get("card_count", 0),
                brief.get("generated_deck_count", 0),
                json.dumps(brief.get("next_research_actions", []), ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _top_generated_decks(decks: pd.DataFrame) -> list[dict[str, Any]]:
    if decks.empty:
        return []
    work = decks.copy()
    for column in ["condition_score", "evaluation_score", "civilization_match_rate"]:
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")
    sort_columns = [column for column in ["condition_score", "evaluation_score"] if column in work.columns]
    if sort_columns:
        work = work.sort_values(sort_columns, ascending=False, na_position="last")
    return work.head(5).to_dict("records")


def _weak_generated_decks(decks: pd.DataFrame) -> list[dict[str, Any]]:
    if decks.empty:
        return []
    work = decks.copy()
    for column in ["condition_score", "defense_count", "starter_count", "finisher_count", "average_cost"]:
        if column in work.columns:
            work[column] = pd.to_numeric(work[column], errors="coerce")

    weak = work[
        (work.get("condition_score", 100) < 75)
        | (work.get("starter_count", 99) < 8)
        | (work.get("defense_count", 99) < 6)
        | (work.get("finisher_count", 99) < 3)
    ]
    if weak.empty:
        return []
    return weak.sort_values("condition_score", ascending=True, na_position="last").head(5).to_dict("records")


def _research_status(dashboard: dict[str, Any], generated_decks: pd.DataFrame) -> str:
    card_stats = dashboard["card_stats"]
    research_stats = dashboard["research_stats"]
    if card_stats["card_count"] < 1000:
        return "カードDB整備優先"
    if len(generated_decks) == 0:
        return "探索開始待ち"
    if research_stats["match_log_count"] == 0:
        return "実戦ログ待ち"
    if dashboard["rework_candidates"]:
        return "改良優先"
    return "自律研究可能"


def _build_research_actions(
    dashboard: dict[str, Any],
    generated_decks: pd.DataFrame,
    top_generated: list[dict[str, Any]],
    weak_generated: list[dict[str, Any]],
    meta_summary: dict[str, Any] | None = None,
    combo_summary: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    card_stats = dashboard["card_stats"]
    research_stats = dashboard["research_stats"]

    actions.extend(_build_route_priority_actions())

    if card_stats["missing_tag_count"]:
        actions.append(
            {
                "優先度": "高",
                "アクション": "タグ未設定カードを補強する",
                "理由": f'{card_stats["missing_tag_count"]}枚のカードにタグがありません。',
                "次の画面": "CSV管理",
            }
        )
    else:
        actions.append(
            {
                "優先度": "高",
                "アクション": "効果構造解析を開始する",
                "理由": (
                    "カードDB5178枚のタグ空欄が0になり、タグベース探索の前提が整いました。"
                    "次は特殊勝利・ループ・退化・制約解除など、タグだけでは見落とす構造を扱います。"
                ),
                "次の画面": "効果構造解析",
            }
        )

    if len(generated_decks) == 0:
        actions.append(
            {
                "優先度": "高",
                "アクション": "自律探索で候補デッキを生成する",
                "理由": "保存済み生成デッキがまだありません。",
                "次の画面": "MANA研究室 / 自動デッキ探索",
            }
        )
    if not meta_summary or meta_summary.get("count", 0) == 0:
        actions.append(
            {
                "優先度": "高",
                "アクション": "環境デッキDBに現環境の主要デッキを登録する",
                "理由": "未知デッキ判定には、既知環境との比較対象が必要です。",
                "次の画面": "環境デッキ",
            }
        )
    if not combo_summary or combo_summary.get("count", 0) == 0:
        actions.append(
            {
                "優先度": "高",
                "アクション": "既知コンボDBに代表コンボを登録する",
                "理由": "未知シナジー探索には、既存コンボの構造分解が必要です。",
                "次の画面": "コンボ研究",
            }
        )
    if top_generated and not _has_route_ready_action(actions):
        best = top_generated[0]
        origin = best.get("candidate_origin", "tag_based")
        if origin == "route_based":
            actions.append(
                {
                    "優先度": "中",
                    "アクション": f'{best.get("deck_name", "route_based候補")} のroute再評価を確認する',
                    "理由": "route_based候補はcondition_scoreではなく、adjusted_route_score、成立ターン、必要サポートを優先して確認します。",
                    "次の画面": "MANA解析ブリーフ",
                }
            )
        else:
            actions.append(
                {
                    "優先度": "低",
                    "アクション": "tag_based候補の状態変換連鎖を確認する",
                    "理由": "tag_based候補は条件適合スコアが高くても、未知勝利ルートとしては状態変換連鎖と勝利条件到達の確認が必要です。",
                    "次の画面": "効果構造解析",
                }
            )

    if research_stats["match_log_count"] == 0:
        actions.append(
            {
                "優先度": "中",
                "アクション": "実戦ログを最低5件記録する",
                "理由": "勝率、弱点、改善候補の精度を上げるためです。",
                "次の画面": "対戦ログ",
            }
        )

    if weak_generated:
        weak = weak_generated[0]
        actions.append(
            {
                "優先度": "中",
                "アクション": f'{weak.get("deck_name", "低スコア候補")} を改良候補に回す',
                "理由": f'条件適合スコア {weak.get("condition_score", "-")} で不足が見えます。',
                "次の画面": "デッキ履歴 / デッキ生成",
            }
        )

    for action in dashboard["next_actions"][:2]:
        actions.append(
            {
                "優先度": "低",
                "アクション": action,
                "理由": "既存ダッシュボードからの継続タスクです。",
                "次の画面": "ダッシュボード",
            }
        )

    return _dedupe_actions(actions)[:8]


def _build_route_priority_actions() -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    try:
        from src.route_validation_brief import load_route_deck_validation_results

        validation_rows = load_route_deck_validation_results()
    except Exception:
        validation_rows = []

    ok_rows = [
        row
        for row in validation_rows
        if row.get("validation_verdict") == "検証OK" and _safe_int(row.get("warning_count"), 99) == 0
    ]
    if ok_rows:
        row = ok_rows[0]
        seed = row.get("route_seed_cards", "-")
        deck_name = row.get("deck_name", "route_seed展開デッキ")
        actions.append(
            {
                "優先度": "高",
                "アクション": f"{deck_name} を一人回しする",
                "理由": f"route_seed展開後の成立条件検証で warning_count 0 の検証OK候補です。seedは {seed} です。",
                "次の画面": "一人回しシミュレーション",
            }
        )

    try:
        from src.import_cards import DEFAULT_DB_PATH
        from src.route_candidate_evaluator import evaluate_saved_route_based_decks

        route_rows = evaluate_saved_route_based_decks(DEFAULT_DB_PATH)
    except Exception:
        route_rows = []

    route_rows = sorted(
        route_rows,
        key=lambda row: (
            0 if "loop_output_to_win" in str(row.get("missing_support_states") or "") else 1,
            -_safe_int(row.get("adjusted_route_score"), 0),
        ),
    )

    added_ready = False
    added_repair = False
    added_learning = False
    for row in route_rows:
        score = _safe_int(row.get("adjusted_route_score"), 0)
        deck_name = row.get("deck_name", "route_based候補")
        missing = row.get("missing_support_states") or "-"
        roles = row.get("required_support_roles") or "-"

        if score >= 51 and not added_ready:
            actions.append(
                {
                    "優先度": "高",
                    "アクション": f"{deck_name} を一人回しする",
                    "理由": f"adjusted_route_score {score} のroute_based候補です。必要サポート={roles}、missing_support_states={missing}。",
                    "次の画面": "一人回しシミュレーション",
                }
            )
            added_ready = True
        elif 21 <= score <= 50 and not added_repair:
            action = _route_repair_action_name(deck_name, row)
            actions.append(
                {
                    "優先度": "中",
                    "アクション": action,
                    "理由": f"adjusted_route_score {score}の研究候補です。missing_support_states={missing} を補う必要があります。required_support_roles={roles}。",
                    "次の画面": "効果構造解析" if "loop_output_to_win" in str(missing) else "コンボ研究",
                }
            )
            added_repair = True
        elif 0 <= score <= 20 and not added_learning:
            actions.append(
                {
                    "優先度": "低",
                    "アクション": f"{deck_name} を失敗例/構造学習用に回す",
                    "理由": f"adjusted_route_score {score} のため、現時点では一人回し候補にしません。必要マナ・成立ターン・不足状態を学習材料として扱います。",
                    "次の画面": "MANA解析ブリーフ",
                }
            )
            added_learning = True

    return actions


def _route_repair_action_name(deck_name: str, row: dict[str, Any]) -> str:
    missing = str(row.get("missing_support_states") or "")
    if "loop_output_to_win" in missing:
        return f"{deck_name} のループ出力を明確化する"
    if missing:
        return f"{deck_name} の不足状態を補完する"
    return f"{deck_name} の補助役割を追加する"


def _has_route_ready_action(actions: list[dict[str, str]]) -> bool:
    return any("route_seed" in action.get("理由", "") or "route_based" in action.get("理由", "") for action in actions)


def _dedupe_actions(actions: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for action in actions:
        key = (action.get("アクション", ""), action.get("次の画面", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(action)
    return result


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _quantity(card: dict[str, Any]) -> int:
    try:
        return int(card.get("quantity", 1))
    except Exception:
        return 1


def _split_tags(value: str) -> list[str]:
    return [tag.strip() for tag in str(value).split(";") if tag.strip()]


def _role_counts(deck: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"初動": 0, "受け札": 0, "フィニッシャー": 0, "除去": 0, "ドロー/リソース": 0}
    for card in deck:
        tags = set(_split_tags(card.get("tags", "")))
        quantity = _quantity(card)
        if tags.intersection({"初動", "低コスト", "マナ加速", "チャージャー"}):
            counts["初動"] += quantity
        if tags.intersection({"受け札", "S・トリガー", "G・ストライク", "逆転撃", "ブロッカー"}):
            counts["受け札"] += quantity
        if tags.intersection({"フィニッシャー", "打点"}):
            counts["フィニッシャー"] += quantity
        if tags.intersection({"除去", "バウンス", "パワー低下", "盤面処理"}):
            counts["除去"] += quantity
        if tags.intersection({"ドロー", "リソース", "サーチ候補"}):
            counts["ドロー/リソース"] += quantity
    return counts


def _average_cost(deck: list[dict[str, Any]]) -> float:
    total_cost = 0
    total_quantity = 0
    for card in deck:
        quantity = _quantity(card)
        try:
            cost = int(float(card.get("cost", 0)))
        except Exception:
            cost = 0
        total_cost += cost * quantity
        total_quantity += quantity
    return round(total_cost / total_quantity, 2) if total_quantity else 0.0


def _same_name_limit_ok(deck: list[dict[str, Any]]) -> bool:
    counts: dict[str, int] = {}
    for card in deck:
        name = str(card.get("name", ""))
        counts[name] = counts.get(name, 0) + _quantity(card)
    return all(count <= 4 for count in counts.values())


def _candidate_filter_reason(candidate: dict[str, Any]) -> str:
    goldfish = candidate.get("goldfish", {})
    return (
        f'適合 {candidate.get("condition_score", 0)} / '
        f'評価 {candidate.get("evaluation_score", 0)} / '
        f'未知性 {candidate.get("novelty_score", 0)} / '
        f'初動 {goldfish.get("early_success_rate", 0):.1%} / '
        f'受け {goldfish.get("defense_seen_rate", 0):.1%}'
    )


def _candidate_filter_failures(candidate: dict[str, Any], novelty_mode: bool = False) -> list[str]:
    goldfish = candidate.get("goldfish", {})
    condition_score = float(candidate.get("condition_score", 0))
    evaluation_score = float(candidate.get("evaluation_score", 0))
    novelty_score = float(candidate.get("novelty_score", 0))
    deck_size = int(candidate.get("deck_size") or sum(_quantity(card) for card in candidate.get("deck", [])))
    same_name_ok = bool(candidate.get("same_name_limit_ok", _same_name_limit_ok(candidate.get("deck", []))))

    failures = []
    if condition_score < 60:
        failures.append(f"適合{condition_score:g}<60")
    if evaluation_score < (25 if novelty_mode else 40):
        failures.append(f"評価{evaluation_score:g}不足")
    if float(candidate.get("candidate_score", 0)) < (85 if novelty_mode else 90):
        failures.append(f"狙い目{candidate.get('candidate_score', 0)}不足")
    if novelty_mode and novelty_score < 75:
        failures.append(f"未知性{novelty_score:g}<75")
    if goldfish.get("early_success_rate", 0) < (0.60 if novelty_mode else 0.65):
        failures.append(f"初動{goldfish.get('early_success_rate', 0):.1%}不足")
    if goldfish.get("defense_seen_rate", 0) < 0.45:
        failures.append(f"受け{goldfish.get('defense_seen_rate', 0):.1%}不足")
    if deck_size != 40:
        failures.append(f"{deck_size}枚")
    if not same_name_ok:
        failures.append("同名4枚制限違反")
    return failures


def _build_improvement_candidates(candidates: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    rows = []
    for candidate in candidates[:limit]:
        failures = _candidate_filter_failures(candidate, novelty_mode=True) or _candidate_filter_failures(candidate)
        rows.append(
            {
                "候補": candidate.get("pattern_name", ""),
                "狙い目": candidate.get("candidate_score", 0),
                "適合": candidate.get("condition_score", 0),
                "評価": candidate.get("evaluation_score", 0),
                "初動": f'{candidate.get("goldfish", {}).get("early_success_rate", 0):.1%}',
                "受け": f'{candidate.get("goldfish", {}).get("defense_seen_rate", 0):.1%}',
                "改良方針": _improvement_direction(candidate, failures),
            }
        )
    return rows


def _build_rejected_rows(candidates: list[dict[str, Any]], novelty_mode: bool = False) -> list[dict[str, Any]]:
    return [
        {
            "候補": candidate.get("pattern_name", ""),
            "狙い目": candidate.get("candidate_score", 0),
            "適合": candidate.get("condition_score", 0),
            "評価": candidate.get("evaluation_score", 0),
            "初動": f'{candidate.get("goldfish", {}).get("early_success_rate", 0):.1%}',
            "受け": f'{candidate.get("goldfish", {}).get("defense_seen_rate", 0):.1%}',
            "落選理由": " / ".join(_candidate_filter_failures(candidate, novelty_mode=novelty_mode)),
        }
        for candidate in candidates
        if _candidate_filter_failures(candidate, novelty_mode=novelty_mode)
    ]


def _improvement_direction(candidate: dict[str, Any], failures: list[str]) -> str:
    joined = " / ".join(failures)
    if "同名4枚制限違反" in joined:
        return "同名カードを4枚以内に整理し、役割が近い別名カードへ分散します。"
    if "初動" in joined:
        return "低コスト、初動、マナ加速タグのカードを優先して増やします。"
    if "受け" in joined:
        return "S・トリガー、受け札、除去を追加して防御確認率を上げます。"
    if "評価" in joined:
        return "役割枚数とコスト配分を整え、デッキ評価を底上げします。"
    if "未知性" in joined:
        return "コンボ、踏み倒し、墓地利用、ロックなどの研究タグを増やします。"
    if "狙い目" in joined:
        return "探索パターンの重視タグを増やし、候補スコアを上げます。"
    if candidate.get("average_cost", 0) and float(candidate.get("average_cost", 0)) > 5:
        return "高コストが多いため、軽い初動と中盤札へ差し替えます。"
    return "落選理由が小さい候補です。上位カードの枚数配分を調整して再検査します。"


def _untagged_importance(card: dict[str, Any]) -> int:
    score = 0
    try:
        cost = int(card.get("cost") or 0)
    except Exception:
        cost = 0
    text = str(card.get("text", ""))
    if cost <= 3:
        score += 20
    if cost >= 7:
        score += 15
    for keyword in ["S・トリガー", "G・ストライク", "破壊", "引", "マナ", "コストを支払わず", "進化"]:
        if keyword in text:
            score += 10
    return score


def _untagged_reason(card: dict[str, Any]) -> str:
    reasons = []
    try:
        cost = int(card.get("cost") or 0)
    except Exception:
        cost = 0
    if cost <= 3:
        reasons.append("低コストで採用判断に影響しやすい")
    if cost >= 7:
        reasons.append("フィニッシャー候補になり得る")
    text = str(card.get("text", ""))
    for keyword in ["S・トリガー", "G・ストライク", "破壊", "引", "マナ", "コストを支払わず", "進化"]:
        if keyword in text:
            reasons.append(f"`{keyword}` を含む")
    return " / ".join(reasons) if reasons else "タグ未設定のため確認対象"

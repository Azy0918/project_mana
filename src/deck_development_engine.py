"""デッキ開発エンジン (LLM思考プロセスの機械化).

「未開拓デッキを開発して」と頼まれたときにLLMが行う手順を
決定的なコードとして実装する:

  1. seed接続の実証 — タグ一致ではなくカードテキストを読み、
     実際に相互作用があるか (サーチ/ドロー/回収/コスト軽減/種族参照) を確認
  2. ターンプラン構築 — 1〜5ターン目の理想ムーブをカーブから組み立て、
     カーブ穴を検出
  3. 再現性の計算 — 超幾何分布でseed成立確率を見積もり、
     ドロー/サーチ補正を加味
  4. 弱点診断と修繕の反復 — validatorの警告を具体的なカード入替に翻訳し、
     再検証しながら警告が減らなくなるまで改善
  5. 開発ログ — 何をなぜ変えたかを人間が追える形で記録

route_deck_expander の展開結果 (expansion dict) を入力に取り、
改善済み expansion と開発ログを返す。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_DB_PATH
from src.route_deck_expander import (
    CardRow,
    _load_cards,
    _norm,
    _route_role_tags,
    _split_terms,
    analyze_expanded_deck_quality,
)
from src.route_deck_validator import validate_expanded_deck


# ---------------------------------------------------------------------------
# 1. seed接続の実証 (テキストレベル)
# ---------------------------------------------------------------------------

# 「AがBに触れる」ことを示すテキストパターン
ACCESS_PATTERNS = [
    (r"カードを(\d+|１|２|３|４)枚引", "draw"),
    (r"山札.{0,12}(見て|探し|表向き)", "search"),
    (r"手札に(加え|戻)", "to_hand"),
    (r"墓地から.{0,12}(手札|バトルゾーン|マナ)", "recover"),
    (r"コストを.{0,6}(少なく|支払わずに)", "cost_cheat"),
    (r"バトルゾーンに出(す|る|して)", "put_into_play"),
    (r"マナゾーンに(置く|加え)", "ramp"),
]

SYNERGY_KEYWORD_GROUPS = [
    {"呪文", "唱え"},
    {"墓地", "捨て"},
    {"シールド", "ブレイク"},
    {"進化", "クリーチャー"},
    {"マナ", "チャージ"},
    {"ブロッカー", "攻撃"},
    {"ドラゴン"},
    {"アンタップ", "タップ"},
]


def _text_access_signals(text: str) -> set[str]:
    signals: set[str] = set()
    for pattern, label in ACCESS_PATTERNS:
        if re.search(pattern, text):
            signals.add(label)
    return signals


def _references_card(source: CardRow, target: CardRow) -> list[str]:
    """source のテキストが target に実際に触れられる根拠を列挙する。"""
    reasons: list[str] = []
    text = source.text or ""

    # 名指し参照 (最も強い接続)
    core = re.sub(r"[《》]", "", target.name).split("/")[0].strip()
    if core and len(core) >= 3 and core in text:
        reasons.append(f"テキストが「{core}」を名指し参照")

    # 種族/カードタイプ参照
    for race in _split_terms(getattr(target, "card_type", "")):
        if race and len(race) >= 2 and race in text:
            reasons.append(f"種族/種別「{race}」を参照")
            break

    # アクセス手段 (サーチ/ドロー/回収) がありコスト帯が繋がる
    signals = _text_access_signals(text)
    if signals & {"search", "draw", "to_hand", "recover"}:
        reasons.append(f"手札供給手段あり ({'/'.join(sorted(signals))})")
    if "cost_cheat" in signals and target.cost >= source.cost:
        reasons.append("コスト踏み倒し/軽減で重い相方に接続")
    if "ramp" in signals and target.cost > source.cost:
        reasons.append("マナ加速で相方のコスト帯へ接続")

    return reasons


def verify_seed_interactions(seed_cards: list[CardRow]) -> dict[str, Any]:
    """seedカード群の実接続を検証する。

    タグの偶然一致ではなく、テキストと文明・コスト帯から
    「本当に同じデッキで機能するか」を判定する。
    """
    pair_results: list[dict[str, Any]] = []
    connected_pairs = 0
    total_pairs = 0

    for i, a in enumerate(seed_cards):
        for b in seed_cards[i + 1:]:
            total_pairs += 1
            reasons = _references_card(a, b) + [
                f"(逆方向) {r}" for r in _references_card(b, a)
            ]

            # 共有キーワードグループ (弱い接続)
            blob = f"{a.text};{b.text}"
            shared_groups = [
                "/".join(sorted(group))
                for group in SYNERGY_KEYWORD_GROUPS
                if all(any(kw in card.text for kw in group) for card in (a, b))
            ]
            if shared_groups and not reasons:
                reasons.append(f"共通メカニズム: {', '.join(shared_groups[:2])}")

            civ_overlap = bool(a.civ_set & b.civ_set) or "無色" in (a.civ_set | b.civ_set)
            connected = bool(reasons) and civ_overlap
            if connected:
                connected_pairs += 1
            pair_results.append(
                {
                    "pair": f"{a.name} × {b.name}",
                    "connected": connected,
                    "civ_compatible": civ_overlap,
                    "reasons": reasons or ["実接続の根拠が見つからない (タグ偶然一致の疑い)"],
                }
            )

    ratio = connected_pairs / total_pairs if total_pairs else 0.0
    return {
        "connected_pairs": connected_pairs,
        "total_pairs": total_pairs,
        "connection_ratio": round(ratio, 2),
        "verdict": (
            "接続実証OK" if ratio >= 0.5
            else "一部接続のみ" if ratio > 0
            else "接続実証できず"
        ),
        "pairs": pair_results,
    }


# ---------------------------------------------------------------------------
# 2. ターンプラン構築
# ---------------------------------------------------------------------------

def build_turn_plan(deck_rows: list[dict[str, Any]], max_turn: int = 6) -> dict[str, Any]:
    """マナカーブから理想ターンプランを組み、カーブ穴を検出する。"""
    by_cost: dict[int, list[dict[str, Any]]] = {}
    for row in deck_rows:
        cost = int(row.get("cost") or 0)
        by_cost.setdefault(cost, []).append(row)

    plan: list[dict[str, Any]] = []
    curve_holes: list[int] = []
    for turn in range(1, max_turn + 1):
        plays = by_cost.get(turn, [])
        plays.sort(key=lambda r: ("seed" not in str(r.get("role", "")), -int(r.get("count") or 0)))
        best = plays[0] if plays else None
        count_at_cost = sum(int(r.get("count") or 0) for r in plays)
        if turn <= 3 and count_at_cost < 4:
            curve_holes.append(turn)
        plan.append(
            {
                "turn": turn,
                "ideal_play": best.get("card_name") if best else None,
                "role": best.get("role") if best else None,
                "options_at_cost": count_at_cost,
            }
        )

    seed_costs = sorted(
        int(r.get("cost") or 0)
        for r in deck_rows
        if "seed" in str(r.get("role", ""))
    )
    route_online_turn = seed_costs[-1] if seed_costs else None

    warnings = []
    for hole in curve_holes:
        warnings.append(f"{hole}ターン目の動きが薄い (コスト{hole}のカードが4枚未満)")
    if route_online_turn and route_online_turn >= 6:
        warnings.append(f"ルート成立が{route_online_turn}ターン目以降で環境速度に遅れる可能性")

    return {
        "plan": plan,
        "curve_holes": curve_holes,
        "route_online_turn": route_online_turn,
        "turn_plan_warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. 再現性の計算 (超幾何分布)
# ---------------------------------------------------------------------------

def _prob_at_least_one(deck_size: int, copies: int, draws: int) -> float:
    """draws枚見た中に対象が1枚以上ある確率。"""
    if copies <= 0 or deck_size <= 0 or draws <= 0:
        return 0.0
    draws = min(draws, deck_size)
    none = math.comb(deck_size - copies, draws) / math.comb(deck_size, draws)
    return 1.0 - none


def estimate_consistency(deck_rows: list[dict[str, Any]], by_turn: int = 4) -> dict[str, Any]:
    """seed各パーツをターンNまでに引き込める確率を見積もる。

    初手5枚 + 毎ターン1ドロー + デッキ内のドロー/サーチ実質枚数を加味。
    """
    deck_size = sum(int(r.get("count") or 0) for r in deck_rows)
    extra_draw = 0
    for row in deck_rows:
        tags = str(row.get("tags") or "")
        if "ドロー" in tags or "サーチ候補" in tags:
            extra_draw += int(row.get("count") or 0)
    # ドロソ1枚 ≒ 0.4枚分の追加視界という保守的換算
    effective_draws = 5 + by_turn + int(extra_draw * 0.4)

    piece_probs: list[dict[str, Any]] = []
    all_prob = 1.0
    for row in deck_rows:
        if "seed" not in str(row.get("role", "")):
            continue
        p = _prob_at_least_one(deck_size, int(row.get("count") or 0), effective_draws)
        piece_probs.append(
            {
                "card_name": row.get("card_name"),
                "copies": int(row.get("count") or 0),
                f"prob_by_turn_{by_turn}": round(p, 3),
            }
        )
        all_prob *= p

    warnings = []
    if piece_probs and all_prob < 0.35:
        warnings.append(
            f"ターン{by_turn}までにseed全部が揃う確率が低い ({all_prob:.0%})。"
            "サーチ/ドローの増量が必要"
        )

    return {
        "deck_size": deck_size,
        "effective_draws": effective_draws,
        "draw_search_count": extra_draw,
        "seed_pieces": piece_probs,
        "all_pieces_prob": round(all_prob, 3),
        "consistency_warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 4. 弱点診断と修繕の反復
# ---------------------------------------------------------------------------

# validator警告 -> 補強すべきrole の翻訳表
WARNING_TO_ROLE = [
    ("受け札", "defense"),
    ("防御が薄く", "defense"),
    ("初動/リソース", "starter"),
    ("初動", "starter"),
    ("リソースが少なく", "resource"),
    ("除去/盤面処理", "removal"),
    ("勝ち切り手段", "payoff"),
    ("到達する初動", "starter"),
]


def _cut_priority(row: dict[str, Any]) -> tuple:
    """入替時に削る優先度。seedは絶対に削らない。"""
    role = str(row.get("role") or "")
    is_seed = "seed" in role
    is_flex = "flex" in role
    return (
        is_seed,                       # seedは最後 (実質削らない)
        not is_flex,                   # flexを最初に削る
        -int(row.get("cost") or 0),    # 高コストから削る
    )


def _find_reinforcement(
    all_cards: list[CardRow],
    role: str,
    route_type: str,
    target_civs: set[str],
    existing_names: set[str],
) -> CardRow | None:
    """指定roleを補強する低リスクカードを1種選ぶ。"""
    role_tags = _route_role_tags(route_type).get(role, [])
    best: tuple[int, CardRow] | None = None
    for card in all_cards:
        if _norm(card.name) in existing_names:
            continue
        if card.cost <= 0 or card.cost > 5:
            continue
        civs = {c for c in card.civ_set if c != "無色"}
        if target_civs and civs and not (civs & target_civs):
            continue
        blob = f"{card.name};{card.tags};{card.text}"
        matched = sum(1 for tag in role_tags if tag in blob)
        if matched <= 0:
            continue
        score = matched * 10 + max(0, 6 - card.cost)
        if best is None or score > best[0]:
            best = (score, card)
    return best[1] if best else None


def diagnose_and_repair(
    expansion: dict[str, Any],
    all_cards: list[CardRow],
    max_iterations: int = 4,
) -> tuple[dict[str, Any], list[str]]:
    """検証警告を具体的なカード入替に翻訳し、改善が止まるまで反復する。"""
    dev_log: list[str] = []
    route_type = str(expansion.get("route_type") or "lock_confirmed_win")
    target_civs = {
        c for c in str(expansion.get("target_civilizations") or "").split("/") if c
    }

    current = dict(expansion)
    validation = validate_expanded_deck(current)
    best_warnings = int(validation.get("warning_count") or 0)
    dev_log.append(f"初期状態: {validation.get('validation_verdict')} / 警告{best_warnings}件")

    for iteration in range(1, max_iterations + 1):
        warnings = validation.get("warnings") or []
        # 警告から補強roleを決める (最初に翻訳できたもの)
        reinforce_role = None
        matched_warning = None
        for warning in warnings:
            for keyword, role in WARNING_TO_ROLE:
                if keyword in warning:
                    reinforce_role = role
                    matched_warning = warning
                    break
            if reinforce_role:
                break
        if not reinforce_role:
            dev_log.append(f"反復{iteration}: 入替に翻訳できる警告なし。終了")
            break

        deck_rows = [dict(r) for r in current.get("deck_rows", [])]
        existing = {_norm(str(r.get("card_name") or "")) for r in deck_rows}
        newcomer = _find_reinforcement(all_cards, reinforce_role, route_type, target_civs, existing)
        if newcomer is None:
            dev_log.append(f"反復{iteration}: {reinforce_role}補強カードが見つからない。終了")
            break

        # 削るカードを選ぶ (seed以外・flex/高コスト優先)
        deck_rows.sort(key=_cut_priority)
        cut_row = None
        for row in deck_rows:
            if "seed" in str(row.get("role") or ""):
                continue
            cut_row = row
            break
        if cut_row is None:
            dev_log.append(f"反復{iteration}: 削れるカードがない。終了")
            break

        add_copies = min(3, int(cut_row.get("count") or 1))
        remaining = int(cut_row.get("count") or 0) - add_copies
        if remaining > 0:
            cut_row["count"] = remaining
        else:
            deck_rows.remove(cut_row)
        deck_rows.append(
            {
                "count": add_copies,
                "card_name": newcomer.name,
                "civilization": newcomer.civilization,
                "cost": newcomer.cost,
                "card_type": newcomer.card_type,
                "tags": newcomer.tags,
                "role": reinforce_role,
            }
        )

        candidate = dict(current)
        candidate["deck_rows"] = deck_rows
        quality = analyze_expanded_deck_quality(deck_rows, target_civs)
        candidate.update(
            {
                "deck_size": sum(int(r.get("count") or 0) for r in deck_rows),
                "average_cost": quality["average_cost"],
                "deck_quality_warnings": quality["deck_quality_warnings"],
            }
        )
        new_validation = validate_expanded_deck(candidate)
        new_warnings = int(new_validation.get("warning_count") or 0)

        if new_warnings < best_warnings:
            dev_log.append(
                f"反復{iteration}: 「{matched_warning}」に対応 — "
                f"{cut_row.get('card_name')} {add_copies}枚 → {newcomer.name} ({reinforce_role})。"
                f"警告 {best_warnings} → {new_warnings}件"
            )
            current = candidate
            validation = new_validation
            best_warnings = new_warnings
        else:
            dev_log.append(
                f"反復{iteration}: {newcomer.name} 投入を試行したが警告が減らず "
                f"({best_warnings} → {new_warnings})。変更を破棄して終了"
            )
            break

    current["final_validation"] = validation
    return current, dev_log


# ---------------------------------------------------------------------------
# 5. 統合: develop_unexplored_deck
# ---------------------------------------------------------------------------

def develop_unexplored_deck(
    expansion: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
    max_repair_iterations: int = 4,
) -> dict[str, Any]:
    """expansion (route_deck_expanderの出力) をLLM式の手順で開発する。

    Returns: {
        "expansion": 改善済みexpansion,
        "seed_interaction": 接続実証結果,
        "turn_plan": ターンプラン,
        "consistency": 再現性見積もり,
        "final_validation": 最終検証,
        "development_log": 開発ログ,
    }
    """
    all_cards = _load_cards(db_path)
    dev_log: list[str] = []

    # 1. seed接続の実証
    seed_names = _split_terms(str(expansion.get("route_seed_cards", "")).replace(" / ", ";"))
    seed_cards = [c for c in all_cards if any(_norm(n) == _norm(c.name) for n in seed_names)]
    interaction = verify_seed_interactions(seed_cards)
    dev_log.append(
        f"seed接続実証: {interaction['verdict']} "
        f"({interaction['connected_pairs']}/{interaction['total_pairs']}ペア接続)"
    )

    # 2. 弱点診断と修繕の反復
    improved, repair_log = diagnose_and_repair(
        expansion, all_cards, max_iterations=max_repair_iterations
    )
    dev_log.extend(repair_log)

    # 3. 改善後デッキでターンプラン / 再現性
    deck_rows = improved.get("deck_rows", [])
    turn_plan = build_turn_plan(deck_rows)
    consistency = estimate_consistency(deck_rows)
    dev_log.extend(turn_plan.get("turn_plan_warnings", []))
    dev_log.extend(consistency.get("consistency_warnings", []))
    if consistency.get("seed_pieces"):
        dev_log.append(f"seed成立確率(T4): {consistency['all_pieces_prob']:.0%}")

    final_validation = improved.pop("final_validation", None) or validate_expanded_deck(improved)

    # seed接続が実証できないデッキは開発判定を格下げする
    development_verdict = final_validation.get("validation_verdict", "棄却候補")
    if interaction["verdict"] == "接続実証できず" and development_verdict == "検証OK":
        development_verdict = "要修正"
        dev_log.append("seed接続が実証できないため、判定を要修正へ格下げ")

    return {
        "expansion": improved,
        "seed_interaction": interaction,
        "turn_plan": turn_plan,
        "consistency": consistency,
        "final_validation": final_validation,
        "development_verdict": development_verdict,
        "development_log": dev_log,
    }


def development_log_to_note(result: dict[str, Any]) -> str:
    """開発結果をstrategy_note向けの文章にまとめる。"""
    lines = ["deck_development_engine v1 開発ログ:"]
    lines.extend(f"- {entry}" for entry in result.get("development_log", []))
    validation = result.get("final_validation") or {}
    lines.append(
        f"- 最終判定: {result.get('development_verdict', '-')} "
        f"(警告{validation.get('warning_count', '-')}件)"
    )
    return "\n".join(lines)

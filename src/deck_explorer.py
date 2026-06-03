from __future__ import annotations

from pathlib import Path
from collections import Counter
from typing import Any

from src.deck_builder import build_deck_for_request
from src.deck_candidate_scorer import score_deck_candidate
from src.deck_condition_analyzer import analyze_deck_condition
from src.deck_generation_request import DeckGenerationRequest
from src.evaluate_deck import evaluate_deck
from src.search_cards import DEFAULT_DB_PATH


EXPLORATION_PATTERNS = [
    {
        "name": "水自然コンボランプ",
        "civilizations": ["水", "自然"],
        "deck_type": "コンボ",
        "focus_tags": ["ドロー", "マナ加速", "コンボ", "踏み倒し", "フィニッシャー"],
        "avoid_tags": ["速攻", "ハンデス"],
        "strategy_note": "自然でマナを伸ばし、水で手札を整え、踏み倒しや大型で勝つ。",
    },
    {
        "name": "闇自然墓地マナ利用",
        "civilizations": ["闇", "自然"],
        "deck_type": "中速",
        "focus_tags": ["墓地利用", "マナ加速", "墓地回収", "除去", "フィニッシャー"],
        "avoid_tags": ["速攻"],
        "strategy_note": "墓地とマナを両方使い、粘り強く中盤以降に勝つ。",
    },
    {
        "name": "光闇自然耐久ロック",
        "civilizations": ["光", "闇", "自然"],
        "deck_type": "コントロール",
        "focus_tags": ["マナ加速", "受け札", "ハンデス", "ロック", "フィニッシャー"],
        "avoid_tags": ["速攻"],
        "strategy_note": "守りながらマナを伸ばし、ハンデスとロックで相手を縛る。",
    },
    {
        "name": "火水テンポ呪文ビート",
        "civilizations": ["火", "水"],
        "deck_type": "テンポ",
        "focus_tags": ["ドロー", "軽量除去", "速攻", "テンポ", "フィニッシュ補助"],
        "avoid_tags": ["大型", "ランプ"],
        "strategy_note": "水で手札を維持し、火の除去と速攻でテンポよく攻める。",
    },
    {
        "name": "水闇火墓地コントロール",
        "civilizations": ["水", "闇", "火"],
        "deck_type": "コントロール",
        "focus_tags": ["ドロー", "ハンデス", "除去", "墓地利用", "フィニッシャー"],
        "avoid_tags": ["自然", "光自然"],
        "strategy_note": "ハンデスと除去で妨害し、墓地利用フィニッシャーで勝つ。",
    },
    {
        "name": "光水進化テンポ",
        "civilizations": ["光", "水"],
        "deck_type": "進化",
        "focus_tags": ["進化", "進化元", "ドロー", "受け札", "テンポ"],
        "avoid_tags": ["大型", "墓地利用"],
        "strategy_note": "軽い進化元とドローで盤面を維持し、進化でテンポを取る。",
    },
    {
        "name": "火自然速攻進化",
        "civilizations": ["火", "自然"],
        "deck_type": "速攻",
        "focus_tags": ["速攻", "低コスト", "進化", "進化元", "フィニッシュ補助"],
        "avoid_tags": ["耐久", "大型"],
        "strategy_note": "低コストを並べ、進化と打点補助で早い決着を狙う。",
    },
    {
        "name": "水光受けコントロール",
        "civilizations": ["水", "光"],
        "deck_type": "耐久",
        "focus_tags": ["受け札", "S・トリガー", "ドロー", "ロック", "フィニッシャー"],
        "avoid_tags": ["速攻", "墓地利用"],
        "strategy_note": "受け札とドローで耐え、ロックや大型で安全に勝つ。",
    },
    {
        "name": "闇火ハンデス除去ビート",
        "civilizations": ["闇", "火"],
        "deck_type": "中速",
        "focus_tags": ["ハンデス", "除去", "軽量除去", "速攻", "フィニッシャー"],
        "avoid_tags": ["ランプ", "耐久"],
        "strategy_note": "手札と盤面を削りながら、中速の打点で押し込む。",
    },
    {
        "name": "五文明多色グッドスタッフ",
        "civilizations": ["自然", "水", "闇", "火", "光"],
        "deck_type": "ランプ",
        "focus_tags": ["多色", "マナ加速", "受け札", "除去", "フィニッシャー"],
        "avoid_tags": ["速攻"],
        "strategy_note": "多色のカードパワーを活かし、マナ加速から広い対応力で勝つ。",
    },
]


def run_deck_exploration(
    db_path: Path = DEFAULT_DB_PATH,
    seeds_per_pattern: int = 3,
    deck_size: int = 40,
    format: str = "ND",
) -> dict[str, Any]:
    candidates = []
    for pattern_index, pattern in enumerate(EXPLORATION_PATTERNS, start=1):
        request = _request_from_pattern(pattern, deck_size, format=format)
        for seed_offset in range(seeds_per_pattern):
            seed = pattern_index * 100 + seed_offset
            deck = build_deck_for_request(request, db_path, seed=seed)
            analysis = analyze_deck_condition(
                deck_cards=deck,
                civilizations=request.civilizations,
                focus_tags=request.focus_tags,
                avoid_tags=request.avoid_tags,
                target_starter_count=round(deck_size * request.early_ratio / 100),
                target_defense_count=round(deck_size * request.defense_ratio / 100),
                target_finisher_count=round(deck_size * request.finisher_ratio / 100),
            )
            evaluation = evaluate_deck(deck)
            score = score_deck_candidate(evaluation, analysis, deck)
            candidate_comments = _candidate_comments(request, deck, analysis, score)
            candidates.append(
                {
                    "pattern_name": pattern["name"],
                    "seed": seed,
                    "request": request,
                    "deck": deck,
                    "analysis": analysis,
                    "evaluation": evaluation,
                    **score,
                    "starter_count": analysis.starter_count,
                    "defense_count": analysis.defense_count,
                    "finisher_count": analysis.finisher_count,
                    "removal_count": analysis.removal_count,
                    "draw_count": analysis.draw_count,
                    "average_cost": analysis.average_cost,
                    "warnings": analysis.warnings,
                    **candidate_comments,
                }
            )

    candidates = sorted(candidates, key=lambda item: item["candidate_score"], reverse=True)
    return {
        "patterns": EXPLORATION_PATTERNS,
        "candidates": candidates,
        "summary_rows": [_summary_row(candidate) for candidate in candidates],
    }


def _request_from_pattern(pattern: dict[str, Any], deck_size: int, format: str = "ND") -> DeckGenerationRequest:
    return DeckGenerationRequest(
        deck_name=pattern["name"],
        format=format or pattern.get("format", "ND"),
        civilizations=list(pattern["civilizations"]),
        deck_type=pattern["deck_type"],
        focus_tags=list(pattern["focus_tags"]),
        avoid_tags=list(pattern["avoid_tags"]),
        strategy_note=pattern["strategy_note"],
        deck_size=deck_size,
        early_ratio=30,
        defense_ratio=30,
        finisher_ratio=20,
    )


def _summary_row(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "候補": candidate["pattern_name"],
        "形式": getattr(candidate["request"], "format", "ND"),
        "seed": candidate["seed"],
        "候補スコア": candidate["candidate_score"],
        "評価": candidate["evaluation_score"],
        "適合": candidate["condition_score"],
        "未知性": candidate["novelty_score"],
        "メタ": candidate["meta_score"],
        "初動": candidate["starter_count"],
        "受け札": candidate["defense_count"],
        "フィニッシャー": candidate["finisher_count"],
        "除去": candidate["removal_count"],
        "ドロー": candidate["draw_count"],
        "平均コスト": candidate["average_cost"],
        "警告数": len(candidate["warnings"]),
        "狙い目理由": " / ".join(candidate["why_good"][:2]),
    }


def _candidate_comments(
    request: DeckGenerationRequest,
    deck: list[dict[str, Any]],
    analysis: Any,
    score: dict[str, Any],
) -> dict[str, list[str] | str]:
    tag_counts = _deck_tag_counts(deck)
    top_tags = [tag for tag, _ in tag_counts.most_common(8)]
    why_good = _build_why_good(request, analysis, score, tag_counts, top_tags)
    weak_points: list[str] = []
    adjustment_ideas: list[str] = []

    if analysis.warnings:
        weak_points.extend(analysis.warnings[:3])
    if analysis.starter_count < 8:
        weak_points.append("初動が少ないため、序盤の安定性に不安があります。")
    if analysis.defense_count < 8:
        weak_points.append("受け札が薄く、速いデッキに押し切られる可能性があります。")
    if analysis.finisher_count < 4:
        weak_points.append("フィニッシャーが少なく、決定力不足になりやすいです。")
    if analysis.average_cost >= 5:
        weak_points.append("平均コストが高く、手札事故の確認が必要です。")
    if not weak_points:
        weak_points.append("大きな不足は少なめです。実戦では同名枚数と序盤事故を確認してください。")

    focus = set(request.focus_tags)
    if "受け札" in focus or "S・トリガー" in focus or analysis.defense_count >= 8:
        first_matchup = "速攻・ビートダウン相手に受け性能を確認"
    elif "ハンデス" in focus or "ロック" in focus:
        first_matchup = "コンボ・コントロール相手に妨害の刺さり方を確認"
    elif "墓地利用" in focus:
        first_matchup = "中速・除去コントロール相手に継戦能力を確認"
    elif "速攻" in focus or request.deck_type in {"速攻", "テンポ"}:
        first_matchup = "ランプ・コントロール相手に押し切れるか確認"
    else:
        first_matchup = "中速デッキ相手に基本速度と安定性を確認"

    if analysis.starter_count < 8:
        adjustment_ideas.append("初動またはマナ加速タグのカードを増やす。")
    if analysis.defense_count < 8:
        adjustment_ideas.append("受け札やS・トリガーを追加する。")
    if analysis.finisher_count < 4:
        adjustment_ideas.append("フィニッシャーを2〜4枚増やす。")
    if analysis.draw_count < 6:
        adjustment_ideas.append("ドロー・リソース札を増やして再現性を上げる。")
    if score["shortage_penalty"] > 0:
        adjustment_ideas.append("初動、受け札、フィニッシャーの不足役割を優先して入れ替える。")
    if not adjustment_ideas:
        adjustment_ideas.append("上位カードの同名枚数を調整し、苦手対面に合わせて除去か受け札を差し替える。")

    return {
        "why_good": why_good,
        "weak_points": weak_points,
        "first_matchup": first_matchup,
        "adjustment_ideas": adjustment_ideas,
    }


def _deck_tag_counts(deck: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for card in deck:
        try:
            quantity = int(card.get("quantity", 1))
        except Exception:
            quantity = 1
        for tag in str(card.get("tags", "")).split(";"):
            tag = tag.strip()
            if tag:
                counts[tag] += quantity
    return counts


def _build_why_good(
    request: DeckGenerationRequest,
    analysis: Any,
    score: dict[str, Any],
    tag_counts: Counter[str],
    top_tags: list[str],
) -> list[str]:
    reasons: list[str] = []
    deck_type = request.deck_type

    if deck_type in {"ランプ", "コンボ"}:
        ramp = tag_counts.get("マナ加速", 0) + tag_counts.get("チャージャー", 0)
        draw = tag_counts.get("ドロー", 0) + tag_counts.get("リソース", 0)
        cheat = tag_counts.get("踏み倒し", 0) + tag_counts.get("メクレイド", 0)
        if ramp or draw or cheat:
            reasons.append(f"{deck_type}軸として、マナ加速{ramp}枚・ドロー/リソース{draw}枚・踏み倒し系{cheat}枚があり、展開の筋が見えます。")

    if deck_type in {"コントロール", "耐久"}:
        defense = analysis.defense_count
        removal = analysis.removal_count
        lock = tag_counts.get("ロック", 0) + tag_counts.get("呪文ロック", 0) + tag_counts.get("攻撃制限", 0)
        reasons.append(f"{deck_type}軸として、受け札{defense}枚・除去{removal}枚・ロック/制限系{lock}枚で相手の動きを遅らせやすいです。")

    if deck_type in {"速攻", "テンポ", "中速"}:
        low = tag_counts.get("低コスト", 0)
        speed = tag_counts.get("速攻", 0)
        removal = analysis.removal_count
        reasons.append(f"{deck_type}軸として、低コスト{low}枚・速攻札{speed}枚・除去{removal}枚があり、序盤から主導権を取りに行けます。")

    if deck_type == "進化":
        evolution = tag_counts.get("進化", 0)
        source_like = tag_counts.get("低コスト", 0) + tag_counts.get("進化元", 0)
        reasons.append(f"進化軸として、進化関連{evolution}枚と進化元候補{source_like}枚があり、盤面から進化へつなげやすいです。")

    focus_hits = [(tag, tag_counts.get(tag, 0)) for tag in request.focus_tags if tag_counts.get(tag, 0)]
    if focus_hits:
        best_focus = sorted(focus_hits, key=lambda item: item[1], reverse=True)[:3]
        reasons.append("重視タグでは " + " / ".join(f"{tag}{count}枚" for tag, count in best_focus) + " が厚く出ています。")

    if analysis.starter_count >= 8 and analysis.defense_count >= 6:
        reasons.append(f"初動{analysis.starter_count}枚と受け札{analysis.defense_count}枚があり、試験デッキとして最低限の安定性があります。")
    elif analysis.starter_count >= 8:
        reasons.append(f"初動{analysis.starter_count}枚で、動き出しの再現性を検証しやすいです。")

    if score["novelty_score"] >= 70:
        reasons.append(f"未知性スコア{score['novelty_score']:.0f}で、既存候補と違う構成を試す価値があります。")

    if top_tags:
        reasons.append("デッキの色は " + " / ".join(top_tags[:4]) + " に寄っており、狙いが読み取りやすいです。")

    if not reasons:
        reasons.append(f"{request.deck_name} は候補スコア{score['candidate_score']}で、比較用の初回検証候補になります。")

    return _dedupe_keep_order(reasons)[:4]


def _dedupe_keep_order(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

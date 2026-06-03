from __future__ import annotations

from pathlib import Path
from typing import Any

from src.deck_explorer import run_deck_exploration
from src.generated_deck_store import save_generated_deck
from src.search_cards import DEFAULT_DB_PATH


def auto_generate_and_save_decks(
    db_path: Path = DEFAULT_DB_PATH,
    seeds_per_pattern: int = 2,
    deck_size: int = 40,
    save_top_n: int = 5,
    minimum_score: float = 0,
    format: str = "ND",
) -> dict[str, Any]:
    exploration = run_deck_exploration(
        db_path=db_path,
        seeds_per_pattern=seeds_per_pattern,
        deck_size=deck_size,
        format=format,
    )
    selected_candidates = [
        candidate
        for candidate in exploration["candidates"]
        if float(candidate["candidate_score"]) >= minimum_score
    ][:save_top_n]

    saved_rows = []
    for rank, candidate in enumerate(selected_candidates, start=1):
        request = candidate["request"]
        saved_id = save_generated_deck(
            deck_name=f"自動探索{rank}: {request.deck_name}",
            civilizations=request.civilizations,
            deck_type=request.deck_type,
            focus_tags=request.focus_tags,
            avoid_tags=request.avoid_tags,
            strategy_note=_build_strategy_note(candidate),
            deck_cards=candidate["deck"],
            analysis=candidate["analysis"],
            evaluation=candidate["evaluation"],
            format=getattr(request, "format", "ND"),
            candidate_origin="tag_based",
            db_path=db_path,
        )
        saved_rows.append(
            {
                "保存ID": saved_id,
                "順位": rank,
                "形式": getattr(request, "format", "ND"),
                "候補": candidate["pattern_name"],
                "seed": candidate["seed"],
                "狙い目スコア": candidate["candidate_score"],
                "条件適合": candidate["condition_score"],
                "評価": candidate["evaluation_score"],
                "最初に試す対面": candidate["first_matchup"],
            }
        )

    return {
        "exploration": exploration,
        "saved_rows": saved_rows,
    }


def _build_strategy_note(candidate: dict[str, Any]) -> str:
    request = candidate["request"]
    lines = [
        request.strategy_note,
        "",
        "自動探索メモ:",
        f"狙い目スコア: {candidate['candidate_score']}",
        f"最初に試す対面: {candidate['first_matchup']}",
        "なぜ狙い目か:",
    ]
    lines.extend(f"- {item}" for item in candidate.get("why_good", []))
    lines.append("弱そうな点:")
    lines.extend(f"- {item}" for item in candidate.get("weak_points", []))
    lines.append("調整候補:")
    lines.extend(f"- {item}" for item in candidate.get("adjustment_ideas", []))
    return "\n".join(lines)

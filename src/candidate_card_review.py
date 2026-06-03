from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_REPORTS = [
    Path("data/reports/route_seed_candidates.csv"),
    Path("data/reports/expanded_route_decks/expanded_route_decks.md"),
    Path("data/reports/expanded_route_decks/route_deck_validation.md"),
]

DEFAULT_OUT = Path("data/reports/candidate_card_review.csv")


def _split_seed_cards(value: str) -> list[str]:
    return [x.strip() for x in str(value or "").split("/") if x.strip()]


def _read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _extract_from_route_seed_csv(path: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    for row in _read_csv(path):
        deck_name = row.get("deck_name", "")
        for card in _split_seed_cards(row.get("route_seed_cards", "")):
            found[card].add(f"seed:{deck_name}")
    return found


def _extract_from_expanded_md(path: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        return found

    text = path.read_text(encoding="utf-8")
    current_deck = ""
    for line in text.splitlines():
        if line.startswith("# expanded "):
            current_deck = line.lstrip("# ").strip()
            continue

        # Table rows:
        # | 4 | カード名 | 文明 | コスト | 種類 | role | タグ |
        if not line.startswith("|"):
            continue
        if "---" in line or "カード名" in line or "枚数" in line:
            continue

        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 7 and cells[0].isdigit():
            card_name = cells[1]
            role = cells[5]
            if card_name:
                found[card_name].add(f"deck:{current_deck}:{role}")
    return found


def _extract_from_validation_md(path: Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        return found

    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("| expanded route_seed"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 6:
                deck_name = cells[0]
                for card in _split_seed_cards(cells[5]):
                    found[card].add(f"validation:{deck_name}")
        elif line.startswith("- seed:"):
            seed_text = line.split(":", 1)[1].strip()
            for card in _split_seed_cards(seed_text):
                found[card].add("validation_detail")
    return found


def merge_found(*items: dict[str, set[str]]) -> dict[str, set[str]]:
    merged: dict[str, set[str]] = defaultdict(set)
    for item in items:
        for card, refs in item.items():
            merged[card].update(refs)
    return merged


def load_suspects(path: Path = Path("data/source_suspect_cards.csv")) -> dict[str, str]:
    if not path.exists():
        return {}
    rows = _read_csv(path)
    return {row.get("card_name", ""): row.get("reason", "") for row in rows if row.get("card_name")}


def build_review_rows(
    route_seed_csv: Path = Path("data/reports/route_seed_candidates.csv"),
    expanded_md: Path = Path("data/reports/expanded_route_decks/expanded_route_decks.md"),
    validation_md: Path = Path("data/reports/expanded_route_decks/route_deck_validation.md"),
) -> list[dict[str, Any]]:
    found = merge_found(
        _extract_from_route_seed_csv(route_seed_csv),
        _extract_from_expanded_md(expanded_md),
        _extract_from_validation_md(validation_md),
    )
    suspects = load_suspects()

    rows: list[dict[str, Any]] = []
    for card_name, refs in sorted(found.items()):
        status = ""
        reason = ""
        if card_name in suspects:
            status = "suspect"
            reason = suspects[card_name]

        rows.append(
            {
                "card_name": card_name,
                "review_status": status,
                "official_dmps_search": "",
                "use_in_game_generation": "0" if status == "suspect" else "",
                "reason": reason,
                "appears_in_count": len(refs),
                "appears_in": " || ".join(sorted(refs))[:1000],
            }
        )
    return rows


def write_review_csv(rows: list[dict[str, Any]], out_path: Path = DEFAULT_OUT) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "card_name",
        "review_status",
        "official_dmps_search",
        "use_in_game_generation",
        "reason",
        "appears_in_count",
        "appears_in",
    ]
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def write_source_suspect_from_review(
    review_csv: Path = DEFAULT_OUT,
    out_path: Path = Path("data/source_suspect_cards.csv"),
) -> Path:
    rows = _read_csv(review_csv)
    suspects = []
    for row in rows:
        status = str(row.get("review_status", "")).strip().lower()
        use_flag = str(row.get("use_in_game_generation", "")).strip()
        if status in {"suspect", "exclude", "ng", "no"} or use_flag == "0":
            suspects.append(
                {
                    "card_name": row.get("card_name", ""),
                    "reason": row.get("reason", "") or "候補カードレビューで除外",
                }
            )

    # de-dupe while preserving order
    seen = set()
    unique = []
    for row in suspects:
        name = row["card_name"]
        if not name or name in seen:
            continue
        seen.add(name)
        unique.append(row)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["card_name", "reason"])
        writer.writeheader()
        writer.writerows(unique)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or apply candidate card review list.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--apply", action="store_true", help="Create data/source_suspect_cards.csv from reviewed CSV")
    args = parser.parse_args()

    out = Path(args.out)
    if args.apply:
        path = write_source_suspect_from_review(out)
        print(f"source_suspect_cards: {path}")
        return

    rows = build_review_rows()
    path = write_review_csv(rows, out)
    print(f"review_csv: {path}")
    print(f"cards_to_review: {len(rows)}")
    print("Edit review_status/use_in_game_generation, then run:")
    print(f"python -m src.candidate_card_review --out {path} --apply")


if __name__ == "__main__":
    main()

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def parse_deck_counts(deck_text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for raw_line in deck_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        counts[parts[1].strip()] += int(parts[0])
    return counts


def compare_deck_texts(
    before_text: str,
    after_text: str,
    default_reason: str = "",
) -> list[dict[str, Any]]:
    before = parse_deck_counts(before_text)
    after = parse_deck_counts(after_text)
    changes = []

    for card_name in sorted(set(before) | set(after)):
        diff = after[card_name] - before[card_name]
        if diff > 0:
            changes.append(
                {
                    "change_type": "追加",
                    "card_name": card_name,
                    "count": diff,
                    "reason": default_reason,
                }
            )
        elif diff < 0:
            changes.append(
                {
                    "change_type": "削減",
                    "card_name": card_name,
                    "count": abs(diff),
                    "reason": default_reason,
                }
            )

    return changes


def summarize_changes(changes: list[dict[str, Any]]) -> str:
    if not changes:
        return "変更なし"
    removed = [f'{item["card_name"]} -{item["count"]}' for item in changes if item.get("change_type") == "削減"]
    added = [f'{item["card_name"]} +{item["count"]}' for item in changes if item.get("change_type") == "追加"]
    parts = []
    if removed:
        parts.append(" / ".join(removed))
    if added:
        parts.append(" / ".join(added))
    return " / ".join(parts)


def calc_win_rate_for_names(logs: list[dict[str, Any]], names: set[str]) -> dict[str, Any]:
    matched = [log for log in logs if (log.get("deck_name") or "未設定") in names]
    wins = sum(1 for log in matched if log.get("result") == "勝ち")
    losses = sum(1 for log in matched if log.get("result") == "負け")
    total = wins + losses
    return {
        "matches": len(matched),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / total * 100, 1) if total else 0.0,
    }


def attach_match_stats_to_versions(
    versions: list[dict[str, Any]],
    logs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []
    for version in versions:
        names = {version.get("deck_name") or "未設定"}
        if version.get("version_name"):
            names.add(version["version_name"])
        stats = calc_win_rate_for_names(logs, names)
        enriched.append({**version, **stats})
    return enriched


def compare_parent_child_stats(enriched_versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {version["id"]: version for version in enriched_versions}
    rows = []
    for version in enriched_versions:
        parent = by_id.get(version.get("parent_version_id"))
        if not parent:
            continue
        rows.append(
            {
                "親バージョン": parent.get("version_name") or f'#{parent["id"]}',
                "子バージョン": version.get("version_name") or f'#{version["id"]}',
                "親勝率": parent.get("win_rate", 0.0),
                "子勝率": version.get("win_rate", 0.0),
                "勝率差": round(version.get("win_rate", 0.0) - parent.get("win_rate", 0.0), 1),
                "総合差": _score_diff(version, parent, "total_score"),
                "未知性差": _score_diff(version, parent, "novelty_score"),
                "メタ差": _score_diff(version, parent, "meta_score"),
            }
        )
    return rows


def group_versions_by_deck(versions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for version in versions:
        grouped[version.get("deck_name") or "未設定"].append(version)
    return dict(grouped)


def _score_diff(version: dict[str, Any], parent: dict[str, Any], key: str) -> float | None:
    if version.get(key) is None or parent.get(key) is None:
        return None
    return round(float(version[key]) - float(parent[key]), 1)

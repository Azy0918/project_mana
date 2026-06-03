from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CARD_DB = Path("data/cards.db")
DEFAULT_EXPANDED_MD = Path("data/reports/expanded_route_decks/expanded_route_decks.md")
DEFAULT_OUT_DIR = Path("data/reports/current_meta_matchup")


@dataclass
class DeckCard:
    count: int
    name: str


@dataclass
class CardInfo:
    name: str
    cost: int = 0
    civilization: str = ""
    card_type: str = ""
    tags: set[str] | None = None


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def merge_deck_cards(cards: list[DeckCard]) -> list[DeckCard]:
    merged: dict[str, int] = {}
    for c in cards:
        if c.name and c.count > 0:
            merged[c.name] = merged.get(c.name, 0) + c.count
    return [DeckCard(count, name) for name, count in merged.items()]


def parse_candidate_from_expanded_md(path: Path, keyword: str) -> tuple[str, list[DeckCard]]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", text)
    chosen = next((b for b in blocks if keyword in b and "# expanded " in b), None)
    if chosen is None:
        raise RuntimeError(f"候補デッキ {keyword} を {path} から見つけられませんでした。")

    title_match = re.search(r"^# (expanded .+)$", chosen, flags=re.M)
    title = title_match.group(1).strip() if title_match else f"candidate {keyword}"

    cards: list[DeckCard] = []
    in_table = False
    for raw in chosen.splitlines():
        line = raw.strip()
        if line.startswith("| 枚数 | カード名 |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if "---" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2 and cells[0].isdigit():
                cards.append(DeckCard(safe_int(cells[0]), cells[1]))
    return title, merge_deck_cards(cards)


def load_card_info(card_db: Path) -> dict[str, CardInfo]:
    con = sqlite3.connect(card_db)
    con.row_factory = sqlite3.Row
    infos: dict[str, CardInfo] = {}

    tag_map: dict[str, set[str]] = {}
    try:
        for row in con.execute("SELECT c.name, t.tag FROM card_tags t JOIN cards c ON c.card_id=t.card_id").fetchall():
            tag_map.setdefault(row["name"], set()).add(row["tag"])
    except Exception:
        pass

    for row in con.execute("SELECT name, cost, civilization, card_type FROM cards").fetchall():
        infos[row["name"]] = CardInfo(
            name=row["name"],
            cost=safe_int(row["cost"]),
            civilization=str(row["civilization"] or ""),
            card_type=str(row["card_type"] or ""),
            tags=tag_map.get(row["name"], set()),
        )
    con.close()
    return infos


def load_current_meta_decks(db_path: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT deck_name, format, tier, civilizations, deck_type, confidence, source_url
        FROM meta_decks
        WHERE source_name LIKE '神ゲー攻略 第36弾現在流行中%'
        ORDER BY id
        """
    ).fetchall()

    out = []
    for row in rows:
        card_rows = con.execute(
            """
            SELECT card_name, count
            FROM meta_deck_cards
            WHERE deck_name = ? AND format = ? AND source_url = ?
            ORDER BY id
            """,
            (row["deck_name"], row["format"], row["source_url"]),
        ).fetchall()
        cards = merge_deck_cards([DeckCard(int(r["count"]), r["card_name"]) for r in card_rows])
        out.append({**dict(row), "cards": cards})
    con.close()
    return out


def deck_features(deck: list[DeckCard], infos: dict[str, CardInfo]) -> dict[str, float]:
    total = sum(c.count for c in deck) or 1

    def tag_count(tags: set[str]) -> int:
        n = 0
        for c in deck:
            info = infos.get(c.name)
            if info and info.tags and info.tags & tags:
                n += c.count
        return n

    costs = []
    known = 0
    for c in deck:
        info = infos.get(c.name)
        if info:
            known += c.count
            costs.extend([info.cost] * c.count)

    return {
        "total": total,
        "known": known,
        "known_rate": known / total if total else 0,
        "avg_cost": sum(costs) / len(costs) if costs else 0,
        "low_cost": sum(1 for x in costs if 0 < x <= 2),
        "low_attack": sum(
            c.count
            for c in deck
            if (info := infos.get(c.name))
            and info.tags
            and info.tags & {"打点", "フィニッシャー", "フィニッシャー候補", "シールド圧力", "即効性"}
            and 2 <= info.cost <= 4
            and "クリーチャー" in info.card_type
        ),
        "high_cost": sum(1 for x in costs if x >= 6),
        "defense": tag_count({"受け札", "S・トリガー", "G・ストライク", "ブロッカー"}),
        "resource": tag_count({"リソース", "ドロー", "サーチ候補", "マナ加速"}),
        "removal": tag_count({"除去", "破壊", "バウンス", "タップ"}),
        "attack": tag_count({"打点", "フィニッシャー", "フィニッシャー候補", "シールド圧力", "即効性"}),
        "lock": tag_count({"ロック", "攻撃制限", "呪文ロック", "踏み倒しメタ"}),
    }


def estimate_matchup(candidate: list[DeckCard], meta: dict[str, Any], infos: dict[str, CardInfo]) -> dict[str, Any]:
    opponent = meta["cards"]
    cand = deck_features(candidate, infos)
    opp = deck_features(opponent, infos)

    cand_score = (
        min(cand["defense"] / 10, 3.0)
        + min(cand["resource"] / 10, 3.0)
        + min(cand["removal"] / 10, 2.5)
        + min(cand["attack"] / 8, 3.5)
        + min(cand["lock"] / 8, 2.5)
    )
    opp_score = (
        min(opp["defense"] / 10, 3.0)
        + min(opp["resource"] / 10, 3.0)
        + min(opp["removal"] / 10, 2.5)
        + min(opp["attack"] / 8, 3.5)
        + min(opp["lock"] / 8, 2.5)
    )

    reasons = []
    deck_type = str(meta.get("deck_type") or "")

    if meta.get("confidence", 0) >= 90:
        opp_score += 0.5

    if any(x in deck_type for x in ["ビート", "ワンショット", "速攻"]):
        if cand["defense"] >= 16:
            cand_score += 0.8
            reasons.append("受け札が多く、速い対面に耐えやすい")
        else:
            cand_score -= 0.8
            reasons.append("速い対面に対する受けが不足気味")
    if "カウンター" in deck_type:
        if cand["attack"] < 12:
            cand_score -= 0.8
            reasons.append("カウンター相手を押し切る打点が少なめ")
        if cand["resource"] >= 18:
            cand_score += 0.4
            reasons.append("リソース量で長期戦に入りやすい")
    if "ビッグマナ" in deck_type:
        if cand["attack"] < 14:
            cand_score -= 0.8
            reasons.append("ビッグマナ相手を早めに詰め切る打点が少なめ")
        if cand["attack"] >= 16 and cand["low_attack"] >= 12 and cand["avg_cost"] <= 4.2:
            cand_score += 1.3
            reasons.append("軽量攻撃札が多く、ビッグマナ着地前に詰める速度がある")
        if cand["lock"] >= 8:
            cand_score += 0.5
            reasons.append("ロック要素で大型展開を遅らせる可能性")

    if cand["defense"] >= 20 and cand["attack"] < 16:
        cand_score -= 0.4
        reasons.append("受け寄りで、勝ち切り速度には不安")

    diff = cand_score - opp_score
    win_rate = 1 / (1 + math.exp(-diff / 3.0))
    win_rate = max(0.18, min(0.82, win_rate))
    note = "有利寄り" if win_rate >= 0.55 else "五分寄り" if win_rate >= 0.45 else "不利寄り"

    return {
        "opponent": meta["deck_name"],
        "format": meta["format"],
        "tier": meta["tier"],
        "deck_type": meta["deck_type"],
        "confidence": meta["confidence"],
        "opponent_deck_size": sum(c.count for c in opponent),
        "estimated_win_rate": round(win_rate, 4),
        "note": note,
        "reasons": reasons,
        "candidate_features": cand,
        "opponent_features": opp,
        "opponent_cards": [{"count": c.count, "name": c.name} for c in opponent],
    }


def write_outputs(candidate_name: str, candidate: list[DeckCard], results: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "current_meta_matchup_report.md"
    csv_path = out_dir / "current_meta_matchup_results.csv"
    json_path = out_dir / "current_meta_matchup_results.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["opponent", "deck_type", "opponent_deck_size", "confidence", "estimated_win_rate", "note", "reasons"])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "opponent": r["opponent"],
                "deck_type": r["deck_type"],
                "opponent_deck_size": r["opponent_deck_size"],
                "confidence": r["confidence"],
                "estimated_win_rate": r["estimated_win_rate"],
                "note": r["note"],
                "reasons": " / ".join(r["reasons"]),
            })

    lines = []
    lines.append("# MANA current meta matchup report")
    lines.append("")
    lines.append(f"- candidate: {candidate_name}")
    lines.append(f"- candidate_deck_size: {sum(c.count for c in candidate)}")
    lines.append("")
    lines.append("> 注意: 完全な実ルールシミュレーションではなく、現在流行中5デッキのレシピに基づく代理相性評価です。")
    lines.append("")
    lines.append("| opponent | type | opponent_size | confidence | estimated_win_rate | note | reasons |")
    lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
    for r in sorted(results, key=lambda x: x["estimated_win_rate"], reverse=True):
        lines.append(f"| {r['opponent']} | {r['deck_type']} | {r['opponent_deck_size']} | {r['confidence']} | {r['estimated_win_rate']:.1%} | {r['note']} | {' / '.join(r['reasons']) or '-'} |")

    lines.append("")
    lines.append("## candidate deck")
    for c in candidate:
        lines.append(f"- {c.count} {c.name}")

    lines.append("")
    lines.append("## difficult matchups")
    for r in sorted(results, key=lambda x: x["estimated_win_rate"])[:5]:
        lines.append("")
        lines.append(f"### {r['opponent']}")
        lines.append(f"- estimated_win_rate: {r['estimated_win_rate']:.1%}")
        lines.append(f"- type: {r['deck_type']}")
        lines.append(f"- reasons: {' / '.join(r['reasons']) or '-'}")
        lines.append("- opponent cards:")
        for c in r["opponent_cards"]:
            lines.append(f"  - {c['count']} {c['name']}")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print("markdown:", md_path)
    print("csv:", csv_path)
    print("json:", json_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a MANA candidate against current meta full recipes in meta_deck_cards.")
    parser.add_argument("--card-db", default=str(DEFAULT_CARD_DB))
    parser.add_argument("--expanded-md", default=str(DEFAULT_EXPANDED_MD))
    parser.add_argument("--candidate-keyword", default="#45")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    db_path = Path(args.card_db)
    infos = load_card_info(db_path)
    candidate_name, candidate = parse_candidate_from_expanded_md(Path(args.expanded_md), args.candidate_keyword)
    meta_decks = load_current_meta_decks(db_path)
    if not meta_decks:
        raise RuntimeError("current meta_decks が見つかりません。先に import_current_kamigame_meta.py を実行してください。")
    results = [estimate_matchup(candidate, meta, infos) for meta in meta_decks]
    write_outputs(candidate_name, candidate, results, Path(args.out))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CARD_DB = Path("data/cards.db")
DEFAULT_EXPANDED_MD = Path("data/reports/expanded_route_decks/expanded_route_decks.md")
DEFAULT_META_DB = Path("data/reset_backup_20260531_205932/cards.db")
DEFAULT_OUT_DIR = Path("data/reports/meta_simulation")


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


def split_tags(value: Any) -> set[str]:
    if isinstance(value, set):
        return value
    if isinstance(value, list):
        return {str(x).strip() for x in value if str(x).strip()}
    return {x.strip() for x in re.split(r"[;,]", str(value or "")) if x.strip()}


def parse_key_cards(value: str, default_count: int = 3) -> list[DeckCard]:
    """Parse meta_decks.key_cards like 'A;B;C' into an approximate deck shell.

    Because meta_decks stores key cards rather than a full 40-card list, each key
    card is assigned a representative count. This is not a full rule sim; it is
    a proxy matchup model against the archetype's important cards.
    """
    cards: list[DeckCard] = []
    text = str(value or "").strip()
    if not text:
        return cards

    # split mainly by semicolon; avoid splitting twinpact names on slash
    names = [x.strip() for x in re.split(r"[;\n]", text) if x.strip()]
    for name in names:
        # allow "4 Name" if present
        m = re.match(r"^(\d+)\s+(.+)$", name)
        if m:
            cards.append(DeckCard(safe_int(m.group(1), default_count), m.group(2).strip()))
        else:
            cards.append(DeckCard(default_count, name))
    return merge_deck_cards(cards)


def merge_deck_cards(cards: list[DeckCard]) -> list[DeckCard]:
    merged: dict[str, int] = {}
    for c in cards:
        if not c.name or c.count <= 0:
            continue
        merged[c.name] = merged.get(c.name, 0) + c.count
    return [DeckCard(count, name) for name, count in merged.items()]


def parse_candidate_from_expanded_md(path: Path, keyword: str) -> tuple[str, list[DeckCard]]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", text)
    chosen = None

    for block in blocks:
        if keyword in block and "# expanded " in block:
            chosen = block
            break

    if chosen is None:
        raise RuntimeError(f"候補デッキ {keyword} を {path} から見つけられませんでした。")

    title_match = re.search(r"^# (expanded .+)$", chosen, flags=re.M)
    title = title_match.group(1).strip() if title_match else f"candidate {keyword}"

    in_table = False
    cards: list[DeckCard] = []
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
    try:
        cards = con.execute("SELECT card_id, name, cost, civilization, card_type FROM cards").fetchall()
    except Exception:
        con.close()
        return infos

    tag_map: dict[str, set[str]] = {}
    try:
        for row in con.execute("SELECT c.name, t.tag FROM card_tags t JOIN cards c ON c.card_id=t.card_id").fetchall():
            tag_map.setdefault(row["name"], set()).add(row["tag"])
    except Exception:
        pass

    for row in cards:
        infos[row["name"]] = CardInfo(
            name=row["name"],
            cost=safe_int(row["cost"]),
            civilization=str(row["civilization"] or ""),
            card_type=str(row["card_type"] or ""),
            tags=tag_map.get(row["name"], set()),
        )

    con.close()
    return infos


def load_meta_decks(meta_db: Path) -> list[dict[str, Any]]:
    if not meta_db.exists():
        return []
    con = sqlite3.connect(meta_db)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT deck_name, format, tier, civilizations, deck_type, key_cards,
                   good_matchups, bad_matchups, notes
            FROM meta_decks
            ORDER BY
              CASE tier WHEN 'S' THEN 1 WHEN 'A' THEN 2 WHEN 'B' THEN 3 ELSE 9 END,
              deck_name
            """
        ).fetchall()
    except Exception:
        con.close()
        return []
    con.close()
    return [dict(r) for r in rows]


def deck_features(deck: list[DeckCard], infos: dict[str, CardInfo]) -> dict[str, float]:
    total = sum(c.count for c in deck) or 1

    def tag_count(tags: set[str]) -> int:
        n = 0
        for c in deck:
            info = infos.get(c.name, CardInfo(c.name, tags=set()))
            if info.tags and info.tags & tags:
                n += c.count
        return n

    costs = []
    known = 0
    for c in deck:
        info = infos.get(c.name)
        if info:
            known += c.count
            costs.extend([info.cost] * c.count)

    avg_cost = sum(costs) / len(costs) if costs else 0
    low_cost = sum(1 for x in costs if 0 < x <= 2)
    high_cost = sum(1 for x in costs if x >= 6)

    return {
        "total": total,
        "known": known,
        "known_rate": known / total if total else 0,
        "avg_cost": avg_cost,
        "low_cost": low_cost,
        "high_cost": high_cost,
        "defense": tag_count({"受け札", "S・トリガー", "G・ストライク", "ブロッカー"}),
        "resource": tag_count({"リソース", "ドロー", "サーチ候補", "マナ加速"}),
        "removal": tag_count({"除去", "破壊", "バウンス", "タップ"}),
        "attack": tag_count({"打点", "フィニッシャー", "フィニッシャー候補", "シールド圧力", "即効性"}),
        "lock": tag_count({"ロック", "攻撃制限", "呪文ロック", "踏み倒しメタ"}),
        "graveyard": tag_count({"墓地利用", "リアニメイト"}),
        "hand": tag_count({"ハンデス"}),
    }


def archetype_adjustment(candidate_features: dict[str, float], meta_row: dict[str, Any], opponent_features: dict[str, float]) -> tuple[float, list[str]]:
    """Heuristic matchup adjustments based on meta archetype and notes."""
    adj = 0.0
    reasons: list[str] = []
    deck_type = str(meta_row.get("deck_type") or "")
    notes = str(meta_row.get("notes") or "")
    key_cards = str(meta_row.get("key_cards") or "")

    if "ビート" in deck_type or "ワンショット" in deck_type or "速攻" in deck_type:
        if candidate_features["defense"] >= 16:
            adj += 0.08
            reasons.append("受け札が多く、ビート/ワンショットに耐えやすい")
        else:
            adj -= 0.08
            reasons.append("ビート/ワンショット相手に受け札が不足気味")
        if candidate_features["avg_cost"] >= 4:
            adj -= 0.04
            reasons.append("平均コストが高く、速い相手に遅れやすい")

    if "コントロール" in deck_type:
        if candidate_features["resource"] >= 18:
            adj += 0.04
            reasons.append("リソース量があり、長期戦に入りやすい")
        if candidate_features["attack"] < 10:
            adj -= 0.06
            reasons.append("コントロール相手を押し切る打点が不足気味")

    if "墓地" in notes or "墓地" in key_cards or "魔導具" in str(meta_row.get("deck_name", "")):
        if candidate_features["lock"] >= 8 or candidate_features["removal"] >= 10:
            adj += 0.03
            reasons.append("墓地/魔導具系に対して妨害札が一定数ある")
        else:
            adj -= 0.05
            reasons.append("墓地/魔導具系への明確な妨害が薄い")

    if "踏み倒し" in notes or "革命チェンジ" in notes or "ドギラゴン" in key_cards:
        if candidate_features["lock"] >= 8:
            adj += 0.05
            reasons.append("踏み倒し/革命チェンジ系に対してロック要素がある")
        else:
            adj -= 0.04
            reasons.append("踏み倒し/革命チェンジへの制限が薄い")

    return adj, reasons


def estimate_matchup(candidate: list[DeckCard], meta_row: dict[str, Any], infos: dict[str, CardInfo], key_count: int) -> dict[str, Any]:
    opponent = parse_key_cards(str(meta_row.get("key_cards") or ""), default_count=key_count)
    cand_f = deck_features(candidate, infos)
    opp_f = deck_features(opponent, infos)

    # Base score: compare structure. This is intentionally conservative.
    cand_score = 0.0
    opp_score = 0.0

    cand_score += min(cand_f["defense"] / 10.0, 3.0)
    cand_score += min(cand_f["resource"] / 10.0, 3.0)
    cand_score += min(cand_f["removal"] / 10.0, 2.5)
    cand_score += min(cand_f["attack"] / 8.0, 3.5)
    cand_score += min(cand_f["lock"] / 8.0, 2.5)

    opp_score += min(opp_f["defense"] / 10.0, 3.0)
    opp_score += min(opp_f["resource"] / 10.0, 3.0)
    opp_score += min(opp_f["removal"] / 10.0, 2.5)
    opp_score += min(opp_f["attack"] / 8.0, 3.5)
    opp_score += min(opp_f["lock"] / 8.0, 2.5)

    # Tier pressure: S/A decks deserve extra respect.
    tier = str(meta_row.get("tier") or "")
    if tier == "S":
        opp_score += 1.0
    elif tier == "A":
        opp_score += 0.6
    elif tier == "B":
        opp_score += 0.3

    adj, reasons = archetype_adjustment(cand_f, meta_row, opp_f)
    cand_score += adj * 10

    # Convert score delta to estimated win rate.
    diff = cand_score - opp_score
    win_rate = 1 / (1 + pow(2.718281828, -diff / 3.0))
    # keep conservative range because opponent deck is key-card-only
    win_rate = max(0.18, min(0.82, win_rate))

    if win_rate >= 0.55:
        note = "有利寄り"
    elif win_rate >= 0.45:
        note = "五分寄り"
    else:
        note = "不利寄り"

    return {
        "opponent": meta_row.get("deck_name"),
        "format": meta_row.get("format"),
        "tier": tier,
        "deck_type": meta_row.get("deck_type"),
        "estimated_win_rate": round(win_rate, 4),
        "note": note,
        "reasons": reasons,
        "candidate_features": cand_f,
        "opponent_features": opp_f,
        "opponent_key_cards": [c.name for c in opponent],
    }


def write_outputs(candidate_name: str, candidate: list[DeckCard], meta_rows: list[dict[str, Any]], results: list[dict[str, Any]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "meta_keycard_matchup_results.csv"
    md_path = out_dir / "meta_keycard_matchup_report.md"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = ["opponent", "format", "tier", "deck_type", "estimated_win_rate", "note", "reasons"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "opponent": r["opponent"],
                    "format": r["format"],
                    "tier": r["tier"],
                    "deck_type": r["deck_type"],
                    "estimated_win_rate": r["estimated_win_rate"],
                    "note": r["note"],
                    "reasons": " / ".join(r["reasons"]),
                }
            )

    lines = []
    lines.append("# MANA meta key-card matchup report")
    lines.append("")
    lines.append(f"- candidate: {candidate_name}")
    lines.append(f"- candidate_deck_size: {sum(c.count for c in candidate)}")
    lines.append(f"- meta_decks: {len(meta_rows)}")
    lines.append("")
    lines.append("> 注意: meta_decks は full deck list ではなく key_cards 保存です。この結果は完全な勝率シミュレーションではなく、環境キーカード群に対する代理相性評価です。")
    lines.append("")
    lines.append("| opponent | format | tier | type | estimated_win_rate | note | reasons |")
    lines.append("| --- | --- | --- | --- | ---: | --- | --- |")
    for r in sorted(results, key=lambda x: x["estimated_win_rate"], reverse=True):
        reasons = " / ".join(r["reasons"]) or "-"
        lines.append(f"| {r['opponent']} | {r['format']} | {r['tier']} | {r['deck_type']} | {r['estimated_win_rate']:.1%} | {r['note']} | {reasons} |")

    lines.append("")
    lines.append("## candidate deck")
    for c in candidate:
        lines.append(f"- {c.count} {c.name}")

    lines.append("")
    lines.append("## most difficult matchups")
    for r in sorted(results, key=lambda x: x["estimated_win_rate"])[:5]:
        lines.append("")
        lines.append(f"### {r['opponent']} ({r['tier']}, {r['deck_type']})")
        lines.append(f"- estimated_win_rate: {r['estimated_win_rate']:.1%}")
        lines.append(f"- note: {r['note']}")
        lines.append(f"- reasons: {' / '.join(r['reasons']) or '-'}")
        lines.append(f"- opponent_key_cards: {'; '.join(r['opponent_key_cards'][:20])}")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    print("markdown:", md_path)
    print("csv:", csv_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a MANA candidate deck against saved meta_decks.key_cards.")
    parser.add_argument("--card-db", default=str(DEFAULT_CARD_DB))
    parser.add_argument("--expanded-md", default=str(DEFAULT_EXPANDED_MD))
    parser.add_argument("--meta-db", default=str(DEFAULT_META_DB))
    parser.add_argument("--candidate-keyword", default="#45")
    parser.add_argument("--key-count", type=int, default=3)
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    infos = load_card_info(Path(args.card_db))
    candidate_name, candidate = parse_candidate_from_expanded_md(Path(args.expanded_md), args.candidate_keyword)
    meta_rows = load_meta_decks(Path(args.meta_db))

    if not meta_rows:
        raise RuntimeError(f"meta_decks を {args.meta_db} から読み込めませんでした。")

    results = [estimate_matchup(candidate, row, infos, args.key_count) for row in meta_rows]
    write_outputs(candidate_name, candidate, meta_rows, results, Path(args.out))


if __name__ == "__main__":
    main()

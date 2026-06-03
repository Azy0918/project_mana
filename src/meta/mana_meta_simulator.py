from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_CARD_DB = Path("data/cards.db")
DEFAULT_EXPANDED_MD = Path("data/reports/expanded_route_decks/expanded_route_decks.md")
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


def parse_deck_text(text: str) -> list[DeckCard]:
    cards: list[DeckCard] = []
    if not text:
        return cards

    # Try JSON first
    try:
        data = json.loads(text)
        parsed = parse_deck_json(data)
        if parsed:
            return parsed
    except Exception:
        pass

    # Lines like "4 カード名" / "4x カード名" / "カード名 x4"
    for raw in str(text).splitlines():
        line = raw.strip().strip("|").strip()
        if not line or line.startswith("#") or "---" in line:
            continue

        m = re.match(r"^(\d+)\s*[xX枚]?\s+(.+)$", line)
        if m:
            count = safe_int(m.group(1))
            name = m.group(2).strip()
            if name:
                cards.append(DeckCard(count, name))
            continue

        m = re.match(r"^(.+?)\s*[xX×]\s*(\d+)$", line)
        if m:
            name = m.group(1).strip()
            count = safe_int(m.group(2))
            if name:
                cards.append(DeckCard(count, name))
            continue

        # CSV-ish "4,Card"
        parts = [p.strip() for p in re.split(r"[,，\t]", line)]
        if len(parts) >= 2 and parts[0].isdigit():
            cards.append(DeckCard(safe_int(parts[0]), parts[1]))

    return merge_deck_cards(cards)


def parse_deck_json(data: Any) -> list[DeckCard]:
    cards: list[DeckCard] = []

    if isinstance(data, dict):
        for key in ["cards", "deck", "deck_cards", "list", "main"]:
            if isinstance(data.get(key), list):
                return parse_deck_json(data[key])
        # Maybe dict of name -> count
        if all(isinstance(k, str) for k in data.keys()) and all(isinstance(v, (int, float, str)) for v in data.values()):
            for name, count in data.items():
                if str(name).strip():
                    cards.append(DeckCard(safe_int(count), str(name).strip()))
            return merge_deck_cards(cards)

    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                parsed = parse_deck_text(item)
                cards.extend(parsed)
            elif isinstance(item, dict):
                name = item.get("name") or item.get("card_name") or item.get("カード名")
                count = item.get("count") or item.get("枚数") or item.get("num") or item.get("quantity") or 1
                if name:
                    cards.append(DeckCard(safe_int(count, 1), str(name).strip()))

    return merge_deck_cards(cards)


def merge_deck_cards(cards: list[DeckCard]) -> list[DeckCard]:
    merged: dict[str, int] = {}
    for c in cards:
        if not c.name or c.count <= 0:
            continue
        merged[c.name] = merged.get(c.name, 0) + c.count
    return [DeckCard(count, name) for name, count in merged.items()]


def parse_candidate_from_expanded_md(path: Path, keyword: str = "#45") -> tuple[str, list[DeckCard]]:
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n---\n", text)
    chosen = None

    for block in blocks:
        if keyword in block and "# expanded " in block:
            chosen = block
            break

    if chosen is None:
        # fallback: first expanded deck
        for block in blocks:
            if "# expanded " in block:
                chosen = block
                break

    if chosen is None:
        raise RuntimeError(f"候補デッキを {path} から見つけられませんでした。")

    title_match = re.search(r"^# (expanded .+)$", chosen, flags=re.M)
    title = title_match.group(1).strip() if title_match else "candidate"

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


def list_sqlite_tables(db_path: Path) -> list[str]:
    try:
        con = sqlite3.connect(db_path)
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        con.close()
        return tables
    except Exception:
        return []


def get_table_columns(db_path: Path, table: str) -> list[str]:
    try:
        con = sqlite3.connect(db_path)
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
        con.close()
        return cols
    except Exception:
        return []


def discover_environment_decks(search_dir: Path = Path("data")) -> tuple[list[tuple[str, list[DeckCard]]], list[str]]:
    found: list[tuple[str, list[DeckCard]]] = []
    logs: list[str] = []

    db_paths = sorted(search_dir.glob("*.db"))
    name_col_candidates = ["deck_name", "name", "title", "meta_name", "archetype", "opponent_deck", "deck_id"]
    list_col_candidates = ["deck_list", "cards", "deck_json", "deck", "list", "main_deck", "card_list"]

    for db_path in db_paths:
        for table in list_sqlite_tables(db_path):
            cols = get_table_columns(db_path, table)
            lower_cols = {c.lower(): c for c in cols}

            possible_name_cols = [lower_cols[c] for c in name_col_candidates if c in lower_cols]
            possible_list_cols = [lower_cols[c] for c in list_col_candidates if c in lower_cols]

            if not possible_list_cols:
                continue

            name_col = possible_name_cols[0] if possible_name_cols else None
            list_col = possible_list_cols[0]

            try:
                con = sqlite3.connect(db_path)
                con.row_factory = sqlite3.Row
                query_cols = [list_col] + ([name_col] if name_col else [])
                sql = f"SELECT {', '.join(query_cols)} FROM {table} LIMIT 200"
                rows = con.execute(sql).fetchall()
                con.close()
            except Exception as exc:
                logs.append(f"skip {db_path}:{table}: {exc}")
                continue

            for idx, row in enumerate(rows, start=1):
                text = row[list_col]
                cards = parse_deck_text(str(text or ""))
                if sum(c.count for c in cards) < 20:
                    continue
                name = str(row[name_col]) if name_col else f"{db_path.stem}.{table}.{idx}"
                found.append((name, cards))
                logs.append(f"found deck: {name} from {db_path.name}:{table}")

    # de-dupe by name
    unique: dict[str, list[DeckCard]] = {}
    for name, cards in found:
        unique[name] = cards

    return list(unique.items()), logs


def expanded_deck(deck: list[DeckCard]) -> list[str]:
    pool = []
    for c in deck:
        pool.extend([c.name] * c.count)
    return pool


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
    for c in deck:
        info = infos.get(c.name)
        if info:
            costs.extend([info.cost] * c.count)

    avg_cost = sum(costs) / len(costs) if costs else 0
    low_cost = sum(1 for x in costs if 0 < x <= 2)
    mid_cost = sum(1 for x in costs if 3 <= x <= 5)
    high_cost = sum(1 for x in costs if x >= 6)

    return {
        "total": total,
        "avg_cost": avg_cost,
        "low_cost": low_cost,
        "mid_cost": mid_cost,
        "high_cost": high_cost,
        "defense": tag_count({"受け札", "S・トリガー", "G・ストライク", "ブロッカー"}),
        "resource": tag_count({"リソース", "ドロー", "サーチ候補", "マナ加速"}),
        "removal": tag_count({"除去", "破壊", "バウンス", "タップ"}),
        "attack": tag_count({"打点", "フィニッシャー", "フィニッシャー候補", "シールド圧力", "即効性"}),
        "lock": tag_count({"ロック", "攻撃制限", "呪文ロック", "踏み倒しメタ"}),
    }


def trial_score(hand: list[str], infos: dict[str, CardInfo], features: dict[str, float]) -> float:
    score = 0.0
    low = 0
    resource = 0
    defense = 0
    attack = 0
    removal = 0
    lock = 0

    for name in hand:
        info = infos.get(name, CardInfo(name, tags=set()))
        tags = info.tags or set()
        if 0 < info.cost <= 2:
            low += 1
        if tags & {"リソース", "ドロー", "サーチ候補", "マナ加速"}:
            resource += 1
        if tags & {"受け札", "S・トリガー", "G・ストライク", "ブロッカー"}:
            defense += 1
        if tags & {"打点", "フィニッシャー", "フィニッシャー候補", "シールド圧力", "即効性"}:
            attack += 1
        if tags & {"除去", "破壊", "バウンス", "タップ"}:
            removal += 1
        if tags & {"ロック", "攻撃制限", "呪文ロック", "踏み倒しメタ"}:
            lock += 1

    score += min(low, 3) * 1.1
    score += min(resource, 3) * 1.0
    score += min(defense, 4) * 0.8
    score += min(removal, 3) * 0.9
    score += min(attack, 4) * 1.15
    score += min(lock, 2) * 1.0

    # deck-level structure
    score += min(features["attack"] / 6.0, 4.0)
    score += min(features["resource"] / 8.0, 3.5)
    score += min(features["defense"] / 8.0, 3.0)
    score += min(features["removal"] / 8.0, 2.5)
    score += min(features["lock"] / 6.0, 2.5)

    # punish clunky curve
    score -= max(0.0, features["avg_cost"] - 4.5) * 0.8
    return score


def simulate_matchup(candidate: list[DeckCard], opponent: list[DeckCard], infos: dict[str, CardInfo], trials: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    cand_pool = expanded_deck(candidate)
    opp_pool = expanded_deck(opponent)

    cand_features = deck_features(candidate, infos)
    opp_features = deck_features(opponent, infos)

    if len(cand_pool) < 20 or len(opp_pool) < 20:
        return {"error": "deck too small"}

    cand_wins = 0
    opp_wins = 0
    draws = 0

    for _ in range(trials):
        cand_draw = rng.sample(cand_pool, min(len(cand_pool), 11))  # opening + draws through midgame
        opp_draw = rng.sample(opp_pool, min(len(opp_pool), 11))

        cand_score = trial_score(cand_draw, infos, cand_features)
        opp_score = trial_score(opp_draw, infos, opp_features)

        # Interaction adjustment
        cand_score += min(cand_features["defense"] / 10.0, 2.0) if opp_features["attack"] > 12 else 0
        opp_score += min(opp_features["defense"] / 10.0, 2.0) if cand_features["attack"] > 12 else 0

        cand_score += rng.gauss(0, 1.2)
        opp_score += rng.gauss(0, 1.2)

        if abs(cand_score - opp_score) < 0.5:
            draws += 1
        elif cand_score > opp_score:
            cand_wins += 1
        else:
            opp_wins += 1

    win_rate = cand_wins / trials
    draw_rate = draws / trials

    return {
        "trials": trials,
        "candidate_wins": cand_wins,
        "opponent_wins": opp_wins,
        "draws": draws,
        "candidate_win_rate": round(win_rate, 4),
        "draw_rate": round(draw_rate, 4),
        "candidate_features": cand_features,
        "opponent_features": opp_features,
    }


def write_outputs(candidate_name: str, candidate: list[DeckCard], opponents: list[tuple[str, list[DeckCard]]], results: list[dict[str, Any]], logs: list[str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "meta_simulation_results.csv"
    md_path = out_dir / "meta_simulation_report.md"
    log_path = out_dir / "meta_simulation_discovery_log.txt"

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        fieldnames = [
            "opponent",
            "candidate_win_rate",
            "draw_rate",
            "trials",
            "candidate_attack",
            "candidate_defense",
            "candidate_resource",
            "opponent_attack",
            "opponent_defense",
            "opponent_resource",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            cf = r.get("candidate_features", {})
            of = r.get("opponent_features", {})
            writer.writerow(
                {
                    "opponent": r["opponent"],
                    "candidate_win_rate": r.get("candidate_win_rate"),
                    "draw_rate": r.get("draw_rate"),
                    "trials": r.get("trials"),
                    "candidate_attack": cf.get("attack"),
                    "candidate_defense": cf.get("defense"),
                    "candidate_resource": cf.get("resource"),
                    "opponent_attack": of.get("attack"),
                    "opponent_defense": of.get("defense"),
                    "opponent_resource": of.get("resource"),
                }
            )

    lines = []
    lines.append("# MANA meta simulation report")
    lines.append("")
    lines.append(f"- candidate: {candidate_name}")
    lines.append(f"- candidate_deck_size: {sum(c.count for c in candidate)}")
    lines.append(f"- opponents_found: {len(opponents)}")
    lines.append("")
    lines.append("> 注意: これは完全なデュエプレルールシミュレーションではなく、タグ・コスト・初動・受け・攻撃札を使った代理シミュレーションです。")
    lines.append("")
    lines.append("| opponent | estimated_win_rate | draw_rate | trials | note |")
    lines.append("| --- | --- | --- | --- | --- |")

    for r in sorted(results, key=lambda x: x.get("candidate_win_rate", 0), reverse=True):
        wr = r.get("candidate_win_rate", 0)
        note = "有利寄り" if wr >= 0.55 else "五分寄り" if wr >= 0.45 else "不利寄り"
        lines.append(f"| {r['opponent']} | {wr:.1%} | {r.get('draw_rate', 0):.1%} | {r.get('trials')} | {note} |")

    lines.append("")
    lines.append("## candidate deck")
    for c in candidate:
        lines.append(f"- {c.count} {c.name}")

    lines.append("")
    lines.append("## discovery logs")
    for log in logs[:100]:
        lines.append(f"- {log}")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    log_path.write_text("\n".join(logs), encoding="utf-8")

    print("markdown:", md_path)
    print("csv:", csv_path)
    print("log:", log_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run proxy simulations for a MANA candidate deck against saved meta/environment decks.")
    parser.add_argument("--card-db", default=str(DEFAULT_CARD_DB))
    parser.add_argument("--expanded-md", default=str(DEFAULT_EXPANDED_MD))
    parser.add_argument("--candidate-keyword", default="#45", help="Text used to find candidate block in expanded_route_decks.md, e.g. #45 or #46")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    infos = load_card_info(Path(args.card_db))
    candidate_name, candidate = parse_candidate_from_expanded_md(Path(args.expanded_md), args.candidate_keyword)
    opponents, logs = discover_environment_decks(Path(args.data_dir))

    # Avoid comparing candidate-like report tables; filter exact same deck if found.
    opponents = [(name, deck) for name, deck in opponents if sum(c.count for c in deck) >= 30]

    if not opponents:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "meta_simulation_report.md").write_text(
            "# MANA meta simulation report\n\n保存済み環境デッキを自動検出できませんでした。\n\n"
            "次を確認してください。\n"
            "- 環境デッキがSQLite DBに保存されているか\n"
            "- deck_list / cards / deck_json のような列にデッキリストが入っているか\n"
            "- または --data-dir で保存先フォルダを指定してください。\n",
            encoding="utf-8",
        )
        print("opponents_found: 0")
        print("markdown:", out_dir / "meta_simulation_report.md")
        return

    results = []
    for i, (opp_name, opp_deck) in enumerate(opponents, start=1):
        r = simulate_matchup(candidate, opp_deck, infos, args.trials, args.seed + i)
        r["opponent"] = opp_name
        results.append(r)

    write_outputs(candidate_name, candidate, opponents, results, logs, Path(args.out))


if __name__ == "__main__":
    main()

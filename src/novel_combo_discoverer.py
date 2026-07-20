from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.card_reference_extractor import deploy_link, ride_condition_link
from src.combo_knowledge_base import load_known_combos
from src.deck_condition_analyzer import analyze_deck_condition
from src.generated_deck_store import save_generated_deck
from src.import_cards import DEFAULT_DB_PATH
from src.route_deck_expander import expand_route_seed_to_deck
from src.route_proof_searcher import (
    _reference_bonus,
    list_proof_win_conditions,
    load_proof_card_nodes,
    search_route_proofs,
)


DEFAULT_OUT = Path("data/reports/novel_combos")


def _split_names(value: Any) -> list[str]:
    return [name.strip() for name in str(value or "").split(";") if name.strip()]


def _route_names(row: dict[str, Any]) -> frozenset[str]:
    return frozenset(
        part.strip() for part in str(row.get("route_seed_cards", "")).split(" / ") if part.strip()
    )


def _load_known_core_sets(db_path: Path) -> list[tuple[str, frozenset[str]]]:
    combos = load_known_combos(db_path)
    sets: list[tuple[str, frozenset[str]]] = []
    for _, combo in combos.iterrows():
        core = frozenset(_split_names(combo.get("core_cards")))
        if core:
            sets.append((str(combo.get("combo_name", "")), core))
    return sets


def _load_meta_deck_sets(db_path: Path) -> list[tuple[str, frozenset[str]]]:
    import sqlite3

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT m.deck_name, c.card_name
                FROM meta_decks m JOIN meta_deck_cards c ON c.meta_deck_id = m.id
                """
            ).fetchall()
    except Exception:
        return []
    decks: dict[str, set[str]] = {}
    for row in rows:
        decks.setdefault(str(row["deck_name"]), set()).add(str(row["card_name"]))
    return [(name, frozenset(cards)) for name, cards in decks.items()]


def _tier_s_lethal_turn(db_path: Path) -> int:
    """Tier S仮想敵の想定リーサルターン。mana_meta_deck_seedsのspeedから推定する。"""
    import sqlite3

    speed_to_turn = {"fast": 5, "mid": 6, "slow": 7}
    try:
        with sqlite3.connect(db_path) as conn:
            speeds = [row[0] for row in conn.execute("SELECT speed FROM mana_meta_deck_seeds")]
    except Exception:
        speeds = []
    turns = [speed_to_turn.get(str(speed), 6) for speed in speeds]
    return min(turns) if turns else 5


def estimate_online_turn(names: frozenset[str], nodes_by_name: dict[str, Any]) -> int | None:
    """コンボが最速で成立するターンの粗い推定。

    deploy linkはエネイブラーの着地ターン、チェンジ/侵略/進化は踏み台コスト+1(攻撃/重ね)とする。
    """
    cards = [nodes_by_name[name] for name in names if name in nodes_by_name]
    best: int | None = None

    def consider(turn: int) -> None:
        nonlocal best
        if best is None or turn < best:
            best = turn

    for enabler in cards:
        for target in cards:
            if target is enabler or enabler.reference is None:
                continue
            if deploy_link(
                enabler.reference,
                target_civ=target.civilization,
                target_cost=target.cost,
                target_power=target.power,
                target_type=target.card_type,
                target_name=target.name,
                target_text=target.text,
                target_race=target.race,
                target_is_evolution="進化" in target.card_type,
            ):
                consider(max(2, enabler.cost))
            if target.reference is not None:
                for condition in [
                    target.reference.change_condition,
                    target.reference.invasion_condition,
                    target.reference.evolution_condition,
                ]:
                    if condition and ride_condition_link(
                        condition,
                        source_civ=enabler.civilization,
                        source_cost=enabler.cost,
                        source_type=enabler.card_type,
                        source_name=enabler.name,
                        source_text=enabler.text,
                        source_race=enabler.race,
                    ):
                        consider(max(2, enabler.cost) + 1)
    if best is None and cards:
        best = max(card.cost for card in cards)
    return best


def discover_novel_combos(
    db_path: Path = DEFAULT_DB_PATH,
    beam_width: int = 100,
    limit_per_condition: int = 100,
    max_depth: int = 3,
    max_total_cost: int = 22,
    top_n: int = 40,
) -> dict[str, Any]:
    """参照リンク付きルートから既知コンボ・既知メタ内ペアを除外し、新規コンボ候補を抽出する。"""
    known_sets = _load_known_core_sets(db_path)
    meta_sets = _load_meta_deck_sets(db_path)

    all_rows: list[dict[str, Any]] = []
    for condition_key in list_proof_win_conditions():
        all_rows.extend(
            search_route_proofs(
                db_path=db_path,
                win_condition=condition_key,
                max_depth=max_depth,
                beam_width=beam_width,
                max_total_cost=max_total_cost,
                limit=limit_per_condition,
            )
        )

    nodes_by_name = {node.name: node for node in load_proof_card_nodes(db_path)}
    lethal_turn = _tier_s_lethal_turn(db_path)

    def linked_pair_signature(names: frozenset[str]) -> frozenset[tuple[str, str]]:
        """ルート内で実際に参照リンクが成立しているペアの集合。

        同じコンボ核に汎用カードを入れ替えただけのバリエーションを
        1グループへ集約するためのシグネチャ。
        """
        pairs = set()
        cards = [nodes_by_name[name] for name in names if name in nodes_by_name]
        for i, a in enumerate(cards):
            for b in cards[i + 1 :]:
                if _reference_bonus((a, b)) > 0:
                    pairs.add(tuple(sorted((a.name, b.name))))
        return frozenset(pairs)

    seen: set[frozenset[str]] = set()
    groups: dict[tuple[str, frozenset[tuple[str, str]]], dict[str, Any]] = {}
    known_hits: list[dict[str, Any]] = []
    meta_hits: list[dict[str, Any]] = []
    for row in all_rows:
        links = int(row.get("reference_links", 0) or 0)
        if links <= 0:
            continue
        names = _route_names(row)
        if len(names) < 2 or names in seen:
            continue
        seen.add(names)

        known_match = next((combo for combo, core in known_sets if core <= names), "")
        meta_match = next((deck for deck, cards in meta_sets if names <= cards), "")
        entry = {
            "route_type": row.get("route_type", ""),
            "cards": " / ".join(sorted(names)),
            "reference_links": links,
            "proof_score": row.get("proof_score", 0),
            "discovery_score": int(row.get("proof_score", 0)) + links,
            "total_cost": row.get("total_cost", ""),
            "state_chain": row.get("state_chain", ""),
            "proof_comment": row.get("proof_comment", ""),
        }
        if known_match:
            known_hits.append({**entry, "known_combo": known_match})
            continue
        if meta_match:
            meta_hits.append({**entry, "meta_deck": meta_match})
            continue

        signature = linked_pair_signature(names)
        key = (str(entry["route_type"]), signature)
        entry["linked_pairs"] = " ; ".join(f"{a}+{b}" for a, b in sorted(signature))
        existing = groups.get(key)
        if existing is None:
            entry["variant_count"] = 1
            groups[key] = entry
        else:
            existing["variant_count"] = int(existing.get("variant_count", 1)) + 1
            if entry["discovery_score"] > existing["discovery_score"]:
                entry["variant_count"] = existing["variant_count"]
                groups[key] = entry

    ranked = sorted(groups.values(), key=lambda item: item["discovery_score"], reverse=True)
    # 多様性フィルタ: 同ルート型で同じカードが2回まで。同型シェルの
    # バリエーション(hubカード使い回し)が上位を占有するのを防ぐ。
    from collections import Counter

    novel: list[dict[str, Any]] = []
    usage: dict[str, Counter[str]] = {}
    for entry in ranked:
        names = frozenset(str(entry["cards"]).split(" / "))
        route_type = str(entry["route_type"])
        counter = usage.setdefault(route_type, Counter())
        if any(counter[name] >= 2 for name in names):
            continue
        counter.update(names)
        online_turn = estimate_online_turn(names, nodes_by_name)
        entry["estimated_online_turn"] = online_turn
        entry["race_check"] = (
            "間に合う"
            if online_turn is not None and online_turn <= lethal_turn
            else ("ギリギリ" if online_turn is not None and online_turn == lethal_turn + 1 else "遅い")
        )
        novel.append(entry)
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "searched_rows": len(all_rows),
        "linked_unique_routes": len(seen),
        "tier_s_lethal_turn": lethal_turn,
        "novel_candidates": novel[:top_n],
        "known_combo_hits": known_hits,
        "meta_deck_hits": meta_hits,
    }


def expand_top_candidates(
    report: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
    expand_n: int = 3,
) -> list[dict[str, Any]]:
    """上位候補を40枚デッキ案へ展開する(DB保存はしない)。"""
    expansions = []
    for candidate in report.get("novel_candidates", [])[:expand_n]:
        try:
            expansion = expand_route_seed_to_deck(
                {
                    "route_type": candidate["route_type"],
                    "route_seed_cards": candidate["cards"].replace(" / ", " / "),
                },
                db_path=db_path,
            )
            expansions.append(
                {
                    "cards": candidate["cards"],
                    "route_type": candidate["route_type"],
                    "deck": expansion.get("deck_rows") or expansion.get("deck") or [],
                    "evaluation_summary": {
                        key: expansion.get(key)
                        for key in ["total_score", "novelty_score", "meta_score"]
                        if key in expansion
                    },
                }
            )
        except Exception as exc:
            expansions.append({"cards": candidate["cards"], "error": str(exc)})
    return expansions


def save_top_candidate_decks(
    report: dict[str, Any],
    db_path: Path = DEFAULT_DB_PATH,
    save_n: int = 5,
) -> list[dict[str, Any]]:
    """上位候補の40枚展開デッキをgenerated_decksへ保存し、実テスト対象に載せる。"""
    saved = []
    for candidate in report.get("novel_candidates", [])[:save_n]:
        try:
            expansion = expand_route_seed_to_deck(
                {
                    "route_type": candidate["route_type"],
                    "route_seed_cards": candidate["cards"],
                },
                db_path=db_path,
            )
            deck_cards = [
                {
                    "name": row["card_name"],
                    "count": row["count"],
                    # generated_deck_storeの_deck_sizeはquantityキーで枚数を数える
                    "quantity": row["count"],
                    "civilization": row.get("civilization", ""),
                    "cost": row.get("cost", 0),
                    "card_type": row.get("card_type", ""),
                    "tags": row.get("tags", ""),
                }
                for row in expansion.get("deck_rows", [])
            ]
            analysis = analyze_deck_condition(
                deck_cards,
                civilizations=[],
                focus_tags=[],
                avoid_tags=[],
                target_starter_count=8,
                target_defense_count=6,
                target_finisher_count=3,
            )
            core = candidate["cards"].replace(" / ", "+")
            deck_name = f"novel {candidate['route_type']} {core}"[:80]
            saved_id = save_generated_deck(
                deck_name=deck_name,
                civilizations=[],
                deck_type=str(candidate["route_type"]),
                focus_tags=[],
                avoid_tags=[],
                strategy_note=(
                    f"未知コンボ発掘候補。リンクペア: {candidate.get('linked_pairs', '')} / "
                    f"成立目安{candidate.get('estimated_online_turn', '?')}ターン({candidate.get('race_check', '')}) / "
                    f"{expansion.get('strategy_note', '')}"
                ),
                deck_cards=deck_cards,
                analysis=analysis,
                evaluation=expansion.get("deck_evaluation") or {},
                format="ND",
                candidate_origin="novel_combo_discovery",
                db_path=db_path,
            )
            saved.append({"saved_id": saved_id, "deck_name": deck_name, "cards": candidate["cards"]})
        except Exception as exc:
            saved.append({"cards": candidate["cards"], "error": str(exc)})
    return saved


def report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 未知コンボ候補レポート",
        "",
        f"- 実行日時: {report['created_at']}",
        f"- 探索ルート行数: {report['searched_rows']} / 参照リンク付きユニークルート: {report['linked_unique_routes']}",
        f"- 新規候補: {len(report['novel_candidates'])}件 / 既知コンボ一致: {len(report['known_combo_hits'])}件 / 既知メタ内: {len(report['meta_deck_hits'])}件",
        "",
        "## 新規コンボ候補 (発掘スコア順)",
        "",
        f"- Tier S仮想敵の想定リーサル: {report.get('tier_s_lethal_turn', '?')}ターン",
        "",
        "| # | ルート型 | カード | リンクペア | links | score | 成立T | レース | 変種数 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, row in enumerate(report["novel_candidates"], start=1):
        lines.append(
            "| {i} | {rt} | {cards} | {pairs} | {links} | {score} | {turn} | {race} | {variants} |".format(
                i=index,
                rt=row["route_type"],
                cards=row["cards"],
                pairs=str(row.get("linked_pairs", "")).replace("|", "\\|"),
                links=row["reference_links"],
                score=row["discovery_score"],
                turn=row.get("estimated_online_turn", "?"),
                race=row.get("race_check", ""),
                variants=row.get("variant_count", 1),
            )
        )
    if report["known_combo_hits"]:
        lines.extend(["", "## 既知コンボとして再発見されたルート(検証成功の証跡)", ""])
        for row in report["known_combo_hits"]:
            lines.append(f"- {row['known_combo']}: {row['cards']} (links={row['reference_links']})")
    lines.extend(
        [
            "",
            "備考: 候補は参照リンク(踏み倒し/チェンジ/侵略/進化元/マッドネス)を持つルートのみ。",
            "既知コンボKBのコアを含むルートと、単一の既知メタデッキ内に収まるルートは除外済み。",
        ]
    )
    return "\n".join(lines)


def write_novel_combo_outputs(
    report: dict[str, Any],
    expansions: list[dict[str, Any]] | None = None,
    output_dir: Path = DEFAULT_OUT,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "novel_combo_candidates.md"
    json_path = output_dir / "novel_combo_candidates.json"
    payload = dict(report)
    if expansions is not None:
        payload["expansions"] = expansions
    md_path.write_text(report_to_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"markdown": md_path, "json": json_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="未知コンボ候補の発掘")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--beam-width", type=int, default=100)
    parser.add_argument("--limit-per-condition", type=int, default=100)
    parser.add_argument("--max-total-cost", type=int, default=22)
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--expand", type=int, default=3, help="上位N件を40枚デッキ案へ展開")
    parser.add_argument("--save-decks", type=int, default=0, help="上位N件をgenerated_decksへ保存")
    args = parser.parse_args()

    report = discover_novel_combos(
        db_path=Path(args.db),
        beam_width=args.beam_width,
        limit_per_condition=args.limit_per_condition,
        max_total_cost=args.max_total_cost,
        top_n=args.top,
    )
    expansions = expand_top_candidates(report, Path(args.db), expand_n=args.expand) if args.expand else None
    if args.save_decks:
        for row in save_top_candidate_decks(report, Path(args.db), save_n=args.save_decks):
            if "error" in row:
                print(f"保存失敗: {row['cards']}: {row['error']}")
            else:
                print(f"generated_decks保存: id={row['saved_id']} {row['deck_name']}")
    paths = write_novel_combo_outputs(report, expansions, Path(args.out))
    print(f"新規候補: {len(report['novel_candidates'])}件 / 既知一致: {len(report['known_combo_hits'])}件 / メタ内: {len(report['meta_deck_hits'])}件")
    for row in report["novel_candidates"][:10]:
        print(f"- [{row['route_type']}] {row['cards']} (links={row['reference_links']} score={row['discovery_score']})")
    for key, path in paths.items():
        print(f"{key}: {path}")


if __name__ == "__main__":
    main()

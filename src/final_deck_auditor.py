from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.current_meta_deck_practical_auditor import (
    audit_deck,
    primary_role,
    secondary_roles,
)
from src.current_meta_deck_regenerator import Card, DeckCard, load_cards, split_civs
from src.current_meta_matchup_simulator import (
    DeckCard as MatchupDeckCard,
    estimate_matchup,
    load_card_info,
    load_current_meta_decks,
)


DEFAULT_DB = Path("data/cards.db")
DEFAULT_PRACTICAL_JSON = Path("data/reports/current_meta_practical_audit/current_meta_practical_audit.json")
DEFAULT_OUT = Path("data/reports/final_deck")
TARGET_IMPROVEMENT_TITLE = "色事故除去・火光自然アグロロック"
SUSPECT_CARDS = ["コモロキシ", "緑知銀 イーアル"]


@dataclass
class FinalDeck:
    name: str
    version: str
    cards: list[DeckCard]
    adjustment_note: str


def load_card_catalog(db_path: Path) -> dict[str, Card]:
    return {card.name: card for card in load_cards(db_path)}


def load_improvement_deck(db_path: Path, practical_json: Path = DEFAULT_PRACTICAL_JSON) -> list[DeckCard]:
    catalog = load_card_catalog(db_path)
    data = json.loads(practical_json.read_text(encoding="utf-8"))
    improvement = next(
        (item for item in data.get("improvements", []) if item.get("title") == TARGET_IMPROVEMENT_TITLE),
        data.get("improvements", [{}])[0],
    )
    deck = []
    for row in improvement.get("deck", []):
        card = catalog.get(str(row.get("name", "")))
        if card:
            deck.append(DeckCard(int(row.get("count") or 0), card, "practical improvement base"))
    return merge_deck(deck)


def build_final_decks(db_path: Path) -> list[FinalDeck]:
    catalog = load_card_catalog(db_path)
    base = load_improvement_deck(db_path)

    recommended = replace_cards(
        base,
        catalog,
        remove_names=["コモロキシ", "緑知銀 イーアル"],
        additions=[
            ("奇石 ミクセル/ジャミング・チャフ", 4, "踏み倒しメタとチャフ面。水を使わずデンジャデオンの大型着地を遅らせる。"),
            ("フルール・ライフ", 2, "自然単色の受け兼マナ補助。自然有効供給を補正。"),
        ],
    )

    reserve = replace_cards(
        base,
        catalog,
        remove_names=["コモロキシ"],
        additions=[
            ("奇石 ミクセル/ジャミング・チャフ", 2, "踏み倒しメタ補強。"),
        ],
    )

    return [
        FinalDeck(
            name="MANA推奨 実戦版A",
            version="A",
            cards=recommended,
            adjustment_note=(
                "コモロキシは攻撃できないため採用外。緑知銀 イーアルはタグ過大評価リスクを避け、"
                "奇石 ミクセル/ジャミング・チャフとフルール・ライフで水なし火光自然に整理。"
            ),
        ),
        FinalDeck(
            name="MANA予備案B",
            version="B",
            cards=reserve,
            adjustment_note=(
                "コモロキシのみ除外。緑知銀 イーアルを受け/マナ補助として残す予備案。"
                "攻撃札としては扱わない。"
            ),
        ),
    ]


def replace_cards(
    deck: list[DeckCard],
    catalog: dict[str, Card],
    remove_names: list[str],
    additions: list[tuple[str, int, str]],
) -> list[DeckCard]:
    rows = [DeckCard(entry.count, entry.card, entry.reason) for entry in deck if entry.card.name not in set(remove_names)]
    for name, count, reason in additions:
        card = catalog.get(name)
        if card:
            rows.append(DeckCard(count, card, reason))
    rows = merge_deck(rows)
    return normalize_to_40(rows, catalog)


def merge_deck(deck: list[DeckCard]) -> list[DeckCard]:
    merged: dict[str, DeckCard] = {}
    for entry in deck:
        if entry.count <= 0:
            continue
        if entry.card.name in merged:
            merged[entry.card.name].count += entry.count
        else:
            merged[entry.card.name] = DeckCard(entry.count, entry.card, entry.reason)
    return list(merged.values())


def normalize_to_40(deck: list[DeckCard], catalog: dict[str, Card]) -> list[DeckCard]:
    total = sum(entry.count for entry in deck)
    fill_order = [
        "奇石 ミクセル/ジャミング・チャフ",
        "フルール・ライフ",
        "血風神官フンヌー",
        "マツぽっくん",
        "ライラ・アイニー",
    ]
    while total < 40:
        changed = False
        current = {entry.card.name: entry for entry in deck}
        for name in fill_order:
            entry = current.get(name)
            if entry and entry.count < 4:
                entry.count += 1
                total += 1
                changed = True
                break
            if not entry and name in catalog:
                deck.append(DeckCard(1, catalog[name], "40枚補正"))
                total += 1
                changed = True
                break
        if not changed:
            break
    while total > 40:
        target = max(deck, key=lambda entry: (entry.card.cost, entry.count))
        target.count -= 1
        total -= 1
        if target.count <= 0:
            deck.remove(target)
    return deck


def final_primary_role(card: Card) -> str:
    text = card.text
    tags = card.tags
    if "攻撃できない" in text or "相手プレイヤーを攻撃できない" in text:
        if tags & {"受け札", "S・トリガー", "G・ストライク", "ブロッカー"}:
            return "defense"
        if tags & {"マナ加速", "リソース", "サーチ候補"}:
            return "resource"
        if tags & {"除去", "タップ", "破壊"}:
            return "removal"
        return "utility"
    if tags & {"呪文ロック", "ロック", "踏み倒しメタ"} and "クリーチャー" in card.card_type and card.cost <= 4:
        return "lock"
    if tags & {"受け札", "S・トリガー", "G・ストライク"} and not _has_attack_evidence(card):
        return "defense"
    if "クリーチャー" in card.card_type and 2 <= card.cost <= 4:
        return "attack"
    if _has_attack_evidence(card):
        return "finisher" if card.cost >= 5 else "attack"
    if tags & {"マナ加速", "リソース", "サーチ候補", "ドロー"}:
        return "resource"
    if tags & {"除去", "タップ", "破壊", "バウンス"}:
        return "removal"
    return primary_role(card)


def final_secondary_roles(card: Card) -> set[str]:
    roles = set()
    text = card.text
    tags = card.tags
    if final_primary_role(card) in {"attack", "finisher"}:
        roles.add("attack")
    if tags & {"受け札", "S・トリガー", "G・ストライク", "ブロッカー"}:
        roles.add("defense")
    if tags & {"マナ加速", "リソース", "サーチ候補", "ドロー"} or "マナゾーンに置" in text:
        roles.add("resource")
    if tags & {"除去", "タップ", "破壊", "バウンス"} or any(k in text for k in ["破壊", "タップ", "マナゾーンに置く"]):
        roles.add("removal")
    if tags & {"ロック", "呪文ロック", "攻撃制限", "踏み倒しメタ"} or "唱えられない" in text:
        roles.add("lock")
    return roles


def audit_final_deck(deck: FinalDeck, db_path: Path) -> dict[str, Any]:
    base_audit = audit_deck(deck.cards, db_path)
    primary_counts = Counter()
    secondary_counts = Counter()
    low_primary_attack = 0
    card_checks = []
    for entry in deck.cards:
        role = final_primary_role(entry.card)
        primary_counts[role] += entry.count
        if role == "attack" and 2 <= entry.card.cost <= 4:
            low_primary_attack += entry.count
        for secondary in final_secondary_roles(entry.card):
            secondary_counts[secondary] += entry.count
        card_checks.append(card_db_check(entry.card.name, db_path, entry))

    avg_cost = sum(entry.count * entry.card.cost for entry in deck.cards) / max(1, sum(entry.count for entry in deck.cards))
    effective_supply = effective_civ_supply(deck.cards)
    warnings = []
    if any("水" in split_civs(entry.card.civilization) for entry in deck.cards):
        warnings.append("水文明要求カードが入っています。")
    if avg_cost > 4.0:
        warnings.append(f"平均コストが4.0を超えています: {avg_cost:.2f}")
    if sum(entry.count for entry in deck.cards if entry.card.cost >= 7) > 2:
        warnings.append("7コスト以上が3枚以上あります。")
    if primary_counts["attack"] < 24:
        warnings.append(f"primary attack不足: {primary_counts['attack']}")
    if low_primary_attack < 20:
        warnings.append(f"2〜4 cost primary attack不足: {low_primary_attack}")
    if secondary_counts["defense"] < 8:
        warnings.append(f"defense不足: {secondary_counts['defense']}")
    if secondary_counts["resource"] < 6:
        warnings.append(f"resource不足: {secondary_counts['resource']}")
    for civ, minimum in {"火": 20, "光": 8, "自然": 8}.items():
        if effective_supply.get(civ, 0) < minimum:
            warnings.append(f"{civ}文明有効供給不足: {effective_supply.get(civ, 0)} / 目標 {minimum}")

    return {
        "deck_name": deck.name,
        "deck_version": deck.version,
        "deck_size": sum(entry.count for entry in deck.cards),
        "avg_cost": round(avg_cost, 2),
        "high_cost_count": sum(entry.count for entry in deck.cards if entry.card.cost >= 7),
        "primary_counts": dict(primary_counts),
        "secondary_counts": dict(secondary_counts),
        "low_primary_attack_count": low_primary_attack,
        "effective_supply": effective_supply,
        "base_audit": base_audit,
        "card_checks": card_checks,
        "suspect_cards": [suspect_card_review(name, db_path) for name in SUSPECT_CARDS],
        "format_note": format_note(db_path),
        "warnings": warnings,
        "matchups": estimate_matchups(deck.cards, db_path),
    }


def card_db_check(name: str, db_path: Path, entry: DeckCard) -> dict[str, Any]:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM cards WHERE name = ?", (name,)).fetchall()
        tag_rows = con.execute(
            """
            SELECT DISTINCT tag
            FROM card_tags ct
            JOIN cards c ON c.card_id = ct.card_id
            WHERE c.name = ?
            ORDER BY tag
            """,
            (name,),
        ).fetchall()
    first = dict(rows[0]) if rows else {}
    return {
        "count": entry.count,
        "exists": bool(rows),
        "duplicate_name_count": len(rows),
        "card_id": first.get("card_id", ""),
        "name": name,
        "civilization": first.get("civilization", ""),
        "cost": first.get("cost", ""),
        "card_type": first.get("card_type", ""),
        "text": first.get("text", ""),
        "tags": [row["tag"] for row in tag_rows],
        "official_db_origin": bool(rows),
        "primary_role": final_primary_role(entry.card),
        "secondary_roles": sorted(final_secondary_roles(entry.card)),
    }


def suspect_card_review(name: str, db_path: Path) -> dict[str, Any]:
    catalog = load_card_catalog(db_path)
    card = catalog.get(name)
    if not card:
        return {"name": name, "exists": False, "judgement": "DBに存在しません。"}
    text = card.text
    roles = final_secondary_roles(card)
    attack_evidence = _has_attack_evidence(card) and "攻撃できない" not in text
    review = {
        "name": name,
        "exists": True,
        "tags": sorted(card.tags),
        "text": text,
        "primary_role": final_primary_role(card),
        "secondary_roles": sorted(roles),
        "attack_evidence": attack_evidence,
        "lock_evidence": "唱えられない" in text or "攻撃できない" in text or bool(card.tags & {"ロック", "攻撃制限", "呪文ロック"}),
        "removal_evidence": any(k in text for k in ["破壊", "タップ", "マナゾーンに置く"]),
        "resource_evidence": "マナゾーンに置" in text or bool(card.tags & {"マナ加速", "リソース"}),
    }
    if name == "コモロキシ":
        review["judgement"] = "攻撃できないため攻撃札としては過大評価。最終推奨Aでは不採用。SST除去/マナ補助としてのみ評価可能。"
    elif name == "緑知銀 イーアル":
        review["judgement"] = "攻撃札ではなく、受け札/条件付きマナ補助として評価。最終推奨Aでは安定性優先で不採用。"
    else:
        review["judgement"] = "要確認。"
    return review


def format_note(db_path: Path) -> str:
    with sqlite3.connect(db_path) as con:
        columns = [row[1] for row in con.execute("PRAGMA table_info(cards)").fetchall()]
    usable = [col for col in columns if col.lower() in {"format", "pack", "is_nd", "new_division", "all_division"}]
    if not usable:
        return "フォーマット使用可否はDB列不足のため未判定。推測でND/AD使用可能とは扱いません。"
    return f"フォーマット判定に利用可能な列があります: {usable}"


def effective_civ_supply(deck: list[DeckCard]) -> dict[str, float]:
    supply = {civ: 0.0 for civ in ["光", "水", "闇", "火", "自然"]}
    for entry in deck:
        civs = split_civs(entry.card.civilization)
        for civ in civs:
            supply[civ] += entry.count if len(civs) == 1 else entry.count * 0.5
    return {key: round(value, 1) for key, value in supply.items()}


def estimate_matchups(deck: list[DeckCard], db_path: Path) -> list[dict[str, Any]]:
    infos = load_card_info(db_path)
    metas = load_current_meta_decks(db_path)
    candidate = [MatchupDeckCard(entry.count, entry.card.name) for entry in deck]
    return [estimate_matchup(candidate, meta, infos) for meta in metas]


def matchup_plans() -> dict[str, dict[str, str]]:
    return {
        "自然単デンジャデオン": {
            "先攻": "2〜4ターン目に火の小型を連続展開し、マツぽっくん/ミクセルで大型着地を遅らせながら先に盾を詰める。",
            "後攻": "受け札を1枚キープしつつ、早撃人形マグナムやマグナム・チュリスで踏み倒し/展開に干渉する。",
            "出したいカード": "ボルット・紫郎・バルット、早撃人形マグナム、マグナム・チュリス、マツぽっくん、奇石 ミクセル/ジャミング・チャフ",
            "キープ": "2〜4コスト攻撃札2枚以上、火マナ、自然または光の干渉札。",
            "盾を詰めるタイミング": "4ターン目までに2体以上残れば積極的に詰める。大型着地前にリーサル圏へ入れる。",
            "受けに回る場面": "相手が早期に大型展開の準備を見せた時だけ除去/メタ優先。",
            "不利パターン": "初手が多色過多、火単色不足、相手のマナ加速連打から先に大型が着地する。",
            "入れ替え候補": "メタが刺さらない場合はフルール・ライフ枠を追加打点または確定除去へ。",
        },
        "火光レイド": {
            "先攻": "火小型で先に盤面を取り、相手のレイド前に盾を2〜3枚削る。",
            "後攻": "受け札をキープし、相手の横展開に対して除去付きツインパクトを優先。",
            "出したいカード": "血風神官フンヌー、ライラ・アイニー、スニーク戦車系、火の軽量打点。",
            "キープ": "火マナ、2〜3コスト打点、受け札1枚。",
            "盾を詰めるタイミング": "相手のカウンター札が薄い時。無理に全割りしない。",
            "受けに回る場面": "相手が先に横展開した時。",
            "不利パターン": "受け札を引けず後攻でテンポ負け。",
            "入れ替え候補": "火光レイドが多いなら受け札枠を増やす。",
        },
        "火水レイド": {
            "先攻": "序盤から圧をかけ、相手のドロー/展開前に盾を詰める。",
            "後攻": "除去札を温存し、相手の主力展開に合わせる。",
            "出したいカード": "早撃人形マグナム、マグナム・チュリス、ミクセル。",
            "キープ": "火の軽量打点、除去、メタカード。",
            "盾を詰めるタイミング": "相手の手札補充前、または盤面を返した直後。",
            "受けに回る場面": "相手がSA/連続展開に入る直前。",
            "不利パターン": "除去が薄く盤面を返せない。",
            "入れ替え候補": "除去不足なら火の軽量除去を追加。",
        },
        "水単スコーラー": {
            "先攻": "ミクセル/チャフ系を絡めて呪文連打を遅らせ、打点を先行。",
            "後攻": "呪文制限を優先。手札を整えられる前に盾を詰める。",
            "出したいカード": "奇石 ミクセル/ジャミング・チャフ、ミラクルストップ、火の軽量打点。",
            "キープ": "呪文制限、火打点、光マナ。",
            "盾を詰めるタイミング": "呪文制限を置いたターン。",
            "受けに回る場面": "相手がコンボ始動に入る前のメタ設置優先。",
            "不利パターン": "光マナが遅れて呪文制限が間に合わない。",
            "入れ替え候補": "スコーラーが多いならミラクルストップ増量。",
        },
        "光単裁きの紋章Z": {
            "先攻": "受け切られる前に小型打点を並べ、チャフで返しを縛る。",
            "後攻": "無理に全割りせず、相手のシールド操作前に盤面を作る。",
            "出したいカード": "軽量打点、ミクセル、ミラクルストップ。",
            "キープ": "2〜3コスト打点2枚、光マナ、呪文制限。",
            "盾を詰めるタイミング": "呪文制限と同時、または相手の返し札が薄い時。",
            "受けに回る場面": "相手の表向き盾が増え、無理攻めが裏目になる時。",
            "不利パターン": "受け札を連続で踏み、手札が切れる。",
            "入れ替え候補": "長期戦が多いならリソース札を増やす。",
        },
    }


def build_final_report(decks: list[FinalDeck], audits: list[dict[str, Any]], db_path: Path) -> dict[str, Any]:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "mana_evaluation": "MANA上では、#45/#46より自然単デンジャデオン対面の代理評価が改善しています。",
        "unconfirmed_points": "ND/AD使用可否、所持状況、実際の手札事故率、コモロキシ/緑知銀 イーアルの実戦評価は人間の確認が必要です。",
        "human_check_points": [
            "全カードがゲーム内で使えるか",
            "所持しているか",
            "ND/ADで使えるか",
            "4ターン目までに盤面を作れるか",
            "6ターン目までに詰め切れるか",
        ],
        "final_decks": [
            {
                "name": deck.name,
                "version": deck.version,
                "adjustment_note": deck.adjustment_note,
                "cards": serialize_deck(deck.cards),
                "audit": audit,
            }
            for deck, audit in zip(decks, audits)
        ],
        "matchup_plans": matchup_plans(),
        "first_five_test_plan": [
            "自然単デンジャデオン",
            "自然単デンジャデオン",
            "自然単デンジャデオン",
            "火光レイド",
            "火水レイド",
        ],
    }


def serialize_deck(deck: list[DeckCard]) -> list[dict[str, Any]]:
    return [
        {
            "count": entry.count,
            "name": entry.card.name,
            "civilization": entry.card.civilization,
            "cost": entry.card.cost,
            "primary_role": final_primary_role(entry.card),
            "secondary_roles": sorted(final_secondary_roles(entry.card)),
        }
        for entry in deck
    ]


def write_report(payload: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "final_deck_report.json"
    md_path = out_dir / "final_deck_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(to_markdown(payload), encoding="utf-8")
    print("markdown:", md_path)
    print("json:", json_path)


def to_markdown(payload: dict[str, Any]) -> str:
    rec = payload["final_decks"][0]
    audit = rec["audit"]
    lines = ["# Project MANA final deck report", ""]
    lines.append("## 1. 最終推奨デッキ")
    lines.append("")
    lines.append(f"- デッキ名: {rec['name']}")
    lines.append(f"- バージョン: {rec['version']}")
    lines.append(f"- 平均コスト: {audit['avg_cost']}")
    lines.append(f"- 役割集計: {audit['primary_counts']}")
    lines.append(f"- secondary roles: {audit['secondary_counts']}")
    lines.append(f"- 2〜4 cost primary attack: {audit['low_primary_attack_count']}")
    lines.append(f"- 色供給: {audit['effective_supply']}")
    lines.append(f"- フォーマット: {audit['format_note']}")
    lines.append("")
    lines.append("### 40枚リスト")
    for card in rec["cards"]:
        lines.append(f"- {card['count']} {card['name']} [{card['civilization']} / {card['cost']}] primary={card['primary_role']}")
    lines.append("")
    lines.append("### 勝ち筋")
    lines.append("2〜4ターン目に火の小型打点を連続展開し、ミクセル/マグナム/マツぽっくんで相手の大型展開を遅らせ、5〜6ターン目までに盾を詰め切る仮説です。")
    lines.append("")
    lines.append("## 2. なぜこのデッキを選んだか")
    lines.append("- #45/#46は自然単デンジャデオンに30.47%/37.17%でした。")
    lines.append("- 元候補2は54.78%まで改善しましたが、水供給1.0で音精 ラフルルを使う色事故リスクがありました。")
    lines.append("- 改良候補1は62.83%まで改善しましたが、コモロキシ/緑知銀 イーアルのタグ過大評価が残りました。")
    lines.append(f"- 最終調整: {rec['adjustment_note']}")
    lines.append("")
    lines.append("### MANA上の評価")
    lines.append(payload["mana_evaluation"])
    lines.append("### 実戦上の未確認点")
    lines.append(payload["unconfirmed_points"])
    lines.append("### 人間が確認すべき点")
    for point in payload["human_check_points"]:
        lines.append(f"- {point}")
    lines.append("### 次の改良条件")
    lines.append("5戦ログで色事故率、4ターン目盤面形成率、6ターン目詰め切り率、弱かったカードを確認して差し替えます。")
    lines.append("")
    lines.append("## 3. 対面別プラン")
    for matchup, plan in payload["matchup_plans"].items():
        lines.append(f"### {matchup}")
        for key, value in plan.items():
            lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## 4. 実戦前チェックリスト")
    checklist = [
        "全カードがゲーム内で使えるか",
        "所持しているか",
        "ND/ADで使えるか",
        "色事故しないか",
        "コモロキシ/緑知銀 イーアルが本当に役割を持つか",
        "5戦テストで何を見るか",
    ]
    for item in checklist:
        lines.append(f"- [ ] {item}")
    lines.append("")
    lines.append("### コモロキシ/緑知銀 イーアルの扱い")
    for review in audit["suspect_cards"]:
        lines.append(f"- {review['name']}: {review.get('judgement')}")
    lines.append("")
    lines.append("## 5. 最初の5戦テスト計画")
    for index, opponent in enumerate(payload["first_five_test_plan"], start=1):
        lines.append(f"{index}. {opponent}")
    lines.append("")
    lines.append("記録すること: 勝敗、先攻/後攻、決着ターン、4ターン目までに盤面を作れたか、6ターン目までに詰め切れたか、色事故したか、強かったカード、弱かったカード、腐ったカード。")
    lines.append("")
    lines.append("## 予備案")
    if len(payload["final_decks"]) > 1:
        backup = payload["final_decks"][1]
        lines.append(f"- {backup['name']}: {backup['adjustment_note']}")
        lines.append(f"- avg_cost: {backup['audit']['avg_cost']}")
        lines.append(f"- primary roles: {backup['audit']['primary_counts']}")
    return "\n".join(lines)


def _has_attack_evidence(card: Card) -> bool:
    text = card.text
    return (
        "スピードアタッカー" in text
        or "W・ブレイカー" in text
        or "T・ブレイカー" in text
        or "Q・ブレイカー" in text
        or "パワード・ブレイカー" in text
        or bool(card.tags & {"打点", "即効性", "シールド圧力"})
    )


def load_card_catalog(db_path: Path) -> dict[str, Card]:
    return {card.name: card for card in load_cards(db_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build final practical MANA deck package.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--practical-json", default=str(DEFAULT_PRACTICAL_JSON))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    db_path = Path(args.db)
    decks = build_final_decks(db_path)
    audits = [audit_final_deck(deck, db_path) for deck in decks]
    payload = build_final_report(decks, audits, db_path)
    write_report(payload, Path(args.out))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import csv
import itertools
import re
import sqlite3
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from src.import_cards import DEFAULT_DB_PATH
from src.route_candidate_evaluator import evaluate_route_candidates


@dataclass
class SeedCard:
    name: str
    cost: int
    civilization: str = ""
    card_type: str = ""
    tags: str = ""
    text: str = ""

    @property
    def terms(self) -> set[str]:
        values = set(_split_terms(self.tags))
        values.update(_split_terms(self.civilization))
        for token in re.findall(r"[一-龥ぁ-んァ-ンーA-Za-z0-9・_]+", self.text):
            if len(token) >= 2:
                values.add(token)
        return values


ROUTE_PLANS: list[dict[str, Any]] = [
    {
        "route_type": "lock_confirmed_win",
        "name": "軽量メタからロック制圧",
        "roles": [
            {
                "role": "early_interference",
                "tags": ["ロック", "呪文ロック", "攻撃制限", "G・ストライク", "ハンデス"],
                "max_cost": 4,
            },
            {
                "role": "lock_payoff",
                "tags": ["ロック", "呪文ロック", "フィニッシャー", "攻撃制限"],
                "max_cost": 8,
            },
            {
                "role": "finish_or_stabilize",
                "tags": ["打点", "フィニッシャー", "ブロッカー", "シールド追加", "受け札"],
                "max_cost": 7,
            },
        ],
        "state_chain_template": "{a} -> {b} -> {c} -> lock_confirmed_win (opponent_action_lock:+2 / disruption:+2 / defense:+1 / win_progress:+1)",
    },
    {
        "route_type": "damage_overflow_win",
        "name": "踏み倒し/展開から打点過剰",
        "roles": [
            {
                "role": "starter",
                "tags": ["初動", "低コスト", "サーチ候補", "マナ加速"],
                "max_cost": 3,
            },
            {
                "role": "cheat_or_swarm",
                "tags": ["踏み倒し", "侵略", "革命チェンジ", "G・ゼロ", "メクレイド"],
                "max_cost": 6,
            },
            {
                "role": "damage_payoff",
                "tags": ["打点", "フィニッシャー", "スピードアタッカー", "アンブロッカブル"],
                "max_cost": 8,
            },
        ],
        "state_chain_template": "{a} -> {b} -> {c} -> damage_overflow_win (tempo:+2 / board:+2 / damage_pressure:+3 / attack_permission:+1 / win_progress:+1)",
    },
    {
        "route_type": "loop_converted_win",
        "name": "リソース循環から勝利出力",
        "roles": [
            {
                "role": "resource_engine",
                "tags": ["ドロー", "リソース", "墓地利用", "山札操作", "回収"],
                "max_cost": 5,
            },
            {
                "role": "repeat_or_bypass",
                "tags": ["踏み倒し", "コストを支払わず", "墓地利用", "回収", "コンボ"],
                "max_cost": 7,
            },
            {
                "role": "win_output",
                "tags": ["フィニッシャー", "打点", "ロック", "特殊勝利", "山札操作"],
                "max_cost": 8,
            },
        ],
        "state_chain_template": "{a} -> {b} -> {c} -> loop_converted_win (resource_loop:+3 / hand:+1 / board:+1 / win_progress:+2)",
    },
    {
        "route_type": "alternate_effect_win",
        "name": "耐久/山札操作から特殊勝利",
        "roles": [
            {
                "role": "defense",
                "tags": ["S・トリガー", "G・ストライク", "ブロッカー", "シールド追加", "受け札"],
                "max_cost": 5,
            },
            {
                "role": "condition_builder",
                "tags": ["山札操作", "シールド追加", "ドロー", "リソース", "コンボ"],
                "max_cost": 6,
            },
            {
                "role": "alternate_payoff",
                "tags": ["特殊勝利", "フィニッシャー", "山札操作", "ロック"],
                "max_cost": 9,
            },
        ],
        "state_chain_template": "{a} -> {b} -> {c} -> alternate_effect_win (defense:+2 / alternate_win_progress:+2 / win_progress:+1 / shield:+1)",
    },
    {
        "route_type": "opponent_deckout_win",
        "name": "防御から相手山札圧力",
        "roles": [
            {
                "role": "defense",
                "tags": ["S・トリガー", "G・ストライク", "ブロッカー", "受け札", "攻撃制限"],
                "max_cost": 5,
            },
            {
                "role": "deck_pressure",
                "tags": ["山札操作", "ドロー", "バウンス", "ハンデス", "リソース"],
                "max_cost": 7,
            },
            {
                "role": "lock_or_stabilize",
                "tags": ["ロック", "呪文ロック", "攻撃制限", "シールド追加", "ブロッカー"],
                "max_cost": 8,
            },
        ],
        "state_chain_template": "{a} -> {b} -> {c} -> opponent_deckout_win (defense:+2 / opponent_deck_pressure:+2 / disruption:+1 / opponent_action_lock:+1)",
    },
]


def _connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _split_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = re.split(r"[;/／,\n]+", str(value))
    return [str(item).strip() for item in raw if str(item).strip()]


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _load_cards(db_path: str | Path = DEFAULT_DB_PATH) -> list[SeedCard]:
    with _connect(db_path) as conn:
        if not _table_exists(conn, "cards"):
            return []

        cols = _columns(conn, "cards")
        name_col = "name" if "name" in cols else None
        if not name_col:
            return []

        select_cols = [
            "name",
            "cost" if "cost" in cols else "0 AS cost",
            "civilization" if "civilization" in cols else "'' AS civilization",
            "card_type" if "card_type" in cols else "'' AS card_type",
            "text" if "text" in cols else "'' AS text",
        ]
        rows = conn.execute(f"SELECT {', '.join(select_cols)} FROM cards").fetchall()

        tags_by_name: dict[str, str] = {}
        if _table_exists(conn, "card_tags"):
            tag_cols = _columns(conn, "card_tags")
            card_cols = _columns(conn, "cards")
            if {"card_id", "tag"} <= tag_cols and "card_id" in card_cols:
                try:
                    tag_rows = conn.execute(
                        """
                        SELECT c.name, GROUP_CONCAT(ct.tag, ';') AS tags
                        FROM cards c
                        JOIN card_tags ct ON c.card_id = ct.card_id
                        GROUP BY c.name
                        """
                    ).fetchall()
                    tags_by_name = {row["name"]: row["tags"] or "" for row in tag_rows}
                except Exception:
                    tags_by_name = {}

    cards: list[SeedCard] = []
    for row in rows:
        try:
            cost = int(row["cost"] or 0)
        except Exception:
            cost = 0
        cards.append(
            SeedCard(
                name=str(row["name"] or ""),
                cost=cost,
                civilization=str(row["civilization"] or ""),
                card_type=str(row["card_type"] or ""),
                tags=tags_by_name.get(str(row["name"] or ""), ""),
                text=str(row["text"] or ""),
            )
        )
    return cards


def _matches_role(card: SeedCard, role: dict[str, Any]) -> bool:
    max_cost = int(role.get("max_cost") or 99)
    if card.cost > max_cost:
        return False

    role_tags = set(role.get("tags") or [])
    if not role_tags:
        return True

    text_blob = f"{card.name};{card.tags};{card.text}"
    return any(tag in text_blob for tag in role_tags)


def _role_match_score(card: SeedCard, role: dict[str, Any]) -> int:
    role_tags = set(role.get("tags") or [])
    text_blob = f"{card.name};{card.tags};{card.text}"
    matched = sum(1 for tag in role_tags if tag in text_blob)
    score = matched * 12
    score += max(0, 8 - card.cost)
    if "S・トリガー" in card.tags or "G・ストライク" in card.tags:
        score += 4
    if "初動" in card.tags or card.cost <= 3:
        score += 3
    return score


def _pick_role_cards(cards: list[SeedCard], role: dict[str, Any], per_role_limit: int = 12) -> list[SeedCard]:
    matched = [card for card in cards if _matches_role(card, role)]
    matched.sort(key=lambda card: (_role_match_score(card, role), -card.cost), reverse=True)

    # Avoid all candidates becoming the same over-tagged cards by keeping name-unique and role-relevant.
    picked: list[SeedCard] = []
    seen: set[str] = set()
    for card in matched:
        key = _norm(card.name)
        if not key or key in seen:
            continue
        seen.add(key)
        picked.append(card)
        if len(picked) >= per_role_limit:
            break
    return picked


def _candidate_route_score(route_type: str, cards: list[SeedCard]) -> int:
    if not cards:
        return 0
    avg_cost = sum(card.cost for card in cards) / len(cards)
    max_cost = max(card.cost for card in cards)
    tag_blob = ";".join(card.tags for card in cards)

    score = 55
    score += max(0, int(18 - avg_cost * 2))
    if max_cost <= 6:
        score += 10
    elif max_cost >= 9:
        score -= 20

    if route_type == "lock_confirmed_win" and ("ロック" in tag_blob or "呪文ロック" in tag_blob):
        score += 15
    if route_type == "damage_overflow_win" and ("打点" in tag_blob or "踏み倒し" in tag_blob):
        score += 15
    if route_type == "loop_converted_win" and ("リソース" in tag_blob or "墓地利用" in tag_blob):
        score += 12
    if route_type == "alternate_effect_win" and ("シールド追加" in tag_blob or "山札操作" in tag_blob):
        score += 12
    if route_type == "opponent_deckout_win" and ("山札操作" in tag_blob or "ドロー" in tag_blob):
        score += 10

    if "マナ加速" in tag_blob or "チャージャー" in tag_blob:
        score += 8
    if "受け札" in tag_blob or "S・トリガー" in tag_blob or "G・ストライク" in tag_blob:
        score += 6

    return max(0, min(100, int(score)))


def _candidate_key(route_type: str, cards: list[SeedCard]) -> tuple[str, tuple[str, ...]]:
    return route_type, tuple(sorted(_norm(card.name) for card in cards))


EXTERNAL_ZONE_TERMS = [
    "ドラグハート",
    "サイキック",
    "超次元",
    "龍魂",
    "覚醒",
    "禁断",
    "鼓動",
    "セル",
    "最終禁断",
]

SOFT_RISK_TERMS = [
    "コストを支払わず",
    "踏み倒し",
    "G・ゼロ",
    "侵略",
    "革命チェンジ",
    "メクレイド",
]

PAYOFF_TERMS = [
    "フィニッシャー",
    "打点",
    "ロック",
    "呪文ロック",
    "特殊勝利",
    "山札操作",
    "攻撃制限",
    "シールド追加",
]


def is_likely_external_or_non_main_card(card: SeedCard) -> bool:
    """Return True for cards that are risky as route seeds.

    v1 policy:
    - Exclude obvious external-zone / special-zone objects.
    - Exclude cost 0 route seeds because many are not normal main-deck plays.
    """
    blob = f"{card.name};{card.card_type};{card.tags};{card.text}"
    if card.cost <= 0:
        return True
    return any(term in blob for term in EXTERNAL_ZONE_TERMS)


def seed_quality_penalty(route_type: str, cards: list[SeedCard]) -> tuple[int, list[str]]:
    """Compute quality penalty and reasons for a route seed.

    This is intentionally conservative. It does not reject all unusual cards,
    but it sharply penalizes seeds that look like tag coincidences rather than
    executable routes.
    """
    penalty = 0
    reasons: list[str] = []

    if any(is_likely_external_or_non_main_card(card) for card in cards):
        penalty += 80
        reasons.append("外部ゾーン/特殊ゾーン/通常プレイ困難カードを含む可能性")

    if len(cards) < 2:
        penalty += 40
        reasons.append("seed枚数が少なすぎる")

    tag_blobs = [set(_split_terms(card.tags)) for card in cards]
    if len(cards) >= 2 and len({";".join(sorted(tags)) for tags in tag_blobs}) <= 1:
        penalty += 12
        reasons.append("seed内の役割が重複しすぎている可能性")

    all_blob = ";".join(f"{card.name};{card.card_type};{card.tags};{card.text}" for card in cards)
    if not any(term in all_blob for term in PAYOFF_TERMS):
        penalty += 25
        reasons.append("勝利出力/payoffが薄い")

    if route_type == "lock_confirmed_win":
        if not any(term in all_blob for term in ["ロック", "呪文ロック", "攻撃制限", "ハンデス"]):
            penalty += 25
            reasons.append("lock_confirmed_winだが行動制限要素が薄い")
    elif route_type == "damage_overflow_win":
        if not any(term in all_blob for term in ["打点", "スピードアタッカー", "侵略", "革命チェンジ", "アンブロッカブル"]):
            penalty += 25
            reasons.append("damage_overflow_winだが打点形成要素が薄い")
    elif route_type == "loop_converted_win":
        if not any(term in all_blob for term in ["リソース", "回収", "墓地利用", "ドロー", "踏み倒し"]):
            penalty += 25
            reasons.append("loop_converted_winだが循環要素が薄い")
    elif route_type == "alternate_effect_win":
        if not any(term in all_blob for term in ["特殊勝利", "山札操作", "シールド追加"]):
            penalty += 25
            reasons.append("alternate_effect_winだが特殊条件形成が薄い")
    elif route_type == "opponent_deckout_win":
        if not any(term in all_blob for term in ["山札操作", "ドロー", "バウンス", "ハンデス"]):
            penalty += 25
            reasons.append("opponent_deckout_winだが相手山札/リソース圧力が薄い")

    max_cost = max((card.cost for card in cards), default=0)
    if max_cost >= 8:
        penalty += 20
        reasons.append("最大コストが重い")
    elif max_cost >= 7:
        penalty += 10
        reasons.append("最大コストがやや重い")

    # Two-card routes are attractive, but if both cards are just broad tags and no
    # support text exists, penalize slightly.
    if len(cards) == 2 and not any(term in all_blob for term in SOFT_RISK_TERMS + ["サーチ", "ドロー", "手札に加える", "マナ加速"]):
        penalty += 8
        reasons.append("2枚seedだが接続補助が薄い")

    return penalty, reasons


def passes_seed_quality_filter(route_type: str, cards: list[SeedCard], strict: bool = True) -> tuple[bool, int, list[str]]:
    penalty, reasons = seed_quality_penalty(route_type, cards)
    if strict and penalty >= 80:
        return False, penalty, reasons
    if strict and penalty >= 55:
        return False, penalty, reasons
    return True, penalty, reasons


def generate_route_seed_candidates(
    db_path: str | Path = DEFAULT_DB_PATH,
    per_route_limit: int = 10,
    per_role_limit: int = 10,
    max_candidates: int = 50,
    evaluate: bool = True,
    strict_quality_filter: bool = True,
) -> list[dict[str, Any]]:
    """Generate route_based seed candidates from the current card/tag DB.

    This does not save anything to DB. It returns candidate dicts that are
    compatible with src.route_candidate_evaluator.
    """
    cards = _load_cards(db_path)
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    for plan in ROUTE_PLANS:
        route_type = str(plan["route_type"])
        role_pools = [
            _pick_role_cards(cards, role, per_role_limit=per_role_limit)
            for role in plan["roles"]
        ]
        if any(not pool for pool in role_pools):
            continue

        raw_candidates: list[dict[str, Any]] = []
        for combo in itertools.product(*role_pools):
            combo_cards = list(combo)
            # Keep candidates to 2-3 unique cards.
            unique_by_name: dict[str, SeedCard] = {}
            for card in combo_cards:
                unique_by_name[_norm(card.name)] = card
            combo_cards = list(unique_by_name.values())
            if len(combo_cards) < 2:
                continue

            quality_ok, quality_penalty, quality_reasons = passes_seed_quality_filter(
                route_type,
                combo_cards,
                strict=strict_quality_filter,
            )
            if not quality_ok:
                continue

            key = _candidate_key(route_type, combo_cards)
            if key in seen:
                continue
            seen.add(key)

            names = [card.name for card in combo_cards]
            raw_route_score = _candidate_route_score(route_type, combo_cards)
            route_score = max(0, min(100, raw_route_score - quality_penalty))
            if route_score < 35:
                continue

            padded = names + [""] * 3
            state_chain = str(plan["state_chain_template"]).format(
                a=padded[0],
                b=padded[1],
                c=padded[2],
            )
            avg_cost = sum(card.cost for card in combo_cards) / len(combo_cards)
            max_cost = max(card.cost for card in combo_cards)

            raw_candidates.append(
                {
                    "deck_name": f"route_seed {route_type}: {plan['name']} #{len(raw_candidates) + 1}",
                    "candidate_origin": "route_based",
                    "route_type": route_type,
                    "route_score": route_score,
                    "route_seed_cards": " / ".join(names),
                    "seed_cards": " / ".join(names),
                    "state_chain": state_chain,
                    "strategy_note": (
                        f"route_seed_generator v1。plan={plan['name']}。"
                        f"平均コスト={avg_cost:.2f} / 最大コスト={max_cost}。"
                        "この候補は保存前にroute_candidate_evaluatorで現実補正してください。"
                    ),
                    "avg_seed_cost": round(avg_cost, 2),
                    "max_seed_cost": max_cost,
                    "seed_quality_penalty": quality_penalty,
                    "seed_quality_reasons": ";".join(quality_reasons),
                    "strict_quality_filter": strict_quality_filter,
                }
            )

        raw_candidates.sort(key=lambda row: int(row.get("route_score") or 0), reverse=True)
        candidates.extend(raw_candidates[:per_route_limit])

    candidates.sort(key=lambda row: int(row.get("route_score") or 0), reverse=True)
    candidates = candidates[:max_candidates]

    if evaluate:
        candidates = evaluate_route_candidates(candidates, db_path)
        for row in candidates:
            penalty = int(row.get("seed_quality_penalty") or 0)
            adjusted = int(row.get("adjusted_route_score") or 0)
            row["adjusted_route_score"] = max(0, min(100, adjusted - penalty))
            if penalty >= 25:
                row["route_evaluation_comment"] = (
                    f"品質フィルターで{penalty}点の減点があります。"
                    f"理由: {row.get('seed_quality_reasons') or '-'}。"
                    "カード間の実接続と使用可能フォーマットを確認してください。"
                )
        candidates.sort(key=lambda row: int(row.get("adjusted_route_score") or 0), reverse=True)

    return candidates


def route_seed_candidates_to_markdown(candidates: list[dict[str, Any]], limit: int = 30) -> str:
    lines: list[str] = []
    lines.append("# route_seed_generator 生成候補")
    lines.append("")
    if not candidates:
        lines.append("候補は生成されませんでした。")
        return "\n".join(lines)

    columns = [
        "deck_name",
        "route_type",
        "route_score",
        "adjusted_route_score",
        "required_mana_estimate",
        "earliest_route_turn",
        "route_reproducibility_score",
        "route_risk_score",
        "nearest_known_combo",
        "known_combo_similarity",
        "route_seed_cards",
        "seed_quality_penalty",
        "seed_quality_reasons",
        "required_support_roles",
    ]
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for row in candidates[:limit]:
        lines.append("| " + " | ".join(str(row.get(col, "")).replace("\n", " ") for col in columns) + " |")

    lines.append("")
    lines.append("## 上位候補詳細")
    lines.append("")
    for index, row in enumerate(candidates[:10], start=1):
        lines.append(f"### {index}. {row.get('deck_name', '-')}")
        lines.append(f"- route_type: {row.get('route_type', '-')}")
        lines.append(f"- seed: {row.get('route_seed_cards', '-')}")
        lines.append(f"- adjusted_route_score: {row.get('adjusted_route_score', '-')}")
        lines.append(f"- required_mana_estimate: {row.get('required_mana_estimate', '-')}")
        lines.append(f"- earliest_route_turn: {row.get('earliest_route_turn', '-')}")
        lines.append(f"- reproducibility/risk: {row.get('route_reproducibility_score', '-')}/{row.get('route_risk_score', '-')}")
        lines.append(f"- nearest_known_combo: {row.get('nearest_known_combo', '-')}")
        lines.append(f"- target_meta_decks: {row.get('target_meta_decks', '-')}")
        lines.append(f"- comment: {row.get('route_evaluation_comment', '-')}")
        lines.append("")
    return "\n".join(lines)


def route_seed_candidates_to_csv(candidates: list[dict[str, Any]]) -> str:
    if not candidates:
        return ""

    preferred = [
        "deck_name",
        "candidate_origin",
        "route_type",
        "route_score",
        "adjusted_route_score",
        "required_mana_estimate",
        "earliest_route_turn",
        "route_reproducibility_score",
        "route_risk_score",
        "nearest_known_combo",
        "known_combo_similarity",
        "target_meta_decks",
        "route_seed_cards",
        "seed_quality_penalty",
        "seed_quality_reasons",
        "state_chain",
        "required_support_roles",
        "missing_support_states",
        "route_evaluation_comment",
        "strategy_note",
    ]
    extra = sorted({key for row in candidates for key in row.keys()} - set(preferred))
    columns = preferred + extra

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in candidates:
        writer.writerow(row)
    return output.getvalue()


def write_route_seed_outputs(
    output_dir: str | Path = "data/reports",
    db_path: str | Path = DEFAULT_DB_PATH,
    max_candidates: int = 50,
    strict_quality_filter: bool = True,
) -> dict[str, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = generate_route_seed_candidates(
        db_path=db_path,
        max_candidates=max_candidates,
        evaluate=True,
        strict_quality_filter=strict_quality_filter,
    )
    md_path = output_dir / "route_seed_candidates.md"
    csv_path = output_dir / "route_seed_candidates.csv"

    md_path.write_text(route_seed_candidates_to_markdown(candidates), encoding="utf-8")
    csv_path.write_text(route_seed_candidates_to_csv(candidates), encoding="utf-8-sig")

    return {"markdown": md_path, "csv": csv_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Project MANA route seed candidates.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="SQLite DB path")
    parser.add_argument("--out", default="data/reports", help="Output directory")
    parser.add_argument("--max", type=int, default=50, help="Max candidates")
    parser.add_argument(
        "--loose",
        action="store_true",
        help="Disable strict quality filtering. Useful for debugging raw seed generation.",
    )
    args = parser.parse_args()

    paths = write_route_seed_outputs(
        output_dir=args.out,
        db_path=args.db,
        max_candidates=args.max,
        strict_quality_filter=not args.loose,
    )
    print(f"markdown: {paths['markdown']}")
    print(f"csv: {paths['csv']}")


if __name__ == "__main__":
    main()

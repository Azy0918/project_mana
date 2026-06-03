from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_EXPANDED_JSON = Path("data/reports/expanded_route_decks/expanded_route_decks.json")
DEFAULT_EXPANDED_MD = Path("data/reports/expanded_route_decks/expanded_route_decks.md")
DEFAULT_OUT_DIR = Path("data/reports/expanded_route_decks")

CIVS = ["光", "水", "闇", "火", "自然"]


GENERIC_SHARED_TAGS = {
    "クリーチャー",
    "呪文",
    "低コスト",
    "軽量",
    "初動候補",
    "リソース",
    "受け札",
    "S・トリガー",
    "多色",
}

MEANINGFUL_CONNECTION_TAGS = {
    "ロック",
    "呪文ロック",
    "攻撃制限",
    "踏み倒し",
    "踏み倒しメタ",
    "リアニメイト",
    "墓地利用",
    "マナ加速",
    "マナ利用",
    "コスト軽減",
    "打点",
    "フィニッシャー",
    "フィニッシャー候補",
    "シールド圧力",
    "シールド追加",
    "ドロー",
    "サーチ候補",
    "山札操作",
    "ハンデス",
    "除去",
    "破壊",
    "バウンス",
    "タップ",
    "耐性",
    "コンボ",
}

ATTACK_TAGS = {
    "打点",
    "フィニッシャー",
    "フィニッシャー候補",
    "シールド圧力",
    "即効性",
}


def split_tags(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(x).strip() for x in value if str(x).strip()}
    text = str(value or "")
    return {x.strip() for x in re.split(r"[;,]", text) if x.strip()}


def split_civ(value: str) -> set[str]:
    text = str(value or "")
    return {civ for civ in CIVS if civ in text}


def card_name(card: dict[str, Any]) -> str:
    return str(card.get("name") or card.get("card_name") or "").strip()


def card_count(card: dict[str, Any]) -> int:
    try:
        return int(card.get("count") or card.get("枚数") or 0)
    except Exception:
        return 0


def card_cost(card: dict[str, Any]) -> int:
    try:
        return int(float(str(card.get("cost") or 0)))
    except Exception:
        return 0


def card_type(card: dict[str, Any]) -> str:
    return str(card.get("card_type") or card.get("type") or card.get("種類") or "")


def card_civ(card: dict[str, Any]) -> str:
    return str(card.get("civilization") or card.get("文明") or "")


def is_creature(card: dict[str, Any]) -> bool:
    return "クリーチャー" in card_type(card)


def is_evolution(card: dict[str, Any]) -> bool:
    t = card_type(card)
    text = str(card.get("text") or "")
    tags = split_tags(card.get("tags"))
    return "進化クリーチャー" in t or "進化" in t or "進化" in text or "進化" in tags


def is_attack_card(card: dict[str, Any]) -> bool:
    tags = split_tags(card.get("tags"))
    if not is_creature(card):
        return False

    cost = card_cost(card)

    if is_evolution(card):
        return bool(tags & ATTACK_TAGS)

    if tags & ATTACK_TAGS:
        return True

    if cost <= 2 and "ブロッカー" not in tags:
        return True

    if cost >= 4 and "ブロッカー" not in tags and "受け札" not in tags:
        return True

    return False


def is_meaningful_attack_card(card: dict[str, Any]) -> bool:
    tags = split_tags(card.get("tags"))
    if not is_attack_card(card):
        return False
    if tags & ATTACK_TAGS:
        return True
    return card_cost(card) <= 2 and is_creature(card) and not is_evolution(card)


def evolution_base_candidates(deck_cards: list[dict[str, Any]], evo_card: dict[str, Any]) -> list[dict[str, Any]]:
    evo_civs = split_civ(card_civ(evo_card))
    broad = len(evo_civs) >= 3 or not evo_civs

    candidates = []
    for c in deck_cards:
        if card_name(c) == card_name(evo_card):
            continue
        if not is_creature(c):
            continue
        if is_evolution(c):
            continue
        c_civs = split_civ(card_civ(c))
        if broad or not evo_civs or evo_civs & c_civs:
            candidates.append(c)
    return candidates


def shared_seed_tags(seed_cards: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    if not seed_cards:
        return set(), set()
    tag_sets = [split_tags(c.get("tags")) for c in seed_cards]
    tag_sets = [s for s in tag_sets if s]
    if not tag_sets:
        return set(), set()
    shared = set.intersection(*tag_sets)
    meaningful = (shared - GENERIC_SHARED_TAGS) & MEANINGFUL_CONNECTION_TAGS
    return shared, meaningful


def load_json_decks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["decks", "expanded_decks", "items", "results", "expansions"]:
            if isinstance(data.get(key), list):
                return data[key]
    return []


def parse_md_decks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    decks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_deck_table = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if line.startswith("# expanded "):
            if current:
                decks.append(current)
            current = {"deck_name": line.lstrip("# ").strip(), "cards": []}
            in_deck_table = False
            continue

        if current is None:
            continue

        if line.startswith("- route_type:"):
            current["route_type"] = line.split(":", 1)[1].strip()
        elif line.startswith("- route_seed_cards:"):
            current["route_seed_cards"] = line.split(":", 1)[1].strip()

        if line.startswith("| 枚数 | カード名 |"):
            in_deck_table = True
            continue

        if in_deck_table:
            if not line.startswith("|"):
                in_deck_table = False
                continue
            if "---" in line:
                continue

            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 7:
                continue
            if not re.fullmatch(r"\d+", cells[0]):
                continue

            current["cards"].append(
                {
                    "count": int(cells[0]),
                    "name": cells[1],
                    "civilization": cells[2],
                    "cost": cells[3],
                    "card_type": cells[4],
                    "role": cells[5],
                    "tags": cells[6],
                }
            )

    if current:
        decks.append(current)

    return decks


def normalize_deck(deck: dict[str, Any]) -> dict[str, Any]:
    cards = None
    for key in ["cards", "deck", "deck_cards", "card_rows", "list"]:
        if isinstance(deck.get(key), list):
            cards = deck[key]
            break
    if cards is None:
        cards = []

    norm_cards = []
    for c in cards:
        if not isinstance(c, dict):
            continue
        norm_cards.append(
            {
                "count": card_count(c),
                "name": card_name(c),
                "civilization": c.get("civilization") or c.get("文明") or "",
                "cost": c.get("cost") or c.get("コスト") or "",
                "card_type": c.get("card_type") or c.get("type") or c.get("種類") or "",
                "role": c.get("role") or "",
                "tags": c.get("tags") or "",
                "text": c.get("text") or "",
            }
        )

    out = dict(deck)
    out["cards"] = norm_cards
    return out


def get_seed_names(deck: dict[str, Any]) -> list[str]:
    raw = deck.get("route_seed_cards") or deck.get("seed") or ""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [x.strip() for x in str(raw).split("/") if x.strip()]


def civilization_counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    counts = {civ: 0 for civ in CIVS}
    for c in cards:
        civs = split_civ(card_civ(c))
        cnt = card_count(c)
        for civ in civs:
            counts[civ] += cnt
    return counts


def civilization_requirements(cards: list[dict[str, Any]]) -> dict[str, int]:
    req = {civ: 0 for civ in CIVS}
    for c in cards:
        civs = split_civ(card_civ(c))
        cnt = card_count(c)
        for civ in civs:
            req[civ] += cnt
    return req


def audit_mana_base(cards: list[dict[str, Any]], seed_cards: list[dict[str, Any]]) -> tuple[list[str], list[str], dict[str, int], dict[str, int]]:
    warnings: list[str] = []
    fatal: list[str] = []

    civ_available = civilization_counts(cards)
    civ_required = civilization_requirements(cards)

    for civ in CIVS:
        required = civ_required[civ]
        available = civ_available[civ]
        if required == 0:
            continue

        # Practical thresholds for a 40-card deck.
        if required >= 8 and available < 10:
            warnings.append(f"{civ}文明の供給が少なめ: 要求{required}枚 / 供給{available}枚")
        elif required >= 4 and available < 8:
            warnings.append(f"{civ}文明の供給がかなり少ない: 要求{required}枚 / 供給{available}枚")

    for seed in seed_cards:
        seed_civs = split_civ(card_civ(seed))
        cnt = card_count(seed)
        if len(seed_civs) >= 3:
            warnings.append(f"多文明seed注意: {card_name(seed)} は {card_civ(seed)}。実戦では色事故確認が必要")
        for civ in seed_civs:
            if civ_available[civ] < 8:
                warnings.append(f"seed文明不足: {card_name(seed)} に必要な {civ} が供給{civ_available[civ]}枚")

    return fatal, warnings, civ_available, civ_required


def audit_deck(deck: dict[str, Any]) -> dict[str, Any]:
    deck = normalize_deck(deck)
    cards = deck.get("cards", [])
    seed_names = set(get_seed_names(deck))
    seed_cards = [c for c in cards if card_name(c) in seed_names or str(c.get("role", "")) == "seed"]

    warnings: list[str] = []
    fatal: list[str] = []

    attack_cards = [c for c in cards if is_attack_card(c)]
    meaningful_attack_cards = [c for c in cards if is_meaningful_attack_card(c)]
    attack_count = sum(card_count(c) for c in attack_cards)
    meaningful_attack_count = sum(card_count(c) for c in meaningful_attack_cards)

    evo_cards = [c for c in cards if is_evolution(c)]
    for evo in evo_cards:
        bases = evolution_base_candidates(cards, evo)
        base_count = sum(card_count(c) for c in bases)
        evo_count = card_count(evo)
        threshold = 8
        if card_name(evo) in seed_names or str(evo.get("role", "")) == "seed":
            threshold = 12
        if base_count < threshold:
            msg = f"進化元不足: {card_name(evo)} {evo_count}枚に対して進化元候補 {base_count}枚"
            if card_name(evo) in seed_names or str(evo.get("role", "")) == "seed":
                fatal.append(msg)
            else:
                warnings.append(msg)

    shared, meaningful_shared = shared_seed_tags(seed_cards)
    if seed_cards and not meaningful_shared:
        warnings.append(
            "seed接続が弱い: 共有タグが実質的ではありません "
            f"(共有タグ: {', '.join(sorted(shared)) or '-'})"
        )

    if cards and meaningful_attack_count < 8:
        fatal.append(f"攻撃札不足: 実質攻撃札 {meaningful_attack_count}枚")
    elif meaningful_attack_count < 12:
        warnings.append(f"攻撃札が少なめ: 実質攻撃札 {meaningful_attack_count}枚")

    route_type = str(deck.get("route_type") or "")
    if route_type in {"damage_overflow_win", "lock_confirmed_win"} and meaningful_attack_count < 12:
        warnings.append(f"{route_type} に対して勝ち切り打点が少なめ: {meaningful_attack_count}枚")

    mana_fatal, mana_warnings, civ_available, civ_required = audit_mana_base(cards, seed_cards)
    fatal.extend(mana_fatal)
    warnings.extend(mana_warnings)

    if not cards:
        fatal.append("カード一覧を読み取れませんでした。expanded_route_decks.md または json の形式を確認してください。")

    verdict = "実戦候補"
    if fatal:
        verdict = "不採用"
    elif warnings:
        verdict = "要確認"

    return {
        "deck_name": deck.get("deck_name") or deck.get("name") or "",
        "route_type": route_type,
        "verdict": verdict,
        "fatal_count": len(fatal),
        "warning_count": len(warnings),
        "deck_size": sum(card_count(c) for c in cards),
        "attack_count": attack_count,
        "meaningful_attack_count": meaningful_attack_count,
        "evolution_count": sum(card_count(c) for c in evo_cards),
        "seed_shared_tags": ";".join(sorted(shared)),
        "seed_meaningful_shared_tags": ";".join(sorted(meaningful_shared)),
        "civ_available": civ_available,
        "civ_required": civ_required,
        "fatal": fatal,
        "warnings": warnings,
        "attack_cards": [card_name(c) for c in meaningful_attack_cards],
        "evolution_cards": [card_name(c) for c in evo_cards],
    }


def markdown_report(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# deck playability audit v3")
    lines.append("")
    if not rows:
        lines.append("監査対象がありません。")
        return "\n".join(lines)

    lines.append("| deck_name | verdict | fatal | warnings | deck_size | attack | evolution | meaningful_seed_tags |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in rows:
        lines.append(
            f"| {r['deck_name']} | {r['verdict']} | {r['fatal_count']} | {r['warning_count']} | "
            f"{r['deck_size']} | {r['meaningful_attack_count']} | {r['evolution_count']} | "
            f"{r['seed_meaningful_shared_tags'] or '-'} |"
        )

    for idx, r in enumerate(rows, start=1):
        lines.append("")
        lines.append(f"## {idx}. {r['deck_name']}")
        lines.append("")
        lines.append(f"- verdict: {r['verdict']}")
        lines.append(f"- route_type: {r['route_type']}")
        lines.append(f"- attack_count: {r['attack_count']}")
        lines.append(f"- meaningful_attack_count: {r['meaningful_attack_count']}")
        lines.append(f"- evolution_count: {r['evolution_count']}")
        lines.append(f"- seed_shared_tags: {r['seed_shared_tags'] or '-'}")
        lines.append(f"- seed_meaningful_shared_tags: {r['seed_meaningful_shared_tags'] or '-'}")
        lines.append(f"- civ_available: {r['civ_available']}")
        lines.append(f"- civ_required: {r['civ_required']}")
        lines.append("")
        if r["fatal"]:
            lines.append("### 不採用理由")
            for msg in r["fatal"]:
                lines.append(f"- {msg}")
            lines.append("")
        if r["warnings"]:
            lines.append("### 警告")
            for msg in r["warnings"]:
                lines.append(f"- {msg}")
            lines.append("")
        lines.append("### 実質攻撃札")
        if r["attack_cards"]:
            for name in r["attack_cards"]:
                lines.append(f"- {name}")
        else:
            lines.append("- なし")
        if r["evolution_cards"]:
            lines.append("")
            lines.append("### 進化カード")
            for name in r["evolution_cards"]:
                lines.append(f"- {name}")

    return "\n".join(lines)


def write_outputs(rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "deck_playability_audit.json"
    md_path = out_dir / "deck_playability_audit.md"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown_report(rows), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit expanded route decks for playability. v3 adds mana-base checks.")
    parser.add_argument("--expanded", default=str(DEFAULT_EXPANDED_JSON))
    parser.add_argument("--expanded-md", default=str(DEFAULT_EXPANDED_MD))
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    decks = load_json_decks(Path(args.expanded))
    if not decks or not any(normalize_deck(d).get("cards") for d in decks):
        decks = parse_md_decks(Path(args.expanded_md))

    rows = [audit_deck(deck) for deck in decks]
    paths = write_outputs(rows, Path(args.out))

    for key, path in paths.items():
        print(f"{key}: {path}")

    verdict_counts: dict[str, int] = {}
    for r in rows:
        verdict_counts[r["verdict"]] = verdict_counts.get(r["verdict"], 0) + 1
    print("verdict_counts:", verdict_counts)


if __name__ == "__main__":
    main()

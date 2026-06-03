from __future__ import annotations

import argparse
import html
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_DB = Path("data/cards.db")
DEFAULT_OUT = Path("data/reports/current_meta_import_report.md")

CURRENT_META_DECKS = [
    {
        "deck_name": "火光レイド",
        "format": "ND",
        "tier": "Current",
        "civilizations": "火/光",
        "deck_type": "ビート",
        "source_url": "https://kamigame.jp/%E3%83%87%E3%83%A5%E3%82%A8%E3%83%97%E3%83%AC/page/424307893676865413.html",
    },
    {
        "deck_name": "火水レイド",
        "format": "ND",
        "tier": "Current",
        "civilizations": "火/水",
        "deck_type": "ビート",
        "source_url": "https://kamigame.jp/%E3%83%87%E3%83%A5%E3%82%A8%E3%83%97%E3%83%AC/page/424307378482055404.html",
    },
    {
        "deck_name": "光単裁きの紋章Z",
        "format": "ND",
        "tier": "Current",
        "civilizations": "光",
        "deck_type": "カウンター",
        "source_url": "https://kamigame.jp/%E3%83%87%E3%83%A5%E3%82%A8%E3%83%97%E3%83%AC/page/424307549290941432.html",
    },
    {
        "deck_name": "水単スコーラー",
        "format": "ND",
        "tier": "Current",
        "civilizations": "水",
        "deck_type": "ワンショット",
        "source_url": "https://kamigame.jp/%E3%83%87%E3%83%A5%E3%82%A8%E3%83%97%E3%83%AC/page/424321997376345218.html",
    },
    {
        "deck_name": "自然単デンジャデオン",
        "format": "ND",
        "tier": "Current",
        "civilizations": "自然",
        "deck_type": "ビッグマナ",
        "source_url": "https://kamigame.jp/%E3%83%87%E3%83%A5%E3%82%A8%E3%83%97%E3%83%AC/page/424468721830999540.html",
    },
]


def fetch_text(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 Project-MANA-current-meta-importer-v3/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    res = requests.get(url, headers=headers, timeout=30)
    res.raise_for_status()
    if not res.encoding:
        res.encoding = res.apparent_encoding
    return res.text


def visible_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<script.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def recipe_section(raw_html: str) -> str:
    text = visible_text(raw_html)
    start = text.find("デッキの詳細レシピ")
    if start < 0:
        start = text.find("デッキレシピ")
    if start < 0:
        start = 0

    stop_words = [
        "超次元ゾーン",
        "デッキコード",
        "の特徴",
        "の回し方",
        "マスター・レジェンド到達",
        "入れ替え候補",
    ]
    end_candidates = []
    for stop in stop_words:
        idx = text.find(stop, start + 10)
        if idx > start:
            end_candidates.append(idx)
    end = min(end_candidates) if end_candidates else min(len(text), start + 10000)
    return text[start:end]


def norm(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\u3000", "")
    text = re.sub(r"\s+", "", text)
    replacements = {
        "／": "/",
        "（": "(",
        "）": ")",
        "［": "[",
        "］": "]",
        "【": "[",
        "】": "]",
        "“": '"',
        "”": '"',
        "＂": '"',
        "’": "'",
        "‘": "'",
        "－": "-",
        "―": "-",
        "〜": "～",
        "・": "",
        "《": "",
        "》": "",
        "「": "",
        "」": "",
        "『": "",
        "』": "",
        " ": "",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text.lower()


def load_official_names(db_path: Path) -> list[str]:
    con = sqlite3.connect(db_path)
    rows = con.execute("SELECT DISTINCT name FROM cards WHERE name IS NOT NULL AND name != ''").fetchall()
    con.close()
    return sorted({str(r[0]) for r in rows}, key=len, reverse=True)


def build_name_index(official_names: list[str]) -> dict[str, str]:
    idx: dict[str, str] = {}
    for name in official_names:
        n = norm(name)
        if n and n not in idx:
            idx[n] = name
    return idx


def strip_product_tail(segment: str) -> str:
    # The page often has: CardName ProductName 4枚
    # Remove known product labels from the end portion, not from actual card names.
    product_patterns = [
        r"スーパーマスターデッキ\d{4}",
        r"レジェプレ\d{4}",
        r"アーク\d{4}",
        r"第\d+弾",
        r"構築済みデッキ\d*",
    ]
    s = segment
    for pat in product_patterns:
        s = re.sub(pat, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def find_best_official_name(segment: str, official_names: list[str], name_index: dict[str, str]) -> str | None:
    cleaned = strip_product_tail(segment)
    nseg = norm(cleaned)

    # Exact normalized match after stripping product tail.
    if nseg in name_index:
        return name_index[nseg]

    # Longest official name contained near the end of the segment.
    best_name = None
    best_len = 0
    for name in official_names:
        nn = norm(name)
        if len(nn) < 3:
            continue
        pos = nseg.rfind(nn)
        if pos >= 0 and len(nn) > best_len:
            best_len = len(nn)
            best_name = name

    return best_name


def extract_recipe(raw_html: str, official_names: list[str]) -> tuple[list[dict[str, Any]], str]:
    section = recipe_section(raw_html)
    name_index = build_name_index(official_names)

    # Restrict to main recipe before evaluation links. This prevents duplicate cards later in the page.
    stop = section.find("《")
    if stop > 0:
        section_for_recipe = section[:stop]
    else:
        section_for_recipe = section

    # Remove heading text.
    section_for_recipe = re.sub(r"^.*?カード\s+関連商品\s+枚数", " ", section_for_recipe, flags=re.S)
    section_for_recipe = re.sub(r"\s+", " ", section_for_recipe).strip()

    # Split by valid main-deck count marker. Important:
    # - Do NOT match 2026 as 6枚 or 62枚.
    # - Count is 1-4 only, followed by 枚.
    # - The card/product segment is text before that marker.
    parts = re.split(r"([1-4])枚", section_for_recipe)

    recipe: list[dict[str, Any]] = []
    cursor = ""
    for i in range(0, len(parts) - 1, 2):
        segment = (cursor + " " + parts[i]).strip()
        count = int(parts[i + 1])
        name = find_best_official_name(segment, official_names, name_index)
        if name:
            recipe.append({"name": name, "count": count, "raw_segment": strip_product_tail(segment)})
        cursor = ""

    # Deduplicate while preserving order.
    out: list[dict[str, Any]] = []
    seen = set()
    for r in recipe:
        if r["name"] in seen:
            continue
        seen.add(r["name"])
        out.append(r)

    return out, section


def ensure_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta_decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            deck_name TEXT,
            format TEXT,
            tier TEXT,
            civilizations TEXT,
            deck_type TEXT,
            key_cards TEXT,
            favorable_matchups TEXT,
            unfavorable_matchups TEXT,
            source_name TEXT,
            source_url TEXT,
            confidence INTEGER,
            observed_at TEXT,
            notes TEXT,
            good_matchups TEXT,
            bad_matchups TEXT
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS meta_deck_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deck_name TEXT NOT NULL,
            format TEXT,
            source_url TEXT,
            card_name TEXT NOT NULL,
            count INTEGER NOT NULL,
            raw_line TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def upsert_meta(con: sqlite3.Connection, deck: dict[str, Any], recipe: list[dict[str, Any]]) -> None:
    deck_name = deck["deck_name"]
    fmt = deck["format"]
    total = sum(r["count"] for r in recipe)
    confidence = 95 if total == 40 else 75 if total >= 30 else 40
    key_cards = ";".join(r["name"] for r in recipe)

    con.execute(
        """
        DELETE FROM meta_decks
        WHERE deck_name = ? AND format = ? AND source_name LIKE '神ゲー攻略 第36弾現在流行中%'
        """,
        (deck_name, fmt),
    )
    con.execute(
        """
        INSERT INTO meta_decks (
            deck_name, format, tier, civilizations, deck_type, key_cards,
            favorable_matchups, unfavorable_matchups, source_name, source_url,
            confidence, observed_at, notes, good_matchups, bad_matchups
        ) VALUES (?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, date('now'), ?, '', '')
        """,
        (
            deck_name,
            fmt,
            deck["tier"],
            deck["civilizations"],
            deck["deck_type"],
            key_cards,
            "神ゲー攻略 第36弾現在流行中",
            deck["source_url"],
            confidence,
            "神ゲー攻略の現在流行中ページからデッキ詳細レシピを抽出。meta_deck_cardsに枚数保存。v3 extractor.",
        ),
    )

    con.execute(
        "DELETE FROM meta_deck_cards WHERE deck_name = ? AND format = ? AND source_url = ?",
        (deck_name, fmt, deck["source_url"]),
    )
    for r in recipe:
        con.execute(
            """
            INSERT INTO meta_deck_cards (deck_name, format, source_url, card_name, count, raw_line)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (deck_name, fmt, deck["source_url"], r["name"], int(r["count"]), r.get("raw_segment", "")),
        )


def write_report(rows: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# current meta import report v3")
    lines.append("")
    lines.append("神ゲー攻略の第36弾「現在流行中｜環境デッキ候補」をMANAの `meta_decks` / `meta_deck_cards` に取り込みました。")
    lines.append("")
    lines.append("| deck_name | status | card_kinds | deck_size | confidence |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for r in rows:
        lines.append(f"| {r['deck_name']} | {r['status']} | {r['card_kinds']} | {r['deck_size']} | {r['confidence']} |")

    for r in rows:
        lines.append("")
        lines.append(f"## {r['deck_name']}")
        lines.append("")
        lines.append(f"- source_url: {r['source_url']}")
        lines.append(f"- status: {r['status']}")
        lines.append(f"- deck_size: {r['deck_size']}")
        lines.append(f"- confidence: {r['confidence']}")
        lines.append("")
        for card in r.get("cards", []):
            lines.append(f"- {card['count']} {card['name']}")
        if r.get("debug_section") and r["deck_size"] != 40:
            lines.append("")
            lines.append("<details><summary>debug recipe section preview</summary>")
            lines.append("")
            lines.append("```text")
            lines.append(r["debug_section"][:1800])
            lines.append("```")
            lines.append("")
            lines.append("</details>")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import current Kamigame meta recipe into MANA DB. v3 fixes 2026-count parsing.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--sleep", type=float, default=0.5)
    args = parser.parse_args()

    db_path = Path(args.db)
    official_names = load_official_names(db_path)
    con = sqlite3.connect(db_path)
    ensure_tables(con)

    rows: list[dict[str, Any]] = []
    for deck in CURRENT_META_DECKS:
        time.sleep(args.sleep)
        try:
            raw = fetch_text(deck["source_url"])
            recipe, section = extract_recipe(raw, official_names)
            total = sum(r["count"] for r in recipe)
            upsert_meta(con, deck, recipe)
            confidence = 95 if total == 40 else 75 if total >= 30 else 40
            rows.append(
                {
                    **deck,
                    "status": "ok" if total > 0 else "no_cards_extracted",
                    "card_kinds": len(recipe),
                    "deck_size": total,
                    "confidence": confidence,
                    "cards": recipe,
                    "debug_section": section,
                }
            )
        except Exception as exc:
            rows.append({**deck, "status": f"error: {exc}", "card_kinds": 0, "deck_size": 0, "confidence": 0, "cards": [], "debug_section": ""})

    con.commit()
    con.close()

    write_report(rows, Path(args.out))

    print("imported:", sum(1 for r in rows if r["deck_size"] > 0))
    print("report:", args.out)
    for r in rows:
        print(r["deck_name"], r["status"], "deck_size", r["deck_size"], "kinds", r["card_kinds"], "confidence", r["confidence"])


if __name__ == "__main__":
    main()

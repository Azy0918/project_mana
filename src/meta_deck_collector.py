from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import unescape
import importlib
from pathlib import Path
import re
import ssl
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.import_cards import DEFAULT_DB_PATH
import src.meta_deck_store as meta_deck_store


meta_deck_store = importlib.reload(meta_deck_store)


@dataclass(frozen=True)
class MetaDeckSource:
    source_name: str
    source_url: str
    format: str = ""
    confidence: int = 60


DEFAULT_META_SOURCES = [
    MetaDeckSource(
        source_name="神ゲー攻略 AllDivision最強デッキ",
        source_url="https://kamigame.jp/%E3%83%87%E3%83%A5%E3%82%A8%E3%83%97%E3%83%AC/%E3%83%87%E3%83%83%E3%82%AD/%E6%9C%80%E5%BC%B7%E3%83%87%E3%83%83%E3%82%AD.html",
        format="AD",
        confidence=75,
    ),
    MetaDeckSource(
        source_name="Gamerch デュエプレ最強デッキランキング",
        source_url="https://gamerch.com/duelmasters-plays/117427",
        format="",
        confidence=55,
    ),
    MetaDeckSource(
        source_name="スマホゲームNavi デュエプレ環境デッキ",
        source_url="https://games.appmatch.jp/gamewiki/duelmasters/177954811862244960/",
        format="ND",
        confidence=55,
    ),
]


DECK_KEYWORDS = [
    "ブランド",
    "アポロ",
    "ドルマゲドン",
    "サッヴァーク",
    "モルト",
    "NEXT",
    "墓地",
    "水単",
    "火水",
    "火光",
    "水闇",
    "闇自然",
    "光水",
    "光闇",
    "自然",
    "ビート",
    "コントロール",
    "コンボ",
    "速攻",
    "ドラゴン",
    "魔導具",
    "エグザイル",
    "グッドスタッフ",
]


TIER_PATTERN = re.compile(r"(?:Tier|ティア)\s*([SABC])", re.IGNORECASE)
RANKED_NAME_PATTERN = re.compile(r"^(?:[0-9０-９]+[位.)．、\s]+)?(.{2,36}?)(?:デッキ)?(?:\s*(?:Tier|ティア)\s*[SABC])?$")


def collect_default_meta_decks(
    db_path: Path = DEFAULT_DB_PATH,
    delay_seconds: float = 1.0,
    verify_ssl: bool = True,
    allowed_tiers: set[str] | None = None,
    replace_existing_sources: bool = False,
) -> dict[str, Any]:
    return collect_meta_decks_from_sources(
        DEFAULT_META_SOURCES,
        db_path=db_path,
        delay_seconds=delay_seconds,
        verify_ssl=verify_ssl,
        allowed_tiers=allowed_tiers,
        replace_existing_sources=replace_existing_sources,
    )


def collect_meta_decks_from_sources(
    sources: list[MetaDeckSource],
    db_path: Path = DEFAULT_DB_PATH,
    delay_seconds: float = 1.0,
    verify_ssl: bool = True,
    allowed_tiers: set[str] | None = None,
    replace_existing_sources: bool = False,
) -> dict[str, Any]:
    all_candidates: list[dict[str, Any]] = []
    source_results = []
    saved_rows = []
    errors = []

    if replace_existing_sources:
        _delete_source_rows([source.source_name for source in sources], db_path)

    for index, source in enumerate(sources):
        if index > 0 and delay_seconds > 0:
            time.sleep(delay_seconds)
        try:
            html = fetch_html(source.source_url, verify_ssl=verify_ssl)
            candidates = extract_meta_deck_candidates(html, source)
            if allowed_tiers:
                candidates = [candidate for candidate in candidates if candidate["tier"] in allowed_tiers]
            all_candidates.extend(candidates)
            source_results.append(
                {
                    "情報源": source.source_name,
                    "候補": len(candidates),
                    "URL": source.source_url,
                }
            )
        except Exception as exc:
            errors.append(
                {
                    "情報源": source.source_name,
                    "URL": source.source_url,
                    "エラー": str(exc),
                }
            )

    for candidate in all_candidates:
        if meta_deck_store.meta_deck_exists(candidate["deck_name"], candidate["source_url"], db_path=db_path):
            continue
        saved_id = meta_deck_store.save_meta_deck(
            deck_name=candidate["deck_name"],
            format=candidate["format"],
            tier=candidate["tier"],
            civilizations=candidate["civilizations"],
            deck_type=candidate["deck_type"],
            key_cards=candidate["key_cards"],
            favorable_matchups="",
            unfavorable_matchups="",
            source_name=candidate["source_name"],
            source_url=candidate["source_url"],
            confidence=candidate["confidence"],
            observed_at=candidate["observed_at"],
            notes=candidate["notes"],
            db_path=db_path,
        )
        saved_rows.append({"ID": saved_id, **candidate})

    return {
        "source_results": source_results,
        "candidate_count": len(all_candidates),
        "saved_count": len(saved_rows),
        "saved_rows": saved_rows,
        "errors": errors,
    }


def _delete_source_rows(source_names: list[str], db_path: Path) -> None:
    if not source_names:
        return
    import sqlite3

    placeholders = ",".join("?" for _ in source_names)
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"DELETE FROM meta_decks WHERE source_name IN ({placeholders})", source_names)
        conn.commit()


def fetch_html(url: str, timeout: int = 20, verify_ssl: bool = True) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 ProjectMANA/1.0 (+meta deck research)",
            "Accept-Language": "ja,en-US;q=0.8,en;q=0.5",
        },
    )
    context = None if verify_ssl else ssl._create_unverified_context()
    try:
        with urlopen(request, timeout=timeout, context=context) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except URLError as exc:
        raise RuntimeError(f"取得に失敗しました: {exc}") from exc


def extract_meta_deck_candidates(html: str, source: MetaDeckSource) -> list[dict[str, Any]]:
    title = _extract_title(html)
    text = _html_to_text(html)
    lines = _clean_lines(text)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_tier = "調査中"

    for line in lines:
        tier_match = TIER_PATTERN.search(line)
        if tier_match:
            current_tier = tier_match.group(1).upper()

        deck_name = _extract_deck_name(line)
        if not deck_name or deck_name in seen:
            continue
        if not _looks_like_deck_name(deck_name):
            continue

        seen.add(deck_name)
        candidates.append(
            {
                "deck_name": deck_name,
                "format": _infer_format(line, source.format),
                "tier": _infer_tier(line, current_tier),
                "civilizations": _infer_civilizations(deck_name),
                "deck_type": _infer_deck_type(deck_name),
                "key_cards": _infer_key_cards(deck_name),
                "source_name": source.source_name,
                "source_url": source.source_url,
                "confidence": source.confidence,
                "observed_at": date.today().isoformat(),
                "notes": f"自動収集: {title}",
            }
        )

    return candidates[:30]


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip()


def _html_to_text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</?(?:h[1-6]|p|li|tr|td|th|div|section|article|br)[^>]*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    return unescape(html)


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if 2 <= len(line) <= 80:
            lines.append(line)
    return lines


def _extract_deck_name(line: str) -> str:
    line = re.sub(r"^【[^】]+】", "", line).strip()
    line = re.sub(r"(デッキレシピ|回し方|対策|解説|ランキング|一覧|おすすめ|最強|環境版)", "", line).strip()
    line = re.sub(r"(?:Tier|ティア)\s*[SABC]", "", line, flags=re.IGNORECASE).strip()
    line = re.split(r"[【《]|作成難度|操作難度|採用文明|特徴|評価", line, maxsplit=1)[0].strip()
    match = RANKED_NAME_PATTERN.match(line)
    if not match:
        return ""
    name = match.group(1).strip(" -｜|:：[]【】")
    name = re.sub(r"\s+", "", name)
    return name


def _looks_like_deck_name(name: str) -> bool:
    if len(name) < 3 or len(name) > 28:
        return False
    generic_names = {
        "ビート",
        "ビート型",
        "コントロール",
        "コントロール型",
        "コンボ",
        "速攻",
        "速攻型",
        "ランプ",
        "中速",
        "耐久",
        "墓地利用",
    }
    if name in generic_names:
        return False
    bad_words = [
        "更新",
        "目次",
        "この記事",
        "コメント",
        "メニュー",
        "ログイン",
        "カード一覧",
        "攻略",
        "作成難度",
        "操作難度",
        "弱い",
        "リスク",
        "シナジー",
        "並べ",
        "勝利",
        "浮上",
        "現在",
        "台頭",
        "クリーチャー",
        "除去コントロールに",
        "マナ事故",
    ]
    if any(word in name for word in bad_words):
        return False
    if len(name) >= 14 and any(marker in name for marker in ["が", "を", "に", "で", "する", "した"]):
        return False
    return any(keyword in name for keyword in DECK_KEYWORDS)


def _infer_format(line: str, default: str) -> str:
    upper = line.upper()
    if "NEW" in upper or "ND" in upper or "NEW DIVISION" in upper:
        return "ND"
    if "ALL" in upper or "AD" in upper or "ALL DIVISION" in upper:
        return "AD"
    return default or "調査中"


def _infer_tier(line: str, current_tier: str) -> str:
    match = TIER_PATTERN.search(line)
    if match:
        return match.group(1).upper()
    return current_tier


def _infer_civilizations(name: str) -> str:
    civs = []
    for civ in ["光", "水", "闇", "火", "自然"]:
        if civ in name:
            civs.append(civ)
    return "/".join(civs)


def _infer_deck_type(name: str) -> str:
    if any(word in name for word in ["速攻", "ブランド", "アポロ", "ビート"]):
        return "速攻"
    if any(word in name for word in ["コントロール", "ロック", "ハンデス"]):
        return "コントロール"
    if any(word in name for word in ["コンボ", "ループ", "魔導具"]):
        return "コンボ"
    if any(word in name for word in ["墓地", "ドルマゲドン"]):
        return "墓地利用"
    if any(word in name for word in ["モルト", "NEXT", "ドラゴン"]):
        return "ランプ"
    return "調査中"


def _infer_key_cards(name: str) -> str:
    return ";".join([keyword for keyword in DECK_KEYWORDS if keyword in name][:5])

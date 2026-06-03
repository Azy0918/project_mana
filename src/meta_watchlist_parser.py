from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


HIGH_RATE_KEYWORDS = ["最高レート", "瞬間1位", "レート1600", "1600到達", "1700到達", "レジェンド到達", "最終レジェンド", "最終順位"]
TOURNAMENT_KEYWORDS = ["優勝", "準優勝", "入賞", "ベスト4", "ベスト8", "公認大会", "タカラトミー杯", "非公式大会"]
WINRATE_KEYWORDS = ["勝率", "勝率上昇", "使用率上昇", "急増", "増えている", "メタに刺さる", "環境に刺さる"]
MATCHUP_KEYWORDS = ["対策", "メタ", "刺さる", "完封", "有利", "不利", "苦手", "勝てる", "負ける"]
OVERSEAS_KEYWORDS = ["海外", "中国版", "台湾版", "韓国版", "先行環境", "海外サーバー"]
EXTERNAL_ZONE_KEYWORDS = ["超次元", "サイキック", "ドラグハート", "外部ゾーン", "次元枠", "超次元ゾーン", "差し替え"]
PAPER_DIFF_KEYWORDS = ["紙", "TCG版", "紙では", "デュエプレ版", "効果差分", "強化", "ナーフ", "調整", "別効果"]
ROGUE_KEYWORDS = ["ローグ", "新型", "新構築", "新デッキ", "メタ外", "初見", "地雷"]

KNOWN_DECK_HINTS = [
    "火光レイド",
    "火水レイド",
    "赤白レイド",
    "赤青レイド",
    "黒緑ドンジャングル",
    "青単スコーラー",
    "水単スコーラー",
    "黒単デスザーク",
    "闇単デスザーク",
    "白単サバキZ",
    "光単裁きの紋章Z",
    "自然単デンジャデオン",
    "アナカラーQQQX",
]


def parse_meta_watchlist_note(
    note_text: str,
    source_type: str = "",
    source_name: str = "",
    source_url: str = "",
    format_name: str = "",
    memo: str = "",
    db_path: str | Path = "data/cards.db",
) -> dict[str, Any]:
    blob = "\n".join(str(x or "") for x in [source_type, source_name, source_url, format_name, note_text, memo])
    detected_rate = _hits(blob, HIGH_RATE_KEYWORDS)
    detected_tournament = _hits(blob, TOURNAMENT_KEYWORDS)
    detected_winrate = _hits(blob, WINRATE_KEYWORDS)
    detected_matchup_words = _hits(blob, MATCHUP_KEYWORDS)
    detected_region = _hits(blob, OVERSEAS_KEYWORDS)
    detected_external_words = _hits(blob, EXTERNAL_ZONE_KEYWORDS)
    detected_paper = _hits(blob, PAPER_DIFF_KEYWORDS)
    detected_rogue = _hits(blob, ROGUE_KEYWORDS)

    detected_cards = _detect_cards(blob, Path(db_path))
    detected_deck_names = _detect_deck_names(blob)
    detected_matchups = _detect_matchups(blob, detected_deck_names)
    detected_external_zone_cards = [
        name for name in detected_cards
        if any(keyword in name for keyword in EXTERNAL_ZONE_KEYWORDS)
    ]

    seed_type = _select_seed_type(
        detected_rate,
        detected_tournament,
        detected_winrate,
        detected_matchup_words,
        detected_region,
        detected_external_words,
        detected_paper,
        detected_rogue,
        source_type,
        source_name,
    )
    priority = _priority_for(seed_type, bool(source_url))
    confidence = _confidence_for(seed_type, source_type, source_name, detected_cards, detected_deck_names)
    required_tags, avoid_tags = _tags_for(seed_type, blob)
    strategy_hint = _strategy_hint(seed_type, detected_deck_names, detected_matchups)

    return {
        "source_category": _source_category(source_type, source_name, source_url),
        "seed_type": seed_type,
        "priority": priority,
        "confidence": confidence,
        "format": format_name or _detect_format(blob),
        "detected_cards": detected_cards,
        "detected_deck_names": detected_deck_names,
        "detected_matchups": detected_matchups,
        "detected_external_zone_cards": detected_external_zone_cards,
        "detected_result_keywords": sorted(set(detected_tournament + detected_winrate + detected_rogue)),
        "detected_rate_keywords": detected_rate,
        "detected_tournament_keywords": detected_tournament,
        "detected_region_keywords": detected_region,
        "paper_diff_flag": bool(detected_paper),
        "mana_action": mana_action_for(seed_type),
        "strategy_hint": strategy_hint,
        "required_tags": required_tags,
        "avoid_tags": avoid_tags,
        "source_type": source_type,
        "source_name": source_name,
        "source_url": source_url,
        "note_text": note_text,
        "memo": memo,
        "candidate_origin": candidate_origin_for(seed_type),
    }


def mana_action_for(seed_type: str) -> str:
    actions = {
        "high_rate_recipe": "レシピを環境DB候補として登録し、既存環境デッキとの構造差分を確認する。",
        "tournament_result": "入賞デッキとして信頼度高めに扱い、対面・勝ち筋・採用カードを解析する。",
        "winrate_spike": "勝率急上昇デッキとして、苦手対面と有利対面を重点確認する。",
        "matchup_counter": "特定対面へのメタ候補として、対策タグと差し替え候補を探索する。",
        "overseas_meta": "海外先行環境seedとして、日本版カードプールで再現可能か確認する。",
        "external_zone_tech": "外部ゾーン差し替え候補として、通常40枚とは別枠で保存する。",
        "paper_diff_hypothesis": "デュエプレ版公式テキストを優先し、紙評価との差分を効果構造解析へ渡す。",
        "rogue_deck_signal": "ローグデッキ兆候として、未知性スコアと環境対策性能を確認する。",
        "manual_meta_note": "研究メモとして保存し、関連カードや対面が増えたらseed化する。",
    }
    return actions.get(seed_type, actions["manual_meta_note"])


def candidate_origin_for(seed_type: str) -> str:
    if seed_type == "external_zone_tech":
        return "external_zone_based"
    if seed_type == "overseas_meta":
        return "overseas_based"
    if seed_type == "paper_diff_hypothesis":
        return "paper_diff_based"
    if seed_type in {"matchup_counter", "winrate_spike", "high_rate_recipe", "tournament_result"}:
        return "meta_counter_based"
    if seed_type == "rogue_deck_signal":
        return "rogue_signal_based"
    return "rogue_signal_based"


def _select_seed_type(
    rate: list[str],
    tournament: list[str],
    winrate: list[str],
    matchup: list[str],
    region: list[str],
    external: list[str],
    paper: list[str],
    rogue: list[str],
    source_type: str,
    source_name: str,
) -> str:
    source_blob = f"{source_type} {source_name}".lower()
    if external:
        return "external_zone_tech"
    if paper:
        return "paper_diff_hypothesis"
    if region:
        return "overseas_meta"
    if rate:
        return "high_rate_recipe"
    if tournament:
        return "tournament_result"
    if winrate and ("beans" in source_blob or "有志" in source_blob or "対戦データ" in source_blob):
        return "winrate_spike"
    if matchup:
        return "matchup_counter"
    if winrate:
        return "winrate_spike"
    if rogue:
        return "rogue_deck_signal"
    return "manual_meta_note"


def _priority_for(seed_type: str, has_url: bool) -> str:
    if seed_type in {"high_rate_recipe", "tournament_result", "winrate_spike"}:
        return "高"
    if seed_type in {"matchup_counter", "external_zone_tech", "paper_diff_hypothesis", "overseas_meta", "rogue_deck_signal"}:
        return "中" if not has_url else "高"
    return "低"


def _confidence_for(seed_type: str, source_type: str, source_name: str, cards: list[str], decks: list[str]) -> float:
    score = 0.45
    source_blob = f"{source_type} {source_name}".lower()
    if seed_type in {"high_rate_recipe", "tournament_result"}:
        score += 0.20
    if seed_type == "winrate_spike" and ("beans" in source_blob or "対戦データ" in source_blob):
        score += 0.25
    if seed_type == "overseas_meta":
        score = 0.55
    if cards:
        score += 0.10
    if decks:
        score += 0.10
    return round(max(0.1, min(0.95, score)), 2)


def _tags_for(seed_type: str, text: str) -> tuple[list[str], list[str]]:
    required: list[str] = []
    avoid: list[str] = []
    if seed_type == "matchup_counter":
        required.extend(["メタ", "除去", "ロック"])
    if seed_type == "winrate_spike":
        required.extend(["環境適性", "リソース"])
    if seed_type == "external_zone_tech":
        required.extend(["超次元", "サイキック"])
        avoid.append("通常40枚混入")
    if seed_type == "paper_diff_hypothesis":
        required.extend(["効果差分", "状態変換"])
    if seed_type == "rogue_deck_signal":
        required.extend(["未知性", "コンボ"])
    if any(word in text for word in ["速攻", "早期", "詰める"]):
        required.append("打点")
    if any(word in text for word in ["受け", "トリガー", "耐える"]):
        required.append("受け札")
    return list(dict.fromkeys(required)), list(dict.fromkeys(avoid))


def _strategy_hint(seed_type: str, deck_names: list[str], matchups: list[str]) -> str:
    deck_text = " / ".join(deck_names) if deck_names else "デッキ名未特定"
    matchup_text = " / ".join(matchups) if matchups else "対面未特定"
    if seed_type == "external_zone_tech":
        return f"{deck_text}の外部ゾーン枠として扱い、{matchup_text}への差し替え効果を見る。"
    if seed_type == "paper_diff_hypothesis":
        return f"{deck_text}のデュエプレ版テキストを公式DBで確認し、紙評価との差分を効果構造に分解する。"
    if seed_type == "overseas_meta":
        return f"{deck_text}を海外先行環境seedとして、日本版カードプールで再現可能か確認する。"
    return f"{deck_text}をseedとして、{matchup_text}への有利理由と弱点を確認する。"


def _source_category(source_type: str, source_name: str, source_url: str) -> str:
    text = f"{source_type} {source_name} {source_url}".lower()
    if "x" in text or "twitter" in text or "最高レート" in text:
        return "x_social"
    if "beans" in text or "有志" in text or "攻略" in text:
        return "community_data"
    if any(k in text for k in ["海外", "中国", "台湾", "韓国"]):
        return "overseas"
    return source_type or "manual"


def _detect_format(text: str) -> str:
    upper = text.upper()
    if "ND" in upper or "NEW DIVISION" in upper:
        return "ND"
    if "AD" in upper or "ALL DIVISION" in upper:
        return "AD"
    return ""


def _detect_deck_names(text: str) -> list[str]:
    found = [name for name in KNOWN_DECK_HINTS if name in text]
    pattern_hits = re.findall(r"([一-龥ぁ-んァ-ヶA-Za-z0-9・/＋+]{2,12}(?:レイド|スコーラー|デスザーク|サバキZ|ドンジャングル|QQQX|ブランド|魔導具|デンジャデオン))", text)
    found.extend(pattern_hits)
    return list(dict.fromkeys(found))[:12]


def _detect_matchups(text: str, deck_names: list[str]) -> list[str]:
    found = []
    for name in deck_names:
        if any(prefix + name in text for prefix in ["対", "vs", "VS", "対面"]):
            found.append(name)
    for name in KNOWN_DECK_HINTS:
        if name in text and any(word in text for word in MATCHUP_KEYWORDS):
            found.append(name)
    return list(dict.fromkeys(found))[:12]


def _detect_cards(text: str, db_path: Path) -> list[str]:
    try:
        if not db_path.exists():
            return []
        con = sqlite3.connect(db_path)
        rows = con.execute("SELECT DISTINCT name FROM cards").fetchall()
        con.close()
        names = [str(row[0]) for row in rows if row and row[0]]
    except Exception:
        return []
    compact_text = _compact(text)
    found = []
    for name in names:
        if len(name) < 3:
            continue
        if name in text or _compact(name) in compact_text:
            found.append(name)
        if len(found) >= 40:
            break
    return found


def _hits(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value).replace("　", ""))

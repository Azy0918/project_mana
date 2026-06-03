from __future__ import annotations

import json
import os
import re
import sqlite3
import hashlib
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

DB_PATH = Path(os.getenv("MANA_DB_PATH", "data/cards.db"))
TRANSCRIPTS_DIR = Path(os.getenv("MANA_TRANSCRIPTS_DIR", "transcripts"))
REPORT_DIR = Path("reports/youtube_research")

KNOWN_CARDS = [
    "ドンジャングルS7", "ドンジャングルストロング7", "ドンジャングル",
    "ヤドック", "ジェニージェン", "ジェニージェーン", "ソーナンデス", "ソナンデス",
    "スペル・デル・フィン", "スペルデルフィン", "デルフィン", "ニコル・ボーラス", "ニコル",
    "ライフプラン・チャージャー", "ライフプランチャージャー", "ライフプラン",
    "龍罠 エスカルデン/マクスカルゴ・トラップ", "エスカルデン", "神秘の宝箱",
    "ジャスミン", "フェアリー・ライフ", "ミクセル", "オニカマス", "次元の嵐 スコーラー",
]

CARD_NORMALIZE = {
    "ドンジャングルストロング7": "ドンジャングルS7",
    "ドンジャングル": "ドンジャングルS7",
    "ジェニージェーン": "ジェニージェン",
    "ソナンデス": "ソーナンデス",
    "スペルデルフィン": "スペル・デル・フィン",
    "デルフィン": "スペル・デル・フィン",
    "ニコル": "ニコル・ボーラス",
    "ライフプランチャージャー": "ライフプラン・チャージャー",
    "ライフプラン": "ライフプラン・チャージャー",
    "龍罠 エスカルデン/マクスカルゴ・トラップ": "エスカルデン",
}

MATCHUP_PATTERNS = {
    "赤系レイド": ["赤レイド", "赤代レイド", "火光レイド", "火水レイド", "ブレイズレイド", "レイド"],
    "水単スコーラー": ["青単スコーラー", "青タースコーラー", "スコーラー"],
    "青緑デンジャレオン": ["青緑", "デンジャレオン", "デンジャー", "ツインパクト"],
}

POSITIVE_WORDS = ["強い", "刺さ", "有利", "勝て", "戦える", "完封", "偉い", "噛み合", "価値", "ほぼ勝ち"]
NEGATIVE_WORDS = ["弱い", "無駄", "危険", "苦しい", "崩れる", "破綻", "注意", "怖い", "怒られ", "困った"]
ROLE_KEYWORDS = {
    "踏み倒しメタ": ["踏み倒し", "出た時効果", "レイド", "スコーラー", "止める", "阻止"],
    "ハンデス": ["ハンデス", "手札", "抜", "落と", "キーパーツ"],
    "踏み倒し先": ["ドンジャングル", "マナから", "踏み倒", "出す"],
    "制圧": ["制圧", "負けない", "アタック誘導", "盤面", "残して"],
    "マナ加速/サーチ": ["ライフプラン", "エスカルデン", "ブースト", "マナを伸ば", "補充", "拾"],
    "フィニッシャー": ["詰め", "フィニッシュ", "勝ち", "殴って"],
}

@dataclass
class CardInsight:
    card_name: str
    role: str = "言及"
    reason: str = ""
    related_matchup: str = ""
    sentiment: str = "neutral"
    confidence: float = 0.55

@dataclass
class MatchupInsight:
    opponent_deck: str
    evaluation: str = "unknown"
    game_plan: str = ""
    key_cards: List[str] = field(default_factory=list)
    caution_points: List[str] = field(default_factory=list)
    confidence: float = 0.55

@dataclass
class PlayPattern:
    pattern_name: str
    description: str
    turn_range: str = ""
    required_cards: List[str] = field(default_factory=list)

@dataclass
class TranscriptKnowledge:
    video_title: str = ""
    video_url: str = ""
    video_id: str = ""
    file_path: str = ""
    deck_name: str = ""
    archetype: str = ""
    mentioned_cards: List[str] = field(default_factory=list)
    key_cards: List[str] = field(default_factory=list)
    main_plan: List[str] = field(default_factory=list)
    good_matchups: List[str] = field(default_factory=list)
    bad_matchups: List[str] = field(default_factory=list)
    matchup_notes: List[str] = field(default_factory=list)
    play_patterns: List[PlayPattern] = field(default_factory=list)
    mulligan_or_early_game_notes: List[str] = field(default_factory=list)
    strong_cards: List[str] = field(default_factory=list)
    weak_or_risky_cards: List[str] = field(default_factory=list)
    color_balance_notes: List[str] = field(default_factory=list)
    caution_points: List[str] = field(default_factory=list)
    improvement_ideas: List[str] = field(default_factory=list)
    card_insights: List[CardInsight] = field(default_factory=list)
    matchup_insights: List[MatchupInsight] = field(default_factory=list)
    raw_summary: str = ""
    used_ai: bool = False


def normalize_card_name(name: str) -> str:
    return CARD_NORMALIZE.get(name.strip(), name.strip())


def safe_slug(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[\\/:*?\"<>|\s]+", "_", text.strip())
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return text[:max_len]


def read_transcript(path: str | Path) -> Tuple[Dict[str, str], str]:
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    title = ""
    url = ""
    video_id = ""
    body_start = 0
    for i, line in enumerate(lines[:8]):
        s = line.strip()
        if not s:
            continue
        if "youtube.com" in s or "youtu.be" in s:
            url = s
            body_start = max(body_start, i + 1)
        elif not title and not s.startswith("["):
            title = s
            body_start = max(body_start, i + 1)
    if not title:
        title = p.stem
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url) or re.search(r"_([A-Za-z0-9_-]{8,})$", p.stem)
    if m:
        video_id = m.group(1)
    return {"video_title": title, "video_url": url, "video_id": video_id, "file_path": str(p)}, "\n".join(lines[body_start:])


def split_sentences(text: str) -> List[str]:
    compact = re.sub(r"\n", " ", text)
    parts = re.split(r"(?<=[。！？!?])\s*|\[\d{2}:\d{2}\]", compact)
    return [p.strip() for p in parts if len(p.strip()) >= 8]


def nearby_sentences(sentences: Sequence[str], keyword: str, window: int = 1) -> List[str]:
    hits: List[str] = []
    for i, s in enumerate(sentences):
        if keyword in s:
            lo, hi = max(0, i - window), min(len(sentences), i + window + 1)
            hits.append(" ".join(sentences[lo:hi]))
    return hits[:8]


def extract_cards(text: str, db_path: Path = DB_PATH) -> List[str]:
    cards = set()
    for c in KNOWN_CARDS:
        if c in text:
            cards.add(normalize_card_name(c))
    # 公式DBがある場合は、カード名一致を追加する。長い名前優先で誤検出を減らす。
    try:
        if db_path.exists():
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM cards")
            for (name,) in cur.fetchall():
                if name and len(name) >= 3 and name in text:
                    cards.add(name)
            conn.close()
    except Exception:
        pass
    return sorted(cards, key=lambda x: (-text.count(x), x))


def infer_role(sentence: str, card_name: str) -> str:
    for role, keys in ROLE_KEYWORDS.items():
        if any(k in sentence for k in keys):
            return role
    if card_name in ["ヤドック"]:
        return "踏み倒しメタ"
    if card_name in ["ジェニージェン"]:
        return "ハンデス/キーパーツ除去"
    if card_name in ["ドンジャングルS7"]:
        return "制圧/踏み倒しエンジン"
    if card_name in ["スペル・デル・フィン", "ニコル・ボーラス"]:
        return "踏み倒し先/フィニッシャー"
    if card_name in ["ライフプラン・チャージャー", "エスカルデン"]:
        return "マナ加速/手札調整"
    return "言及"


def sentiment_of(sentence: str) -> str:
    p = sum(1 for w in POSITIVE_WORDS if w in sentence)
    n = sum(1 for w in NEGATIVE_WORDS if w in sentence)
    if p > n:
        return "positive"
    if n > p:
        return "negative"
    return "neutral"


def extract_rule_based(path: str | Path, db_path: Path = DB_PATH) -> TranscriptKnowledge:
    meta, text = read_transcript(path)
    sentences = split_sentences(text)
    cards = extract_cards(text, db_path)
    k = TranscriptKnowledge(**meta)
    k.mentioned_cards = cards

    full = meta["video_title"] + "\n" + text
    if "黒緑" in full and "ドンジャングル" in full:
        k.deck_name = "黒緑ドンジャングル"
        k.archetype = "黒緑コントロール / ドンジャングル制圧"
    else:
        m = re.search(r"[『「]([^』」]{2,40}(?:ドンジャングル|レイド|スコーラー|コントロール)[^』」]*)[』」]", full)
        k.deck_name = m.group(1) if m else ""
        k.archetype = ""

    desired_key = ["ドンジャングルS7", "ヤドック", "ジェニージェン", "ソーナンデス", "スペル・デル・フィン", "ニコル・ボーラス", "ライフプラン・チャージャー", "エスカルデン"]
    k.key_cards = [c for c in desired_key if c in cards or any(alias in full for alias, norm in CARD_NORMALIZE.items() if norm == c)]

    # 対面抽出
    for matchup, pats in MATCHUP_PATTERNS.items():
        if any(p in full for p in pats):
            if any(w in full for w in ["有利", "戦える", "勝つ", "完封"]):
                k.good_matchups.append(matchup)
            else:
                k.matchup_notes.append(matchup)

    # 基本プランと注意点
    def add_if(cond: bool, arr: List[str], msg: str) -> None:
        if cond and msg not in arr:
            arr.append(msg)

    add_if("ヤドック" in full and ("踏み倒" in full or "レイド" in full or "スコーラー" in full), k.main_plan, "ヤドックでレイドやスコーラーなどの踏み倒し・着地を止める")
    add_if("ジェニージェ" in full and ("キーパーツ" in full or "手札" in full or "抜" in full), k.main_plan, "ジェニージェンで相手のキーパーツを落として行動を遅らせる")
    add_if("ドンジャングル" in full and "デルフィン" in full, k.main_plan, "ドンジャングルS7からスペル・デル・フィンを展開して呪文主体の返しを封じる")
    add_if("ドンジャングル" in full and "ニコル" in full, k.main_plan, "ドンジャングルS7からニコル・ボーラスを展開し、手札を削って詰める")
    add_if("制圧" in full or "負けない盤面" in full or "アタック誘導" in full, k.main_plan, "ドンジャングルS7のアタック誘導と大型展開で制圧してから詰める")

    add_if("色マナ" in full and ("ガッタガタ" in full or "破綻" in full), k.color_balance_notes, "色を増やしすぎるとマナ基盤が崩れ、受けが薄い構築では苦しくなる")
    add_if("黒10" in full or "黒マナ" in full, k.color_balance_notes, "黒マナ10枚は神秘の宝箱やライフプラン・チャージャー込みでギリギリ成立する")
    add_if("ドンジャングル経由" in full and "デルフィン" in full, k.caution_points, "スペル・デル・フィンは素出しよりドンジャングル経由で出す方が安全な場面がある")
    add_if("鬼カマス" in full and "バウンス" in full, k.caution_points, "オニカマス系がいる場面では踏み倒し先が戻されるため、先に盤面処理やマナ伸ばしを検討する")

    if "2ター" in full or "3ター" in full or "4マナ" in full:
        k.mulligan_or_early_game_notes.append("序盤はライフ系から入り、対面に応じてヤドックまたはライフプラン・チャージャーへつなぐ")
    if "ライフプラン" in full and "ソーナンデス" in full:
        k.mulligan_or_early_game_notes.append("ライフプラン・チャージャーでソーナンデスやドンジャングルS7を探し、Jチェンジに備える")

    # カード別インサイト
    for card in cards:
        contexts = []
        for alias, norm in CARD_NORMALIZE.items():
            if norm == card:
                contexts.extend(nearby_sentences(sentences, alias))
        contexts.extend(nearby_sentences(sentences, card))
        seen = set()
        for ctx in contexts[:4]:
            if ctx in seen:
                continue
            seen.add(ctx)
            related = ""
            for matchup, pats in MATCHUP_PATTERNS.items():
                if any(p in ctx for p in pats):
                    related = matchup
                    break
            k.card_insights.append(CardInsight(
                card_name=card,
                role=infer_role(ctx, card),
                reason=ctx[:280],
                related_matchup=related,
                sentiment=sentiment_of(ctx),
                confidence=0.72 if card in k.key_cards else 0.58,
            ))
    # 強弱カード
    k.strong_cards = sorted({ci.card_name for ci in k.card_insights if ci.sentiment == "positive" or ci.card_name in k.key_cards})
    k.weak_or_risky_cards = sorted({ci.card_name for ci in k.card_insights if ci.sentiment == "negative" and ci.card_name not in k.key_cards})

    # 対面インサイト
    for matchup in sorted(set(k.good_matchups + k.matchup_notes)):
        ctx = []
        for pat in MATCHUP_PATTERNS.get(matchup, [matchup]):
            ctx.extend(nearby_sentences(sentences, pat, window=2))
        joined = " ".join(ctx)[:700]
        eval_ = "favorable" if matchup in k.good_matchups else "even/unknown"
        key = [c for c in k.key_cards if c in joined or c in ["ヤドック", "ジェニージェン", "ドンジャングルS7"]]
        plan = joined[:360] if joined else "動画内で対面として言及あり"
        cautions = [p for p in k.caution_points if any(w in p for w in ["デルフィン", "色", "マナ"])]
        k.matchup_insights.append(MatchupInsight(matchup, eval_, plan, key, cautions, 0.68))

    # プレイパターン
    if {"ソーナンデス", "ドンジャングルS7"}.issubset(set(k.key_cards)):
        k.play_patterns.append(PlayPattern("ソーナンデスJチェンジ制圧", "ソーナンデスからドンジャングルS7へJチェンジし、盤面処理とマナからの踏み倒しを同時に狙う", "中盤", ["ソーナンデス", "ドンジャングルS7"]))
    if {"ドンジャングルS7", "スペル・デル・フィン"}.issubset(set(k.key_cards)):
        k.play_patterns.append(PlayPattern("ドンジャングル経由デルフィン", "ドンジャングルS7経由でスペル・デル・フィンを出し、マッハファイターや除去をケアしながら呪文を封じる", "7〜9マナ", ["ドンジャングルS7", "スペル・デル・フィン"]))
    if {"ヤドック", "ジェニージェン"}.issubset(set(k.key_cards)):
        k.play_patterns.append(PlayPattern("ヤドック＋ジェニージェン妨害", "ヤドックで踏み倒しを止めた状態でジェニージェンを通し、相手の手札のキーパーツを落とす", "序盤〜中盤", ["ヤドック", "ジェニージェン"]))

    k.raw_summary = make_summary(k)
    return k


def make_summary(k: TranscriptKnowledge) -> str:
    lines = [f"# {k.deck_name or k.video_title}", "", f"- archetype: {k.archetype}", f"- key_cards: {', '.join(k.key_cards)}"]
    if k.good_matchups:
        lines.append(f"- good_matchups: {', '.join(k.good_matchups)}")
    if k.main_plan:
        lines.append("\n## main_plan")
        lines += [f"- {x}" for x in k.main_plan]
    if k.color_balance_notes:
        lines.append("\n## color_balance_notes")
        lines += [f"- {x}" for x in k.color_balance_notes]
    if k.caution_points:
        lines.append("\n## caution_points")
        lines += [f"- {x}" for x in k.caution_points]
    return "\n".join(lines)


def ai_enrich(k: TranscriptKnowledge, transcript_text: str) -> TranscriptKnowledge:
    if not os.getenv("OPENAI_API_KEY"):
        return k
    try:
        from openai import OpenAI
        client = OpenAI()
        schema_hint = json.dumps({
            "deck_name": "", "archetype": "", "key_cards": [], "main_plan": [],
            "good_matchups": [], "bad_matchups": [], "matchup_notes": [],
            "mulligan_or_early_game_notes": [], "strong_cards": [], "weak_or_risky_cards": [],
            "color_balance_notes": [], "caution_points": [], "improvement_ideas": [],
            "card_insights": [{"card_name":"", "role":"", "reason":"", "related_matchup":"", "sentiment":"positive|neutral|negative", "confidence":0.0}],
            "matchup_insights": [{"opponent_deck":"", "evaluation":"favorable|even|unfavorable|unknown", "game_plan":"", "key_cards":[], "caution_points":[], "confidence":0.0}],
            "play_patterns": [{"pattern_name":"", "description":"", "turn_range":"", "required_cards":[]}]
        }, ensure_ascii=False)
        prompt = f"""You are Project MANA, a Duel Masters Plays deck research extractor.\nReturn ONLY JSON matching this shape: {schema_hint}\nExtract reusable deckbuilding, matchup and play knowledge. Do not invent facts not in transcript.\n\nCurrent rule-based draft:\n{json.dumps(asdict(k), ensure_ascii=False)[:5000]}\n\nTranscript:\n{transcript_text[:24000]}"""
        resp = client.responses.create(model=os.getenv("OPENAI_MODEL", "gpt-5-mini"), input=prompt)
        raw = getattr(resp, "output_text", "") or ""
        raw = raw.strip().strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
        data = json.loads(raw)
        for field_name in ["deck_name", "archetype"]:
            if data.get(field_name):
                setattr(k, field_name, data[field_name])
        for field_name in ["key_cards", "main_plan", "good_matchups", "bad_matchups", "matchup_notes", "mulligan_or_early_game_notes", "strong_cards", "weak_or_risky_cards", "color_balance_notes", "caution_points", "improvement_ideas"]:
            vals = data.get(field_name) or []
            if vals:
                merged = list(dict.fromkeys(list(getattr(k, field_name)) + vals))
                setattr(k, field_name, merged)
        for item in data.get("card_insights", []) or []:
            if item.get("card_name"):
                k.card_insights.append(CardInsight(**{**{"role":"言及","reason":"","related_matchup":"","sentiment":"neutral","confidence":0.7}, **item}))
        for item in data.get("matchup_insights", []) or []:
            if item.get("opponent_deck"):
                k.matchup_insights.append(MatchupInsight(**{**{"evaluation":"unknown","game_plan":"","key_cards":[],"caution_points":[],"confidence":0.7}, **item}))
        for item in data.get("play_patterns", []) or []:
            if item.get("pattern_name"):
                k.play_patterns.append(PlayPattern(**{**{"description":"","turn_range":"","required_cards":[]}, **item}))
        k.used_ai = True
        k.raw_summary = make_summary(k)
    except Exception as e:
        k.caution_points.append(f"AI抽出は失敗したためルールベース結果を使用: {e}")
    return k


def analyze_transcript(path: str | Path, db_path: Path = DB_PATH, use_ai: bool = True) -> TranscriptKnowledge:
    k = extract_rule_based(path, db_path)
    if use_ai:
        _, text = read_transcript(path)
        k = ai_enrich(k, text)
    return k


def init_transcript_db(db_path: str | Path = DB_PATH) -> None:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    cur = conn.cursor()
    cur.executescript("""
CREATE TABLE IF NOT EXISTS transcript_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_title TEXT,
  video_url TEXT,
  video_id TEXT,
  file_path TEXT UNIQUE,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS deck_knowledge (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER,
  deck_name TEXT,
  archetype TEXT,
  main_plan TEXT,
  color_balance_notes TEXT,
  caution_points TEXT,
  raw_summary TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(source_id) REFERENCES transcript_sources(id)
);
CREATE TABLE IF NOT EXISTS card_insights (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER,
  card_name TEXT,
  role TEXT,
  reason TEXT,
  related_matchup TEXT,
  sentiment TEXT,
  confidence REAL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(source_id) REFERENCES transcript_sources(id)
);
CREATE TABLE IF NOT EXISTS matchup_insights (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER,
  deck_name TEXT,
  opponent_deck TEXT,
  evaluation TEXT,
  game_plan TEXT,
  key_cards TEXT,
  caution_points TEXT,
  confidence REAL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(source_id) REFERENCES transcript_sources(id)
);
CREATE TABLE IF NOT EXISTS play_patterns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER,
  deck_name TEXT,
  pattern_name TEXT,
  description TEXT,
  turn_range TEXT,
  required_cards TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(source_id) REFERENCES transcript_sources(id)
);
""")
    conn.commit()
    conn.close()


def save_knowledge(k: TranscriptKnowledge, db_path: str | Path = DB_PATH) -> int:
    init_transcript_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
INSERT INTO transcript_sources(video_title, video_url, video_id, file_path, created_at)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(file_path) DO UPDATE SET video_title=excluded.video_title, video_url=excluded.video_url, video_id=excluded.video_id
""", (k.video_title, k.video_url, k.video_id, k.file_path, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    cur.execute("SELECT id FROM transcript_sources WHERE file_path=?", (k.file_path,))
    source_id = int(cur.fetchone()[0])
    # 再解析時は当該sourceの派生知識を差し替え
    for table in ["deck_knowledge", "card_insights", "matchup_insights", "play_patterns"]:
        cur.execute(f"DELETE FROM {table} WHERE source_id=?", (source_id,))
    cur.execute("""
INSERT INTO deck_knowledge(source_id, deck_name, archetype, main_plan, color_balance_notes, caution_points, raw_summary, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (source_id, k.deck_name, k.archetype, json.dumps(k.main_plan, ensure_ascii=False), json.dumps(k.color_balance_notes, ensure_ascii=False), json.dumps(k.caution_points, ensure_ascii=False), k.raw_summary, datetime.now().isoformat(timespec="seconds")))
    for ci in k.card_insights:
        cur.execute("""
INSERT INTO card_insights(source_id, card_name, role, reason, related_matchup, sentiment, confidence)
VALUES (?, ?, ?, ?, ?, ?, ?)
""", (source_id, ci.card_name, ci.role, ci.reason, ci.related_matchup, ci.sentiment, ci.confidence))
    for mi in k.matchup_insights:
        cur.execute("""
INSERT INTO matchup_insights(source_id, deck_name, opponent_deck, evaluation, game_plan, key_cards, caution_points, confidence)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (source_id, k.deck_name, mi.opponent_deck, mi.evaluation, mi.game_plan, json.dumps(mi.key_cards, ensure_ascii=False), json.dumps(mi.caution_points, ensure_ascii=False), mi.confidence))
    for pp in k.play_patterns:
        cur.execute("""
INSERT INTO play_patterns(source_id, deck_name, pattern_name, description, turn_range, required_cards)
VALUES (?, ?, ?, ?, ?, ?)
""", (source_id, k.deck_name, pp.pattern_name, pp.description, pp.turn_range, json.dumps(pp.required_cards, ensure_ascii=False)))
    conn.commit()
    conn.close()
    return source_id


def export_markdown(k: TranscriptKnowledge, out_dir: str | Path = REPORT_DIR) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = k.video_id or safe_slug(k.video_title)
    path = out / f"{name}.md"
    lines = [
        f"# YouTube研究: {k.deck_name or k.video_title}", "",
        f"- video_title: {k.video_title}",
        f"- video_url: {k.video_url}",
        f"- video_id: {k.video_id}",
        f"- deck_name: {k.deck_name}",
        f"- archetype: {k.archetype}",
        f"- used_ai: {k.used_ai}", "",
        "## キーカード", *[f"- {x}" for x in k.key_cards], "",
        "## 基本プラン", *[f"- {x}" for x in k.main_plan], "",
        "## 有利/戦える対面", *[f"- {x}" for x in k.good_matchups], "",
        "## 注意点", *[f"- {x}" for x in k.caution_points], "",
        "## 色基盤メモ", *[f"- {x}" for x in k.color_balance_notes], "",
        "## カード別インサイト",
    ]
    for ci in k.card_insights[:80]:
        lines.append(f"- **{ci.card_name}** / {ci.role} / {ci.sentiment} / {ci.confidence:.2f}: {ci.reason}")
    lines += ["", "## 対面別インサイト"]
    for mi in k.matchup_insights:
        lines.append(f"- **{mi.opponent_deck}** / {mi.evaluation} / {mi.confidence:.2f}: {mi.game_plan}")
    lines += ["", "## プレイパターン"]
    for pp in k.play_patterns:
        lines.append(f"- **{pp.pattern_name}** ({pp.turn_range}): {pp.description} / required={', '.join(pp.required_cards)}")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def list_transcript_files(transcripts_dir: str | Path = TRANSCRIPTS_DIR) -> List[Path]:
    p = Path(transcripts_dir)
    if not p.exists():
        return []
    return sorted(p.glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)


def load_saved_overview(db_path: str | Path = DB_PATH) -> Dict[str, List[Dict[str, Any]]]:
    init_transcript_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    result: Dict[str, List[Dict[str, Any]]] = {}
    for name, sql in {
        "sources": "SELECT * FROM transcript_sources ORDER BY id DESC LIMIT 100",
        "deck_knowledge": "SELECT dk.*, ts.video_title FROM deck_knowledge dk LEFT JOIN transcript_sources ts ON ts.id=dk.source_id ORDER BY dk.id DESC LIMIT 100",
        "card_insights": "SELECT ci.*, ts.video_title FROM card_insights ci LEFT JOIN transcript_sources ts ON ts.id=ci.source_id ORDER BY ci.id DESC LIMIT 300",
        "matchup_insights": "SELECT mi.*, ts.video_title FROM matchup_insights mi LEFT JOIN transcript_sources ts ON ts.id=mi.source_id ORDER BY mi.id DESC LIMIT 200",
    }.items():
        cur.execute(sql)
        result[name] = [dict(r) for r in cur.fetchall()]
    conn.close()
    return result


def build_generation_context(deck_theme: str = "", opponent: str = "", db_path: str | Path = DB_PATH, limit: int = 12) -> str:
    """deck_builder/ai_deck_builderから呼ぶための軽量コンテキスト生成。"""
    init_transcript_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    like_terms = [t for t in [deck_theme, opponent] if t]
    where = ""
    params: List[Any] = []
    if like_terms:
        clauses = []
        for term in like_terms:
            clauses.append("(dk.deck_name LIKE ? OR dk.archetype LIKE ? OR ci.card_name LIKE ? OR mi.opponent_deck LIKE ?)")
            params.extend([f"%{term}%"] * 4)
        where = "WHERE " + " OR ".join(clauses)
    sql = f"""
SELECT dk.deck_name, dk.archetype, dk.main_plan, dk.color_balance_notes, dk.caution_points,
       ci.card_name, ci.role, ci.reason, ci.related_matchup, ci.sentiment,
       mi.opponent_deck, mi.evaluation, mi.game_plan
FROM deck_knowledge dk
LEFT JOIN card_insights ci ON ci.source_id=dk.source_id
LEFT JOIN matchup_insights mi ON mi.source_id=dk.source_id
{where}
ORDER BY dk.id DESC, ci.confidence DESC
LIMIT ?
"""
    params.append(limit)
    cur.execute(sql, params)
    rows = cur.fetchall()
    conn.close()
    lines = ["# YouTube動画由来の研究知識"]
    for r in rows:
        parts = [f"deck={r['deck_name']}", f"archetype={r['archetype']}"]
        if r["card_name"]:
            parts.append(f"card={r['card_name']} role={r['role']} note={r['reason'][:120]}")
        if r["opponent_deck"]:
            parts.append(f"vs={r['opponent_deck']} eval={r['evaluation']} plan={r['game_plan'][:120]}")
        if r["caution_points"]:
            parts.append(f"caution={r['caution_points']}")
        lines.append("- " + " / ".join(str(x) for x in parts if x))
    return "\n".join(lines)


def build_evaluation_comments(deck_cards: Iterable[str], db_path: str | Path = DB_PATH) -> List[str]:
    init_transcript_db(db_path)
    cards = [normalize_card_name(str(c)) for c in deck_cards]
    if not cards:
        return []
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    comments: List[str] = []
    for c in sorted(set(cards)):
        cur.execute("SELECT role, related_matchup, reason, sentiment FROM card_insights WHERE card_name=? ORDER BY confidence DESC LIMIT 2", (c,))
        for role, matchup, reason, sentiment in cur.fetchall():
            if sentiment in ("positive", "neutral"):
                target = f"は{matchup}に" if matchup else "は動画知識で"
                comments.append(f"{c}{target}{role}として言及あり: {reason[:120]}")
    cur.execute("SELECT caution_points FROM deck_knowledge ORDER BY id DESC LIMIT 20")
    for (raw,) in cur.fetchall():
        try:
            for p in json.loads(raw or "[]"):
                if any(word in p for word in ["色", "マナ", "ドンジャングル", "デルフィン"]):
                    comments.append(p)
        except Exception:
            pass
    conn.close()
    return list(dict.fromkeys(comments))[:8]


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--no-ai", action="store_true")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    knowledge = analyze_transcript(args.path, Path(args.db), use_ai=not args.no_ai)
    print(json.dumps(asdict(knowledge), ensure_ascii=False, indent=2))
    md = export_markdown(knowledge)
    print(f"markdown: {md}")
    if args.save:
        sid = save_knowledge(knowledge, args.db)
        print(f"saved source_id={sid}")

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("data/cards.db")
DEFAULT_TRANSCRIPT_DIR = Path("data/youtube/transcripts")
DEFAULT_ALIAS_PATH = Path("data/youtube/card_aliases.csv")
DEFAULT_REPORT_DIR = Path("data/reports/video_learning")


STRONG_WORDS = ["強い", "刺さる", "偉い", "優秀", "通る", "勝てる", "キープ", "欲しい"]
WEAK_WORDS = ["弱い", "微妙", "きつい", "厳しい", "間に合わない", "不要"]
DEAD_WORDS = ["腐る", "使えない", "出せない", "抱える", "邪魔"]
KEEP_WORDS = ["キープ", "初手", "マリガン", "持っておきたい"]
EARLY_WORDS = ["序盤", "2ターン", "3ターン", "4ターン", "初動"]
MID_WORDS = ["中盤", "5ターン", "6ターン", "リソース"]
FINISH_WORDS = ["リーサル", "詰め", "フィニッシュ", "勝ち", "盾を割る", "殴る"]
DEFENSE_WORDS = ["受け", "トリガー", "守る", "耐える", "返す"]
ATTACK_TIMING_WORDS = ["盾", "詰める", "殴る", "全割り", "攻撃"]
REPLACEMENT_WORDS = ["入れ替え", "採用", "不採用", "抜く", "増やす", "減らす"]
META_WORDS = ["環境", "対面", "レイド", "スコーラー", "デンジャデオン", "裁き", "紋章"]
DECK_NAMES = ["火光レイド", "火水レイド", "光単裁きの紋章Z", "水単スコーラー", "自然単デンジャデオン"]


def get_connection(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table(db_path: Path = DEFAULT_DB) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS video_learning_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                title TEXT,
                speaker_deck TEXT,
                opponent_deck TEXT,
                format TEXT,
                mentioned_cards_json TEXT,
                strong_cards_json TEXT,
                weak_cards_json TEXT,
                dead_cards_json TEXT,
                keep_advice TEXT,
                early_game_plan TEXT,
                mid_game_plan TEXT,
                finish_plan TEXT,
                defense_plan TEXT,
                attack_timing TEXT,
                matchup_notes TEXT,
                replacement_ideas TEXT,
                meta_notes TEXT,
                confidence REAL,
                raw_summary TEXT,
                created_at TEXT
            )
            """
        )
        conn.commit()


def load_card_dictionary(db_path: Path = DEFAULT_DB, alias_path: Path = DEFAULT_ALIAS_PATH) -> tuple[list[str], dict[str, str]]:
    with get_connection(db_path) as conn:
        names = [str(row["name"]) for row in conn.execute("SELECT DISTINCT name FROM cards WHERE name IS NOT NULL").fetchall()]
    aliases: dict[str, str] = {}
    if alias_path.exists():
        with alias_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                alias = str(row.get("alias", "")).strip()
                card_name = str(row.get("card_name", "")).strip()
                if alias and card_name:
                    aliases[alias] = card_name
    return names, aliases


def normalize_text(value: str) -> str:
    return re.sub(r"[\s　・/／,，、。!！?？:：;；「」『』（）()\[\]【】\-ー]", "", value or "").lower()


def split_sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[。！？!?])|\n+", text)
    return [s.strip() for s in raw if s.strip()]


def extract_cards(text: str, card_names: list[str], aliases: dict[str, str]) -> list[str]:
    found: set[str] = set()
    normalized = normalize_text(text)
    for name in card_names:
        if not name:
            continue
        if name in text or normalize_text(name) in normalized:
            found.add(name)
    for alias, card_name in aliases.items():
        if alias in text or normalize_text(alias) in normalized:
            found.add(card_name)
    return sorted(found)


def cards_near_keywords(sentences: list[str], mentioned_cards: list[str], keywords: list[str]) -> list[str]:
    found: Counter[str] = Counter()
    for sentence in sentences:
        if not any(k in sentence for k in keywords):
            continue
        sentence_norm = normalize_text(sentence)
        for card in mentioned_cards:
            if card in sentence or normalize_text(card) in sentence_norm:
                found[card] += 1
    return [name for name, _count in found.most_common(20)]


def collect_sentences(sentences: list[str], keywords: list[str], limit: int = 5) -> str:
    rows = [s for s in sentences if any(k in s for k in keywords)]
    return " / ".join(shorten_sentence(s) for s in rows[:limit])


def shorten_sentence(sentence: str, limit: int = 90) -> str:
    sentence = re.sub(r"\s+", " ", sentence).strip()
    return sentence[:limit] + ("..." if len(sentence) > limit else "")


def infer_decks(text: str, title: str) -> tuple[str, str]:
    combined = f"{title}\n{text[:3000]}"
    found = [name for name in DECK_NAMES if name in combined]
    speaker = found[0] if found else ""
    opponent = found[1] if len(found) >= 2 else ""
    return speaker, opponent


def analyze_text(video_id: str, title: str, text: str, db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    card_names, aliases = load_card_dictionary(db_path)
    sentences = split_sentences(text)
    mentioned_cards = extract_cards(text, card_names, aliases)
    strong_cards = cards_near_keywords(sentences, mentioned_cards, STRONG_WORDS)
    weak_cards = cards_near_keywords(sentences, mentioned_cards, WEAK_WORDS)
    dead_cards = cards_near_keywords(sentences, mentioned_cards, DEAD_WORDS)
    keep_advice = collect_sentences(sentences, KEEP_WORDS)
    early_game_plan = collect_sentences(sentences, EARLY_WORDS)
    mid_game_plan = collect_sentences(sentences, MID_WORDS)
    finish_plan = collect_sentences(sentences, FINISH_WORDS)
    defense_plan = collect_sentences(sentences, DEFENSE_WORDS)
    attack_timing = collect_sentences(sentences, ATTACK_TIMING_WORDS)
    replacement_ideas = collect_sentences(sentences, REPLACEMENT_WORDS)
    meta_notes = collect_sentences(sentences, META_WORDS)
    matchup_notes = collect_sentences(sentences, META_WORDS + ["有利", "不利", "対策"])
    speaker_deck, opponent_deck = infer_decks(text, title)
    confidence = min(1.0, 0.2 + len(mentioned_cards) / 40 + bool(keep_advice) * 0.15 + bool(finish_plan) * 0.15)
    return {
        "video_id": video_id,
        "title": title,
        "speaker_deck": speaker_deck,
        "opponent_deck": opponent_deck,
        "format": "デュエプレ",
        "mentioned_cards": mentioned_cards[:80],
        "strong_cards": strong_cards,
        "weak_cards": weak_cards,
        "dead_cards": dead_cards,
        "keep_advice": keep_advice,
        "early_game_plan": early_game_plan,
        "mid_game_plan": mid_game_plan,
        "finish_plan": finish_plan,
        "defense_plan": defense_plan,
        "attack_timing": attack_timing,
        "matchup_notes": matchup_notes,
        "replacement_ideas": replacement_ideas,
        "meta_notes": meta_notes,
        "confidence": round(confidence, 2),
        "raw_summary": build_raw_summary(mentioned_cards, keep_advice, finish_plan, matchup_notes),
    }


def build_raw_summary(mentioned_cards: list[str], keep_advice: str, finish_plan: str, matchup_notes: str) -> str:
    parts = []
    if mentioned_cards:
        parts.append("抽出カード: " + " / ".join(mentioned_cards[:12]))
    if keep_advice:
        parts.append("キープ: " + keep_advice)
    if finish_plan:
        parts.append("詰め方: " + finish_plan)
    if matchup_notes:
        parts.append("対面: " + matchup_notes)
    return "\n".join(parts)


def save_learning_log(result: dict[str, Any], db_path: Path = DEFAULT_DB) -> None:
    ensure_table(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM video_learning_logs WHERE video_id = ?", (result.get("video_id"),))
        conn.execute(
            """
            INSERT INTO video_learning_logs (
                video_id, title, speaker_deck, opponent_deck, format,
                mentioned_cards_json, strong_cards_json, weak_cards_json, dead_cards_json,
                keep_advice, early_game_plan, mid_game_plan, finish_plan, defense_plan,
                attack_timing, matchup_notes, replacement_ideas, meta_notes,
                confidence, raw_summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.get("video_id"),
                result.get("title"),
                result.get("speaker_deck"),
                result.get("opponent_deck"),
                result.get("format"),
                json.dumps(result.get("mentioned_cards", []), ensure_ascii=False),
                json.dumps(result.get("strong_cards", []), ensure_ascii=False),
                json.dumps(result.get("weak_cards", []), ensure_ascii=False),
                json.dumps(result.get("dead_cards", []), ensure_ascii=False),
                result.get("keep_advice"),
                result.get("early_game_plan"),
                result.get("mid_game_plan"),
                result.get("finish_plan"),
                result.get("defense_plan"),
                result.get("attack_timing"),
                result.get("matchup_notes"),
                result.get("replacement_ideas"),
                result.get("meta_notes"),
                result.get("confidence"),
                result.get("raw_summary"),
                now,
            ),
        )
        conn.execute("UPDATE youtube_videos SET processed_status='analyzed', updated_at=? WHERE video_id=?", (now, result.get("video_id")))
        conn.commit()


def title_for_video(video_id: str, db_path: Path = DEFAULT_DB) -> str:
    try:
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT title FROM youtube_videos WHERE video_id = ?", (video_id,)).fetchone()
            return str(row["title"]) if row else video_id
    except Exception:
        return video_id


def analyze_file(path: Path, db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    video_id = path.stem
    text = path.read_text(encoding="utf-8", errors="replace")
    result = analyze_text(video_id, title_for_video(video_id, db_path), text, db_path)
    save_learning_log(result, db_path)
    return result


def analyze_all(db_path: Path = DEFAULT_DB, transcript_dir: Path = DEFAULT_TRANSCRIPT_DIR) -> list[dict[str, Any]]:
    results = []
    for path in sorted(transcript_dir.glob("*.txt")):
        if path.name.startswith("sample"):
            continue
        results.append(analyze_file(path, db_path))
    write_report(db_path)
    return results


def load_learning_logs(db_path: Path = DEFAULT_DB) -> list[dict[str, Any]]:
    ensure_table(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM video_learning_logs ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def summarize_learning(logs: list[dict[str, Any]]) -> dict[str, Any]:
    strong = Counter()
    weak = Counter()
    dead = Counter()
    mentioned = Counter()
    matchup_notes = defaultdict(list)
    for row in logs:
        for name in json.loads(row.get("strong_cards_json") or "[]"):
            strong[name] += 1
        for name in json.loads(row.get("weak_cards_json") or "[]"):
            weak[name] += 1
        for name in json.loads(row.get("dead_cards_json") or "[]"):
            dead[name] += 1
        for name in json.loads(row.get("mentioned_cards_json") or "[]"):
            mentioned[name] += 1
        for deck in DECK_NAMES:
            note = str(row.get("matchup_notes") or "")
            if deck in note:
                matchup_notes[deck].append(note)
    return {
        "video_count": len(logs),
        "mentioned_card_count": len(mentioned),
        "strong_cards": [{"name": k, "count": v} for k, v in strong.most_common(20)],
        "weak_cards": [{"name": k, "count": v} for k, v in weak.most_common(20)],
        "dead_cards": [{"name": k, "count": v} for k, v in dead.most_common(20)],
        "mentioned_cards": [{"name": k, "count": v} for k, v in mentioned.most_common(50)],
        "matchup_notes": {k: v[:3] for k, v in matchup_notes.items()},
    }


def write_report(db_path: Path = DEFAULT_DB, out_dir: Path = DEFAULT_REPORT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    logs = load_learning_logs(db_path)
    summary = summarize_learning(logs)
    videos = []
    try:
        with get_connection(db_path) as conn:
            videos = [dict(row) for row in conn.execute("SELECT * FROM youtube_videos ORDER BY id DESC").fetchall()]
    except Exception:
        videos = []
    payload = {"summary": summary, "logs": logs, "videos": videos}
    (out_dir / "video_learning_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_card_csv(summary, out_dir / "video_learning_cards.csv")
    (out_dir / "video_learning_report.md").write_text(to_markdown(payload), encoding="utf-8")


def write_card_csv(summary: dict[str, Any], path: Path) -> None:
    names = set()
    for key in ["strong_cards", "weak_cards", "dead_cards", "mentioned_cards"]:
        names.update(item["name"] for item in summary.get(key, []))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["card_name", "strong_count", "weak_count", "dead_count", "mentioned_count"])
        writer.writeheader()
        for name in sorted(names):
            writer.writerow(
                {
                    "card_name": name,
                    "strong_count": count_in(summary.get("strong_cards", []), name),
                    "weak_count": count_in(summary.get("weak_cards", []), name),
                    "dead_count": count_in(summary.get("dead_cards", []), name),
                    "mentioned_count": count_in(summary.get("mentioned_cards", []), name),
                }
            )


def count_in(items: list[dict[str, Any]], name: str) -> int:
    for item in items:
        if item.get("name") == name:
            return int(item.get("count", 0))
    return 0


def to_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    videos = payload.get("videos", [])
    logs = payload.get("logs", [])
    lines = [
        "# YouTube動画学習レポート",
        "",
        "## 実行条件",
        f"- fetched_videos: {len(videos)}",
        f"- transcript_success: {sum(1 for v in videos if v.get('transcript_status') == 'success')}",
        f"- transcript_failed: {sum(1 for v in videos if v.get('transcript_status') == 'failed')}",
        f"- analyzed_count: {len(logs)}",
        "",
        "## 学習サマリー",
        f"- 動画数: {summary['video_count']}",
        f"- 抽出カード数: {summary['mentioned_card_count']}",
        f"- 強いカード上位: {format_items(summary.get('strong_cards', []))}",
        f"- 弱いカード上位: {format_items(summary.get('weak_cards', []))}",
        f"- 腐りカード上位: {format_items(summary.get('dead_cards', []))}",
        "",
        "## 対面別メモ",
    ]
    if summary.get("matchup_notes"):
        for deck, notes in summary["matchup_notes"].items():
            lines.append(f"### {deck}")
            for note in notes:
                lines.append(f"- {note}")
    else:
        lines.append("- まだ対面別メモはありません。")
    lines.append("")
    lines.append("## 動画別解析")
    for row in logs:
        lines.extend(
            [
                f"### {row.get('title') or row.get('video_id')}",
                f"- video_id: {row.get('video_id')}",
                f"- speaker_deck: {row.get('speaker_deck') or '-'}",
                f"- opponent_deck: {row.get('opponent_deck') or '-'}",
                f"- mentioned_cards: {', '.join(json.loads(row.get('mentioned_cards_json') or '[]')[:20])}",
                f"- strong_cards: {', '.join(json.loads(row.get('strong_cards_json') or '[]')[:10]) or '-'}",
                f"- weak_cards: {', '.join(json.loads(row.get('weak_cards_json') or '[]')[:10]) or '-'}",
                f"- keep_advice: {row.get('keep_advice') or '-'}",
                f"- early_game_plan: {row.get('early_game_plan') or '-'}",
                f"- finish_plan: {row.get('finish_plan') or '-'}",
                f"- confidence: {row.get('confidence')}",
                "",
            ]
        )
    lines.extend(
        [
            "## 注意",
            "このレポートは文字起こし全文の転載ではなく、MANA用の短い構造化知識だけを表示します。",
        ]
    )
    return "\n".join(lines)


def format_items(items: list[dict[str, Any]]) -> str:
    return " / ".join(f"{item['name']}: {item['count']}" for item in items[:10]) or "なし"


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze YouTube transcripts into Project MANA learning logs.")
    parser.add_argument("--input", default="")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    db_path = Path(args.db)
    ensure_table(db_path)

    if args.input:
        result = analyze_file(Path(args.input), db_path)
        write_report(db_path)
        print(json.dumps({"analyzed": 1, "video_id": result["video_id"], "cards": len(result["mentioned_cards"])}, ensure_ascii=False, indent=2))
    elif args.all:
        results = analyze_all(db_path)
        print(json.dumps({"analyzed": len(results)}, ensure_ascii=False, indent=2))
    else:
        write_report(db_path)
        print("wrote video learning report")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import ssl
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


DEFAULT_DB = Path("data/cards.db")
DEFAULT_CHANNEL_URL = "https://youtube.com/channel/UC4_4aISKb8T0enw_DJnDTEw?si=7ViTkTw-6_Y9ONGZ"
DEFAULT_VIDEO_LIST = Path("data/youtube/video_urls.txt")
DEFAULT_TRANSCRIPT_DIR = Path("data/youtube/transcripts")
DEFAULT_REPORT_DIR = Path("data/reports/video_learning")


def get_connection(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_tables(db_path: Path = DEFAULT_DB) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT UNIQUE,
                url TEXT,
                title TEXT,
                channel_name TEXT,
                published_at TEXT,
                duration TEXT,
                description TEXT,
                transcript_status TEXT,
                processed_status TEXT,
                error_message TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_transcripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                language TEXT,
                source_type TEXT,
                transcript_text TEXT,
                transcript_path TEXT,
                char_count INTEGER,
                created_at TEXT
            )
            """
        )
        conn.commit()


def extract_channel_id(channel_url: str) -> str | None:
    match = re.search(r"/channel/([^/?&]+)", channel_url)
    return match.group(1) if match else None


def extract_video_id(value: str) -> str | None:
    value = value.strip()
    patterns = [
        r"youtu\.be/([^?&/]+)",
        r"watch\?v=([^?&]+)",
        r"/shorts/([^?&/]+)",
        r"/embed/([^?&/]+)",
        r"^([A-Za-z0-9_-]{8,})$",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    return None


def fetch_channel_videos(channel_url: str, max_videos: int = 20) -> list[dict[str, Any]]:
    channel_id = extract_channel_id(channel_url)
    if not channel_id:
        raise ValueError("channel URLからchannel_idを取得できませんでした。手動URLリストを使ってください。")
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        with urllib.request.urlopen(feed_url, timeout=20) as response:
            xml_text = response.read().decode("utf-8", errors="replace")
    except Exception:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(feed_url, timeout=20, context=context) as response:
            xml_text = response.read().decode("utf-8", errors="replace")
    root = ET.fromstring(xml_text)
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    channel_name = root.findtext("atom:title", default="", namespaces=ns)
    videos = []
    for entry in root.findall("atom:entry", ns)[:max_videos]:
        video_id = entry.findtext("yt:videoId", default="", namespaces=ns)
        title = entry.findtext("atom:title", default="", namespaces=ns)
        published_at = entry.findtext("atom:published", default="", namespaces=ns)
        media_group = entry.find("media:group", ns)
        description = ""
        if media_group is not None:
            description = media_group.findtext("media:description", default="", namespaces=ns)
        videos.append(
            {
                "video_id": video_id,
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "published_at": published_at,
                "duration": "",
                "description": description,
                "channel_name": channel_name,
                "transcript_status": "not_fetched",
                "processed_status": "pending",
            }
        )
    return videos


def load_video_list(path: Path) -> list[dict[str, Any]]:
    ensure_default_files()
    if not path.exists():
        return []
    videos = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        video_id = extract_video_id(line)
        if not video_id:
            continue
        videos.append(
            {
                "video_id": video_id,
                "title": f"manual video {index}",
                "url": line if line.startswith("http") else f"https://www.youtube.com/watch?v={video_id}",
                "published_at": "",
                "duration": "",
                "description": "",
                "channel_name": "manual",
                "transcript_status": "not_fetched",
                "processed_status": "pending",
            }
        )
    return videos


def save_videos(videos: list[dict[str, Any]], db_path: Path = DEFAULT_DB) -> int:
    ensure_tables(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        for video in videos:
            conn.execute(
                """
                INSERT INTO youtube_videos (
                    video_id, url, title, channel_name, published_at, duration, description,
                    transcript_status, processed_status, error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    url=excluded.url,
                    title=excluded.title,
                    channel_name=excluded.channel_name,
                    published_at=excluded.published_at,
                    duration=excluded.duration,
                    description=excluded.description,
                    updated_at=excluded.updated_at
                """,
                (
                    video.get("video_id"),
                    video.get("url"),
                    video.get("title"),
                    video.get("channel_name"),
                    video.get("published_at"),
                    video.get("duration"),
                    video.get("description"),
                    video.get("transcript_status", "not_fetched"),
                    video.get("processed_status", "pending"),
                    "",
                    now,
                    now,
                ),
            )
        conn.commit()
    return len(videos)


def load_pending_videos(db_path: Path = DEFAULT_DB, max_videos: int = 20) -> list[dict[str, Any]]:
    ensure_tables(db_path)
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT * FROM youtube_videos
            WHERE transcript_status IS NULL
               OR transcript_status IN ('not_fetched', 'failed')
            ORDER BY id DESC
            LIMIT ?
            """,
            (max_videos,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_transcript_for_video(video: dict[str, Any], transcript_dir: Path = DEFAULT_TRANSCRIPT_DIR) -> dict[str, Any]:
    transcript_dir.mkdir(parents=True, exist_ok=True)
    video_id = video["video_id"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore

        api = YouTubeTranscriptApi()
        rows = None
        language = ""
        source_type = "youtube"
        for langs in (["ja", "ja-JP"], ["en"]):
            try:
                rows = api.fetch(video_id, languages=langs)
                language = langs[0]
                source_type = "youtube"
                break
            except Exception:
                continue
        if rows is None:
            yt_result = fetch_transcript_with_ytdlp(video_id, transcript_dir)
            if yt_result.get("ok"):
                return yt_result
            raise RuntimeError(yt_result.get("error_message") or "利用可能な日本語/英語字幕が見つかりません。")
        row_dicts, text = transcript_rows_to_text(rows)
        txt_path = transcript_dir / f"{video_id}.txt"
        json_path = transcript_dir / f"{video_id}.json"
        txt_path.write_text(text, encoding="utf-8")
        json_path.write_text(json.dumps(row_dicts, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "ok": True,
            "video_id": video_id,
            "language": language,
            "source_type": source_type,
            "transcript_text": text,
            "transcript_path": str(txt_path),
            "char_count": len(text),
        }
    except Exception as exc:
        return {"ok": False, "video_id": video_id, "error_message": str(exc)}


def transcript_rows_to_text(rows: Any) -> tuple[list[dict[str, Any]], str]:
    row_dicts = []
    text_parts = []
    for item in rows:
        if isinstance(item, dict):
            row = item
        else:
            row = {
                "text": getattr(item, "text", ""),
                "start": getattr(item, "start", 0),
                "duration": getattr(item, "duration", 0),
            }
        row_dicts.append(row)
        text_value = str(row.get("text", "")).strip()
        if text_value:
            text_parts.append(text_value)
    return row_dicts, "\n".join(text_parts)


def fetch_transcript_with_ytdlp(video_id: str, transcript_dir: Path) -> dict[str, Any]:
    temp_dir = transcript_dir / "_yt_dlp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(temp_dir / f"{video_id}.%(ext)s")
    cmd = [
        "python",
        "-m",
        "yt_dlp",
        "--no-check-certificates",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "ja,en",
        "--sub-format",
        "vtt",
        "-o",
        output_template,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return {"ok": False, "video_id": video_id, "error_message": f"yt-dlp実行失敗: {exc}"}
    vtt_files = sorted(temp_dir.glob(f"{video_id}*.vtt"))
    if proc.returncode != 0 and not vtt_files:
        return {"ok": False, "video_id": video_id, "error_message": (proc.stderr or proc.stdout)[-500:]}
    if not vtt_files:
        return {"ok": False, "video_id": video_id, "error_message": "yt-dlpでも字幕ファイルを取得できませんでした。"}
    vtt_path = vtt_files[0]
    text = vtt_to_text(vtt_path.read_text(encoding="utf-8", errors="replace"))
    if not text.strip():
        return {"ok": False, "video_id": video_id, "error_message": "yt-dlp字幕は空でした。"}
    txt_path = transcript_dir / f"{video_id}.txt"
    json_path = transcript_dir / f"{video_id}.json"
    txt_path.write_text(text, encoding="utf-8")
    json_path.write_text(json.dumps({"source": "yt-dlp", "vtt_path": str(vtt_path)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "video_id": video_id,
        "language": "ja/en",
        "source_type": "yt-dlp",
        "transcript_text": text,
        "transcript_path": str(txt_path),
        "char_count": len(text),
    }


def vtt_to_text(value: str) -> str:
    lines = []
    previous = ""
    for line in value.splitlines():
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"&amp;", "&", line)
        if line and line != previous:
            lines.append(line)
            previous = line
    return "\n".join(lines)


def save_transcript_result(result: dict[str, Any], db_path: Path = DEFAULT_DB) -> None:
    ensure_tables(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        if result.get("ok"):
            conn.execute(
                """
                INSERT INTO youtube_transcripts (
                    video_id, language, source_type, transcript_text, transcript_path, char_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["video_id"],
                    result.get("language", ""),
                    result.get("source_type", ""),
                    result.get("transcript_text", ""),
                    result.get("transcript_path", ""),
                    result.get("char_count", 0),
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE youtube_videos
                SET transcript_status='success', error_message='', updated_at=?
                WHERE video_id=?
                """,
                (now, result["video_id"]),
            )
        else:
            conn.execute(
                """
                UPDATE youtube_videos
                SET transcript_status='failed', error_message=?, updated_at=?
                WHERE video_id=?
                """,
                (result.get("error_message", ""), now, result["video_id"]),
            )
        conn.commit()


def fetch_transcripts(db_path: Path = DEFAULT_DB, max_videos: int = 20) -> list[dict[str, Any]]:
    results = []
    for video in load_pending_videos(db_path, max_videos=max_videos):
        result = fetch_transcript_for_video(video)
        save_transcript_result(result, db_path)
        results.append(result)
    return results


def ensure_default_files() -> None:
    DEFAULT_VIDEO_LIST.parent.mkdir(parents=True, exist_ok=True)
    alias_path = Path("data/youtube/card_aliases.csv")
    if not alias_path.exists():
        alias_path.write_text(
            "\n".join(
                [
                    "alias,card_name,notes",
                    "ミクセル,奇石 ミクセル/ジャミング・チャフ,略称",
                    "チャフ,奇石 ミクセル/ジャミング・チャフ,ツインパクト呪文側",
                    "デンジャデオン,自然単デンジャデオン,デッキ名",
                ]
            ),
            encoding="utf-8",
        )
    if not DEFAULT_VIDEO_LIST.exists():
        DEFAULT_VIDEO_LIST.write_text("# YouTube動画URLを1行ずつ入れてください\n", encoding="utf-8")


def write_collection_report(db_path: Path = DEFAULT_DB, out_dir: Path = DEFAULT_REPORT_DIR) -> None:
    ensure_tables(db_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        videos = [dict(row) for row in conn.execute("SELECT * FROM youtube_videos ORDER BY id DESC").fetchall()]
        transcripts = [dict(row) for row in conn.execute("SELECT * FROM youtube_transcripts ORDER BY id DESC").fetchall()]
    summary = {
        "fetched_videos": len(videos),
        "transcript_success": sum(1 for v in videos if v.get("transcript_status") == "success"),
        "transcript_failed": sum(1 for v in videos if v.get("transcript_status") == "failed"),
        "transcript_records": len(transcripts),
    }
    (out_dir / "youtube_collection_status.json").write_text(json.dumps({"summary": summary, "videos": videos}, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect YouTube video metadata and transcripts for Project MANA.")
    parser.add_argument("--channel-url", default="")
    parser.add_argument("--video-list", default="")
    parser.add_argument("--max-videos", type=int, default=20)
    parser.add_argument("--fetch-transcripts", action="store_true")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    db_path = Path(args.db)
    ensure_default_files()
    ensure_tables(db_path)

    videos: list[dict[str, Any]] = []
    if args.video_list:
        videos = load_video_list(Path(args.video_list))[: args.max_videos]
    elif args.channel_url:
        try:
            videos = fetch_channel_videos(args.channel_url, max_videos=args.max_videos)
        except Exception as exc:
            print(f"channel fetch failed: {exc}")
            videos = load_video_list(DEFAULT_VIDEO_LIST)[: args.max_videos]
    elif not args.fetch_transcripts:
        videos = fetch_channel_videos(DEFAULT_CHANNEL_URL, max_videos=args.max_videos)

    if videos:
        saved = save_videos(videos, db_path)
        print(f"saved videos: {saved}")

    if args.fetch_transcripts:
        results = fetch_transcripts(db_path, max_videos=args.max_videos)
        success = sum(1 for r in results if r.get("ok"))
        failed = len(results) - success
        print(f"transcripts success={success} failed={failed}")

    write_collection_report(db_path)


if __name__ == "__main__":
    main()

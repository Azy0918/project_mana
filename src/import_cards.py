from __future__ import annotations

import argparse
import csv
import sqlite3

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CSV_PATH = ROOT_DIR / "data" / "cards.csv"
DEFAULT_DB_PATH = ROOT_DIR / "data" / "cards.db"


from pathlib import Path


DEFAULT_CSV = Path("data/cards.csv")
DEFAULT_DB = Path("data/cards.db")


def safe_int(value, default: int = 0) -> int:
    """Convert official DMPS CSV numeric fields safely.

    Official API records can contain blank values for fields such as cost/power.
    The old importer assumed every cost was an int and crashed on blank strings.
    """
    if value is None:
        return default
    text = str(value).strip()
    if text == "" or text == "-" or text.lower() == "none":
        return default
    # Remove symbols sometimes used in display fields.
    text = text.replace(",", "").replace("+", "")
    try:
        return int(float(text))
    except Exception:
        return default


def first_nonempty(row: dict, *keys: str, default: str = "") -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def normalize_row(row: dict) -> dict:
    """Normalize both old MANA CSV and new official DMPS API CSV."""
    name = first_nonempty(row, "name", "card_name")
    card_id = first_nonempty(row, "card_id", default=name)
    civilization = first_nonempty(row, "civilization", "culture")
    card_type = first_nonempty(row, "card_type")
    race = first_nonempty(row, "race", "race_text")
    text = first_nonempty(row, "text", "body_text")
    tags = first_nonempty(row, "tags", "keyword")

    # Keep both numeric and display information where possible.
    cost = safe_int(row.get("cost"), default=0)
    power = first_nonempty(row, "power", "power_disp", default="")
    nd_legal = first_nonempty(row, "nd_legal", default="")

    return {
        "card_id": card_id,
        "name": name,
        "civilization": civilization,
        "cost": cost,
        "card_type": card_type,
        "power": power,
        "race": race,
        "text": text,
        "tags": tags,
        "nd_legal": nd_legal,
    }


def import_cards(csv_path: str | Path = DEFAULT_CSV, db_path: str | Path = DEFAULT_DB) -> int:
    csv_path = Path(csv_path)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = [normalize_row(row) for row in reader]

    # Drop rows without a usable card name. Keep cost=0 rows because official special records can be blank.
    rows = [row for row in rows if row["name"]]

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    cur.execute("DROP TABLE IF EXISTS cards")
    cur.execute("DROP TABLE IF EXISTS card_tags")

    cur.execute(
        """
        CREATE TABLE cards (
            card_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            civilization TEXT,
            cost INTEGER NOT NULL DEFAULT 0,
            card_type TEXT,
            power TEXT,
            race TEXT,
            text TEXT,
            nd_legal TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE card_tags (
            card_id TEXT NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY (card_id, tag)
        )
        """
    )

    inserted = 0
    for row in rows:
        cur.execute(
            """
            INSERT OR REPLACE INTO cards
            (card_id, name, civilization, cost, card_type, power, race, text, nd_legal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["card_id"],
                row["name"],
                row["civilization"],
                row["cost"],
                row["card_type"],
                row["power"],
                row["race"],
                row["text"],
                row["nd_legal"],
            ),
        )
        inserted += 1

        tags = [t.strip() for t in str(row.get("tags", "")).replace(",", ";").split(";") if t.strip()]
        for tag in tags:
            cur.execute(
                "INSERT OR IGNORE INTO card_tags (card_id, tag) VALUES (?, ?)",
                (row["card_id"], tag),
            )

    con.commit()
    con.close()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Project MANA card CSV into SQLite.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    count = import_cards(args.csv, args.db)
    print(f"{count} cards imported to {args.db}")


if __name__ == "__main__":
    main()

# Backward compatibility for route modules
DEFAULT_CSV_PATH = DEFAULT_CSV
DEFAULT_DB_PATH = DEFAULT_DB

# =========================
# YouTube研究 画面
# =========================
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from src.transcript_analyzer import analyze_transcript_file, save_analysis_to_db
except Exception as e:
    analyze_transcript_file = None
    save_analysis_to_db = None

DB_PATH = Path("data/cards.db")
TRANSCRIPTS_DIR = Path("transcripts")
YOUTUBE_REPORT_DIR = Path("reports/youtube_research")


def _yt_read_table(query: str, params=()):
    if not DB_PATH.exists():
        return pd.DataFrame()
    con = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(query, con, params=params)
    finally:
        con.close()


with st.expander("YouTube研究 / 動画知識DB", expanded=False):
    st.subheader("YouTube研究 / 動画知識DB")

    st.caption("YouTube文字起こしを、デッキ知識・カード知識・対面知識として確認します。")

    tabs_yt = st.tabs([
        "文字起こし解析",
        "保存済み動画知識",
        "カード別知識",
        "対面別知識",
        "プレイパターン",
    ])

    with tabs_yt[0]:
        st.markdown("### transcripts フォルダ内のtxt解析")

        TRANSCRIPTS_DIR.mkdir(exist_ok=True)
        txt_files = sorted(TRANSCRIPTS_DIR.glob("*.txt"))

        if not txt_files:
            st.warning("transcripts フォルダに .txt ファイルがありません。")
        else:
            selected = st.selectbox(
                "解析する文字起こし",
                txt_files,
                format_func=lambda p: p.name,
            )

            use_ai = st.checkbox("AI抽出を使う", value=False)
            save_db = st.checkbox("DBに保存する", value=True)

            if st.button("選択した文字起こしを解析"):
                if analyze_transcript_file is None:
                    st.error("src.transcript_analyzer を読み込めませんでした。")
                else:
                    result = analyze_transcript_file(
                        selected,
                        use_ai=use_ai,
                        db_path=DB_PATH,
                    )

                    st.success("解析しました。")
                    st.json(result)

                    if save_db:
                        source_id = save_analysis_to_db(result, DB_PATH)
                        st.success(f"DBに保存しました。source_id={source_id}")

    with tabs_yt[1]:
        st.markdown("### 保存済み動画知識")

        df = _yt_read_table("""
            SELECT
                s.id AS source_id,
                s.video_title,
                s.video_url,
                s.video_id,
                k.deck_name,
                k.archetype,
                k.main_plan,
                k.color_balance_notes,
                k.caution_points,
                s.created_at
            FROM transcript_sources s
            LEFT JOIN deck_knowledge k ON k.source_id = s.id
            ORDER BY s.id DESC
        """)

        if df.empty:
            st.info("保存済み動画知識はまだありません。")
        else:
            st.dataframe(df, use_container_width=True)

    with tabs_yt[2]:
        st.markdown("### カード別の言及一覧")

        card_filter = st.text_input("カード名で検索", "")

        if card_filter:
            df = _yt_read_table("""
                SELECT
                    c.card_name,
                    c.role,
                    c.reason,
                    c.related_matchup,
                    c.sentiment,
                    c.confidence,
                    s.video_title,
                    s.video_id
                FROM card_insights c
                LEFT JOIN transcript_sources s ON s.id = c.source_id
                WHERE c.card_name LIKE ?
                ORDER BY c.card_name, c.confidence DESC
            """, (f"%{card_filter}%",))
        else:
            df = _yt_read_table("""
                SELECT
                    c.card_name,
                    c.role,
                    c.reason,
                    c.related_matchup,
                    c.sentiment,
                    c.confidence,
                    s.video_title,
                    s.video_id
                FROM card_insights c
                LEFT JOIN transcript_sources s ON s.id = c.source_id
                ORDER BY c.card_name, c.confidence DESC
            """)

        if df.empty:
            st.info("カード知識はまだありません。")
        else:
            st.dataframe(df, use_container_width=True)

    with tabs_yt[3]:
        st.markdown("### 対面別の知識一覧")

        matchup_filter = st.text_input("対面名で検索", "")

        if matchup_filter:
            df = _yt_read_table("""
                SELECT
                    m.deck_name,
                    m.opponent_deck,
                    m.evaluation,
                    m.game_plan,
                    m.key_cards,
                    m.caution_points,
                    m.confidence,
                    s.video_title,
                    s.video_id
                FROM matchup_insights m
                LEFT JOIN transcript_sources s ON s.id = m.source_id
                WHERE m.opponent_deck LIKE ? OR m.deck_name LIKE ?
                ORDER BY m.confidence DESC
            """, (f"%{matchup_filter}%", f"%{matchup_filter}%"))
        else:
            df = _yt_read_table("""
                SELECT
                    m.deck_name,
                    m.opponent_deck,
                    m.evaluation,
                    m.game_plan,
                    m.key_cards,
                    m.caution_points,
                    m.confidence,
                    s.video_title,
                    s.video_id
                FROM matchup_insights m
                LEFT JOIN transcript_sources s ON s.id = m.source_id
                ORDER BY m.confidence DESC
            """)

        if df.empty:
            st.info("対面知識はまだありません。")
        else:
            st.dataframe(df, use_container_width=True)

    with tabs_yt[4]:
        st.markdown("### プレイパターン")

        df = _yt_read_table("""
            SELECT
                p.deck_name,
                p.pattern_name,
                p.description,
                p.turn_range,
                p.required_cards,
                s.video_title,
                s.video_id
            FROM play_patterns p
            LEFT JOIN transcript_sources s ON s.id = p.source_id
            ORDER BY p.deck_name, p.pattern_name
        """)

        if df.empty:
            st.info("プレイパターンはまだありません。")
        else:
            st.dataframe(df, use_container_width=True)

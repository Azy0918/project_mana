from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.remote_research_loop import (
    DEFAULT_DB,
    add_match,
    create_session,
    deck_items_from_candidate,
    list_matches,
    list_sessions,
    summarize_session,
    summary_to_markdown,
    write_summary_report,
)

REPORT_JSON_CANDIDATES = [
    Path("data/reports/night_research/night_research_results.json"),
    Path("data/reports/night_research/night_research_report.json"),
]

DEFAULT_THEME = "黒緑TierSメタコントロール"
DEFAULT_FORMAT = "AD"


st.set_page_config(page_title="MANA Remote Research Loop", layout="wide")


def run_command(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return p.returncode, p.stdout


def load_latest_payload() -> dict[str, Any]:
    for path in REPORT_JSON_CANDIDATES:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def top_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ["top_candidates", "fallback_candidates", "all_candidates"]:
        value = payload.get(key)
        if isinstance(value, list) and value:
            return [x for x in value if isinstance(x, dict)]
    return []


def show_deck(candidate: dict[str, Any]) -> None:
    deck = deck_items_from_candidate(candidate)
    if not deck:
        st.warning("デッキリストを読み取れませんでした。night_research_results.jsonを確認してください。")
        return
    df = pd.DataFrame(deck)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.code("\n".join(f"{d['count']} {d['name']}" for d in deck), language="text")


def candidate_label(c: dict[str, Any], idx: int) -> str:
    name = c.get("deck_name") or c.get("name") or f"Rank {idx + 1}"
    score = c.get("final_fitness", "")
    return f"Rank {idx + 1}: {name} / fitness={score}"


def yes_no(label: str, key: str) -> str:
    return st.selectbox(label, ["", "yes", "no"], key=key)


st.title("MANA Remote Research Loop")
st.caption("PCを使えない時でも、スマホから候補確認・実戦ログ入力・5戦判定を回すための画面です。")

db_path = st.sidebar.text_input("DB path", value=str(DEFAULT_DB))
theme = st.sidebar.text_input("研究テーマ", value=DEFAULT_THEME)
format_name = st.sidebar.selectbox("フォーマット", ["AD", "ND"], index=0)
opponent_default = "火光レイド/ブランド Tier S" if format_name == "AD" else "火光レイド"
opponent = st.sidebar.text_input("仮想敵", value=opponent_default)

tabs = st.tabs(["候補生成/開始", "実戦ログ入力", "5戦判定", "セッション一覧"])

with tabs[0]:
    st.header("候補生成/研究セッション開始")

    col1, col2, col3 = st.columns(3)
    generations = col1.number_input("generations", min_value=1, max_value=20, value=5)
    population = col2.number_input("population", min_value=4, max_value=100, value=20)
    stable = col3.checkbox("stable", value=True)

    st.write("内部的には night_research_runner を実行します。外部サイト上ではPowerShell不要で回せる想定です。")

    if st.button("候補生成を実行", type="primary"):
        cmd = [
            sys.executable,
            "-m",
            "src.night_research_runner",
            "--theme",
            theme,
            "--generations",
            str(int(generations)),
            "--population",
            str(int(population)),
        ]
        if stable:
            cmd.append("--stable")
        # v4/v5以降のrunnerなら --format が使える。古いrunnerなら失敗するため、失敗時にformatなしで再試行。
        cmd_with_format = cmd + ["--format", format_name]
        with st.spinner("候補生成中..."):
            code, out = run_command(cmd_with_format)
            if code != 0 and "unrecognized arguments" in out:
                code, out = run_command(cmd)
        st.code(out[-8000:], language="text")
        if code == 0:
            st.success("候補生成が完了しました。")
        else:
            st.error("候補生成でエラーが出ました。ログを確認してください。")

    payload = load_latest_payload()
    candidates = top_candidates(payload)

    if not candidates:
        st.info("まだ候補がありません。候補生成を実行してください。")
    else:
        st.subheader("候補")
        selected_idx = st.selectbox(
            "使用する候補",
            options=list(range(len(candidates[:10]))),
            format_func=lambda i: candidate_label(candidates[i], i),
        )
        candidate = candidates[selected_idx]
        show_deck(candidate)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("final_fitness", candidate.get("final_fitness", ""))
        c2.metric("Tier S後攻耐性", candidate.get("tier_s_second_resistance_score", candidate.get("Tier S後攻耐性スコア", "")))
        c3.metric("sanity", candidate.get("sanity_score", candidate.get("sanity", {}).get("score", "")))
        c4.metric("theme_fit", candidate.get("theme_fit_score", candidate.get("theme_fit", {}).get("score", "")))

        session_title = st.text_input("セッション名", value=f"{theme} / {format_name} / {opponent}")
        notes = st.text_area("セッションメモ", value="スマホ研究ループ初回セッション")
        if st.button("この候補で研究セッションを開始"):
            sid = create_session(
                db_path=db_path,
                title=session_title,
                theme_name=theme,
                format_name=format_name,
                opponent=opponent,
                candidate=candidate,
                notes=notes,
            )
            st.success(f"研究セッションを開始しました: session_id={sid}")
            st.session_state["active_session_id"] = sid

with tabs[1]:
    st.header("実戦ログ入力")
    sessions = list_sessions(db_path, limit=50)
    if not sessions:
        st.info("まず候補生成/開始タブで研究セッションを開始してください。")
    else:
        default_sid = st.session_state.get("active_session_id", sessions[0]["id"])
        ids = [int(s["id"]) for s in sessions]
        index = ids.index(default_sid) if default_sid in ids else 0
        session_id = st.selectbox(
            "セッション",
            ids,
            index=index,
            format_func=lambda sid: next((f"#{s['id']} {s['title']} / {s.get('match_count', 0)}戦" for s in sessions if int(s["id"]) == int(sid)), str(sid)),
        )
        matches = list_matches(db_path, session_id)
        next_no = len(matches) + 1

        with st.form("match_form"):
            st.subheader(f"Match {next_no}")
            col1, col2, col3, col4 = st.columns(4)
            play_order = col1.selectbox("先後", ["後攻", "先攻"])
            result = col2.selectbox("勝敗", ["lose", "win"])
            finish_turn = col3.number_input("決着ターン", min_value=1, max_value=30, value=5)
            match_opponent = col4.text_input("相手", value=opponent)

            y = yes_no("ヤドックが間に合った", "yadok")
            t = yes_no("トラップ×トラップが有効", "trap")
            r = yes_no("軽量除去が機能", "removal")
            l = yes_no("ロック札が間に合った", "lock")
            x = yes_no("超次元/外部ゾーンが有効", "external")
            i = yes_no("5ターン目までに干渉", "interfere")
            w = yes_no("止めた後に勝ち筋があった", "wincond")

            strong_cards = st.text_input("強かったカード", placeholder="ヤドック, トラップ×トラップ")
            weak_cards = st.text_input("弱かったカード", placeholder="カード名をカンマ区切り")
            dead_cards = st.text_input("腐ったカード", placeholder="カード名をカンマ区切り")
            loss_reason = st.text_input("敗因", placeholder="速度負け / 勝ち筋不足 / 色不足 など")
            notes = st.text_area("メモ")

            submitted = st.form_submit_button("この試合を保存", type="primary")
            if submitted:
                add_match(
                    db_path=db_path,
                    session_id=session_id,
                    match_no=next_no,
                    opponent=match_opponent,
                    format_name=format_name,
                    play_order=play_order,
                    result=result,
                    finish_turn=int(finish_turn),
                    yadok_on_time=y,
                    trap_effective=t,
                    removal_effective=r,
                    lock_on_time=l,
                    external_zone_effective=x,
                    interfered_by_turn5=i,
                    had_win_condition=w,
                    strong_cards=strong_cards,
                    weak_cards=weak_cards,
                    dead_cards=dead_cards,
                    loss_reason=loss_reason,
                    notes=notes,
                )
                st.success("保存しました。")

        if matches:
            st.subheader("入力済みログ")
            st.dataframe(pd.DataFrame(matches), use_container_width=True, hide_index=True)

with tabs[2]:
    st.header("5戦判定")
    sessions = list_sessions(db_path, limit=50)
    if not sessions:
        st.info("研究セッションがありません。")
    else:
        session_id = st.selectbox(
            "判定するセッション",
            [int(s["id"]) for s in sessions],
            format_func=lambda sid: next((f"#{s['id']} {s['title']} / {s.get('match_count', 0)}戦" for s in sessions if int(s["id"]) == int(sid)), str(sid)),
            key="judge_session",
        )
        if st.button("自動判定する", type="primary"):
            summary = summarize_session(db_path, session_id)
            report_path = write_summary_report(db_path, session_id)
            st.success(f"判定レポートを書き出しました: {report_path}")
            st.markdown(summary_to_markdown(summary))
        else:
            matches = list_matches(db_path, session_id)
            st.info(f"現在 {len(matches)} 戦入力済みです。5戦入力後に判定してください。")

with tabs[3]:
    st.header("セッション一覧")
    sessions = list_sessions(db_path, limit=100)
    if sessions:
        st.dataframe(pd.DataFrame(sessions), use_container_width=True, hide_index=True)
    else:
        st.info("まだセッションがありません。")

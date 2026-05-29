from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src.analytics import (
    average_scores,
    best_meta_deck,
    best_novelty_deck,
    best_score_deck,
    evolution_score_history,
    export_rows_to_csv,
    list_battles,
    list_evaluations,
)
from src.ai_deck_builder import DEFAULT_MODEL, build_ai_deck, extract_candidate_cards
from src.backup_manager import (
    backup_csv,
    backup_database,
    create_backup_zip,
    list_backups,
    read_backup_bytes,
    restore_guide,
)
from src.battle_simulator import simulate_battle
from src.card_csv_validator import validate_cards_csv
from src.card_db_completion_checker import check_completion, load_cards
from src.card_db_exporter import (
    export_cards_summary,
    export_completed_cards_csv,
    export_completed_cards_zip,
)
from src.data_health_checker import check_data_health
from src.environment_checker import collect_environment_report
from src.deck_builder import build_deck_for_request
from src.deck_change_analyzer import (
    attach_match_stats_to_versions,
    compare_deck_texts,
    compare_parent_child_stats,
    group_versions_by_deck,
    summarize_changes,
)
from src.card_editor import (
    VALID_CARD_TYPES,
    VALID_CIVILIZATIONS,
    add_card,
    find_card_by_name,
    read_cards,
    update_card,
    validate_card,
)
from src.deck_feedback import generate_feedback
from src.deck_condition_analyzer import analyze_deck_condition
from src.deck_generation_request import DeckGenerationRequest, parse_tag_input
from src.deck_improver import create_improvement_plan
from src.deck_version_manager import (
    ensure_version_tables,
    export_rows_to_csv as export_version_rows_to_csv,
    get_lineage,
    list_deck_changes,
    list_deck_versions,
    save_deck_changes,
    save_deck_version,
)
from src.dashboard import collect_dashboard_data
from src.db_bootstrap import ensure_cards_db_from_csv
from src.evaluate_deck import evaluate_deck
from src.evolutionary_search import WEIGHT_PRESETS, run_evolutionary_search
from src.generate_deck import generate_deck
from src.generated_deck_analyzer import (
    SORT_COLUMNS,
    available_deck_types,
    comparison_summary,
    filter_and_sort_generated_decks,
    generated_decks_to_csv,
)
from src.generated_deck_store import (
    ensure_generated_decks_table,
    load_generated_deck_detail,
    load_generated_decks,
    save_generated_deck,
)
from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH, import_cards
from src.match_log_validator import VALID_PLAY_ORDERS, VALID_RESULTS, validate_match_log
from src.match_recorder import (
    ensure_match_log_table,
    export_match_logs_to_csv,
    list_match_logs,
    save_match_log,
    win_rate_by_deck,
    win_rate_by_opponent,
)
from src.performance_analyzer import (
    analyze_deck_performance,
    fetch_latest_evaluation_by_deck_name,
    fetch_real_match_logs,
)
from src.research_logger import (
    ensure_log_tables,
    save_battle_log,
    save_deck_log,
    save_deck_with_evaluation,
    save_evolution_logs,
)
from src.report_exporter import markdown_to_html, rows_to_csv
from src.report_generator import generate_research_report
from src.release_readiness_checker import check_release_readiness
from src.release_report_exporter import export_release_readiness_report, release_readiness_to_markdown
from src.search_cards import list_civilizations, list_tags, search_cards
from src.settings_manager import env_creation_guide, load_app_settings, setup_guide
from src.simulate_goldfish import simulate_goldfish
from src.tag_suggester import suggest_missing_tags, suggest_tags, suggest_tags_from_text
from src.test_plan_manager import (
    ensure_test_plan_tables,
    export_rows_to_csv as export_test_plan_rows_to_csv,
    list_test_plan_targets,
    list_test_plans,
    save_test_plan,
    targets_for_plan,
    update_test_plan_status,
)
from src.test_result_analyzer import analyze_test_plan, summarize_plan_rows


CARDS_CSV_PATH = Path("data/cards.csv")


st.set_page_config(
    page_title="DMプレイス AIデッキ研究ツール",
    layout="wide",
)


def ensure_database() -> None:
    ensure_cards_db_from_csv()
    ensure_log_tables(DEFAULT_DB_PATH)
    ensure_match_log_table(DEFAULT_DB_PATH)
    ensure_version_tables(DEFAULT_DB_PATH)
    ensure_test_plan_tables(DEFAULT_DB_PATH)
    ensure_generated_decks_table(DEFAULT_DB_PATH)


def render_card(card: dict) -> None:
    tags = [tag for tag in card["tags"].split(";") if tag]
    power = card["power"] if card["power"] is not None else "-"
    race = card["race"] or "-"

    with st.container(border=True):
        st.subheader(card["name"])
        st.caption(f'{card["card_id"]} / {card["civilization"]} / コスト {card["cost"]}')

        col1, col2, col3 = st.columns([1, 1, 2])
        col1.metric("種類", card["card_type"])
        col2.metric("パワー", power)
        col3.write(f"**種族**: {race}")

        st.write(card["text"])
        if tags:
            st.write(" ".join(f"`{tag}`" for tag in tags))


def render_dashboard_page() -> None:
    st.header("ダッシュボード")
    st.caption("カードDB、研究ログ、実戦ログ、検証計画の現在地をまとめて確認します。")

    data = collect_dashboard_data(DEFAULT_DB_PATH, DEFAULT_CSV_PATH)
    card_stats = data["card_stats"]
    research_stats = data["research_stats"]

    st.subheader("カードDB")
    card_cols = st.columns(4)
    card_cols[0].metric("登録カード数", card_stats["card_count"])
    card_cols[1].metric("タグ未設定カード", card_stats["missing_tag_count"])
    card_cols[2].metric("CSVエラー", card_stats["csv_errors"])
    card_cols[3].metric("CSV警告", card_stats["csv_warnings"])

    st.subheader("研究状況")
    research_cols = st.columns(7)
    research_cols[0].metric("保存済み評価", research_stats["evaluation_count"])
    research_cols[1].metric("実戦ログ", research_stats["match_log_count"])
    research_cols[2].metric("デッキバージョン", research_stats["deck_version_count"])
    research_cols[3].metric("進行中テスト計画", research_stats["active_test_plan_count"])
    research_cols[4].metric("再改良候補", len(data["rework_candidates"]))
    research_cols[5].metric("データ健全性", data["data_health"]["status"])
    research_cols[6].metric("環境", data["environment"]["status"])

    if data["data_health"]["issue_count"]:
        st.warning(
            f'データ保守で確認が必要です: {data["data_health"]["issue_count"]}件 / '
            f'quick_check={data["data_health"]["quick_check"]}'
        )
    if data["environment"]["warning_count"]:
        st.warning(f'設定画面で環境警告を確認してください: {data["environment"]["warning_count"]}件')

    st.subheader("次にやるべき作業")
    for action in data["next_actions"]:
        st.info(action)

    focus_col1, focus_col2 = st.columns(2)
    with focus_col1:
        st.subheader("勝率上位デッキ")
        st.dataframe(data["top_decks"], use_container_width=True, hide_index=True)

        st.subheader("検証不足アラート")
        st.dataframe(data["insufficient_alerts"], use_container_width=True, hide_index=True)

    with focus_col2:
        st.subheader("勝率低下中デッキ")
        st.dataframe(data["declining_decks"], use_container_width=True, hide_index=True)

        st.subheader("再改良が必要なデッキ")
        st.dataframe(data["rework_candidates"], use_container_width=True, hide_index=True)

    st.subheader("進行中の検証計画")
    st.dataframe(data["active_plans"], use_container_width=True, hide_index=True)

    st.subheader("直近の実戦ログ")
    st.dataframe(data["recent_logs"], use_container_width=True, hide_index=True)


def render_deck_table(deck: list[dict]) -> None:
    rows = [
        {
            "枚数": card["quantity"],
            "カード名": card["name"],
            "文明": card["civilization"],
            "コスト": card["cost"],
            "種類": card["card_type"],
            "タグ": card["tags"],
        }
        for card in deck
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def deck_to_text(deck: list[dict]) -> str:
    return "\n".join(f'{card["quantity"]} {card["name"]}' for card in deck)


def parse_deck_text(text: str, cards: list[dict]) -> tuple[list[dict], list[str]]:
    cards_by_name = {card["name"]: card for card in cards}
    cards_by_id = {card["card_id"]: card for card in cards}
    grouped: dict[str, dict] = {}
    errors = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not parts[0].isdigit():
            errors.append(f"{line_number}行目: `枚数 カード名` の形式で入力してください。")
            continue

        quantity = int(parts[0])
        key = parts[1].strip()
        card = cards_by_name.get(key) or cards_by_id.get(key)
        if card is None:
            errors.append(f"{line_number}行目: `{key}` がカードDBにありません。")
            continue

        card_id = card["card_id"]
        if card_id not in grouped:
            grouped[card_id] = dict(card)
            grouped[card_id]["quantity"] = 0
        grouped[card_id]["quantity"] += quantity

    return list(grouped.values()), errors


def render_evaluation(summary: dict) -> None:
    score_col, novelty_col, meta_col, total_col = st.columns(4)
    score_col.metric("総合スコア", f'{summary["score"]} / 100')
    novelty_col.metric("未知性スコア", f'{summary["novelty_score"]} / 100')
    meta_col.metric("メタ適性", f'{summary["meta_score"]} / 100')
    total_col.metric("デッキ枚数", summary["total_cards"])

    role_cols = st.columns(4)
    for col, (role, count) in zip(role_cols, summary["role_counts"].items()):
        col.metric(role, count)

    if summary["warnings"]:
        for warning in summary["warnings"]:
            st.warning(warning)
    else:
        st.success("MVP評価では大きな警告はありません。")

    curve_col, civ_col = st.columns(2)
    with curve_col:
        st.subheader("マナカーブ")
        st.bar_chart(summary["cost_curve"])
    with civ_col:
        st.subheader("文明バランス")
        st.bar_chart(summary["civilization_counts"])

    st.subheader("タグ集計")
    st.dataframe(
        [{"タグ": tag, "枚数": count} for tag, count in summary["tag_counts"].items()],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("未知性スコアの内訳"):
        novelty = summary["novelty"]
        rarity = novelty["rarity"]
        st.write(f'既存デッキ参照数: {novelty["reference_deck_count"]}')
        st.write(f'最大類似度: {novelty["max_similarity"]:.2f}')
        st.dataframe(
            [
                {"指標": "カード種類の散らばり", "値": round(rarity["card_variety"], 3)},
                {"指標": "タグ種類の散らばり", "値": round(rarity["tag_variety"], 3)},
                {"指標": "汎用役割外タグ比率", "値": round(rarity["off_role_tag_ratio"], 3)},
                {"指標": "文明ミックス", "値": round(rarity["civilization_mix"], 3)},
                {"指標": "高コスト寄りカーブ", "値": round(rarity["unusual_curve"], 3)},
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("仮想メタゲーム相性")
    meta = summary["meta_matchups"]
    st.dataframe(
        [
            {
                "対面": matchup["profile"],
                "相性スコア": matchup["score"],
                "タグ適合": matchup["tag_coverage"],
                "有利要因": " / ".join(matchup["favorable_factors"]),
                "不利要因": " / ".join(matchup["unfavorable_factors"]),
            }
            for matchup in meta["matchups"].values()
        ],
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("相性コメント"):
        for matchup in meta["matchups"].values():
            st.write(f'**対{matchup["profile"]}: {matchup["score"]} / 100**')
            if matchup["favorable_factors"]:
                st.write("有利要因: " + " / ".join(matchup["favorable_factors"]))
            if matchup["unfavorable_factors"]:
                st.write("不利要因: " + " / ".join(matchup["unfavorable_factors"]))


def render_simulation(summary: dict) -> None:
    st.write(f'{summary["trials"]}回試行 / {summary["max_turns"]}ターン / デッキ{summary["deck_size"]}枚')

    cols = st.columns(4)
    cols[0].metric("初動成功率", f'{summary["early_success_rate"]:.1%}')
    cols[1].metric("マナ加速確認率", f'{summary["ramp_seen_rate"]:.1%}')
    cols[2].metric("受け札確認率", f'{summary["defense_seen_rate"]:.1%}')
    cols[3].metric("フィニッシャー確認率", f'{summary["finisher_seen_rate"]:.1%}')

    st.subheader("初動ターン分布")
    st.bar_chart(summary["early_turn_distribution"])


def render_search_page() -> None:
    with st.sidebar:
        st.header("検索条件")

        civilizations = [""] + list_civilizations(DEFAULT_DB_PATH)
        tags = [""] + list_tags(DEFAULT_DB_PATH)

        civilization = st.selectbox("文明", civilizations, format_func=lambda x: x or "すべて")
        cost_range = st.slider("コスト", 0, 10, (0, 10))
        tag = st.selectbox("タグ", tags, format_func=lambda x: x or "すべて")
        keyword = st.text_input("キーワード", placeholder="カード名・種族・能力テキスト")

    results = search_cards(
        DEFAULT_DB_PATH,
        civilization=civilization,
        min_cost=cost_range[0],
        max_cost=cost_range[1],
        tag=tag,
        keyword=keyword,
    )

    st.write(f"検索結果: **{len(results)}枚**")

    if not results:
        st.info("条件に合うカードがありません。検索条件を広げてください。")
        return

    for card in results:
        render_card(card)


def render_generate_page() -> None:
    st.header("デッキ生成")
    st.caption("入力した文明、デッキタイプ、タグ、役割比率を使って検証用デッキを生成します。")

    st.subheader("デッキ生成条件")
    deck_name = st.text_input(
        "デッキ名",
        value="火自然ドラゴンランプ検証",
    )
    civilizations = st.multiselect(
        "使用文明",
        ["自然", "水", "闇", "火", "光", "無色"],
        default=["火", "自然"],
    )
    deck_type = st.selectbox(
        "想定デッキタイプ",
        [
            "速攻",
            "ビートダウン",
            "中速",
            "コントロール",
            "ランプ",
            "コンボ",
            "ロック",
            "耐久",
            "墓地利用",
            "進化",
            "ランダム",
        ],
    )
    focus_tags_text = st.text_input(
        "重視タグ（; 区切り）",
        value="マナ加速;ドラゴン;フィニッシャー;除去;受け札",
    )
    avoid_tags_text = st.text_input(
        "避けたいタグ（; 区切り）",
        value="",
    )
    strategy_note = st.text_area(
        "想定・戦略メモ",
        value="序盤にマナ加速し、中盤に除去、終盤に大型ドラゴンで決着する。",
    )
    deck_size = st.number_input(
        "デッキ枚数",
        min_value=20,
        max_value=60,
        value=40,
        step=1,
    )

    ratio_col1, ratio_col2, ratio_col3 = st.columns(3)
    early_ratio = ratio_col1.slider("初動・マナ加速比率", 0, 60, 30, 5)
    defense_ratio = ratio_col2.slider("受け札比率", 0, 60, 30, 5)
    finisher_ratio = ratio_col3.slider("フィニッシャー比率", 0, 60, 20, 5)
    seed = st.number_input("乱数シード", min_value=0, value=1, step=1)

    request = DeckGenerationRequest(
        deck_name=deck_name,
        civilizations=civilizations,
        deck_type=deck_type,
        focus_tags=parse_tag_input(focus_tags_text),
        avoid_tags=parse_tag_input(avoid_tags_text),
        strategy_note=strategy_note,
        deck_size=int(deck_size),
        early_ratio=int(early_ratio),
        defense_ratio=int(defense_ratio),
        finisher_ratio=int(finisher_ratio),
    )

    if st.button("条件からデッキを生成", type="primary"):
        deck = build_deck_for_request(request, DEFAULT_DB_PATH, seed=int(seed))
        st.session_state["generated_deck"] = deck
        st.session_state["deck_text"] = deck_to_text(deck)
        st.session_state["deck_generation_request"] = request

    deck = st.session_state.get("generated_deck", [])
    if not deck:
        st.info("条件を選んでデッキを生成してください。")
        render_generated_deck_history()
        return

    used_request = st.session_state.get("deck_generation_request", request)
    st.markdown("### 使用した生成条件")
    st.write(f"デッキ名: {used_request.deck_name}")
    st.write(f"文明: {' / '.join(used_request.civilizations) if used_request.civilizations else '指定なし'}")
    st.write(f"デッキタイプ: {used_request.deck_type}")
    st.write(f"重視タグ: {'; '.join(used_request.focus_tags) if used_request.focus_tags else 'なし'}")
    st.write(f"避けたいタグ: {'; '.join(used_request.avoid_tags) if used_request.avoid_tags else 'なし'}")
    st.write(f"想定: {used_request.strategy_note}")
    st.write(
        f"枚数: {used_request.deck_size} / "
        f"初動・マナ加速 {used_request.early_ratio}% / "
        f"受け札 {used_request.defense_ratio}% / "
        f"フィニッシャー {used_request.finisher_ratio}%"
    )

    analysis = analyze_deck_condition(
        deck_cards=deck,
        civilizations=used_request.civilizations,
        focus_tags=used_request.focus_tags,
        avoid_tags=used_request.avoid_tags,
        target_starter_count=round(used_request.deck_size * used_request.early_ratio / 100),
        target_defense_count=round(used_request.deck_size * used_request.defense_ratio / 100),
        target_finisher_count=round(used_request.deck_size * used_request.finisher_ratio / 100),
    )
    st.markdown("### 生成条件への適合度")
    fit_col1, fit_col2, fit_col3, fit_col4 = st.columns(4)
    fit_col1.metric("条件適合スコア", f"{analysis.condition_score} / 100")
    fit_col2.metric("文明一致率", f"{analysis.civilization_match_rate}%")
    fit_col3.metric("重視タグ一致数", sum(analysis.focus_tag_hits.values()))
    fit_col4.metric("避けたいタグ混入数", sum(analysis.avoid_tag_hits.values()))

    role_col1, role_col2, role_col3, role_col4 = st.columns(4)
    role_col1.metric("初動枚数", analysis.starter_count)
    role_col2.metric("受け札枚数", analysis.defense_count)
    role_col3.metric("フィニッシャー枚数", analysis.finisher_count)
    role_col4.metric("平均コスト", analysis.average_cost)

    extra_col1, extra_col2 = st.columns(2)
    extra_col1.metric("除去枚数", analysis.removal_count)
    extra_col2.metric("ドロー/リソース枚数", analysis.draw_count)

    st.markdown("#### 重視タグ一致")
    st.json(analysis.focus_tag_hits)

    st.markdown("#### 避けたいタグ混入")
    st.json(analysis.avoid_tag_hits)

    if analysis.warnings:
        st.markdown("#### 警告")
        for warning in analysis.warnings:
            st.warning(warning)

    if analysis.comments:
        st.markdown("#### コメント")
        for comment in analysis.comments:
            st.info(comment)

    render_deck_table(deck)
    st.text_area("デッキリスト", value=deck_to_text(deck), height=260)
    summary = evaluate_deck(deck)
    render_evaluation(summary)

    log_col1, log_col2 = st.columns([2, 1])
    log_name = log_col1.text_input("保存名", value=used_request.deck_name or "生成デッキ")
    if log_col2.button("生成デッキ評価を保存"):
        deck_id = save_deck_with_evaluation(log_name, "generated", deck_to_text(deck), summary, DEFAULT_DB_PATH)
        st.success(f"保存しました: {deck_id}")

    st.markdown("### 生成デッキの保存")
    if st.button("この生成デッキを保存"):
        saved_id = save_generated_deck(
            deck_name=used_request.deck_name,
            civilizations=used_request.civilizations,
            deck_type=used_request.deck_type,
            focus_tags=used_request.focus_tags,
            avoid_tags=used_request.avoid_tags,
            strategy_note=used_request.strategy_note,
            deck_cards=deck,
            analysis=analysis,
            evaluation=summary,
            db_path=DEFAULT_DB_PATH,
        )
        st.success(f"生成デッキを保存しました。ID: {saved_id}")

    render_generated_deck_history()


def render_generated_deck_history() -> None:
    st.markdown("### 保存済み生成デッキ")

    saved_df = load_generated_decks(DEFAULT_DB_PATH)
    if saved_df.empty:
        st.info("保存済み生成デッキはまだありません。")
        return

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    deck_type_options = [""] + available_deck_types(saved_df)
    deck_type_filter = filter_col1.selectbox(
        "デッキタイプで絞り込み",
        deck_type_options,
        format_func=lambda value: value or "すべて",
    )
    sort_label = filter_col2.selectbox("並び替え", list(SORT_COLUMNS.keys()), index=1)
    ascending = filter_col3.checkbox("昇順", value=False)

    view_df = filter_and_sort_generated_decks(
        saved_df,
        deck_type=deck_type_filter,
        sort_label=sort_label,
        ascending=ascending,
    )
    st.dataframe(view_df, use_container_width=True, hide_index=True)

    if view_df.empty:
        st.info("条件に合う保存済み生成デッキはありません。")
        return

    st.download_button(
        label="保存済み生成デッキ一覧をCSV出力",
        data=generated_decks_to_csv(view_df),
        file_name="generated_decks.csv",
        mime="text/csv",
    )

    comparison_rows = comparison_summary(view_df)
    if comparison_rows:
        st.markdown("#### 比較サマリー")
        st.dataframe(comparison_rows, use_container_width=True, hide_index=True)

    selected_id = st.selectbox(
        "詳細表示する保存デッキ",
        [int(value) for value in view_df["id"].tolist()],
        format_func=lambda value: f"ID {value}",
    )
    detail = load_generated_deck_detail(int(selected_id), DEFAULT_DB_PATH)
    if detail:
        st.write(f"**{detail.get('deck_name', '')}** / {detail.get('created_at', '')}")
        st.write(f"文明: {detail.get('civilizations') or '指定なし'}")
        st.write(f"重視タグ: {detail.get('focus_tags') or 'なし'}")
        st.write(f"避けたいタグ: {detail.get('avoid_tags') or 'なし'}")
        st.write(f"戦略メモ: {detail.get('strategy_note') or ''}")
        render_deck_table(detail.get("deck_cards", []))


def render_evaluate_page() -> None:
    st.header("デッキ評価")
    st.caption("1行に `枚数 カード名` の形式で入力してください。カードIDでも入力できます。")

    cards = search_cards(DEFAULT_DB_PATH)
    default_text = st.session_state.get("deck_text", "")
    deck_text = st.text_area("デッキリスト", value=default_text, height=320)

    if not deck_text.strip():
        st.info("デッキリストを入力するか、デッキ生成画面で生成してください。")
        return

    deck, errors = parse_deck_text(deck_text, cards)
    for error in errors:
        st.error(error)

    if errors:
        return

    render_deck_table(deck)
    summary = evaluate_deck(deck)
    render_evaluation(summary)

    log_col1, log_col2 = st.columns([2, 1])
    log_name = log_col1.text_input("保存名", value="評価デッキ")
    if log_col2.button("評価結果を保存", type="primary"):
        deck_id = save_deck_with_evaluation(log_name, "evaluation", deck_to_text(deck), summary, DEFAULT_DB_PATH)
        st.success(f"保存しました: {deck_id}")


def render_simulate_page() -> None:
    st.header("一人回しシミュレーション")
    st.caption("初手5枚、毎ターンドロー、毎ターン1枚マナチャージの簡易モデルでタグ確認率を測ります。")

    cards = search_cards(DEFAULT_DB_PATH)
    generated_deck = st.session_state.get("generated_deck", [])
    source_options = ["生成デッキ", "入力デッキ"] if generated_deck else ["入力デッキ"]
    source = st.radio("シミュレーション対象", source_options, horizontal=True)

    if source == "生成デッキ" and generated_deck:
        deck = generated_deck
        render_deck_table(deck)
    else:
        default_text = st.session_state.get("deck_text", "")
        deck_text = st.text_area("デッキリスト", value=default_text, height=300)
        if not deck_text.strip():
            st.info("デッキリストを入力するか、先にデッキ生成画面で生成してください。")
            return
        deck, errors = parse_deck_text(deck_text, cards)
        for error in errors:
            st.error(error)
        if errors:
            return

    config_col1, config_col2, config_col3 = st.columns(3)
    trials = config_col1.number_input("試行回数", min_value=100, max_value=10000, value=1000, step=100)
    max_turns = config_col2.number_input("最大ターン", min_value=1, max_value=10, value=5, step=1)
    seed = config_col3.number_input("乱数シード", min_value=0, value=1, step=1)

    if st.button("シミュレーション実行", type="primary"):
        summary = simulate_goldfish(deck, trials=int(trials), max_turns=int(max_turns), seed=int(seed))
        st.session_state["simulation_summary"] = summary

    summary = st.session_state.get("simulation_summary")
    if summary:
        render_simulation(summary)


def render_ai_deck_page() -> None:
    st.header("AIデッキ生成")
    st.caption("カードDBから候補を抽出し、候補カードだけを使って未知アーキタイプ寄りのデッキ案を作ります。")

    civilizations = list_civilizations(DEFAULT_DB_PATH)
    format_name = st.text_input("フォーマット", placeholder="例: New Division / All Division")
    selected_civs = st.multiselect("文明", civilizations)
    concept = st.text_area("コンセプト", placeholder="例: マナ加速から大型フィニッシャーへつなぐ新型コントロール")
    required_cards = st.text_area("必ず使いたいカード", placeholder="カード名またはカードID。複数は改行またはカンマ区切り")
    target_opponent = st.text_area("対策したい相手", placeholder="例: 速攻、ハンデス、呪文ロック")
    model = st.text_input("モデル", value=DEFAULT_MODEL)

    candidates = extract_candidate_cards(
        DEFAULT_DB_PATH,
        civilizations=selected_civs,
        concept=concept,
        required_cards=required_cards,
        target_opponent=target_opponent,
    )
    with st.expander(f"候補カードを確認 ({len(candidates)}枚)"):
        st.dataframe(
            [
                {
                    "カード名": card["name"],
                    "文明": card["civilization"],
                    "コスト": card["cost"],
                    "種類": card["card_type"],
                    "タグ": card["tags"],
                }
                for card in candidates
            ],
            use_container_width=True,
            hide_index=True,
        )

    if st.button("AIデッキ案を生成", type="primary"):
        try:
            result = build_ai_deck(
                DEFAULT_DB_PATH,
                format_name=format_name,
                civilizations=selected_civs,
                concept=concept,
                required_cards=required_cards,
                target_opponent=target_opponent,
                model=model,
            )
            st.session_state["ai_deck_result"] = result
        except Exception as exc:
            st.error(str(exc))

    result = st.session_state.get("ai_deck_result")
    if result:
        st.write(f'使用モデル: `{result["model"]}` / 候補カード: {result["candidate_count"]}枚')
        st.markdown(result["text"])
        st.info("AI出力の40枚リストをデッキ評価画面に貼り付けると、未知性スコアを含めて評価できます。")


def _deck_input(label: str, cards: list[dict], default_text: str) -> tuple[list[dict], list[str]]:
    deck_text = st.text_area(label, value=default_text, height=260)
    if not deck_text.strip():
        return [], [f"{label}を入力してください。"]
    return parse_deck_text(deck_text, cards)


def render_battle_page() -> None:
    st.header("簡易AI対戦")
    st.caption("タグ、マナカーブ、評価スコアを使ってデッキ同士の勝率傾向を推定します。")

    cards = search_cards(DEFAULT_DB_PATH)
    generated_deck = st.session_state.get("generated_deck", [])
    generated_text = deck_to_text(generated_deck) if generated_deck else ""

    use_generated_a = generated_deck and st.checkbox("デッキAに生成デッキを使う", value=True)
    use_generated_b = generated_deck and st.checkbox("デッキBに生成デッキを使う", value=False)

    col_a, col_b = st.columns(2)
    with col_a:
        if use_generated_a:
            deck_a = generated_deck
            errors_a = []
            st.text_area("デッキA", value=generated_text, height=260, disabled=True)
        else:
            deck_a, errors_a = _deck_input("デッキA", cards, st.session_state.get("deck_text", ""))

    with col_b:
        if use_generated_b:
            deck_b = generated_deck
            errors_b = []
            st.text_area("デッキB", value=generated_text, height=260, disabled=True)
        else:
            deck_b, errors_b = _deck_input("デッキB", cards, "")

    for error in errors_a + errors_b:
        st.error(error)
    if errors_a or errors_b:
        return

    config_col1, config_col2 = st.columns(2)
    trials = config_col1.number_input("試行回数", min_value=100, max_value=1000, value=500, step=100)
    seed = config_col2.number_input("乱数シード", min_value=0, value=1, step=1)

    if st.button("対戦シミュレーション実行", type="primary"):
        st.session_state["battle_result"] = simulate_battle(deck_a, deck_b, trials=int(trials), seed=int(seed))
        st.session_state["battle_deck_a_text"] = deck_to_text(deck_a)
        st.session_state["battle_deck_b_text"] = deck_to_text(deck_b)

    result = st.session_state.get("battle_result")
    if not result:
        return

    cols = st.columns(3)
    cols[0].metric("デッキA勝率", f'{result["deck_a_win_rate"]:.1%}', f'{result["deck_a_wins"]}勝')
    cols[1].metric("デッキB勝率", f'{result["deck_b_win_rate"]:.1%}', f'{result["deck_b_wins"]}勝')
    cols[2].metric("平均決着ターン", f'{result["average_finish_turn"]:.1f}')

    st.subheader("比較指標")
    st.dataframe(
        [
            {
                "デッキ": "A",
                "基礎パワー": result["deck_a"]["base_power"],
                "総合スコア": result["deck_a"]["summary"]["score"],
                "未知性": result["deck_a"]["summary"]["novelty_score"],
                "メタ適性": result["deck_a"]["summary"]["meta_score"],
            },
            {
                "デッキ": "B",
                "基礎パワー": result["deck_b"]["base_power"],
                "総合スコア": result["deck_b"]["summary"]["score"],
                "未知性": result["deck_b"]["summary"]["novelty_score"],
                "メタ適性": result["deck_b"]["summary"]["meta_score"],
            },
        ],
        use_container_width=True,
        hide_index=True,
    )

    factor_col_a, factor_col_b = st.columns(2)
    with factor_col_a:
        st.subheader("デッキAの要因")
        for line in result["deck_a"]["favorable_factors"]:
            st.success(line)
        for line in result["deck_a"]["unfavorable_factors"]:
            st.warning(line)
    with factor_col_b:
        st.subheader("デッキBの要因")
        for line in result["deck_b"]["favorable_factors"]:
            st.success(line)
        for line in result["deck_b"]["unfavorable_factors"]:
            st.warning(line)

    save_col1, save_col2 = st.columns(2)
    name_a = save_col1.text_input("保存名 デッキA", value="対戦デッキA")
    name_b = save_col2.text_input("保存名 デッキB", value="対戦デッキB")
    if st.button("対戦結果を保存"):
        deck_a_id = save_deck_log(name_a, "battle_a", st.session_state.get("battle_deck_a_text", ""), DEFAULT_DB_PATH)
        deck_b_id = save_deck_log(name_b, "battle_b", st.session_state.get("battle_deck_b_text", ""), DEFAULT_DB_PATH)
        battle_id = save_battle_log(deck_a_id, deck_b_id, result, DEFAULT_DB_PATH)
        st.success(f"対戦ログを保存しました: {battle_id}")


def _render_search_result_deck(title: str, result: dict | None) -> None:
    if not result:
        st.info(f"{title}は見つかりませんでした。")
        return
    st.subheader(title)
    cols = st.columns(4)
    cols[0].metric("適応度", result["fitness"])
    cols[1].metric("総合", result["summary"]["score"])
    cols[2].metric("未知性", result["summary"]["novelty_score"])
    cols[3].metric("メタ適性", result["summary"]["meta_score"])
    render_deck_table(result["deck"])
    st.text_area(f"{title} デッキリスト", value=deck_to_text(result["deck"]), height=220)


def render_evolution_page() -> None:
    st.header("進化探索")
    st.caption("評価・選抜・突然変異を繰り返し、強さと未知性を両立する候補を探索します。")

    civilizations = list_civilizations(DEFAULT_DB_PATH)
    config_col1, config_col2 = st.columns(2)
    generations = config_col1.number_input("世代数", min_value=1, max_value=30, value=8, step=1)
    population_size = config_col2.number_input("個体数", min_value=2, max_value=40, value=12, step=2)
    selected_civs = st.multiselect("文明", civilizations)
    focus = st.selectbox("重視項目", list(WEIGHT_PRESETS.keys()))
    seed = st.number_input("乱数シード", min_value=0, value=1, step=1)

    if st.button("進化探索を実行", type="primary"):
        st.session_state["evolution_result"] = run_evolutionary_search(
            DEFAULT_DB_PATH,
            generations=int(generations),
            population_size=int(population_size),
            civilizations=selected_civs,
            focus=focus,
            seed=int(seed),
        )

    result = st.session_state.get("evolution_result")
    if not result:
        return

    st.write(
        f'{result["generations"]}世代 / {result["population_size"]}個体 / '
        f'重視項目: {result["focus"]}'
    )
    st.subheader("世代ごとのスコア推移")
    st.line_chart(
        [
            {
                "世代": item["generation"],
                "適応度": item["fitness"],
                "総合": item["score"],
                "未知性": item["novelty_score"],
                "メタ適性": item["meta_score"],
            }
            for item in result["history"]
        ],
        x="世代",
        y=["適応度", "総合", "未知性", "メタ適性"],
    )

    tab_overall, tab_novelty, tab_meta = st.tabs(["総合最良", "未知性最大", "メタ適性最大"])
    with tab_overall:
        _render_search_result_deck("総合最良デッキ", result["best_overall"])
    with tab_novelty:
        _render_search_result_deck("未知性最大デッキ", result["best_novelty"])
    with tab_meta:
        _render_search_result_deck("メタ適性最大デッキ", result["best_meta"])

    if st.button("進化探索ログを保存"):
        run_id = save_evolution_logs(result, DEFAULT_DB_PATH)
        st.success(f"進化探索ログを保存しました: {run_id}")


def _top_deck_card(label: str, deck: dict | None) -> None:
    st.subheader(label)
    if not deck:
        st.info("まだ保存データがありません。")
        return
    cols = st.columns(3)
    cols[0].metric("総合", deck["total_score"])
    cols[1].metric("未知性", deck["novelty_score"])
    cols[2].metric("メタ適性", deck["meta_score"])
    st.write(f'**{deck["name"]}** / `{deck["deck_id"]}`')
    with st.expander("デッキリスト"):
        st.text(deck["deck_text"])


def render_research_log_page() -> None:
    st.header("研究ログ")
    st.caption("保存した評価、対戦、進化探索のログを一覧・集計します。")

    stats = average_scores(DEFAULT_DB_PATH)
    cols = st.columns(4)
    cols[0].metric("保存評価数", stats["count"])
    cols[1].metric("平均総合", stats["avg_total_score"])
    cols[2].metric("平均未知性", stats["avg_novelty_score"])
    cols[3].metric("平均メタ適性", stats["avg_meta_score"])

    top_col1, top_col2, top_col3 = st.columns(3)
    with top_col1:
        _top_deck_card("最高スコアデッキ", best_score_deck(DEFAULT_DB_PATH))
    with top_col2:
        _top_deck_card("未知性最大デッキ", best_novelty_deck(DEFAULT_DB_PATH))
    with top_col3:
        _top_deck_card("メタ適性最大デッキ", best_meta_deck(DEFAULT_DB_PATH))

    evaluations = list_evaluations(DEFAULT_DB_PATH)
    st.subheader("保存済み評価")
    st.dataframe(evaluations, use_container_width=True, hide_index=True)
    st.download_button(
        "評価ログCSVをダウンロード",
        data=export_rows_to_csv(evaluations).encode("utf-8-sig"),
        file_name="evaluation_logs.csv",
        mime="text/csv",
        disabled=not evaluations,
    )

    battles = list_battles(DEFAULT_DB_PATH)
    st.subheader("対戦ログ")
    st.dataframe(battles, use_container_width=True, hide_index=True)
    st.download_button(
        "対戦ログCSVをダウンロード",
        data=export_rows_to_csv(battles).encode("utf-8-sig"),
        file_name="battle_logs.csv",
        mime="text/csv",
        disabled=not battles,
    )

    evolution = evolution_score_history(DEFAULT_DB_PATH)
    st.subheader("進化探索ログ")
    st.dataframe(evolution, use_container_width=True, hide_index=True)
    if evolution:
        st.line_chart(
            evolution,
            x="generation",
            y=["best_score", "best_novelty_score", "best_meta_score"],
        )
    st.download_button(
        "進化探索ログCSVをダウンロード",
        data=export_rows_to_csv(evolution).encode("utf-8-sig"),
        file_name="evolution_logs.csv",
        mime="text/csv",
        disabled=not evolution,
    )


def render_match_log_page() -> None:
    st.header("対戦ログ")
    st.caption("実戦対戦ログを保存し、デッキ別・相手タイプ別の勝率を集計します。")

    default_deck_text = st.session_state.get("deck_text", "")
    with st.form("real_match_log_form"):
        deck_name = st.text_input("使用デッキ名")
        deck_text = st.text_area("デッキリスト", value=default_deck_text, height=180)
        opponent_deck_type = st.text_input("相手デッキタイプ", placeholder="例: 速攻 / 中速 / コントロール")
        order_col, result_col, turn_col = st.columns(3)
        play_order = order_col.selectbox("先攻 / 後攻", VALID_PLAY_ORDERS)
        result = result_col.selectbox("勝敗", VALID_RESULTS)
        finish_turn = turn_col.number_input("決着ターン", min_value=1, max_value=99, value=6, step=1)
        win_reason = st.text_area("勝因")
        lose_reason = st.text_area("敗因")
        key_cards = st.text_area("使用カード・活躍カード")
        dead_cards = st.text_area("腐ったカード")
        mistake_notes = st.text_area("プレミ・分岐判断メモ")
        video_ref = st.text_input("動画ファイルパス / URL")
        memo = st.text_area("メモ")

        submitted = st.form_submit_button("対戦ログを保存")
        if submitted:
            log = {
                "deck_name": deck_name,
                "deck_text": deck_text,
                "opponent_deck_type": opponent_deck_type,
                "play_order": play_order,
                "result": result,
                "finish_turn": int(finish_turn),
                "win_reason": win_reason,
                "lose_reason": lose_reason,
                "key_cards": key_cards,
                "dead_cards": dead_cards,
                "mistake_notes": mistake_notes,
                "video_ref": video_ref,
                "memo": memo,
            }
            errors = validate_match_log(log)
            if errors:
                for error in errors:
                    st.error(error)
            else:
                try:
                    match_id = save_match_log(log, DEFAULT_DB_PATH)
                    st.success(f"対戦ログを保存しました: #{match_id}")
                except Exception as exc:
                    st.error(f"保存に失敗しました: {exc}")

    logs = list_match_logs(DEFAULT_DB_PATH)
    deck_rates = win_rate_by_deck(DEFAULT_DB_PATH)
    opponent_rates = win_rate_by_opponent(DEFAULT_DB_PATH)

    st.subheader("デッキ別勝率")
    st.dataframe(deck_rates, use_container_width=True, hide_index=True)

    st.subheader("相手デッキタイプ別勝率")
    st.dataframe(opponent_rates, use_container_width=True, hide_index=True)

    st.subheader("保存済み対戦ログ")
    st.dataframe(logs, use_container_width=True, hide_index=True)
    st.download_button(
        "対戦ログCSVをダウンロード",
        data=export_match_logs_to_csv(logs).encode("utf-8-sig"),
        file_name="real_match_logs.csv",
        mime="text/csv",
        disabled=not logs,
    )

    st.subheader("実戦成績フィードバック")
    real_logs = fetch_real_match_logs(DEFAULT_DB_PATH)
    performance = analyze_deck_performance(
        real_logs,
        fetch_latest_evaluation_by_deck_name(DEFAULT_DB_PATH),
    )

    if not performance:
        st.info("まだ対戦ログがありません。")
        return

    selected_deck = st.selectbox("分析するデッキ", list(performance.keys()))
    stats = performance[selected_deck]
    overall = stats["overall"]
    evaluation = stats.get("evaluation")

    metric_cols = st.columns(6)
    metric_cols[0].metric("試合数", overall["matches"])
    metric_cols[1].metric("実戦勝率", f'{overall["win_rate"]}%')
    metric_cols[2].metric("平均決着ターン", stats["average_finish_turn"] or "-")
    metric_cols[3].metric("AI総合", evaluation["total_score"] if evaluation else "-")
    metric_cols[4].metric("AIメタ適性", evaluation["meta_score"] if evaluation else "-")
    metric_cols[5].metric("勝率-総合", stats["score_gap"] if stats["score_gap"] is not None else "-")

    st.write("### 対面別勝率")
    st.dataframe(
        [
            {
                "相手デッキタイプ": opponent,
                "試合数": item["matches"],
                "勝ち": item["wins"],
                "負け": item["losses"],
                "勝率": item["win_rate"],
            }
            for opponent, item in stats["by_opponent"].items()
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.write("### 先攻/後攻別勝率")
    st.dataframe(
        [
            {
                "先攻/後攻": order,
                "試合数": item["matches"],
                "勝ち": item["wins"],
                "負け": item["losses"],
                "勝率": item["win_rate"],
            }
            for order, item in stats["by_play_order"].items()
        ],
        use_container_width=True,
        hide_index=True,
    )

    card_col1, card_col2 = st.columns(2)
    with card_col1:
        st.write("### 活躍カード")
        st.dataframe(
            [{"カード": card, "記録回数": count} for card, count in stats["key_cards"]],
            use_container_width=True,
            hide_index=True,
        )
    with card_col2:
        st.write("### 腐ったカード")
        st.dataframe(
            [{"カード": card, "記録回数": count} for card, count in stats["dead_cards"]],
            use_container_width=True,
            hide_index=True,
        )

    st.write("### 改善コメント")
    for comment in generate_feedback(selected_deck, stats):
        st.info(comment)

    st.write("### デッキ改良候補")
    latest_deck_text = next(
        (
            log.get("deck_text", "")
            for log in real_logs
            if (log.get("deck_name") or "未設定") == selected_deck and log.get("deck_text")
        ),
        "",
    )
    if not latest_deck_text.strip():
        st.info("このデッキの対戦ログにデッキリストがないため、改良案を生成できません。")
        return

    cards = search_cards(DEFAULT_DB_PATH)
    current_deck, deck_errors = parse_deck_text(latest_deck_text, cards)
    if deck_errors:
        for error in deck_errors:
            st.warning(error)
        st.info("デッキリストをカードDBで解決できないため、改良案の生成を止めています。")
        return

    plan = create_improvement_plan(current_deck, stats, DEFAULT_DB_PATH)
    for note in plan["notes"]:
        st.info(note)

    plan_col1, plan_col2 = st.columns(2)
    with plan_col1:
        st.write("#### 推奨タグ")
        if plan["needed_tags"]:
            st.write(" ".join(f'`{tag}`' for tag in plan["needed_tags"]))
        else:
            st.write("なし")

        st.write("#### 抜く候補")
        st.dataframe(plan["cut_cards"], use_container_width=True, hide_index=True)

    with plan_col2:
        st.write("#### 入れる候補")
        st.dataframe(
            [
                {
                    "カード名": card["name"],
                    "文明": card["civilization"],
                    "コスト": card["cost"],
                    "タグ": card["tags"],
                }
                for card in plan["recommendations"]
            ],
            use_container_width=True,
            hide_index=True,
        )

    before = plan["before"]
    after = plan["after"]
    if before and after:
        st.write("#### 改良前後の評価比較")
        st.dataframe(
            [
                {
                    "項目": "総合スコア",
                    "改良前": before["score"],
                    "改良後": after["score"],
                    "差分": after["score"] - before["score"],
                },
                {
                    "項目": "未知性スコア",
                    "改良前": before["novelty_score"],
                    "改良後": after["novelty_score"],
                    "差分": after["novelty_score"] - before["novelty_score"],
                },
                {
                    "項目": "メタ適性",
                    "改良前": before["meta_score"],
                    "改良後": after["meta_score"],
                    "差分": after["meta_score"] - before["meta_score"],
                },
            ],
            use_container_width=True,
            hide_index=True,
        )

    improved_text = deck_to_text(plan["improved_deck"])
    st.text_area("改良デッキ案", value=improved_text, height=260)
    action_col1, action_col2 = st.columns(2)
    if action_col1.button("改良案をデッキ評価へ送る"):
        st.session_state["deck_text"] = improved_text
        st.success("改良デッキ案をデッキ評価画面へ送れる状態にしました。左メニューからデッキ評価を開いてください。")

    with st.expander("改良案をバージョン保存"):
        existing_versions = list_deck_versions(DEFAULT_DB_PATH)
        parent_options = [("親なし", None)] + [
            (f'#{version["id"]} {version["deck_name"]} {version.get("version_name") or ""}', version["id"])
            for version in existing_versions
            if version.get("deck_name") == selected_deck
        ]
        parent_label = st.selectbox("親バージョン", [label for label, _value in parent_options])
        parent_version_id = dict(parent_options)[parent_label]
        version_name = st.text_input("新バージョン名", value=f"{selected_deck} 改良案")
        reason = st.text_area("改良理由", value=" / ".join(plan["notes"]))
        memo = st.text_area("メモ", value=summarize_changes(compare_deck_texts(latest_deck_text, improved_text)))
        if st.button("改良案を履歴に保存"):
            changes = compare_deck_texts(latest_deck_text, improved_text, reason)
            version_id = save_deck_version(
                deck_name=selected_deck,
                version_name=version_name,
                parent_version_id=parent_version_id,
                deck_text=improved_text,
                reason=reason,
                summary=after,
                memo=memo,
                db_path=DEFAULT_DB_PATH,
            )
            save_deck_changes(version_id, changes, DEFAULT_DB_PATH)
            st.success(f"デッキバージョンを保存しました: #{version_id}")


def render_deck_history_page() -> None:
    st.header("デッキ履歴")
    st.caption("改良デッキ案のバージョン、差し替え履歴、実戦勝率の推移を確認します。")

    versions = list_deck_versions(DEFAULT_DB_PATH)
    changes = list_deck_changes(DEFAULT_DB_PATH)
    logs = fetch_real_match_logs(DEFAULT_DB_PATH)
    enriched_versions = attach_match_stats_to_versions(versions, logs)

    if not versions:
        st.info("まだデッキバージョンが保存されていません。対戦ログ画面の改良候補から保存できます。")
        return

    grouped = group_versions_by_deck(enriched_versions)
    selected_deck = st.selectbox("デッキ", list(grouped.keys()))
    deck_versions = grouped[selected_deck]

    st.subheader("成長履歴")
    st.dataframe(
        [
            {
                "ID": version["id"],
                "親ID": version.get("parent_version_id"),
                "バージョン": version.get("version_name") or "",
                "作成日": version.get("created_at"),
                "総合": version.get("total_score"),
                "未知性": version.get("novelty_score"),
                "メタ": version.get("meta_score"),
                "試合数": version.get("matches"),
                "勝率": version.get("win_rate"),
                "理由": version.get("reason"),
            }
            for version in deck_versions
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("親子比較")
    st.dataframe(
        compare_parent_child_stats(enriched_versions),
        use_container_width=True,
        hide_index=True,
    )

    selected_label = st.selectbox(
        "系譜を見るバージョン",
        [f'#{version["id"]} {version.get("version_name") or version["deck_name"]}' for version in deck_versions],
    )
    selected_id = int(selected_label.split()[0].lstrip("#"))
    lineage = get_lineage(selected_id, DEFAULT_DB_PATH)

    st.subheader("デッキ系譜")
    st.dataframe(
        [
            {
                "ID": version["id"],
                "バージョン": version.get("version_name") or "",
                "親ID": version.get("parent_version_id"),
                "総合": version.get("total_score"),
                "未知性": version.get("novelty_score"),
                "メタ": version.get("meta_score"),
                "メモ": version.get("memo"),
            }
            for version in lineage
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("差し替え履歴")
    selected_changes = [change for change in changes if change.get("version_id") in {version["id"] for version in deck_versions}]
    st.dataframe(selected_changes, use_container_width=True, hide_index=True)

    selected_version = next(version for version in versions if version["id"] == selected_id)
    st.text_area("選択バージョンのデッキリスト", value=selected_version["deck_text"], height=260)
    if st.button("選択バージョンをデッキ評価へ送る"):
        st.session_state["deck_text"] = selected_version["deck_text"]
        st.success("選択バージョンをデッキ評価画面へ送れる状態にしました。")

    st.subheader("検証計画")
    with st.expander("新規テスト計画作成"):
        with st.form("test_plan_form"):
            purpose = st.text_input("検証目的", value="改良内容の実戦確認")
            plan_col1, plan_col2, plan_col3 = st.columns(3)
            target_matches = plan_col1.number_input("目標試合数", min_value=1, max_value=200, value=10, step=1)
            target_win_rate = plan_col2.number_input("目標勝率", min_value=0.0, max_value=100.0, value=55.0, step=1.0)
            target_avg_finish_turn = plan_col3.number_input(
                "目標平均決着ターン",
                min_value=0.0,
                max_value=30.0,
                value=7.0,
                step=0.5,
            )
            st.write("重点対面")
            target_rows = []
            for index in range(3):
                target_col1, target_col2, target_col3 = st.columns(3)
                opponent = target_col1.text_input("相手デッキタイプ", key=f"target_opponent_{index}")
                opponent_matches = target_col2.number_input(
                    "目標対戦数",
                    min_value=0,
                    max_value=100,
                    value=5 if index == 0 else 0,
                    step=1,
                    key=f"target_matches_{index}",
                )
                opponent_win_rate = target_col3.number_input(
                    "対面目標勝率",
                    min_value=0.0,
                    max_value=100.0,
                    value=45.0,
                    step=1.0,
                    key=f"target_win_rate_{index}",
                )
                if opponent.strip():
                    target_rows.append(
                        {
                            "opponent_deck_type": opponent,
                            "target_matches": opponent_matches,
                            "target_win_rate": opponent_win_rate,
                        }
                    )
            plan_memo = st.text_area("検証メモ")
            submitted = st.form_submit_button("テスト計画を保存")
            if submitted:
                plan_id = save_test_plan(
                    {
                        "deck_version_id": selected_version["id"],
                        "deck_name": selected_version["deck_name"],
                        "version_name": selected_version.get("version_name") or "",
                        "purpose": purpose,
                        "target_matches": target_matches,
                        "target_win_rate": target_win_rate,
                        "target_avg_finish_turn": target_avg_finish_turn,
                        "status": "検証中",
                        "memo": plan_memo,
                    },
                    target_rows,
                    DEFAULT_DB_PATH,
                )
                st.success(f"テスト計画を保存しました: #{plan_id}")

    test_plans = list_test_plans(DEFAULT_DB_PATH)
    test_targets = list_test_plan_targets(DEFAULT_DB_PATH)
    targets_by_plan = {}
    for target in test_targets:
        targets_by_plan.setdefault(target["test_plan_id"], []).append(target)

    selected_plan_rows = [
        plan
        for plan in test_plans
        if plan.get("deck_version_id") == selected_version["id"]
        or plan.get("deck_name") == selected_version["deck_name"]
        or (
            bool(selected_version.get("version_name"))
            and plan.get("version_name") == selected_version.get("version_name")
        )
    ]

    if not selected_plan_rows:
        st.info("このバージョンの検証計画はまだありません。")
    else:
        st.write("#### 計画一覧")
        st.dataframe(
            summarize_plan_rows(selected_plan_rows, targets_by_plan, logs),
            use_container_width=True,
            hide_index=True,
        )

        plan_label = st.selectbox(
            "進捗を見る計画",
            [f'#{plan["id"]} {plan.get("purpose") or "無題計画"}' for plan in selected_plan_rows],
        )
        plan_id = int(plan_label.split()[0].lstrip("#"))
        selected_plan = next(plan for plan in selected_plan_rows if plan["id"] == plan_id)
        plan_targets = targets_for_plan(plan_id, DEFAULT_DB_PATH)
        analysis = analyze_test_plan(selected_plan, plan_targets, logs)
        progress = analysis["progress"]

        progress_cols = st.columns(5)
        progress_cols[0].metric("判定", analysis["judgement"])
        progress_cols[1].metric("試合数", f'{progress["matches"]} / {selected_plan["target_matches"]}')
        progress_cols[2].metric("勝率", f'{progress["win_rate"]}%')
        progress_cols[3].metric("平均決着ターン", progress["avg_finish_turn"] or "-")
        progress_cols[4].metric("状態", selected_plan.get("status") or "検証中")

        st.write("#### 重点対面の進捗")
        st.dataframe(analysis["opponent_progress"], use_container_width=True, hide_index=True)

        st.write("#### 判定コメント")
        for comment in analysis["comments"]:
            st.info(comment)

        status_col1, status_col2 = st.columns([2, 1])
        new_status = status_col1.selectbox("計画ステータス更新", ["検証中", "完了", "再改良"], index=0)
        if status_col2.button("ステータス保存"):
            update_test_plan_status(plan_id, new_status, DEFAULT_DB_PATH)
            st.success("テスト計画のステータスを更新しました。")

    export_col1, export_col2 = st.columns(2)
    export_col1.download_button(
        "デッキバージョンCSVをダウンロード",
        data=export_version_rows_to_csv(versions).encode("utf-8-sig"),
        file_name="deck_versions.csv",
        mime="text/csv",
        disabled=not versions,
    )
    export_col2.download_button(
        "差し替え履歴CSVをダウンロード",
        data=export_version_rows_to_csv(changes).encode("utf-8-sig"),
        file_name="deck_changes.csv",
        mime="text/csv",
        disabled=not changes,
    )
    export_col3, export_col4 = st.columns(2)
    export_col3.download_button(
        "テスト計画CSVをダウンロード",
        data=export_test_plan_rows_to_csv(list_test_plans(DEFAULT_DB_PATH)).encode("utf-8-sig"),
        file_name="test_plans.csv",
        mime="text/csv",
        disabled=not list_test_plans(DEFAULT_DB_PATH),
    )
    export_col4.download_button(
        "重点対面CSVをダウンロード",
        data=export_test_plan_rows_to_csv(list_test_plan_targets(DEFAULT_DB_PATH)).encode("utf-8-sig"),
        file_name="test_plan_targets.csv",
        mime="text/csv",
        disabled=not list_test_plan_targets(DEFAULT_DB_PATH),
    )


def render_research_report_page() -> None:
    st.header("研究レポート")
    st.caption("評価、実戦、改良履歴、検証計画を1デッキ単位でまとめて出力します。")

    logs = fetch_real_match_logs(DEFAULT_DB_PATH)
    performance = analyze_deck_performance(logs, fetch_latest_evaluation_by_deck_name(DEFAULT_DB_PATH))
    versions = list_deck_versions(DEFAULT_DB_PATH)
    deck_names = sorted(
        set(performance.keys())
        | {version.get("deck_name") for version in versions if version.get("deck_name")}
    )

    if not deck_names:
        st.info("レポート対象のデッキがまだありません。対戦ログまたはデッキ履歴を保存してください。")
        return

    selected_deck = st.selectbox("レポート対象デッキ", deck_names)
    deck_versions = [version for version in versions if version.get("deck_name") == selected_deck]
    version_options = [("デッキ全体", None)] + [
        (f'#{version["id"]} {version.get("version_name") or version["deck_name"]}', version["id"])
        for version in deck_versions
    ]
    version_label = st.selectbox("対象バージョン", [label for label, _value in version_options])
    version_id = dict(version_options)[version_label]

    report = generate_research_report(selected_deck, version_id, DEFAULT_DB_PATH)
    html_report = markdown_to_html(report["markdown"], report["title"])
    csv_report = rows_to_csv(report["rows"])

    st.subheader("プレビュー")
    st.markdown(report["markdown"])

    download_col1, download_col2, download_col3 = st.columns(3)
    base_name = report["title"].replace(" ", "_").replace("/", "_")
    download_col1.download_button(
        "Markdownをダウンロード",
        data=report["markdown"].encode("utf-8-sig"),
        file_name=f"{base_name}.md",
        mime="text/markdown",
    )
    download_col2.download_button(
        "HTMLをダウンロード",
        data=html_report.encode("utf-8-sig"),
        file_name=f"{base_name}.html",
        mime="text/html",
    )
    download_col3.download_button(
        "CSVをダウンロード",
        data=csv_report.encode("utf-8-sig"),
        file_name=f"{base_name}.csv",
        mime="text/csv",
        disabled=not report["rows"],
    )


def render_data_maintenance_page() -> None:
    st.header("データ保守")
    st.caption("CSV、SQLite DB、研究ログをバックアップし、データ健全性を確認します。")

    st.subheader("バックアップ作成")
    backup_col1, backup_col2, backup_col3 = st.columns(3)
    if backup_col1.button("cards.csv をバックアップ"):
        try:
            path = backup_csv(DEFAULT_CSV_PATH)
            st.success(f"CSVバックアップを作成しました: {path.name}")
        except Exception as exc:
            st.error(f"CSVバックアップに失敗しました: {exc}")

    if backup_col2.button("cards.db をバックアップ"):
        try:
            path = backup_database(DEFAULT_DB_PATH)
            st.success(f"DBバックアップを作成しました: {path.name}")
        except Exception as exc:
            st.error(f"DBバックアップに失敗しました: {exc}")

    if backup_col3.button("一括ZIPバックアップ作成"):
        try:
            path = create_backup_zip()
            st.success(f"ZIPバックアップを作成しました: {path.name}")
        except Exception as exc:
            st.error(f"ZIPバックアップに失敗しました: {exc}")

    backups = list_backups()
    st.subheader("バックアップ一覧")
    st.dataframe(backups, use_container_width=True, hide_index=True)
    if backups:
        selected_backup = st.selectbox("ダウンロードするバックアップ", [item["name"] for item in backups])
        selected_path = next(item["path"] for item in backups if item["name"] == selected_backup)
        st.download_button(
            "選択バックアップをダウンロード",
            data=read_backup_bytes(selected_path),
            file_name=selected_backup,
            mime="application/octet-stream",
        )

    st.subheader("データ健全性チェック")
    health = check_data_health(DEFAULT_DB_PATH)
    status_cols = st.columns(3)
    status_cols[0].metric("状態", health["status"])
    status_cols[1].metric("問題数", len(health["issues"]))
    status_cols[2].metric("SQLite quick_check", health["quick_check"])

    if health["issues"]:
        st.warning("確認が必要な項目があります。")
        st.dataframe([{"issue": issue} for issue in health["issues"]], use_container_width=True, hide_index=True)
    else:
        st.success("主要データの健全性チェックはOKです。")

    table_col1, table_col2 = st.columns(2)
    with table_col1:
        st.write("### テーブル存在チェック")
        st.dataframe(health["tables"], use_container_width=True, hide_index=True)
    with table_col2:
        st.write("### 主要テーブル件数")
        st.dataframe(health["counts"], use_container_width=True, hide_index=True)

    st.write("### 孤立データチェック")
    st.dataframe(health["orphans"], use_container_width=True, hide_index=True)

    st.subheader("公開前リリース診断")
    if st.button("公開前診断を実行", type="primary"):
        st.session_state["release_readiness"] = check_release_readiness(DEFAULT_CSV_PATH, DEFAULT_DB_PATH)

    release = st.session_state.get("release_readiness")
    if release:
        release_cols = st.columns(3)
        release_cols[0].metric("公開判定", release["status"])
        release_cols[1].metric("リリーススコア", f'{release["score"]} / 100')
        release_cols[2].metric("問題数", len(release["issues"]))

        if release["issues"]:
            st.error("公開前に直すべき項目があります。")
            st.dataframe([{"問題": issue} for issue in release["issues"]], use_container_width=True, hide_index=True)
        elif release["warnings"]:
            st.warning("公開は可能ですが、確認したい警告があります。")
        else:
            st.success("公開前診断はOKです。")

        if release["warnings"]:
            st.dataframe([{"警告": warning} for warning in release["warnings"]], use_container_width=True, hide_index=True)

        st.dataframe(release["checks"], use_container_width=True, hide_index=True)
        st.write("### サンプル生成チェック")
        st.dataframe([release["sample_generation"]], use_container_width=True, hide_index=True)

        report_col1, report_col2 = st.columns(2)
        if report_col1.button("公開前診断レポートを保存"):
            paths = export_release_readiness_report(release)
            st.success(f"診断レポートを保存しました: {paths['markdown'].name} / {paths['json'].name}")

        report_markdown = release_readiness_to_markdown(release)
        report_col2.download_button(
            "公開前診断レポートをダウンロード",
            data=report_markdown.encode("utf-8"),
            file_name="release_readiness.md",
            mime="text/markdown",
        )

    st.subheader("復元ガイド")
    for index, item in enumerate(restore_guide(), start=1):
        st.write(f"{index}. {item}")


def render_settings_page() -> None:
    st.header("設定")
    st.caption("Project MANA のパス、APIキー設定状況、Python環境、必要ライブラリを確認します。")

    settings = load_app_settings()
    environment = collect_environment_report()

    st.subheader("アプリ設定")
    st.dataframe(
        [
            {"項目": "プロジェクトフォルダ", "値": str(settings["root_dir"])},
            {"項目": "CSVパス", "値": str(settings["csv_path"])},
            {"項目": "DBパス", "値": str(settings["db_path"])},
            {"項目": "バックアップ保存先", "値": str(settings["backup_dir"])},
            {"項目": "dataフォルダ", "値": str(settings["data_dir"])},
            {"項目": ".envパス", "値": str(settings["env_path"])},
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("OpenAI API")
    api_cols = st.columns(3)
    api_cols[0].metric(".env", "あり" if settings["env_exists"] else "なし")
    api_cols[1].metric("APIキー", "設定済み" if settings["openai_api_key_configured"] else "未設定")
    api_cols[2].metric("使用モデル", settings["openai_model"])
    st.caption("APIキー本体は表示しません。")

    st.subheader("Python / Streamlit")
    python_info = environment["python"]
    env_cols = st.columns(3)
    env_cols[0].metric("Python", python_info["python_version"])
    env_cols[1].metric("Streamlit", environment["streamlit"]["version"] or "未検出")
    env_cols[2].metric("環境状態", "OK" if environment["ok"] else "要確認")
    st.write(f'Python実行ファイル: `{python_info["python_executable"]}`')
    st.write(f'OS: `{python_info["platform"]}`')

    st.subheader("必要ライブラリ")
    st.dataframe(environment["libraries"], use_container_width=True, hide_index=True)

    st.subheader("データフォルダ")
    st.dataframe(
        [
            {"項目": "dataフォルダ", "パス": environment["data_paths"]["data_dir"], "存在": environment["data_paths"]["data_dir_exists"]},
            {"項目": "cards.csv", "パス": environment["data_paths"]["csv_path"], "存在": environment["data_paths"]["csv_exists"]},
            {"項目": "cards.db", "パス": environment["data_paths"]["db_path"], "存在": environment["data_paths"]["db_exists"]},
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("環境警告")
    if environment["warnings"]:
        st.dataframe([{"警告": warning} for warning in environment["warnings"]], use_container_width=True, hide_index=True)
    else:
        st.success("環境チェックはOKです。")

    st.subheader("初回セットアップガイド")
    for index, item in enumerate(setup_guide(), start=1):
        st.write(f"{index}. {item}")

    st.subheader(".env 作成ガイド")
    st.markdown(env_creation_guide())


def render_card_db_completion_check() -> None:
    st.subheader("仮カードDB完成度チェック")

    if not CARDS_CSV_PATH.exists():
        st.warning("data/cards.csv が見つかりません。")
        return

    try:
        df = load_cards(CARDS_CSV_PATH)
        result = check_completion(df)
    except Exception as exc:
        st.error(f"完成度チェックに失敗しました: {exc}")
        return

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("仮DB完成度スコア", f"{result.score} / 100")
    metric_col2.metric("総カード数", result.total_cards)
    metric_col3.metric("ユニークカード名数", result.unique_names)
    metric_col4.metric("同名重複数", result.duplicate_name_count)

    if result.score >= 90:
        st.success("仮カードDBとして十分に完成しています。")
    elif result.score >= 70:
        st.info("仮カードDBとして利用可能です。重複整理や不足タグ補強を行うとさらに良くなります。")
    else:
        st.warning("仮カードDBとしてはまだ不足があります。警告内容を確認してください。")

    if result.warnings:
        st.markdown("### 警告")
        for warning in result.warnings:
            st.warning(warning)

    st.markdown("### 重要カテゴリ集計")
    key_df = pd.DataFrame(
        [
            {"カテゴリ": key, "枚数": value}
            for key, value in result.key_category_counts.items()
        ]
    ).sort_values("枚数", ascending=False)
    st.dataframe(key_df, use_container_width=True, hide_index=True)

    st.markdown("### 文明別カード数")
    civ_df = pd.DataFrame(
        [
            {"文明": key, "枚数": value}
            for key, value in result.civilization_counts.items()
        ]
    )
    st.dataframe(civ_df, use_container_width=True, hide_index=True)

    st.markdown("### カードタイプ別カード数")
    type_df = pd.DataFrame(
        [
            {"カードタイプ": key, "枚数": value}
            for key, value in result.card_type_counts.items()
        ]
    )
    st.dataframe(type_df, use_container_width=True, hide_index=True)

    st.markdown("### コスト帯別カード数")
    cost_df = pd.DataFrame(
        [
            {"コスト帯": key, "枚数": value}
            for key, value in result.cost_band_counts.items()
        ]
    )
    st.dataframe(cost_df, use_container_width=True, hide_index=True)

    st.markdown("### タグ上位50件")
    tag_df = pd.DataFrame(
        [
            {"タグ": key, "枚数": value}
            for key, value in result.tag_counts.items()
        ]
    ).sort_values("枚数", ascending=False).head(50)
    st.dataframe(tag_df, use_container_width=True, hide_index=True)


def render_completed_card_db_export_section() -> None:
    st.subheader("仮カードDB完成版エクスポート")

    if not CARDS_CSV_PATH.exists():
        st.warning("data/cards.csv が見つかりません。")
        return

    st.write("現在の data/cards.csv を、仮カードDB完成版として出力します。")

    if st.button("完成版CSVを作成"):
        try:
            output_path = export_completed_cards_csv(CARDS_CSV_PATH)
            st.success(f"完成版CSVを作成しました: {output_path}")

            data = output_path.read_bytes()
            st.download_button(
                label="cards_completed.csv をダウンロード",
                data=data,
                file_name="cards_completed.csv",
                mime="text/csv",
            )
        except Exception as exc:
            st.error(f"CSV作成に失敗しました: {exc}")

    if st.button("サマリーを作成"):
        try:
            summary_path = export_cards_summary(CARDS_CSV_PATH)
            st.success(f"サマリーを作成しました: {summary_path}")

            data = summary_path.read_bytes()
            st.download_button(
                label="cards_summary.txt をダウンロード",
                data=data,
                file_name="cards_summary.txt",
                mime="text/plain",
            )
        except Exception as exc:
            st.error(f"サマリー作成に失敗しました: {exc}")

    if st.button("完成版ZIPを作成"):
        try:
            zip_path = export_completed_cards_zip(CARDS_CSV_PATH)
            st.success(f"完成版ZIPを作成しました: {zip_path}")

            data = zip_path.read_bytes()
            st.download_button(
                label="完成版ZIPをダウンロード",
                data=data,
                file_name="project_mana_cards_completed.zip",
                mime="application/zip",
            )
        except Exception as exc:
            st.error(f"ZIP作成に失敗しました: {exc}")


def render_csv_management_page() -> None:
    st.header("CSV管理")
    st.caption("data/cards.csv の入力ミス検出と、能力テキストからのタグ付け支援を行います。")

    if st.button("CSVバリデーション実行", type="primary"):
        st.session_state["csv_validation"] = validate_cards_csv(DEFAULT_CSV_PATH)

    result = st.session_state.get("csv_validation")
    if not result:
        st.info("CSVバリデーションを実行してください。")
    else:
        status_col, error_col, warning_col = st.columns(3)
        status_col.metric("状態", "OK" if result["ok"] else "要修正")
        error_col.metric("エラー", len(result["errors"]))
        warning_col.metric("警告", len(result["warnings"]))

        if result["errors"]:
            st.subheader("エラー")
            st.dataframe(result["errors"], use_container_width=True, hide_index=True)
        if result["warnings"]:
            st.subheader("警告")
            st.dataframe(result["warnings"], use_container_width=True, hide_index=True)
        if result["ok"] and not result["warnings"]:
            st.success("CSVに大きな問題は見つかりませんでした。")

        st.subheader("行ごとのタグ候補")
        suggestion_rows = []
        for index, row in enumerate(result["rows"], start=2):
            text = row.get("text", "")
            tags = row.get("tags", "")
            suggestions = suggest_tags(text)
            missing = suggest_missing_tags(text, tags)
            suggestion_rows.append(
                {
                    "行": index,
                    "カード名": row.get("name", ""),
                    "現在のタグ": tags,
                    "タグ候補": ";".join(suggestions),
                    "未設定候補": ";".join(missing),
                }
            )
        st.dataframe(suggestion_rows, use_container_width=True, hide_index=True)

    st.subheader("テキストからタグ候補")
    free_text = st.text_area("能力テキスト", placeholder="能力テキストを貼り付けるとタグ候補を表示します。")
    if free_text.strip():
        suggestions = suggest_tags(free_text)
        if suggestions:
            st.write(" ".join(f"`{tag}`" for tag in suggestions))
        else:
            st.info("タグ候補は見つかりませんでした。")

    st.subheader("カード追加")
    with st.form("add_card_form"):
        card_id = st.text_input("card_id")
        name = st.text_input("カード名")
        civilization = st.selectbox("文明", VALID_CIVILIZATIONS, key="add_civilization")
        cost = st.number_input("コスト", min_value=0, max_value=99, step=1)
        card_type = st.selectbox("カードタイプ", VALID_CARD_TYPES, key="add_card_type")
        power = st.text_input("パワー")
        race = st.text_input("種族")
        text = st.text_area("能力テキスト")
        suggested_tags = suggest_tags_from_text(text)
        selected_suggestions = st.multiselect("タグ候補", suggested_tags, default=suggested_tags)
        tags = st.text_input("タグ", value=";".join(selected_suggestions))

        submitted = st.form_submit_button("cards.csv に追加")
        if submitted:
            card = {
                "card_id": card_id,
                "name": name,
                "civilization": civilization,
                "cost": str(cost),
                "card_type": card_type,
                "power": power,
                "race": race,
                "text": text,
                "tags": tags,
            }
            errors = validate_card(card, read_cards(DEFAULT_CSV_PATH))
            if errors:
                for error in errors:
                    st.error(error)
            else:
                try:
                    backup_path = add_card(DEFAULT_CSV_PATH, card)
                    validation = validate_cards_csv(DEFAULT_CSV_PATH)
                    st.success(f"カードを追加しました。バックアップ: {backup_path.name}")
                    st.write(f'保存後検査: エラー {len(validation["errors"])}件 / 警告 {len(validation["warnings"])}件')
                except Exception as exc:
                    st.error(f"追加に失敗しました: {exc}")

    st.subheader("既存カード編集")
    cards = read_cards(DEFAULT_CSV_PATH)
    keyword = st.text_input("編集するカードを検索")
    matched_cards = find_card_by_name(cards, keyword)

    if not matched_cards:
        st.info("該当カードがありません。")
        render_card_db_completion_check()
        render_completed_card_db_export_section()
        return

    selected_label = st.selectbox(
        "編集対象",
        [f'{card.get("card_id")} : {card.get("name")}' for card in matched_cards],
    )
    selected_id = selected_label.split(" : ")[0]
    selected_card = next(card for card in matched_cards if card.get("card_id") == selected_id)

    with st.form("edit_card_form"):
        edit_card_id = st.text_input("card_id", value=selected_card.get("card_id", ""))
        edit_name = st.text_input("カード名", value=selected_card.get("name", ""))
        edit_civilization = st.selectbox(
            "文明",
            VALID_CIVILIZATIONS,
            index=VALID_CIVILIZATIONS.index(selected_card.get("civilization"))
            if selected_card.get("civilization") in VALID_CIVILIZATIONS
            else 0,
            key="edit_civilization",
        )
        edit_cost = st.text_input("コスト", value=selected_card.get("cost", ""))
        edit_card_type = st.selectbox(
            "カードタイプ",
            VALID_CARD_TYPES,
            index=VALID_CARD_TYPES.index(selected_card.get("card_type"))
            if selected_card.get("card_type") in VALID_CARD_TYPES
            else 0,
            key="edit_card_type",
        )
        edit_power = st.text_input("パワー", value=selected_card.get("power", ""))
        edit_race = st.text_input("種族", value=selected_card.get("race", ""))
        edit_text = st.text_area("能力テキスト", value=selected_card.get("text", ""))
        edit_suggested_tags = suggest_tags_from_text(edit_text)
        edit_existing_tags = [tag.strip() for tag in selected_card.get("tags", "").split(";") if tag.strip()]
        edit_selected_suggestions = st.multiselect(
            "タグ候補",
            edit_suggested_tags,
            default=[tag for tag in edit_suggested_tags if tag not in edit_existing_tags],
        )
        merged_tags = edit_existing_tags[:]
        for tag in edit_selected_suggestions:
            if tag not in merged_tags:
                merged_tags.append(tag)
        edit_tags = st.text_input("タグ", value=";".join(merged_tags))

        update_submitted = st.form_submit_button("更新する")
        if update_submitted:
            updated_card = {
                "card_id": edit_card_id,
                "name": edit_name,
                "civilization": edit_civilization,
                "cost": edit_cost,
                "card_type": edit_card_type,
                "power": edit_power,
                "race": edit_race,
                "text": edit_text,
                "tags": edit_tags,
            }
            errors = validate_card(updated_card, cards, original_card_id=selected_id)
            if errors:
                for error in errors:
                    st.error(error)
            else:
                try:
                    backup_path = update_card(DEFAULT_CSV_PATH, selected_id, updated_card)
                    validation = validate_cards_csv(DEFAULT_CSV_PATH)
                    st.success(f"カードを更新しました。バックアップ: {backup_path.name}")
                    st.write(f'保存後検査: エラー {len(validation["errors"])}件 / 警告 {len(validation["warnings"])}件')
                except Exception as exc:
                    st.error(f"更新に失敗しました: {exc}")

    render_card_db_completion_check()
    render_completed_card_db_export_section()


def main() -> None:
    ensure_database()

    st.title("Project MANA")
    st.caption("DMプレイス向けAIデッキ研究ツール MVP")

    page = st.sidebar.radio(
        "画面",
        [
            "ダッシュボード",
            "カード検索",
            "デッキ生成",
            "デッキ評価",
            "一人回しシミュレーション",
            "AIデッキ生成",
            "簡易AI対戦",
            "進化探索",
            "研究ログ",
            "対戦ログ",
            "デッキ履歴",
            "研究レポート",
            "データ保守",
            "設定",
            "CSV管理",
        ],
    )

    if st.sidebar.button("cards.csv を再取り込み", use_container_width=True):
        count = import_cards(DEFAULT_CSV_PATH, DEFAULT_DB_PATH)
        st.sidebar.success(f"{count}枚を取り込みました。")

    if page == "ダッシュボード":
        render_dashboard_page()
    elif page == "カード検索":
        render_search_page()
    elif page == "デッキ生成":
        render_generate_page()
    elif page == "デッキ評価":
        render_evaluate_page()
    elif page == "一人回しシミュレーション":
        render_simulate_page()
    elif page == "AIデッキ生成":
        render_ai_deck_page()
    elif page == "簡易AI対戦":
        render_battle_page()
    elif page == "進化探索":
        render_evolution_page()
    elif page == "研究ログ":
        render_research_log_page()
    elif page == "対戦ログ":
        render_match_log_page()
    elif page == "デッキ履歴":
        render_deck_history_page()
    elif page == "研究レポート":
        render_research_report_page()
    elif page == "データ保守":
        render_data_maintenance_page()
    elif page == "設定":
        render_settings_page()
    else:
        render_csv_management_page()


if __name__ == "__main__":
    main()

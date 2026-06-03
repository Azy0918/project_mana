from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.card_effect_feature_store import summarize_card_effect_features
from src.combo_knowledge_base import load_known_combos, summarize_known_combos
from src.generated_deck_store import ensure_generated_decks_table, load_generated_deck_detail, load_generated_decks
from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH
from src.mana_research_agent import collect_mana_research_brief
from src.meta_deck_store import load_meta_decks, summarize_meta_decks
from src.simulate_goldfish import simulate_goldfish
from src.tag_quality_analyzer import analyze_deck_tag_quality
from src.win_condition_model import list_win_conditions, summarize_mana_core_hypothesis
from src.route_candidate_evaluator import (
    evaluate_saved_route_based_decks,
    route_evaluation_to_markdown,
)
from src.route_validation_brief import build_route_validation_brief_section


INITIAL_COMBO_CANDIDATES = [
    {"コンボ型": "マナ加速 -> 大型展開", "登録理由": "ランプ系未知ルートの基準になる。"},
    {"コンボ型": "墓地肥やし -> 墓地利用", "登録理由": "墓地を資源化する勝利ルートの基準になる。"},
    {"コンボ型": "攻撃可能クリーチャー -> 侵略/革命チェンジ", "登録理由": "攻撃条件を使う踏み倒し型の基準になる。"},
    {"コンボ型": "呪文連打 -> 追加行動/フィニッシュ", "登録理由": "手札と詠唱回数を勝利へ変換する型。"},
    {"コンボ型": "小型展開 -> 種族参照展開", "登録理由": "横展開から打点過剰へ向かう型。"},
    {"コンボ型": "シールド追加 -> 耐久/特殊勝利", "登録理由": "防御状態を勝利条件へ変える型。"},
    {"コンボ型": "ハンデス -> ロック/リソース差", "登録理由": "相手行動制限から実質勝利へ向かう型。"},
    {"コンボ型": "進化元操作 -> 退化/下敷き利用", "登録理由": "タグでは見落としやすいカード束操作の型。"},
    {"コンボ型": "踏み倒し -> 出た時効果連鎖", "登録理由": "コスト制約解除を盤面価値へ変換する型。"},
    {"コンボ型": "山札操作 -> 特殊勝利/山札切れ", "登録理由": "通常打点以外の終端条件へ向かう型。"},
]


def build_mana_context_brief(db_path: str | Path = DEFAULT_DB_PATH) -> str:
    db_path = Path(db_path)
    ensure_generated_decks_table(db_path)
    brief = collect_mana_research_brief(db_path, DEFAULT_CSV_PATH)
    dashboard = brief.get("dashboard", {})
    card_stats = dashboard.get("card_stats", {})
    research_stats = dashboard.get("research_stats", {})
    meta_summary = summarize_meta_decks(db_path)
    combo_summary = summarize_known_combos(db_path)
    effect_summary = summarize_card_effect_features(db_path)
    generated_decks = _safe_dataframe(lambda: load_generated_decks(db_path))
    meta_decks = _safe_dataframe(lambda: load_meta_decks(db_path))
    known_combos = _safe_dataframe(lambda: load_known_combos(db_path))
    core = summarize_mana_core_hypothesis()

    lines: list[str] = []
    lines.append("# Project MANA 解析ブリーフ")
    lines.append("")
    lines.append(f"- 作成日時: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- DB: `{db_path}`")
    lines.append(f"- 目的: 未知の勝利ルート探索")
    lines.append("")
    lines.append("## MANA中核仮説")
    lines.append("")
    lines.append(core["設計思想"])
    lines.append("")
    lines.append("```text")
    lines.append("未知シナジー -> 状態変換連鎖 -> 勝利条件到達 -> 環境への有効性")
    lines.append("```")
    lines.append("")

    lines.append("## 研究状態")
    lines.append("")
    lines.extend(
        _bullet_dict(
            {
                "研究状態": brief.get("research_status", "不明"),
                "カードDB件数": card_stats.get("card_count", 0),
                "タグ未設定数": card_stats.get("missing_tag_count", 0),
                "保存済み生成デッキ数": brief.get("generated_deck_count", len(generated_decks)),
                "候補由来": _format_candidate_origin_counts(generated_decks),
                "環境デッキDB件数": meta_summary.get("count", 0),
                "既知コンボDB件数": combo_summary.get("count", 0),
                "実戦ログ数": research_stats.get("match_log_count", 0),
                "効果特徴件数": effect_summary.get("feature_count", 0),
                "効果特徴DB完成": "Yes" if effect_summary.get("complete") else "No",
            }
        )
    )
    lines.append("")

    lines.append("## MANAの次アクション")
    lines.append("")
    lines.extend(_markdown_table(brief.get("next_research_actions", []), empty_message="次アクションはありません。"))
    lines.append("")

    lines.append("## 候補由来ラベル")
    lines.append("")
    lines.extend(_bullet_dict(_candidate_origin_summary(generated_decks)))
    if _has_tag_based_origin(generated_decks):
        lines.append("")
        lines.append("> このブリーフには `tag_based` 候補が含まれます。tag_based は初期のタグ・役割ベース探索由来であり、未知勝利ルートとして評価するには状態変換連鎖と勝利条件到達の確認が必要です。")
    lines.append("")

    lines.append("## 上位保存済みデッキ")
    lines.append("")
    lines.extend(
        _markdown_table(
            _top_deck_summary_rows(brief.get("top_generated_decks", [])),
            empty_message="上位保存済みデッキはありません。",
        )
    )
    lines.append("")

    lines.append("## 上位保存済みデッキ詳細")
    lines.append("")
    detail_sections = _top_deck_detail_sections(brief.get("top_generated_decks", []), db_path)
    if detail_sections:
        lines.extend(detail_sections)
    else:
        lines.append("上位保存済みデッキの詳細はありません。")
    lines.append("")

    lines.append("## 改善候補")
    lines.append("")
    lines.extend(
        _markdown_table(
            _pick_columns(
                brief.get("weak_generated_decks", []),
                ["deck_name", "format", "deck_type", "condition_score", "starter_count", "defense_count", "finisher_count"],
            ),
            empty_message="改善候補はありません。",
        )
    )
    lines.append("")

    lines.append("## 実戦待ち候補")
    lines.append("")
    lines.extend(
        _markdown_table(
            _pick_columns(
                brief.get("next_test_decks", []),
                ["deck_name", "format", "deck_type", "condition_score", "evaluation_score", "starter_success_rate", "defense_seen_rate"],
            ),
            empty_message="実戦待ち候補はありません。",
        )
    )
    lines.append("")

    lines.append("## 環境デッキ要約")
    lines.append("")
    lines.extend(_bullet_dict(_flatten_summary(meta_summary)))
    lines.append("")
    lines.extend(
        _markdown_table(
            _df_records(
                meta_decks,
                ["deck_name", "format", "tier", "civilizations", "deck_type", "key_cards", "confidence", "observed_at"],
                limit=10,
            ),
            empty_message="環境デッキは未登録です。",
        )
    )
    lines.append("")
    warnings = _meta_quality_warnings(meta_decks)
    if warnings:
        lines.append("### 環境デッキDB精度警告")
        lines.append("")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("## 既知コンボ要約")
    lines.append("")
    lines.extend(_bullet_dict(_flatten_summary(combo_summary)))
    lines.append("")
    lines.extend(
        _markdown_table(
            _df_records(
                known_combos,
                ["combo_name", "format", "archetype", "pattern_type", "core_cards", "win_condition"],
                limit=10,
            ),
            empty_message="既知コンボは未登録です。",
        )
    )
    lines.append("")
    if combo_summary.get("count", 0) == 0:
        lines.append("### 登録すべき初期コンボ候補")
        lines.append("")
        lines.extend(_markdown_table(INITIAL_COMBO_CANDIDATES))
        lines.append("")

    lines.append("## 効果構造理解の状況")
    lines.append("")
    lines.extend(_bullet_dict(_flatten_summary(effect_summary)))
    lines.append("")
    lines.append("### 勝利条件モデル")
    lines.append("")
    lines.extend(_markdown_table(list_win_conditions()))
    lines.append("")

    lines.append("## 生成デッキDB概況")
    lines.append("")
    lines.extend(_bullet_dict(_generated_deck_summary(generated_decks)))
    skew_comments = _generated_deck_skew_comments(generated_decks)
    if skew_comments:
        lines.append("")
        lines.append("### 生成デッキDBの偏りコメント")
        lines.append("")
        for comment in skew_comments:
            lines.append(f"- {comment}")
    lines.append("")

    lines.append("## route_based 候補")
    lines.append("")
    lines.extend(_markdown_table(_route_based_rows(generated_decks, db_path), empty_message="route_based 候補はまだ保存されていません。"))
    lines.append("")

    lines.append("## route_based 再評価")
    lines.append("")
    route_evaluation_rows = _safe_route_evaluation_rows(db_path)
    if route_evaluation_rows:
        lines.extend(_route_evaluation_summary_table(route_evaluation_rows))
        lines.append("")
        lines.extend(_route_evaluation_detail_sections(route_evaluation_rows))
    else:
        lines.append("route_based 再評価はまだ取得できません。`src/route_candidate_evaluator.py` が配置されているか確認してください。")
    lines.append("")


    lines.append(build_route_validation_brief_section())
    lines.append("")

    lines.append("## ChatGPTに聞くべき質問")
    lines.append("")
    for question in _build_questions(brief, meta_summary, combo_summary, effect_summary, generated_decks):
        lines.append(f"- {question}")
    lines.append("")

    lines.append("## 解析依頼テンプレート")
    lines.append("")
    lines.append("```text")
    lines.append("以下のProject MANA解析ブリーフを前提に、未知の勝利ルート探索として次を分析してください。")
    lines.append("1. 有望な状態変換連鎖")
    lines.append("2. 勝利条件到達に近い候補")
    lines.append("3. 既存環境との差分")
    lines.append("4. 実戦検証すべき候補")
    lines.append("5. 次に追加すべきカード効果特徴")
    lines.append("```")

    return "\n".join(lines).strip() + "\n"


def _safe_dataframe(loader: Any) -> pd.DataFrame:
    try:
        return loader()
    except Exception:
        return pd.DataFrame()


def _bullet_dict(values: dict[str, Any]) -> list[str]:
    return [f"- {key}: {_format_value(value)}" for key, value in values.items()]


def _flatten_summary(summary: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, dict):
            flat[key] = ", ".join(f"{k}:{v}" for k, v in value.items()) or "なし"
        else:
            flat[key] = value
    return flat


def _pick_columns(rows: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    picked = []
    for row in rows:
        picked.append({column: row.get(column, "") for column in columns})
    return picked


def _top_deck_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary_rows = []
    for row in rows:
        origin = row.get("candidate_origin") or "tag_based"
        summary_rows.append(
            {
                "deck_name": row.get("deck_name", ""),
                "format": row.get("format", ""),
                "候補由来": origin,
                "candidate_origin": origin,
                "deck_type": row.get("deck_type", ""),
                "condition_score": row.get("condition_score", ""),
                "evaluation_score": row.get("evaluation_score", ""),
                "civilization_match_rate": row.get("civilization_match_rate", ""),
            }
        )
    return summary_rows


def _candidate_origin_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or "candidate_origin" not in df.columns:
        return {"candidate_origin": "未取得"}
    counts = df["candidate_origin"].fillna("").replace("", "tag_based").value_counts().to_dict()
    return {
        "候補由来分布": counts,
        "tag_based": counts.get("tag_based", 0),
        "route_based": counts.get("route_based", 0),
        "combo_based": counts.get("combo_based", 0),
        "meta_counter_based": counts.get("meta_counter_based", 0),
        "human_imported": counts.get("human_imported", 0),
    }


def _format_candidate_origin_counts(df: pd.DataFrame) -> str:
    if df.empty or "candidate_origin" not in df.columns:
        return "未取得"
    counts = df["candidate_origin"].fillna("").replace("", "tag_based").value_counts().to_dict()
    return ", ".join(f"{key}:{value}" for key, value in counts.items()) or "未取得"


def _has_tag_based_origin(df: pd.DataFrame) -> bool:
    if df.empty or "candidate_origin" not in df.columns:
        return False
    origins = df["candidate_origin"].fillna("").replace("", "tag_based")
    return bool((origins == "tag_based").any())


def _df_records(df: pd.DataFrame, columns: list[str], limit: int = 10) -> list[dict[str, Any]]:
    if df.empty:
        return []
    available = [column for column in columns if column in df.columns]
    if not available:
        return []
    return df[available].head(limit).fillna("").to_dict("records")


def _markdown_table(rows: list[dict[str, Any]], empty_message: str = "データはありません。") -> list[str]:
    if not rows:
        return [empty_message]
    columns = list(rows[0].keys())
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_escape_table(_format_value(row.get(column, ""))) for column in columns) + " |")
    return lines


def _generated_deck_summary(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"件数": 0}
    summary: dict[str, Any] = {"件数": len(df)}
    for column in ["format", "deck_type"]:
        if column in df.columns:
            summary[column] = df[column].fillna("").replace("", "不明").value_counts().head(8).to_dict()
    if "candidate_origin" in df.columns:
        summary["candidate_origin"] = df["candidate_origin"].fillna("").replace("", "tag_based").value_counts().to_dict()
    for column in ["condition_score", "evaluation_score", "civilization_match_rate", "average_cost"]:
        if column in df.columns:
            numeric = pd.to_numeric(df[column], errors="coerce")
            if numeric.notna().any():
                summary[f"{column}_平均"] = round(float(numeric.mean()), 2)
                summary[f"{column}_最大"] = round(float(numeric.max()), 2)
    return _flatten_summary(summary)


def _route_based_rows(df: pd.DataFrame, db_path: Path) -> list[dict[str, Any]]:
    if df.empty or "candidate_origin" not in df.columns:
        return []
    route_df = df[df["candidate_origin"].fillna("") == "route_based"].head(10)
    rows = []
    for _, row in route_df.iterrows():
        detail = load_generated_deck_detail(int(row["id"]), db_path)
        route_info = _parse_route_note(str((detail or {}).get("strategy_note", "")))
        rows.append(
            {
                "deck_name": row.get("deck_name", ""),
                "candidate_origin": row.get("candidate_origin", ""),
                "route_type": route_info.get("route_type", row.get("deck_type", "")),
                "route_score": route_info.get("route_score", ""),
                "required_mana_estimate": route_info.get("required_mana_estimate", ""),
                "earliest_route_turn": route_info.get("earliest_route_turn", ""),
                "route_reproducibility_score": route_info.get("route_reproducibility_score", ""),
                "route_risk_score": route_info.get("route_risk_score", ""),
                "missing_support_states": route_info.get("missing_support_states", ""),
                "route_seed_cards": route_info.get("route_seed_cards", ""),
                "route_comment": route_info.get("route_comment", ""),
                "state_chain": route_info.get("state_chain", ""),
            }
        )
    return rows


def _parse_route_note(note: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in note.splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key in {
            "route_type",
            "route_score",
            "required_mana_estimate",
            "earliest_route_turn",
            "route_reproducibility_score",
            "route_risk_score",
            "missing_support_states",
            "required_support_roles",
            "route_seed_cards",
            "state_chain",
            "required_states",
            "produced_states",
            "route_comment",
        }:
            data[key] = value
    return data


def _top_deck_detail_sections(top_rows: list[dict[str, Any]], db_path: Path) -> list[str]:
    lines: list[str] = []
    for index, row in enumerate(top_rows[:3], start=1):
        deck_id = row.get("id")
        if not deck_id:
            continue
        detail = load_generated_deck_detail(int(deck_id), db_path)
        if not detail:
            continue
        deck_cards = detail.get("deck_cards", [])
        goldfish = _safe_goldfish(deck_cards)
        tag_quality = analyze_deck_tag_quality(deck_cards)
        tags = _tag_counts(deck_cards)

        lines.append(f"### {index}. {detail.get('deck_name', '-')}")
        lines.append("")
        lines.extend(
            _bullet_dict(
                {
                    "デッキ名": detail.get("deck_name", "-"),
                    "形式": detail.get("format", "-"),
                    "候補由来": detail.get("candidate_origin", "tag_based"),
                    "デッキタイプ": detail.get("deck_type", "-"),
                    "条件適合スコア": detail.get("condition_score", "-"),
                    "評価スコア": detail.get("evaluation_score", "-"),
                    "未知性スコア": detail.get("novelty_score", "-"),
                    "メタスコア": detail.get("meta_score", "-"),
                    "平均コスト": detail.get("average_cost", "-"),
                    "初動枚数": detail.get("starter_count", "-"),
                    "受け札枚数": detail.get("defense_count", "-"),
                    "フィニッシャー枚数": detail.get("finisher_count", "-"),
                    "除去枚数": detail.get("removal_count", "-"),
                    "ドロー/リソース枚数": detail.get("draw_count", "-"),
                    "初動成功率": _percent(goldfish.get("early_success_rate")) if goldfish else "未取得",
                    "受け札確認率": _percent(goldfish.get("defense_seen_rate")) if goldfish else "未取得",
                    "フィニッシャー確認率": _percent(goldfish.get("finisher_seen_rate")) if goldfish else "未取得",
                    "タグ品質警告": "あり" if tag_quality["has_warning"] else "なし",
                }
            )
        )
        if detail.get("candidate_origin") == "route_based":
            route_info = _parse_route_note(str(detail.get("strategy_note", "")))
            if route_info:
                lines.append("")
                lines.append("#### route_based seed")
                lines.append("")
                lines.extend(_bullet_dict(route_info))
        if tag_quality["has_warning"]:
            lines.append("")
            lines.append("> 注意: タグ品質警告があります。初動成功率、受け札確認率、条件適合スコアを過信しないでください。")
        if detail.get("candidate_origin", "tag_based") == "tag_based":
            lines.append("")
            lines.append("> 候補由来: この候補はタグ・役割ベース探索由来です。未知勝利ルートとして評価するには、別途状態変換連鎖と勝利条件到達の確認が必要です。")
        lines.append("")
        lines.append("#### デッキリスト")
        lines.append("")
        lines.extend(_markdown_table(_deck_list_rows(deck_cards), empty_message="デッキリストはありません。"))
        lines.append("")
        lines.append("#### タグ集計上位20")
        lines.append("")
        lines.extend(_markdown_table([{"タグ": tag, "枚数": count} for tag, count in tags[:20]], empty_message="タグ集計はありません。"))
        lines.append("")
        lines.append("#### タグ品質警告")
        lines.append("")
        if tag_quality["warnings"]:
            for warning in tag_quality["warnings"]:
                lines.append(f"- {warning}")
        else:
            lines.append("- 大きなタグ過剰警告はありません。")
        lines.append("")
        lines.append("#### 過剰に見える役割タグ上位")
        lines.append("")
        role_rows = [
            {"役割タグ": tag, "枚数": count}
            for tag, count in sorted(tag_quality["role_counts"].items(), key=lambda item: item[1], reverse=True)[:12]
        ]
        lines.extend(_markdown_table(role_rows, empty_message="役割タグ集計はありません。"))
        lines.append("")
        lines.append("#### 信頼度の低い役割タグ")
        lines.append("")
        suspicious_rows = [
            {"役割タグ": tag, "疑わしい枚数": count}
            for tag, count in sorted(tag_quality["suspicious_tag_counts"].items(), key=lambda item: item[1], reverse=True)[:12]
        ]
        lines.extend(_markdown_table(suspicious_rows, empty_message="信頼度の低い役割タグは目立ちません。"))
        if tag_quality["over_tagged_cards"]:
            lines.append("")
            lines.append("#### 重要役割タグが多すぎるカード")
            lines.append("")
            lines.extend(_markdown_table(tag_quality["over_tagged_cards"][:12]))
        lines.append("")
        lines.append("#### MANAが見る強み")
        lines.append("")
        for strength in _deck_strengths(detail, goldfish, tag_quality):
            lines.append(f"- {strength}")
        lines.append("")
        lines.append("#### MANAが見る弱点")
        lines.append("")
        for weakness in _deck_weaknesses(detail, goldfish, tag_quality):
            lines.append(f"- {weakness}")
        lines.append("")

        lines.append("#### ChatGPTに確認してほしい観点")
        lines.append("")
        for question in _deck_review_questions(detail):
            lines.append(f"- {question}")
        lines.append("")
    return lines


def _deck_list_rows(deck_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for card in deck_cards:
        rows.append(
            {
                "枚数": card.get("quantity", 1),
                "カード名": card.get("name", ""),
                "文明": card.get("civilization", ""),
                "コスト": card.get("cost", ""),
                "種類": card.get("card_type", ""),
                "タグ": card.get("tags", ""),
            }
        )
    return rows


def _tag_counts(deck_cards: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for card in deck_cards:
        quantity = _quantity(card)
        for tag in _split_tags(str(card.get("tags", ""))):
            counts[tag] = counts.get(tag, 0) + quantity
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)


def _safe_goldfish(deck_cards: list[dict[str, Any]]) -> dict[str, Any]:
    if not deck_cards:
        return {}
    try:
        return simulate_goldfish(deck_cards, trials=200, max_turns=5)
    except Exception:
        return {}


def _deck_strengths(detail: dict[str, Any], goldfish: dict[str, Any], tag_quality: dict[str, Any]) -> list[str]:
    strengths = []
    tag_warning = bool(tag_quality.get("has_warning"))
    if _num(detail.get("condition_score")) >= 80 and not tag_warning:
        strengths.append("入力条件との適合度が高く、研究仮説に沿った構成です。")
    elif _num(detail.get("condition_score")) >= 80:
        strengths.append("条件適合スコアは高いですが、タグ品質警告があるため補正して見る必要があります。")
    if _num(detail.get("novelty_score")) >= 70:
        strengths.append("未知性スコアが高く、既存候補との差分を検証する価値があります。")
    if _num(detail.get("meta_score")) >= 60:
        strengths.append("メタスコアが一定以上あり、環境適性の仮説があります。")
    if _num(detail.get("starter_count")) >= 8:
        strengths.append("初動枚数が一定以上あり、序盤行動の再現性が期待できます。")
    if _num(detail.get("defense_count")) >= 6:
        strengths.append("受け札が一定数あり、速い対面への最低限の耐性があります。")
    if goldfish.get("early_success_rate", 0) >= 0.65 and not tag_warning:
        strengths.append(f"一人回しで初動成功率が {_percent(goldfish.get('early_success_rate'))} あります。")
    elif goldfish.get("early_success_rate", 0) >= 0.65:
        strengths.append(f"一人回し初動成功率は {_percent(goldfish.get('early_success_rate'))} ですが、初動タグ過剰の可能性があります。")
    return strengths or ["明確な強みはまだ数値化できていません。勝利ルートの構造確認が必要です。"]


def _deck_weaknesses(detail: dict[str, Any], goldfish: dict[str, Any], tag_quality: dict[str, Any]) -> list[str]:
    weaknesses = []
    if tag_quality.get("has_warning"):
        weaknesses.append(tag_quality.get("comment", "タグ品質警告があります。"))
    if _num(detail.get("evaluation_score")) < 50:
        weaknesses.append("評価スコアが低く、単純なカード品質やバランス面に不安があります。")
    if _num(detail.get("finisher_count")) < 3:
        weaknesses.append("フィニッシャー枚数が少なく、勝利条件への到達先が細い可能性があります。")
    if _num(detail.get("defense_count")) < 6:
        weaknesses.append("受け札が少なく、速攻・ビート対面で崩れやすい可能性があります。")
    if _num(detail.get("average_cost")) >= 5:
        weaknesses.append("平均コストが高く、重コントロール/耐久寄りに偏っている可能性があります。")
    if goldfish and goldfish.get("early_success_rate", 1) < 0.65:
        weaknesses.append(f"一人回しで初動成功率が {_percent(goldfish.get('early_success_rate'))} と低めです。")
    if goldfish and goldfish.get("defense_seen_rate", 1) < 0.45:
        weaknesses.append(f"一人回しで受け札確認率が {_percent(goldfish.get('defense_seen_rate'))} と低めです。")
    return weaknesses or ["重大な弱点は簡易指標では見えていません。環境対面ごとの負け筋確認が必要です。"]


def _deck_review_questions(detail: dict[str, Any]) -> list[str]:
    name = detail.get("deck_name", "この候補")
    return [
        f"{name} の主な勝利ルートは、直接攻撃、特殊勝利、ロック、ループ変換のどれに近いか。",
        "デッキリスト内で、状態変換連鎖の起点・中継・終端になっているカードはどれか。",
        "環境S/A帯に対して、刺さる状態変換と止められる状態変換は何か。",
        "研究価値を上げるために、抜くべきカードと足すべき状態変換は何か。",
    ]


def _meta_quality_warnings(meta_decks: pd.DataFrame) -> list[str]:
    if meta_decks.empty or "key_cards" not in meta_decks.columns:
        return []
    generic_tokens = {"自然", "水", "闇", "火", "光", "無色", "火光", "光火", "水闇", "闇水", "自然火", "火自然", "光闇", "闇光"}
    warnings = []
    for _, row in meta_decks.head(30).iterrows():
        key_cards = str(row.get("key_cards", "") or "").strip()
        tokens = [token.strip() for token in key_cards.replace(",", ";").replace("、", ";").split(";") if token.strip()]
        if not tokens:
            warnings.append(f"{row.get('deck_name', '名称不明')} は key_cards が空です。")
        elif all(token in generic_tokens or len(token) <= 2 for token in tokens):
            warnings.append(f"{row.get('deck_name', '名称不明')} の key_cards が汎用語のみです: {key_cards}")
    return warnings[:10]


def _generated_deck_skew_comments(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return ["保存済み生成デッキがないため、偏りはまだ判断できません。"]
    comments = []
    if "deck_type" in df.columns:
        distribution = df["deck_type"].fillna("").replace("", "不明").value_counts(normalize=True)
        if not distribution.empty:
            top_type = str(distribution.index[0])
            top_ratio = float(distribution.iloc[0])
            if top_ratio >= 0.45:
                comments.append(f"候補が {top_type} に偏っています（{top_ratio:.0%}）。別勝利条件の探索も必要です。")
            if any(keyword in top_type for keyword in ["コントロール", "耐久", "ロック"]):
                comments.append("候補が重コントロール/耐久に寄りやすい傾向があります。速度系・特殊勝利系との比較が必要です。")
    if "average_cost" in df.columns:
        avg_cost = pd.to_numeric(df["average_cost"], errors="coerce").mean()
        if pd.notna(avg_cost):
            if avg_cost >= 4.8:
                comments.append(f"平均コストが高めです（平均 {avg_cost:.2f}）。初動安定性と速攻耐性を重点確認してください。")
            elif avg_cost <= 3.0:
                comments.append(f"平均コストが低めです（平均 {avg_cost:.2f}）。終盤の勝利到達力を確認してください。")
    if "evaluation_score" in df.columns:
        avg_eval = pd.to_numeric(df["evaluation_score"], errors="coerce").mean()
        if pd.notna(avg_eval) and avg_eval < 50:
            comments.append(f"評価スコア平均が低めです（平均 {avg_eval:.2f}）。未知性だけでなく勝利到達の質を確認してください。")
    return comments


def _build_questions(
    brief: dict[str, Any],
    meta_summary: dict[str, Any],
    combo_summary: dict[str, Any],
    effect_summary: dict[str, Any],
    generated_decks: pd.DataFrame,
) -> list[str]:
    questions = [
        "現在の候補群から、未知勝利ルートとして最も検証価値が高いものはどれか。",
        "状態変換連鎖が勝利条件到達へ接続していない候補は、どの状態が不足しているか。",
        "環境デッキS/A帯に対して、候補ルートが刺さる可能性と弱点は何か。",
    ]
    if meta_summary.get("count", 0) == 0:
        questions.append("環境デッキDBが空の場合、最低限どの環境デッキ情報を優先登録すべきか。")
    if combo_summary.get("count", 0) == 0:
        questions.append("既知コンボDBが空の場合、未知ルート探索の比較対象として最初に登録すべきコンボ型は何か。")
    if not effect_summary.get("complete"):
        questions.append("効果構造DBを完成させるために不足している特徴量は何か。")
    if generated_decks.empty:
        questions.append("保存済み生成デッキがない状態で、最初に探索すべき勝利条件はどれか。")
    if brief.get("weak_generated_decks"):
        questions.append("改善候補を未知勝利ルートとして再利用するなら、どの状態変換を足すべきか。")
    return questions


def _format_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, dict):
        return ", ".join(f"{k}:{v}" for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    text = str(value)
    return text if text else "-"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _split_tags(value: str) -> list[str]:
    tags = []
    for tag in value.replace(",", ";").replace("、", ";").split(";"):
        tag = tag.strip()
        if tag:
            tags.append(tag)
    return tags


def _quantity(card: dict[str, Any]) -> int:
    try:
        return int(card.get("quantity", 1))
    except Exception:
        return 1


def _num(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _percent(value: Any) -> str:
    try:
        return f"{float(value):.1%}"
    except Exception:
        return "未取得"

def _safe_route_evaluation_rows(db_path: Path) -> list[dict[str, Any]]:
    try:
        return evaluate_saved_route_based_decks(db_path)
    except Exception as exc:
        return [
            {
                "deck_name": "route_based 再評価エラー",
                "route_type": "-",
                "route_score": "-",
                "adjusted_route_score": "-",
                "required_mana_estimate": "-",
                "earliest_route_turn": "-",
                "route_reproducibility_score": "-",
                "route_risk_score": "-",
                "nearest_known_combo": "-",
                "known_combo_similarity": "-",
                "target_meta_decks": "-",
                "difference_from_known_combo": f"再評価に失敗しました: {exc}",
                "meta_hit_reason": "-",
                "required_support_roles": "-",
                "missing_support_states": "-",
                "route_evaluation_comment": "-",
            }
        ]


def _route_evaluation_summary_table(rows: list[dict[str, Any]]) -> list[str]:
    columns = [
        "deck_name",
        "route_type",
        "route_score",
        "adjusted_route_score",
        "required_mana_estimate",
        "earliest_route_turn",
        "route_reproducibility_score",
        "route_risk_score",
        "nearest_known_combo",
        "known_combo_similarity",
        "target_meta_decks",
    ]
    picked = []
    for row in rows[:10]:
        picked.append({column: row.get(column, "") for column in columns})
    return _markdown_table(picked, empty_message="route_based 再評価対象はありません。")


def _route_evaluation_detail_sections(rows: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for index, row in enumerate(rows[:5], start=1):
        title = row.get("deck_name") or row.get("route_type") or f"route_based候補 {index}"
        lines.append(f"### route_based 再評価 {index}. {title}")
        lines.append("")
        lines.extend(
            _bullet_dict(
                {
                    "route_type": row.get("route_type", "-"),
                    "route_score": row.get("route_score", "-"),
                    "adjusted_route_score": row.get("adjusted_route_score", "-"),
                    "必要マナ推定": row.get("required_mana_estimate", "-"),
                    "最速成立ターン推定": row.get("earliest_route_turn", "-"),
                    "再現性スコア": row.get("route_reproducibility_score", "-"),
                    "リスクスコア": row.get("route_risk_score", "-"),
                    "近い既知コンボ": row.get("nearest_known_combo", "-"),
                    "既知コンボ類似度": row.get("known_combo_similarity", "-"),
                    "既知コンボとの差分": row.get("difference_from_known_combo", "-"),
                    "刺さり候補環境デッキ": row.get("target_meta_decks", "-"),
                    "刺さる理由": row.get("meta_hit_reason", "-"),
                    "不足補助役割": row.get("required_support_roles", "-"),
                    "不足状態": row.get("missing_support_states", "-"),
                    "評価コメント": row.get("route_evaluation_comment", "-"),
                }
            )
        )
        if _num(row.get("adjusted_route_score")) < _num(row.get("route_score")):
            lines.append("")
            lines.append(
                "> 注意: 構造上の route_score より adjusted_route_score が低いため、"
                "必要マナ・成立ターン・再現性・リスクを優先して見てください。"
            )
        lines.append("")
    return lines

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_OUT = Path("data/reports/meta_intelligence_watchlist")


@dataclass(frozen=True)
class WatchSource:
    name: str
    source_type: str
    priority: str
    watch_targets: list[str]
    mana_value: str
    collection_method: str
    caveats: list[str]


WATCH_SOURCES = [
    WatchSource(
        name="X #デュエプレ最高レート / 入賞報告",
        source_type="real_time_social",
        priority="S",
        watch_targets=[
            "#デュエプレ最高レート",
            "レート1600",
            "レート1700",
            "公認大会",
            "優勝",
            "入賞",
            "デッキレシピ",
        ],
        mana_value="最速でローグデッキ、新型、環境上位の穴を突いた構築を検出する。",
        collection_method="まずは手動メモ/URL登録。API連携は規約と認証が必要なため別タスクで扱う。",
        caveats=["投稿の再現性が不明な場合がある", "画像レシピはOCRまたは手入力が必要", "短期的な上振れ報告を過信しない"],
    ),
    WatchSource(
        name="有志攻略サイト / BEANS系データ",
        source_type="community_data",
        priority="S",
        watch_targets=["非公式大会", "レート上位", "勝率", "使用率", "急上昇", "対戦データ"],
        mana_value="Tier表ではなく勝率上昇・使用率変化・対面データから新しい兆候を拾う。",
        collection_method="サイトURLと該当デッキ名を手動登録。自動取得はサイト構造確認後に追加する。",
        caveats=["データ期間の偏りに注意", "母数が少ない勝率急上昇を高評価しすぎない"],
    ),
    WatchSource(
        name="海外サーバー動向",
        source_type="future_meta_hint",
        priority="A",
        watch_targets=["中国版", "台湾版", "先行実装", "流行デッキ", "環境推移"],
        mana_value="日本版と実装時期がズレる場合、将来メタの仮説として扱う。",
        collection_method="記事/動画/レシピを手動登録し、日本版カードプールとの差分をMANA側で確認する。",
        caveats=["カード効果や実装順が違う可能性", "そのまま日本版へ移植できるとは限らない"],
    ),
    WatchSource(
        name="超次元 / サイキック枠の差し替え",
        source_type="side_zone_tech",
        priority="A",
        watch_targets=["超次元", "サイキック", "ドラグハート", "1枚差し替え", "対策枠", "完封"],
        mana_value="メイン40枚が同じでも、外部ゾーン1〜2枚で対面性能が変わる候補を検出する。",
        collection_method="通常40枚とは別枠として、外部ゾーン技術メモに保存する。",
        caveats=["通常デッキ枠のsanity判定とは別扱い", "対応フォーマットと使用可能性の確認が必要"],
    ),
    WatchSource(
        name="デュエプレ固有効果 / 紙TCGとの差分",
        source_type="rules_delta",
        priority="A",
        watch_targets=["紙では弱い", "デュエプレで強化", "効果変更", "探索", "自動化", "独自裁定"],
        mana_value="紙の評価を鵜呑みにせず、デュエプレ固有テキストから新しい状態変換を探す。",
        collection_method="カード名、紙との差分、デュエプレで強い理由をメモ化して効果構造解析へ渡す。",
        caveats=["紙版知識の先入観を避ける", "必ず公式DBのデュエプレテキストで再確認する"],
    ),
]


SIGNAL_KEYWORDS = {
    "high_rate": ["レート1600", "レート1700", "最高レート", "#デュエプレ最高レート"],
    "tournament_result": ["優勝", "入賞", "準優勝", "ベスト4", "公認大会", "タカラトミー杯"],
    "rogue_or_new": ["新型", "ローグ", "初見", "新デッキ", "新構築", "メタ外"],
    "data_rise": ["勝率", "急上昇", "使用率", "対戦データ", "母数"],
    "side_zone": ["超次元", "サイキック", "ドラグハート", "覚醒"],
    "duelmasters_plays_delta": ["紙", "デュエプレ", "強化", "効果変更", "探索"],
}


def list_watch_sources() -> list[dict[str, Any]]:
    return [asdict(source) for source in WATCH_SOURCES]


def analyze_observation_text(text: str) -> dict[str, Any]:
    try:
        from src.meta_watchlist_parser import parse_meta_watchlist_note

        parsed = parse_meta_watchlist_note(text)
        parsed["score"] = int(round(float(parsed.get("confidence", 0)) * 100))
        return parsed
    except Exception:
        pass
    text = str(text or "")
    signal_hits: dict[str, list[str]] = {}
    score = 0
    for signal, keywords in SIGNAL_KEYWORDS.items():
        hits = [keyword for keyword in keywords if keyword in text]
        if not hits:
            continue
        signal_hits[signal] = hits
        if signal in {"high_rate", "tournament_result"}:
            score += 30
        elif signal in {"rogue_or_new", "data_rise"}:
            score += 22
        else:
            score += 14
    if "デッキレシピ" in text or "レシピ" in text:
        score += 10
    if "画像" in text or "スクショ" in text:
        score += 4
    priority = "低"
    if score >= 60:
        priority = "高"
    elif score >= 30:
        priority = "中"
    return {
        "priority": priority,
        "score": min(100, score),
        "signal_hits": signal_hits,
        "mana_action": suggest_mana_action(signal_hits),
    }


def suggest_mana_action(signal_hits: dict[str, list[str]]) -> str:
    if "side_zone" in signal_hits:
        return "外部ゾーン候補として記録し、通常40枚とは別に対面別効果を確認する。"
    if "duelmasters_plays_delta" in signal_hits:
        return "公式DBテキストを効果構造解析にかけ、紙TCG評価との差分を状態変換として確認する。"
    if "high_rate" in signal_hits or "tournament_result" in signal_hits:
        return "デッキレシピを候補DBへ登録し、テーマ制約つき夜間研究のseedとして扱う。"
    if "data_rise" in signal_hits:
        return "環境DBへ観測メモとして登録し、対面評価の重みを見直す。"
    return "研究メモとして保存し、関連カード/テーマが増えたら候補化する。"


def build_watch_queries() -> list[dict[str, str]]:
    rows = []
    for source in WATCH_SOURCES:
        rows.append(
            {
                "source": source.name,
                "priority": source.priority,
                "query": " OR ".join(source.watch_targets),
                "mana_value": source.mana_value,
            }
        )
    return rows


def build_watch_brief() -> str:
    lines = [
        "# Project MANA 外部定点観測リスト",
        "",
        f"- generated_at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 目的",
        "X、入賞報告、有志データ、海外サーバー、超次元枠、デュエプレ固有効果から、ローグデッキや新型の兆候を拾う。",
        "MANAはこれらをそのまま強いと断定せず、候補seed、環境メモ、効果構造仮説として扱う。",
        "",
        "## 観測対象",
    ]
    for source in WATCH_SOURCES:
        lines.extend(
            [
                "",
                f"### {source.name}",
                f"- 種別: {source.source_type}",
                f"- 優先度: {source.priority}",
                f"- 見る語句: {' / '.join(source.watch_targets)}",
                f"- MANAでの価値: {source.mana_value}",
                f"- 収集方法: {source.collection_method}",
                f"- 注意: {' / '.join(source.caveats)}",
            ]
        )
    lines.extend(
        [
            "",
            "## MANAへの反映ルール",
            "- レート/入賞報告: 候補seedとして登録し、テーマ制約つき夜間研究に渡す。",
            "- 勝率急上昇データ: 環境DBの注目対面として重み付けする。",
            "- 超次元/サイキック差し替え: 通常40枚とは別枠で外部ゾーン技術として扱う。",
            "- 紙TCGとの差分: 公式デュエプレテキストを効果構造解析にかける。",
            "- 未確認情報: 強いと断定せず、実戦ログ待ち候補にする。",
            "",
            "## seed_type分類",
            "- high_rate_recipe: 高レート到達報告。環境DB候補として構造差分を見る。",
            "- tournament_result: 大会入賞報告。信頼度高めの実績seedとして扱う。",
            "- winrate_spike: 勝率/使用率が急上昇したデッキ。メタ適性を重点確認する。",
            "- matchup_counter: 特定対面へのメタseed。target_matchupsとrequired_tagsへ反映する。",
            "- overseas_meta: 海外先行環境seed。日本版カードプールで再現可能か確認する。",
            "- external_zone_tech: 超次元/サイキック/ドラグハートなど外部ゾーン差し替えseed。",
            "- paper_diff_hypothesis: 紙TCGとの差分から生まれる効果構造仮説seed。",
            "- rogue_deck_signal: ローグデッキ兆候。未知性と環境対策性能を確認する。",
        ]
    )
    return "\n".join(lines)


def export_watchlist(out_dir: str | Path = DEFAULT_OUT) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "meta_intelligence_watchlist.md"
    json_path = out_dir / "meta_intelligence_watchlist.json"
    csv_path = out_dir / "meta_intelligence_queries.csv"
    md_path.write_text(build_watch_brief(), encoding="utf-8")
    json_path.write_text(json.dumps(list_watch_sources(), ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "priority", "query", "mana_value"])
        writer.writeheader()
        writer.writerows(build_watch_queries())
    return {"markdown": md_path, "json": json_path, "csv": csv_path}


def main() -> None:
    paths = export_watchlist()
    print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.combo_knowledge_base import (
    ensure_known_combos_table,
    get_connection,
    load_known_combos,
    save_known_combo,
)
from src.import_cards import DEFAULT_DB_PATH


# 現環境(第36弾前後)で実在が確認できている既知コンボ・確定勝ち筋。
# カード名は data/cards.db の cards.name と完全一致させる。
SEED_KNOWN_COMBOS: list[dict[str, Any]] = [
    {
        "combo_name": "青単スコーラー 追加ターン連打",
        "format": "ND",
        "archetype": "青単スコーラー",
        "core_cards": "次元の嵐 スコーラー",
        "starter_cards": "エナジー・ライト;堕呪 ウキドゥ",
        "support_cards": "異端流し オニカマス",
        "payoff_cards": "次元の嵐 スコーラー",
        "required_zones": "手札;墓地",
        "required_conditions": "1ターン中に呪文5枚以上でG・ゼロ達成",
        "main_sequence": "軽量呪文を連打しG・ゼロでスコーラーを複数展開、追加ターンを連続獲得して打点で押し切る",
        "win_condition": "追加ターン連打からの過剰打点",
        "strengths": "受け札を無視できる追加ターン、4-5ターン目の再現性",
        "weaknesses": "呪文メタ(デル・フィン、ミクセル)、ハンデス",
        "counter_cards_or_tags": "呪文ロック;踏み倒しメタ;ハンデス",
        "related_tags": "ドロー;コンボ;追加ターン",
        "pattern_type": "価値増幅",
        "notes": "route想定: loop_converted_win",
    },
    {
        "combo_name": "QQQX 終焉の開闢 山札破壊ループ",
        "format": "AD",
        "archetype": "アナカラーQQQX",
        "core_cards": "Q.Q.QX./終葬 5.S.D.;龍装鬼 オブザ08号/終焉の開闢",
        "starter_cards": "堕魔 ヴォガイガ;ボーンおどり・チャージャー",
        "support_cards": "獣軍隊 ヤドック;刻解人形ジェニー・ジェーン",
        "payoff_cards": "Q.Q.QX./終葬 5.S.D.",
        "required_zones": "墓地;マナ",
        "required_conditions": "墓地肥やしとマナ回収でパーツを揃える",
        "main_sequence": "終葬5.S.D.とオブザ08号側の呪文を相互回収しながら相手の山札・盤面を削り切る",
        "win_condition": "相手山札切れ(ライブラリアウト)",
        "strengths": "受けを介さず勝つ、対コントロールに強い",
        "weaknesses": "墓地メタ、速攻",
        "counter_cards_or_tags": "墓地リセット;速攻",
        "related_tags": "墓地利用;ループ;山札破壊",
        "pattern_type": "ループ",
        "notes": "route想定: opponent_deckout_win",
    },
    {
        "combo_name": "グスタフ 墓地蘇生ループ",
        "format": "AD",
        "archetype": "グスタフループ",
        "core_cards": "グスタフ・アルブサール;堕魔 ドゥポイズ",
        "starter_cards": "ボーンおどり・チャージャー",
        "support_cards": "解体人形ジェニー;終末の時計 ザ・クロック",
        "payoff_cards": "グスタフ・アルブサール",
        "required_zones": "墓地;盤面",
        "required_conditions": "グスタフ着地+墓地に進化でないクリーチャー",
        "main_sequence": "グスタフのキズナプラスで下のカードを墓地に置き、墓地からドゥポイズ等の自壊クリーチャーを毎ターン蘇生して相手盤面と手札を削り続ける",
        "win_condition": "継続的な盤面拘束からの打点",
        "strengths": "対応力が高く、蘇生対象で状況対応できる",
        "weaknesses": "着地前の速攻、墓地メタ",
        "counter_cards_or_tags": "速攻;墓地リセット;踏み倒しメタ",
        "related_tags": "ループ;墓地利用;蘇生",
        "pattern_type": "ループ",
        "notes": "route想定: lock_confirmed_win / opponent_deckout_win。旧記述(落城の計コア)はグスタフのP'S能力(墓地からクリーチャー蘇生)とテキスト上の接続がないため2026-07-09修正",
    },
    {
        "combo_name": "ミラダンテXII ラフルル 呪文召喚ロック",
        "format": "AD",
        "archetype": "革命チェンジ系",
        "core_cards": "時の法皇 ミラダンテXII;音精 ラフルル",
        "starter_cards": "蒼き団長 ドギラゴン剣",
        "support_cards": "単騎連射 マグナム",
        "payoff_cards": "時の法皇 ミラダンテXII",
        "required_zones": "盤面;手札",
        "required_conditions": "革命チェンジ元の攻撃",
        "main_sequence": "チェンジ元で攻撃しミラダンテXII+ラフルルへ革命チェンジ、召喚と呪文を同時封印して安全に詰める",
        "win_condition": "ロック下での確定打点",
        "strengths": "受け札をほぼ無効化する確定詰め",
        "weaknesses": "チェンジ元依存、踏み倒しメタ",
        "counter_cards_or_tags": "踏み倒しメタ;攻撃制限",
        "related_tags": "ロック;革命チェンジ;トリガーケア",
        "pattern_type": "制約解除",
        "notes": "route想定: lock_confirmed_win",
    },
    {
        "combo_name": "必駆蛮触礼亞 クラッシュ覇道 追加ターン",
        "format": "ND",
        "archetype": "レイド覇道",
        "core_cards": "“必駆”蛮触礼亞;勝利龍装 クラッシュ“覇道”",
        "starter_cards": "異端流し オニカマス",
        "support_cards": "龍装者 バルチュリス",
        "payoff_cards": "勝利龍装 クラッシュ“覇道”",
        "required_zones": "手札",
        "required_conditions": "5マナで必駆蛮触礼亞を詠唱",
        "main_sequence": "5ターン目に必駆から覇道を踏み倒し、シールドブレイクで追加ターンを獲得して連続打点で押し切る",
        "win_condition": "追加ターンを絡めた過剰打点",
        "strengths": "5ターン目の疑似2回行動、バルチュリス追撃",
        "weaknesses": "踏み倒しメタ、破壊時デメリット",
        "counter_cards_or_tags": "踏み倒しメタ;バウンス;ブロッカー",
        "related_tags": "踏み倒し;追加ターン;速攻",
        "pattern_type": "制約解除",
        "notes": "route想定: damage_overflow_win",
    },
    {
        "combo_name": "シャコガイル 山札0特殊勝利",
        "format": "AD",
        "archetype": "水コントロール",
        "core_cards": "水上第九院 シャコガイル",
        "starter_cards": "エナジー・ライト;クリスタル・メモリー",
        "support_cards": "終末の時計 ザ・クロック",
        "payoff_cards": "水上第九院 シャコガイル",
        "required_zones": "山札",
        "required_conditions": "シャコガイル着地後に自分の山札を掘り切る",
        "main_sequence": "シャコガイルを出し、大量ドローで自分の山札を0にして敗北置換の特殊勝利を達成する",
        "win_condition": "カード効果による特殊勝利",
        "strengths": "受けながら勝てる、打点不要",
        "weaknesses": "着地前の速攻、除去",
        "counter_cards_or_tags": "除去;速攻;ハンデス",
        "related_tags": "特殊勝利;ドロー;コントロール",
        "pattern_type": "特殊勝利",
        "notes": "route想定: alternate_effect_win",
    },
    {
        "combo_name": "サイバー・J・イレブン 特殊勝利",
        "format": "AD",
        "archetype": "水単展開",
        "core_cards": "サイバー・J・イレブン",
        "starter_cards": "エナジー・ライト",
        "support_cards": "プラチナ・ワルスラS",
        "payoff_cards": "サイバー・J・イレブン",
        "required_zones": "盤面",
        "required_conditions": "自分の水クリーチャーが11体",
        "main_sequence": "小型の水クリーチャーを横展開し、J・イレブン着地時の盤面11体条件で特殊勝利する",
        "win_condition": "カード効果による特殊勝利",
        "strengths": "受け札を無視して勝つ",
        "weaknesses": "全体除去、展開速度",
        "counter_cards_or_tags": "全体除去;ロック",
        "related_tags": "特殊勝利;大量展開",
        "pattern_type": "特殊勝利",
        "notes": "route想定: alternate_effect_win",
    },
    {
        "combo_name": "バクアドルガン バイケン マッドネスカウンター",
        "format": "AD",
        "archetype": "カウンターバイケン",
        "core_cards": "熱血龍 バクアドルガン;蒼神龍バイケン",
        "starter_cards": "",
        "support_cards": "終末の時計 ザ・クロック",
        "payoff_cards": "蒼神龍バイケン",
        "required_zones": "手札",
        "required_conditions": "相手のターン中のハンデス(相手依存)",
        "main_sequence": "相手のハンデスに合わせてバイケンをマッドネスで踏み倒し、バウンスと打点でカウンターする",
        "win_condition": "カウンター展開からの打点",
        "strengths": "ハンデス耐性、攻守一体",
        "weaknesses": "踏み倒しメタ、除去耐性のなさ、相手がハンデスしないと不発",
        "counter_cards_or_tags": "踏み倒しメタ;除去",
        "related_tags": "マッドネス;カウンター;バウンス",
        "pattern_type": "状態変化",
        "notes": "route想定: damage_overflow_win。マッドネスの起動役は相手のハンデスでありデッキ内2枚コンボではない(2026-07-09見直し)。バクアドルガンは手札破棄を持たない",
    },
    {
        "combo_name": "轟轟轟ブランド GG-0 高速打点",
        "format": "ND",
        "archetype": "赤単ブランド",
        "core_cards": "“轟轟轟”ブランド",
        "starter_cards": "一撃奪取 トップギア;凶戦士ブレイズ・クロー",
        "support_cards": "単騎連射 マグナム",
        "payoff_cards": "“轟轟轟”ブランド",
        "required_zones": "手札",
        "required_conditions": "手札0枚でGG-0(コスト0)",
        "main_sequence": "低コスト打点を展開して手札を使い切り、GG-0で轟轟轟ブランドを0コスト召喚して過剰打点を作る",
        "win_condition": "過剰打点による速攻",
        "strengths": "3-4ターンの決着速度",
        "weaknesses": "受け特化デッキ、全体除去",
        "counter_cards_or_tags": "受け札;ブロッカー;全体除去",
        "related_tags": "速攻;過剰打点;制約解除",
        "pattern_type": "制約解除",
        "notes": "route想定: damage_overflow_win",
    },
    {
        "combo_name": "B-零朱レイド シールド焼却",
        "format": "ND",
        "archetype": "赤系レイド",
        "core_cards": "“B-零朱”レイド;“必駆”蛮触礼亞",
        "starter_cards": "ダチッコ・チュリス",
        "support_cards": "“轟轟轟”ブランド",
        "payoff_cards": "“B-零朱”レイド",
        "required_zones": "手札",
        "required_conditions": "必駆または軽減からのレイド早出し",
        "main_sequence": "必駆蛮触礼亞でB-零朱レイドを踏み倒し、シールド焼却でトリガーを封じながら打点を通す",
        "win_condition": "受けを焼却した確定打点",
        "strengths": "トリガーケアしながらの速攻",
        "weaknesses": "踏み倒しメタ、ブロッカー",
        "counter_cards_or_tags": "踏み倒しメタ;ブロッカー",
        "related_tags": "踏み倒し;盾焼却;トリガーケア",
        "pattern_type": "制約解除",
        "notes": "route想定: damage_overflow_win",
    },
    {
        "combo_name": "ザビ・ミラ ヴォルグ・サンダー 山札破壊",
        "format": "AD",
        "archetype": "闇コントロール",
        "core_cards": "復活の祈祷師ザビ・ミラ;ヴォルグ・サンダー",
        "starter_cards": "ボーンおどり・チャージャー",
        "support_cards": "解体人形ジェニー",
        "payoff_cards": "ヴォルグ・サンダー",
        "required_zones": "盤面;超次元",
        "required_conditions": "自分クリーチャー複数体をザビ・ミラのコストにする",
        "main_sequence": "ザビ・ミラで自分の小型を破壊しヴォルグ・サンダーを複数展開、相手の山札を大量に削って勝つ",
        "win_condition": "相手山札切れ(ライブラリアウト)",
        "strengths": "受けを介さない勝ち筋",
        "weaknesses": "超次元メタ、速攻",
        "counter_cards_or_tags": "踏み倒しメタ;速攻",
        "related_tags": "山札破壊;超次元;コンボ",
        "pattern_type": "特殊勝利",
        "notes": "route想定: opponent_deckout_win",
    },
    {
        "combo_name": "ドンジャングルS7 デル・フィン 呪文ロック制圧",
        "format": "ND",
        "archetype": "黒緑ドンジャングル",
        "core_cards": "ドンジャングルS7;光神龍スペル・デル・フィン",
        "starter_cards": "ライフプラン・チャージャー;フェアリー・ライフ",
        "support_cards": "獣軍隊 ヤドック;刻解人形ジェニー・ジェーン",
        "payoff_cards": "光神龍スペル・デル・フィン",
        "required_zones": "マナ;手札",
        "required_conditions": "8マナ+手札にデル・フィン",
        "main_sequence": "マナ加速からドンジャングルS7を着地させ、能力でデル・フィンを踏み倒して呪文を封殺し制圧する",
        "win_condition": "呪文ロック下での盤面制圧",
        "strengths": "呪文主体デッキへの確定有利",
        "weaknesses": "速攻、踏み倒しメタ",
        "counter_cards_or_tags": "速攻;踏み倒しメタ",
        "related_tags": "ロック;踏み倒し;制圧",
        "pattern_type": "制約解除",
        "notes": "route想定: lock_confirmed_win。過去セッションの実テスト対象アーキタイプ",
    },
    {
        "combo_name": "ヘブンズ・フォース 軽量メタクリ多面展開",
        "format": "ND",
        "archetype": "白単メタビート",
        "core_cards": "ヘブンズ・フォース;奇石 ミクセル/ジャミング・チャフ",
        "starter_cards": "絶対の畏れ 防鎧",
        "support_cards": "煌メク聖戦 絶十;煌世主 サッヴァーク†",
        "payoff_cards": "奇石 ミクセル/ジャミング・チャフ",
        "required_zones": "手札;シールド",
        "required_conditions": "2ターン目ヘブンズ・フォース(コスト合計4以下の光クリーチャー)",
        "main_sequence": "2ターン目にヘブンズ・フォースでミクセル等の軽量メタクリーチャーを複数展開し、相手の踏み倒しを封じながら盤面で押し切る",
        "win_condition": "早出しメタ盤面からのビート",
        "strengths": "2ターン目の理不尽ムーブ、メタ性能",
        "weaknesses": "除去、シールド焼却",
        "counter_cards_or_tags": "除去;盾焼却",
        "related_tags": "早出し;踏み倒し;メタビート",
        "pattern_type": "制約解除",
        "notes": "route想定: lock_confirmed_win。旧記述(絶十を出す)はDMPSのコスト上限4以下と矛盾するため2026-07-09修正",
    },
]


def validate_card_names(db_path: Path = DEFAULT_DB_PATH) -> list[str]:
    """seed内のカード名がcardsテーブルに存在するか確認し、見つからない名前を返す。"""
    with get_connection(db_path) as conn:
        known = {row["name"] for row in conn.execute("SELECT DISTINCT name FROM cards")}
    missing: list[str] = []
    for combo in SEED_KNOWN_COMBOS:
        for column in ["core_cards", "starter_cards", "support_cards", "payoff_cards"]:
            for name in str(combo.get(column, "")).split(";"):
                name = name.strip()
                if name and name not in known:
                    missing.append(f"{combo['combo_name']}: {name}")
    return missing


def seed_known_combos(db_path: Path = DEFAULT_DB_PATH, replace: bool = False) -> dict[str, int]:
    ensure_known_combos_table(db_path)
    existing = set(load_known_combos(db_path)["combo_name"].tolist())
    inserted = 0
    skipped = 0
    for combo in SEED_KNOWN_COMBOS:
        if combo["combo_name"] in existing and not replace:
            skipped += 1
            continue
        save_known_combo(db_path=db_path, **combo)
        inserted += 1
    return {"inserted": inserted, "skipped": skipped, "total_seeds": len(SEED_KNOWN_COMBOS)}


def main() -> None:
    parser = argparse.ArgumentParser(description="既知コンボseedをknown_combosへ登録する")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--check-only", action="store_true", help="カード名の存在確認のみ行う")
    args = parser.parse_args()

    db_path = Path(args.db)
    missing = validate_card_names(db_path)
    if missing:
        print("cardsテーブルに見つからないカード名:")
        for item in missing:
            print(f"  - {item}")
    else:
        print("カード名チェック: すべてcardsテーブルに存在します。")
    if args.check_only:
        return
    if missing:
        print("未解決のカード名があるため登録を中止します。")
        raise SystemExit(1)
    result = seed_known_combos(db_path)
    print(f"登録: {result['inserted']}件 / スキップ(既存): {result['skipped']}件 / seed総数: {result['total_seeds']}件")


if __name__ == "__main__":
    main()

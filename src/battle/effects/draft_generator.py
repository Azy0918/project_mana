from __future__ import annotations

import re
from typing import Any

# 能力テキストからEffectScriptの下書きを自動生成する。
# キーワード抽出ベースのため誤りを含みうる。人手レビュー(review_status)を経て
# "approved" になったものだけをカーネル実行に使う想定。

_COUNT_PATTERN = re.compile(r"(\d+)\s*(?:枚|体)")

# 条件句の閾値数(「5枚以下で」「5枚以上あれば」)。効果のcountではないため
# 数の抽出前に取り除く(サスペーガの「draw 5」捏造の対策)
_THRESHOLD_PATTERN = re.compile(r"\d+\s*(?:枚|体)\s*(?:以下|以上)")

_CIVILIZATIONS = ("光", "水", "闇", "火", "自然")


# 踏み倒し対象の記述に現れる、種族ではないカタカナ語(これ以外のカタカナ語は
# 種族・固有名指定とみなし、表現不可として変換を見送る)
_NON_RACE_KATAKANA = {"クリーチャー", "カード", "コスト", "タップ", "アンタップ", "パワー", "ランダム", "シールド", "ゾーン"}


def _summon_filters(sentence: str, zone_word: str) -> dict[str, Any] | None:
    """踏み倒し文(「<ゾーン>から…バトルゾーンに出す」)からフィルタを抽出する。

    コスト上限・文明・進化除外を拾う。対象記述に未知のカタカナ語(種族・
    固有名)が含まれる場合はNone=表現不可を返し、呼び出し側は変換を見送る
    (exact-safe方向。Kサイズ事件: 「イニシャルズ1枚」の種族限定が落ちて
    何でも蘇生する捏造エンジンになった)。
    """
    # 進化元の追跡はカーネル未対応(レッド・エンド事件: 無制限蘇生への化けを防ぐ)。
    # 対象記述がゾーン語の前に来る語順(「Xを、墓地から出す」)があるため文全体で判定
    if "進化元" in sentence:
        return None
    filters: dict[str, Any] = {}
    cost_match = re.search(r"コスト\s*(\d+)\s*以下", sentence)
    if cost_match:
        filters["max_cost"] = int(cost_match.group(1))
    segment_match = re.search(zone_word + r"(.*?)バトルゾーンに出", sentence)
    segment = segment_match.group(1) if segment_match else ""
    if "このクリーチャー" in segment:
        # 自己参照の蘇生(フッシッシ型)は同名限定。無制限蘇生への化けを防ぐ
        filters["name_self"] = True
    else:
        for token in re.findall(r"[ァ-ヴー・]{3,}", segment):
            if token not in _NON_RACE_KATAKANA:
                return None
    civs = [civ for civ in _CIVILIZATIONS if f"{civ}の" in segment]
    if civs:
        filters["civilizations"] = civs
    if "進化でない" in segment:
        filters["exclude_evolution"] = True
    return filters

# 注釈テキスト(全角/半角括弧内のリマインダ)。変換対象から除外する
_REMINDER_PATTERN = re.compile(r"（[^）]*）|\([^)]*\)")

# 「すべて」系の全体効果に使う実用上の上限
ALL_COUNT = 99

# カーネルが直接処理するキーワードのみの行(EffectScript変換不要=変換済み扱い)
_KERNEL_KEYWORD_SENTENCE = re.compile(
    r"^(?:このクリーチャーは)?"
    r"(?:(?:スーパー・)?S・トリガー|(?:ドラゴン・)?[WT]・ブレイカー|パワード・ブレイカー"
    r"|ブロッカー|スピードアタッカー|スレイヤー|チャージャー"
    r"|パワーアタッカー\s*\+?\s*\d+|マッハファイター"
    r"|ブロックされない|相手プレイヤーを攻撃できない|攻撃できない)"
    r"(?:を(?:持つ|得る))?$"
)

# ツインパクトの面区切りなど、効果ではない構造トークン行
_STRUCTURAL_SENTENCE = re.compile(r"^【[^】]*】$")

# 盤面影響がない(またはカーネルの近似で吸収する)注釈・骨組み文
_NOOP_SENTENCE_PATTERNS = [
    re.compile(r"山札をシャッフルする"),
    re.compile(r"^ただし"),
    re.compile(r"「S・トリガー」は使えない"),
    re.compile(r"山札の上から\d*枚?を(見る|表向きにする)"),
    re.compile(r"残りを.*山札の(一番)?下に置く"),
    re.compile(r"^進化(V|GV)?\s*[:：\-−–-]"),  # 進化元条件はカーネルで無視する近似
    re.compile(r"^侵略\s*[:：]"),  # 侵略は通常召喚のみで近似(無償の乗り換えは未対応)
    re.compile(r"破壊される時、かわりに(マナゾーン|山札)"),
    re.compile(r"残りを.*山札の(一番)?上に置く"),
    re.compile(r"バトル中、パワーを\+\d+する"),  # 条件付きパワー加算は無視する近似
    re.compile(r"プレイヤーを攻撃できない$"),  # 条件付きでもカーネルは常時制限として処理
    re.compile(r"このクリーチャーを破壊してもよい$"),  # 任意の自壊は「しない」を選ぶ近似
    re.compile(r"バトルの後、このクリーチャーを破壊する"),  # 自壊デメリットは無視する近似
    re.compile(r"次の相手のターン開始時にアンタップしない"),  # タップ延長は通常タップで近似
    re.compile(r"^可能なら毎ターン(、相手プレイヤーを)?攻撃する$"),  # 方策は常に攻撃する
    re.compile(r"手札に加えるかわりに墓地に置く"),  # シールド焼却はカーネルが処理
    re.compile(r"タップして(バトルゾーンに)?出る"),  # タップイン静的能力は未対応(ル・ギラ・レシール事件: 捏造タップ化を防ぐ)
    re.compile(r"^【[^】]*】"),  # 【SST】等のモード段落は条件未対応→無視する近似(ゲドライド事件: 通常時の捏造全体除去を防ぐ)
]


def _normalize_sentences(text: str) -> list[str]:
    """注釈括弧を除去し、行頭記号(■◇▶など)を落とした文のリストにする。"""
    stripped = _REMINDER_PATTERN.sub("", text)
    sentences = []
    for raw in re.split(r"[。\n]", stripped):
        sentence = raw.strip().lstrip("■◇▶●・ ").strip()
        if sentence:
            sentences.append(sentence)
    return sentences


def _is_kernel_keyword_sentence(sentence: str) -> bool:
    if _KERNEL_KEYWORD_SENTENCE.match(sentence) or _STRUCTURAL_SENTENCE.match(sentence):
        return True
    return any(pattern.search(sentence) for pattern in _NOOP_SENTENCE_PATTERNS)


# トリガー句(「〜時、」)は効果ではないため、効果抽出の前に文頭から取り除く。
# 句内の語(「出た」「攻撃する」「相手のクリーチャーが〜」等)へのキーワード誤反応が
# 捏造スクリプトを生む(ストーム・クロウラー事件の一般化対策)。
# 条件句(「〜であれば」「〜なら」)は意味を変えるため対象にしない。
_TRIGGER_CLAUSE_PATTERN = re.compile(
    r"^[^。]*?(?:出た時|出る時|出した時|攻撃する時|攻撃した時|攻撃される時|攻撃するとき"
    r"|破壊された時|破壊される時|離れた時|捨てられた時|捨てられる時|唱えた時|唱える時"
    r"|ブロックした時|ブロックされた時|タップされた時|ターン開始時|ターンのはじめに?"
    r"|バトルに勝った時|バトルに負けた時|手札に加えた時|カードを引いた時)[、，]\s*"
)


def _strip_trigger_clause(sentence: str) -> str:
    return _TRIGGER_CLAUSE_PATTERN.sub("", sentence, count=1)


def _extract_count(sentence: str) -> int:
    if "すべて" in sentence or "全て" in sentence:
        return ALL_COUNT
    match = _COUNT_PATTERN.search(_THRESHOLD_PATTERN.sub("", sentence))
    if match:
        return max(1, min(10, int(match.group(1))))
    return 1


def _sentence_actions(sentence: str) -> list[dict[str, Any]]:
    # 【SST】等のモード段落は条件未対応のため効果を抽出しない(無視=過小評価側)。
    # 【LINE】はテキスト段階で分離済みのため、ここに残る【】はモード指定
    if re.search(r"【[^】]*】", sentence):
        return []
    # 条件はトリガー句剥がしの前に原文から拾う(「タップ状態で破壊された時」は
    # トリガー句側に条件が埋まっているため)
    original_sentence = sentence
    sentence = _strip_trigger_clause(sentence)
    actions: list[dict[str, Any]] = []
    count = _extract_count(sentence)
    if re.search(r"カードを(\d+枚)?引", sentence) or "ドロー" in sentence:
        actions.append({"op": "draw", "count": count})
    if "山札" in sentence and "マナゾーンに置" in sentence and "相手" not in sentence:
        actions.append({"op": "deck_top_to_mana", "count": count})
    if "相手のクリーチャー" in sentence and "マナゾーンに置" in sentence and "山札" not in sentence:
        # 山札を含む文の「マナゾーンに置く」は山札からのマナ加速(deck_top_to_mana)であり、
        # 節跨ぎで相手マナ送りに誤結合させない(ウインドアックス事件)
        actions.append({"op": "send_creature_to_mana", "count": count, "scope": "opponent"})
    # 「バトルゾーンに出す/出し」(他動詞)のみ。「出た時」はトリガー句であり
    # 「出た時、マナから手札に戻す」をsummon_from_manaと誤読する(ストーム・クロウラー事件)
    if "マナゾーンから" in sentence and re.search(r"バトルゾーンに出[すし]", sentence):
        filters = _summon_filters(sentence, "マナゾーンから")
        if filters is not None:
            actions.append({"op": "summon_from_mana", "count": count, **filters})
    if "破壊" in sentence and "相手" in sentence:
        # 「最もパワーが大きい〜をすべて破壊」は最大1体の破壊で近似
        # (countのすべて=99だと全滅除去を捏造する。1体⊆実際の対象=exact-safe方向)
        destroy_count = 1 if "最もパワーが大きい" in sentence or "いちばんパワーの大きい" in sentence else count
        action: dict[str, Any] = {"op": "destroy_creature", "count": destroy_count, "scope": "opponent"}
        power_match = re.search(r"パワー\s*(\d+)\s*以下", sentence)
        if power_match:
            action["max_power"] = int(power_match.group(1))
        cost_match = re.search(r"コスト\s*(\d+)\s*以下", sentence)
        if cost_match:
            action["max_cost"] = int(cost_match.group(1))
        actions.append(action)
    elif re.search(r"自分のクリーチャー.*破壊", sentence):
        actions.append({"op": "destroy_creature", "count": count, "scope": "self"})
    # パワー低下は同値以下の破壊で近似(パワー0以下は破壊されるルール)
    power_down = re.search(r"相手のクリーチャー.*パワーを\s*[-−]\s*(\d+)", sentence)
    if power_down:
        actions.append(
            {"op": "destroy_creature", "count": count, "scope": "opponent", "max_power": int(power_down.group(1))}
        )
    if "手札に戻" in sentence and "相手" in sentence:
        actions.append({"op": "bounce_creature", "count": count, "scope": "opponent"})
    if "タップ" in sentence and "相手" in sentence and "アンタップ" not in sentence:
        actions.append({"op": "tap_creature", "count": count, "scope": "opponent"})
    if re.search(r"シールド(ゾーン)?に(置|加え)", sentence) and "相手" not in sentence:
        actions.append({"op": "add_shield", "count": count})
    if "相手" in sentence and ("捨て" in sentence or "ハンデス" in sentence):
        actions.append({"op": "discard_opponent_hand", "count": count})
    if "山札の上" in sentence and "墓地に置" in sentence and "相手" not in sentence:
        actions.append({"op": "deck_top_to_grave", "count": count})
    elif re.search(r"その中から\d*枚?を?墓地に置", sentence):
        actions.append({"op": "deck_top_to_grave", "count": count})
    if "墓地から" in sentence and re.search(r"バトルゾーンに出[すし]", sentence):
        filters = _summon_filters(sentence, "墓地から")
        if filters is not None:
            actions.append({"op": "summon_from_grave", "count": count, **filters})
    elif "墓地から" in sentence and re.search(r"手札に(戻|加え)", sentence):
        actions.append({"op": "grave_to_hand", "count": count})
    elif (
        "手札に加え" in sentence
        and "相手" not in sentence
        and "シールド" not in sentence
        and "墓地" not in sentence
    ):
        # 山札からのサーチ・回収をドローで近似
        actions.append({"op": "draw", "count": count})
    if "手札から" in sentence and re.search(r"(コストを)?支払わ(ずに|ない)", sentence) and "出す" in sentence:
        action = {"op": "summon_from_hand", "count": count}
        cost_match = re.search(r"コスト\s*(\d+)\s*以下", sentence)
        if cost_match:
            action["max_cost"] = int(cost_match.group(1))
        actions.append(action)
    if "アンタップ" in sentence and "相手" not in sentence:
        actions.append({"op": "untap_creature", "count": count, "scope": "self"})
    if "相手のシールド" in sentence and "墓地に置" in sentence:
        actions.append({"op": "burn_opponent_shield", "count": count})
    if re.search(r"自分の手札を(\d+枚)?捨てる", sentence):
        actions.append({"op": "discard_own_hand", "count": count})
    if (
        "自分のシールド" in sentence
        and re.search(r"手札に(戻|加え)", sentence)
        and "相手のクリーチャー" not in sentence
    ):
        # 「自分のシールドが2つ以下なら、相手のクリーチャーを手札に戻す」(ペニシリン型)の
        # 条件節との誤結合を防ぐ。手札に戻すのは相手クリーチャーでありシールドではない
        actions.append({"op": "own_shield_to_hand", "count": count})
    if re.search(r"自分の手札.*マナゾーンに置", sentence):
        actions.append({"op": "hand_to_mana", "count": count})
    if "マナゾーンから" in sentence and re.search(r"手札に(戻|加え)", sentence):
        actions.append({"op": "mana_to_hand", "count": count})

    # 数えて判定できる発動条件(マナ武装・墓地枚数・革命・タップ状態)を
    # 文の全アクションに付与する。条件を落とすと無条件発動の捏造になる(ウラミハデス型)。
    # トリガー句側の条件(タップ状態)を逃さないよう原文から抽出する
    condition = _extract_condition(original_sentence)
    if condition is not None:
        for action in actions:
            action["condition"] = condition
    return actions


def _extract_condition(sentence: str) -> dict[str, Any] | None:
    if "タップ状態で破壊された時" in sentence:
        return {"kind": "source_tapped"}
    match = re.search(r"マナゾーンに(光|水|闇|火|自然)のカードが(\d+)枚以上あれば", sentence)
    if match:
        return {"kind": "mana_civ_at_least", "civilization": match.group(1), "count": int(match.group(2))}
    match = re.search(r"自分の墓地に(?:カード|クリーチャー)が(\d+)枚以上あれば", sentence)
    if match:
        return {"kind": "grave_at_least", "count": int(match.group(1))}
    match = re.search(r"自分のシールドが(\d+)(?:つ|枚)以下なら", sentence)
    if match:
        return {"kind": "shields_at_most", "count": int(match.group(1))}
    return None


def _infer_trigger(card: dict[str, Any], text: str) -> str:
    card_type = str(card.get("card_type", ""))
    if "攻撃する時" in text or "攻撃時" in text:
        return "on_attack"
    if "破壊された時" in text:
        return "on_destroyed"
    if "呪文" in card_type:
        return "on_cast"
    return "on_play"


def generate_draft_effect_script(card: dict[str, Any]) -> dict[str, Any]:
    """カード1枚分のEffectScript下書きを生成する。

    抽出できた効果がない場合は abilities が空のスクリプトを返す(バニラ扱い)。
    """
    text = str(card.get("text", "") or "")
    abilities: list[dict[str, Any]] = []
    notes: list[str] = []

    # ツインパクトの後半面(【LINE】以降)はカーネルが面選択未対応のため省略する。
    # 混ぜて抽出すると呪文面の効果がクリーチャー面のon_playに合成される捏造になる
    if "【LINE】" in text:
        text = text.split("【LINE】")[0]
        notes.append("ツインパクト後半面は面選択未対応のため省略(exact-safe)")

    sentences = _normalize_sentences(text)
    main_actions: list[dict[str, Any]] = []
    for sentence in sentences:
        main_actions.extend(_sentence_actions(sentence))

    if main_actions:
        trigger = _infer_trigger(card, text)
        abilities.append({"trigger": trigger, "actions": main_actions})
        if "S・トリガー" in text:
            abilities.append({"trigger": "s_trigger", "actions": main_actions})

    # キーワードのみの文はカーネルが直接処理するため変換済みとみなす
    uncovered = [
        s for s in sentences if not _sentence_actions(s) and not _is_kernel_keyword_sentence(s)
    ]
    if uncovered:
        notes.append("テキストの一部を効果に変換できていません。レビューで補完してください。")
    if not text:
        notes.append("能力テキストなし(バニラ)")

    return {
        "card_id": str(card.get("card_id", "")),
        "name": str(card.get("name", "")),
        "abilities": abilities,
        "notes": notes,
    }

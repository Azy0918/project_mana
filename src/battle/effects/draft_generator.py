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


def _summon_filters(sentence: str, zone_word: str) -> dict[str, Any]:
    """踏み倒し文(「<ゾーン>から…バトルゾーンに出す」)からフィルタを抽出する。

    コスト上限・文明・進化除外を拾う。種族(ハンター等)はDBに種族データがなく
    表現できないため落ちる(過大評価側の近似。鬼流院 刃事件: 無フィルタだと
    任意の大型を踏み倒す捏造になるため、文明だけでも拾う)。
    """
    filters: dict[str, Any] = {}
    cost_match = re.search(r"コスト\s*(\d+)\s*以下", sentence)
    if cost_match:
        filters["max_cost"] = int(cost_match.group(1))
    segment_match = re.search(zone_word + r"(.*?)バトルゾーンに出", sentence)
    segment = segment_match.group(1) if segment_match else ""
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
    sentence = _strip_trigger_clause(sentence)
    actions: list[dict[str, Any]] = []
    count = _extract_count(sentence)
    if re.search(r"カードを(\d+枚)?引", sentence) or "ドロー" in sentence:
        actions.append({"op": "draw", "count": count})
    if "山札" in sentence and "マナゾーンに置" in sentence and "相手" not in sentence:
        actions.append({"op": "deck_top_to_mana", "count": count})
    if "相手のクリーチャー" in sentence and "マナゾーンに置" in sentence:
        actions.append({"op": "send_creature_to_mana", "count": count, "scope": "opponent"})
    # 「バトルゾーンに出す/出し」(他動詞)のみ。「出た時」はトリガー句であり
    # 「出た時、マナから手札に戻す」をsummon_from_manaと誤読する(ストーム・クロウラー事件)
    if "マナゾーンから" in sentence and re.search(r"バトルゾーンに出[すし]", sentence):
        action = {"op": "summon_from_mana", "count": count}
        action.update(_summon_filters(sentence, "マナゾーンから"))
        actions.append(action)
    if "破壊" in sentence and "相手" in sentence:
        action: dict[str, Any] = {"op": "destroy_creature", "count": count, "scope": "opponent"}
        power_match = re.search(r"パワー\s*(\d+)\s*以下", sentence)
        if power_match:
            action["max_power"] = int(power_match.group(1))
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
        action = {"op": "summon_from_grave", "count": count}
        action.update(_summon_filters(sentence, "墓地から"))
        actions.append(action)
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
    if "自分のシールド" in sentence and re.search(r"手札に(戻|加え)", sentence):
        actions.append({"op": "own_shield_to_hand", "count": count})
    if re.search(r"自分の手札.*マナゾーンに置", sentence):
        actions.append({"op": "hand_to_mana", "count": count})
    if "マナゾーンから" in sentence and re.search(r"手札に(戻|加え)", sentence):
        actions.append({"op": "mana_to_hand", "count": count})
    return actions


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

"""カードテキスト→exact EffectScript の忠実パーサ(全節カバー方式)。

設計原則(exact-safe厳守):
- カードの全テキストを節(clause)に分割し、各節を「既知パターンのアクション」
  または「エンジンが模擬済みの静的キーワード」に対応づける。
- **全節を説明できた場合のみ** exact として返す。1節でも未知なら None(=exact化しない)。
- これにより「exactと記録したのに実は未模擬」を構造的に防ぐ。

対応を増やすほど exact 化できるカードが増える。マラソンの心臓部。
"""
from __future__ import annotations

import re
from typing import Any

# エンジンが静的プロパティとして忠実に扱うキーワード節(=空ability側で表現済み)。
# これらの節は「アクション不要・既に忠実」として消費する。
_STATIC_CLAUSE = [
    r"^W・ブレイカー$", r"^T・ブレイカー$", r"^Q・ブレイカー$",
    r"^ブロッカー$", r"^スピードアタッカー$", r"^マッハファイター$", r"^スレイヤー$",
    r"^パワーアタッカー\s*\+?\d+$",
    r"^このクリーチャーは、?タップしてバトルゾーンに出る$",
    r"^多色$", r"^チャージャー$",
    # 注: 進化(簡略模擬)・ニンジャストライク/侵略/革命チェンジ(未模擬)・ワールドブレイカー
    #     (未模擬)は静的扱いにしない=厳密exactを守る
]

# 各文明
_CIV = "光水火闇自然"


def _is_static(clause: str) -> bool:
    c = clause.strip().rstrip("。").strip()
    if not c:
        return True
    return any(re.match(p, c) for p in _STATIC_CLAUSE)


# 条件・未模擬要素を示す語。効果節にこれらが含まれたら exact化しない(reject)。
# 「条件付き効果を無条件適用」する過大評価を構造的に防ぐ。
_REJECT_TOKENS = [
    "マナ武装", "革命", "シンパシー", "ラビリンス", "あれば", "なら", "以上", "以下なら",
    "一度", "そのターン", "次の", "ターン中", "ターンの間", "ＧＲ", "GR", "超次元",
    "シールドが", "場合", "ごとに", "につき", "だけ", "選んでもよい", "見て", "公開",
    "コストを支払", "踏み倒", "山札を見", "から探", "進化", "EXライフ", "封印", "侵略",
    "革命チェンジ", "ニンジャ", "メクレイド", "までの数", "数だけ", "枚以上", "体以上",
    "できる", "してもよい", "選び、", "選んで", "バトルする", "バトルさせ", "持つ",
    "与える", "得る", "パワーを", "コスト", "になる", "扱う", "代わりに", "かわりに",
    "アンタップしない", "攻撃する", "攻撃できない", "ブロックされない", "出さない",
]


def _scope_for(clause: str) -> tuple[str, str | None] | None:
    """対象の所有者と chooser を判定。曖昧なら None(=reject)。

    戻り (scope, chooser): scope='opponent'/'self', chooser='opponent' or None。
    """
    # 「相手は自身の…」= 相手が自分の盤面から選ぶ(chooser opponent, scope opponent)
    if "相手は自身の" in clause or "相手は自分の" in clause:
        return ("opponent", "opponent")
    has_aite = "相手の" in clause
    has_jibun = "自分の" in clause
    if has_aite and not has_jibun:
        return ("opponent", None)
    if has_jibun and not has_aite:
        return ("self", None)
    return None  # 曖昧 → reject


def _count_all(clause: str) -> int:
    return 99 if ("すべて" in clause or "全て" in clause) else 1


def _restrictions(clause: str) -> dict[str, Any]:
    r: dict[str, Any] = {}
    m = re.search(r"コスト(\d+)以下", clause)
    if m:
        r["max_cost"] = int(m.group(1))
    m = re.search(r"パワー(\d+)以下", clause)
    if m:
        r["max_power"] = int(m.group(1))
    if "ブロッカー" in clause:
        r["target_filter"] = "blocker"
    return r


def _parse_action_clause(clause: str) -> list[dict[str, Any]] | None:
    """1つの効果節を action のリストに変換。未知・条件付き・曖昧なら None(=reject)。"""
    cl = clause.strip().rstrip("。")

    # 条件・未模擬要素を含む節は exact化しない(過大評価防止の要)
    if any(tok in cl for tok in _REJECT_TOKENS):
        return None

    # --- 自分ドロー(対象なし) ---
    m = re.search(r"カードを(\d+)枚引く", cl)
    if m and "捨て" not in cl and "相手" not in cl:
        return [{"op": "draw", "count": int(m.group(1))}]
    if "カードを1枚引く" in cl and "捨て" not in cl and "相手" not in cl:
        return [{"op": "draw", "count": 1}]

    # --- ハンデス(相手の手札を捨てさせる) ---
    m = re.search(r"相手は(?:自身の)?手札を(\d+)枚捨てる", cl)
    if m:
        return [{"op": "discard_opponent_hand", "count": int(m.group(1))}]
    if "相手は" in cl and "手札を1枚捨てる" in cl:
        return [{"op": "discard_opponent_hand", "count": 1}]

    # --- 自己リソース(マナ加速/シールド追加/自己ミル): 相手対象でないもののみ ---
    if "相手" not in cl:
        # マナ加速: 山札の上からN枚をマナゾーンに置く
        m = re.search(r"山札の上から(\d+)枚を[、,]?(?:自分の)?マナゾーンに置く", cl)
        if m and "墓地" not in cl:
            return [{"op": "deck_top_to_mana", "count": int(m.group(1))}]
        # シールド追加: 山札の上からN枚をシールド化 / シールドゾーンに置く / シールドをN追加
        m = re.search(r"山札の上から(\d+)枚を[、,]?(?:自分の)?シールド(?:化|ゾーンに置く)", cl)
        if m:
            return [{"op": "add_shield", "count": int(m.group(1))}]
        m = re.search(r"自分のシールドを(\d+)つ追加", cl)
        if m:
            return [{"op": "add_shield", "count": int(m.group(1))}]
        # 自己ミル: 自分の山札の上からN枚を墓地に置く
        m = re.search(r"山札の上から(\d+)枚を[、,]?(?:自分の)?墓地に置く", cl)
        if m:
            return [{"op": "deck_top_to_grave", "count": int(m.group(1))}]

    # 以下はクリーチャー対象(戦場)。墓地が絡む節は別機構なので除外(墓地戻し等の誤認防止)。
    if "墓地" in cl:
        return None
    needs_target = ("クリーチャー" in cl)

    # --- 破壊 ---
    if "破壊する" in cl and needs_target:
        sc = _scope_for(cl)
        if sc is None:
            return None
        scope, chooser = sc
        act = {"op": "destroy_creature", "count": _count_all(cl), "scope": scope}
        act.update(_restrictions(cl))
        if chooser:
            act["chooser"] = chooser
        return [act]

    # --- タップ ---
    if "タップする" in cl and needs_target:
        sc = _scope_for(cl)
        if sc is None:
            return None
        act = {"op": "tap_creature", "count": _count_all(cl), "scope": sc[0]}
        return [act]

    # --- バウンス(手札に戻す) ---
    if "手札に戻す" in cl and needs_target:
        sc = _scope_for(cl)
        if sc is None:
            return None
        act = {"op": "bounce_creature", "count": _count_all(cl), "scope": sc[0]}
        act.update({k: v for k, v in _restrictions(cl).items() if k != "target_filter"})
        if sc[1]:
            act["chooser"] = sc[1]
        return [act]

    # --- マナ送り(クリーチャーをマナゾーンに置く) ---
    if "マナゾーンに置く" in cl and needs_target:
        sc = _scope_for(cl)
        if sc is None:
            return None
        act = {"op": "send_creature_to_mana", "count": _count_all(cl), "scope": sc[0]}
        act.update({k: v for k, v in _restrictions(cl).items() if k != "target_filter"})
        return [act]

    return None


def parse_card(text: str, card_type: str) -> list[dict[str, Any]] | None:
    """カード全文を exact abilities に変換。全節カバーできなければ None。

    戻り値: abilities リスト(空リスト=静的のみで忠実) または None(exact化不可)。
    """
    if text is None:
        return []
    t = text.strip()
    if not t:
        return []  # バニラ=空abilityが忠実

    is_spell = "呪文" in (card_type or "")
    s_trigger = "S・トリガー" in t and "スーパー" not in t  # 通常S・トリガーのみ

    # マーカー行を除去しつつ節分割
    raw_clauses = re.split(r"[\n。]", t)
    clauses: list[str] = []
    for rc in raw_clauses:
        for part in re.split(r"[■◇]", rc):
            p = part.strip()
            if p:
                clauses.append(p)

    cast_actions: list[dict[str, Any]] = []
    on_play_actions: list[dict[str, Any]] = []

    for cl in clauses:
        # マーカー語のみの節は静的扱い
        if cl in ("S・トリガー", "シールド・トリガー"):
            continue
        if _is_static(cl):
            continue

        # ETB(バトルゾーンに出た時)プレフィックスを剥がす
        m = re.match(r"^(?:バトルゾーンに出た時|出た時)[、,]?(.+)$", cl)
        body = m.group(1) if m else cl

        acts = _parse_action_clause(body)
        if acts is None:
            return None  # 未知の節 → exact化不可

        if is_spell:
            cast_actions.extend(acts)
        else:
            if m or is_spell:  # ETB明示 or 呪文
                on_play_actions.extend(acts)
            else:
                # クリーチャーで「出た時」明示なしの効果文 → タイミング不明、保守的に弾く
                return None

    abilities: list[dict[str, Any]] = []
    if is_spell and cast_actions:
        trig = "s_trigger" if s_trigger else "on_cast"
        abilities.append({"trigger": "on_cast", "actions": cast_actions})
        if s_trigger:
            abilities.append({"trigger": "s_trigger", "actions": [dict(a) for a in cast_actions]})
    if on_play_actions:
        abilities.append({"trigger": "on_play", "actions": on_play_actions})
        if s_trigger:  # クリーチャーS・トリガー
            abilities.append({"trigger": "s_trigger", "actions": [dict(a) for a in on_play_actions]})
    return abilities

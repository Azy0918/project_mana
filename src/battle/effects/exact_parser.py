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
    r"^(?:相手)?プレイヤーを攻撃できない$",  # engine: cannot_attack_player で模擬済み
    r"^攻撃できない$",  # engine: cannot_attack で模擬済み
    r"^ブロックされない$",  # engine: is_unblockable で模擬済み
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
    "シンパシー", "ラビリンス", "革命チェンジ", "革命0",
    "一度", "そのターン", "次の", "ターン中", "ターンの間", "ＧＲ", "GR", "超次元",
    "シールドが", "場合", "ごとに", "につき", "だけ", "選んでもよい", "見て", "公開",
    "または", "探索", "マナゾーンから", "山札から", "それより", "大きい",
    "コストを支払", "踏み倒", "山札を見", "から探", "進化", "EXライフ", "封印", "侵略",
    "革命チェンジ", "ニンジャ", "メクレイド", "までの数", "数だけ", "枚以上", "体以上",
    "選び、", "選んで", "バトルする", "バトルさせ",
    "与える", "得る", "パワーを", "になる", "扱う", "代わりに", "かわりに",
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
    if "すべて" in clause or "全て" in clause:
        return 99
    m = re.search(r"(\d+)体(?:まで)?", clause)
    if m:
        return int(m.group(1))
    return 1


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


# アクション動詞の系統(取りこぼし検出用)。節内に複数系統あれば単一パターンでは不足。
_ACTION_FAMILIES = [
    ("引く", "引き"), ("捨てる", "捨て"), ("破壊",), ("タップする",), ("アンタップ",),
    ("手札に戻",), ("マナゾーンに置く",), ("墓地に置く",), ("シールド化", "シールドゾーンに置く", "シールドを"),
]


def _family_count(cl: str) -> int:
    # 「アンタップ」を別記号化して「タップ」系との誤検出を防ぐ
    s = cl.replace("アンタップ", "\x01")
    n = 0
    for fam in _ACTION_FAMILIES:
        words = ["\x01" if w == "アンタップ" else w for w in fam]
        if any(w in s for w in words):
            n += 1
    return n


def _split_compound(cl: str) -> list[str]:
    """連用中止「引き、」や接続「その後、」「した後、」で結ばれた複合節を分解する。"""
    s = cl
    s = s.replace("引き、", "引く\x00")
    s = s.replace("、その後、", "\x00").replace("その後、", "\x00")
    s = s.replace("した後に、", "\x00").replace("した後、", "\x00").replace("した後に", "\x00")
    return [p.strip("、 ") for p in s.split("\x00") if p.strip("、 ")]


def _parse_action_clause(clause: str) -> list[dict[str, Any]] | None:
    """1つの効果節を action のリストに変換。未知・条件付き・曖昧・取りこぼしなら None。"""
    body = clause.rstrip("。")
    all_acts: list[dict[str, Any]] = []
    for part in _split_compound(body):
        # 先頭の条件句(マナ武装/革命/墓地枚数等)を抽出。未知条件キーワードがあれば reject。
        condition, rest, had_cond = _extract_condition(part)
        if condition is None and had_cond:
            return None
        r = _parse_action_clause_raw(rest)
        if r is None:
            return None
        if condition:
            for a in r:
                a["condition"] = condition
        all_acts.extend(r)
    if not all_acts:
        return None
    # 節全体のアクション系統数 > 生成アクション数 なら取りこぼし → exact化しない
    if _family_count(body) > len(all_acts):
        return None
    return all_acts


def _extract_condition(cl: str) -> tuple[dict[str, Any] | None, str, bool]:
    """先頭の条件句を抽出。(condition, 残り節, 条件キーワード検出) を返す。

    engine._condition_met が対応する条件のみ厳密に拾う。条件キーワードがあるのに
    既知形に合致しなければ (None, cl, True) を返し、呼び出し側で reject させる。
    """
    # マナ武装N：自分のマナゾーンに<civ>のカードがN枚以上あれば、…
    m = re.search(r"自分のマナゾーンに([" + _CIV + r"])のカードが(\d+)枚以上あれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_civ_at_least", "civilization": m.group(1), "count": int(m.group(2))}, m.group(3), True)
    m = re.search(r"自分のマナゾーンにカードが(\d+)枚以上あれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "mana_at_least", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"自分の墓地に(?:カード|クリーチャー)が(\d+)枚以上あれば[、,]?(.+)$", cl)
    if m:
        return ({"kind": "grave_at_least", "count": int(m.group(1))}, m.group(2), True)
    m = re.search(r"自分のシールドが(\d+)つ?以下なら[、,]?(.+)$", cl)
    if m:
        return ({"kind": "shields_at_most", "count": int(m.group(1))}, m.group(2), True)
    had = any(w in cl for w in ("あれば", "なら", "マナ武装", "革命"))
    return (None, cl, had)


def _parse_action_clause_raw(clause: str) -> list[dict[str, Any]] | None:
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
    # engineのdiscard_opponent_handはランダム選択なので「ランダムに捨てさせる」と一致=忠実。
    m = re.search(r"相手は(?:自身の)?手札を(\d+)枚捨てる", cl)
    if m:
        return [{"op": "discard_opponent_hand", "count": int(m.group(1))}]
    if "相手は" in cl and "手札を1枚捨てる" in cl:
        return [{"op": "discard_opponent_hand", "count": 1}]
    m = re.search(r"相手の手札を(?:ランダムに)?(\d+)枚捨てさせる", cl)
    if m:
        return [{"op": "discard_opponent_hand", "count": int(m.group(1))}]
    if "相手の手札をランダムに1枚捨てさせる" in cl or "相手の手札を1枚捨てさせる" in cl:
        return [{"op": "discard_opponent_hand", "count": 1}]

    # --- 自己ディスカード ---
    m = re.search(r"自分の手札を(\d+)枚捨てる", cl)
    if m and "選" not in cl:
        return [{"op": "discard_own_hand", "count": int(m.group(1))}]
    if "自分の手札をすべて捨てる" in cl:
        return [{"op": "discard_own_hand", "count": 99}]
    if ("相手は手札をすべて捨てる" in cl) or ("相手は自身の手札をすべて捨てる" in cl):
        return [{"op": "discard_opponent_hand", "count": 99}]

    # --- アンタップ ---
    if "アンタップする" in cl and "クリーチャー" in cl:
        sc = _scope_for(cl)
        if sc is None:
            return None
        return [{"op": "untap_creature", "count": _count_all(cl), "scope": sc[0]}]

    # --- 自己リソース(マナ加速/シールド追加/自己ミル): 相手対象でないもののみ ---
    if "相手" not in cl:
        # マナ加速: 山札の上からN枚(目)をマナゾーンに置く
        m = re.search(r"山札の上から(\d+)枚目?を[、,]?(?:自分の)?マナゾーンに置く", cl)
        if m and "墓地" not in cl:
            return [{"op": "deck_top_to_mana", "count": int(m.group(1))}]
        # シールド追加: 山札の上からN枚(目)をシールド化 / シールドゾーンに置く / シールドをN追加
        m = re.search(r"山札の上から(\d+)枚目?を[、,]?(?:自分の)?シールド(?:化|ゾーンに置く)", cl)
        if m:
            return [{"op": "add_shield", "count": int(m.group(1))}]
        m = re.search(r"自分のシールドを(\d+)つ追加", cl)
        if m:
            return [{"op": "add_shield", "count": int(m.group(1))}]
        # 自己ミル: 自分の山札の上からN枚(目)を墓地に置く
        m = re.search(r"山札の上から(\d+)枚目?を[、,]?(?:自分の)?墓地に置く", cl)
        if m:
            return [{"op": "deck_top_to_grave", "count": int(m.group(1))}]

    # --- 蘇生(墓地からバトルゾーンへ): 自分の墓地から…クリーチャー…出す(強制のみ) ---
    if "墓地から" in cl and "バトルゾーンに出す" in cl and "相手" not in cl:
        act: dict[str, Any] = {"op": "summon_from_grave", "count": 1}
        mc = re.search(r"コスト(\d+)以下", cl)
        if mc:
            act["max_cost"] = int(mc.group(1))
        return [act]

    # --- シールドブレイク(相手のシールドを墓地へ) ---
    m = re.search(r"相手のシールドを(\d+)つ(?:、|を)?(?:墓地に置く|ブレイクする)", cl)
    if m:
        return [{"op": "burn_opponent_shield", "count": int(m.group(1))}]
    if "相手のシールド1つを墓地に置く" in cl or "相手のシールドを1つブレイクする" in cl:
        return [{"op": "burn_opponent_shield", "count": 1}]

    # --- 墓地回収/墓地→マナ/手札→マナ(種別フィルタ付き) ---
    def _cardfilter(s: str) -> str | None:
        if "クリーチャー" in s:
            return "creature"
        if "呪文" in s:
            return "spell"
        return None

    if "墓地から" in cl and "手札に戻" in cl and "相手" not in cl:
        m = re.search(r"墓地から(?:.{0,12}?)(\d+)?枚", cl)
        cnt = int(m.group(1)) if (m and m.group(1)) else 1
        act = {"op": "grave_to_hand", "count": cnt}
        cf = _cardfilter(cl)
        if cf:
            act["card_filter"] = cf
        return [act]
    if "墓地から" in cl and "マナゾーンに置く" in cl and "相手" not in cl:
        act = {"op": "grave_to_mana", "count": 1}
        cf = _cardfilter(cl)
        if cf:
            act["card_filter"] = cf
        return [act]
    if "手札から" in cl and "マナゾーンに置く" in cl and "相手" not in cl:
        m = re.search(r"手札から(?:.{0,12}?)(\d+)枚", cl)
        cnt = int(m.group(1)) if m else 1
        return [{"op": "hand_to_mana", "count": cnt}]

    # 以下はクリーチャー対象(戦場)。墓地・ランダム指定は別機構/未模擬なので除外。
    # (engineはクリーチャーを方策で選ぶため、テキストの「ランダムな1体」とは一致しない)
    if "墓地" in cl or "ランダム" in cl:
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
    if "手札に戻" in cl and needs_target:
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


def _detect_trigger(clause: str) -> tuple[str | None, str]:
    """節の先頭からトリガーを判定し (trigger, 本体) を返す。

    トリガー前置詞がなければ (None, clause)。相手起点の時制は曖昧なので拾わない。
    """
    cl = clause
    m = re.match(r"^(?:このクリーチャーが)?(?:バトルゾーンに)?出た時[、,]?(.+)$", cl)
    if m:
        return ("on_play", m.group(1))
    m = re.match(r"^(?:このクリーチャーが)?攻撃する時[、,]?(.+)$", cl)
    if m and "相手" not in cl[:6]:
        return ("on_attack", m.group(1))
    m = re.match(r"^(?:このクリーチャーが)?(?:破壊された時|バトルゾーンを離れた時)[、,]?(.+)$", cl)
    if m and "相手" not in cl[:8]:
        return ("on_destroyed", m.group(1))
    return (None, cl)


_LAT_RE = re.compile(
    r"^(?:バトルゾーンに出た時、)?(?:自分の)?山札の上から(\d+)枚を見る。?"
    r"その中から(.*?)(?:を)?(\d+)?枚?(?:まで)?手札に(?:加え|加える)(?:る|てもよい)?(?:。|、)?"
    r"(?:残りを(.*?)(?:に|へ)[^。]*置く)?。?$"
)


def _try_look_and_take(t: str, is_spell: bool, s_trigger: bool) -> list[dict[str, Any]] | None:
    """純粋な「山札の上からN枚を見て選ぶ」カードを look_and_take に変換。"""
    # 正規化: マーカー除去・S・トリガー/静的節を除去して残りを連結
    norm = re.sub(r"[■◇]", "", t)
    kept = []
    for cl in re.split(r"\n", norm):
        cl = cl.strip()
        if not cl or cl in ("S・トリガー", "シールド・トリガー") or _is_static(cl):
            continue
        kept.append(cl)
    joined = "".join(kept)
    # 「公開してから」等は描写なので除去(枚数捕捉を保つ)
    joined = joined.replace("を公開してから", "を").replace("公開してから", "").replace("を公開し、", "を")
    m = _LAT_RE.match(joined)
    if not m:
        return None
    look = int(m.group(1))
    filt = m.group(2) or ""
    take = int(m.group(3)) if m.group(3) else 1
    rest = m.group(4) or ""
    # 認識できない絞り込み(種族/完全コスト/以上/探索等)は取りこぼし防止のため reject
    if any(tok in filt for tok in ("探索", "見", "または", "ランダム", "以上")):
        return None
    if "コスト" in filt and "以下" not in filt:
        return None
    recognized = ("クリーチャー" in filt or "呪文" in filt or "カード" in filt
                  or any(cv in filt for cv in _CIV))
    if filt.strip() and not recognized:
        return None
    act: dict[str, Any] = {"op": "look_and_take", "look": look, "take": take}
    if "クリーチャー" in filt:
        act["card_filter"] = "creature"
    elif "呪文" in filt:
        act["card_filter"] = "spell"
    mc = re.search(r"コスト(\d+)以下", filt)
    if mc:
        act["max_cost"] = int(mc.group(1))
    mciv = re.search(r"([" + _CIV + r"])(?:の|文明)", filt)
    if mciv:
        act["civilization"] = mciv.group(1)
    if "墓地" in rest:
        act["rest_zone"] = "grave"
    elif "マナ" in rest:
        act["rest_zone"] = "mana"
    else:
        act["rest_zone"] = "deck_bottom"
    trig = "on_cast" if is_spell else "on_play"
    abilities = [{"trigger": trig, "actions": [act]}]
    if s_trigger:
        abilities.append({"trigger": "s_trigger", "actions": [dict(act)]})
    return abilities


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

    lat = _try_look_and_take(t, is_spell, s_trigger)
    if lat is not None:
        return lat

    # マーカー行を除去しつつ節分割
    raw_clauses = re.split(r"[\n。]", t)
    clauses: list[str] = []
    for rc in raw_clauses:
        for part in re.split(r"[■◇]", rc):
            p = part.strip()
            if p:
                clauses.append(p)

    by_trigger: dict[str, list[dict[str, Any]]] = {}

    for cl in clauses:
        # マーカー語のみの節は静的扱い
        if cl in ("S・トリガー", "シールド・トリガー"):
            continue
        if _is_static(cl):
            continue

        if is_spell:
            trigger, body = "on_cast", cl
        else:
            trigger, body = _detect_trigger(cl)
            if trigger is None:
                # クリーチャーでトリガー前置詞なしの効果文 → タイミング不明、保守的に弾く
                return None

        acts = _parse_action_clause(body)
        if acts is None:
            return None  # 未知の節 → exact化不可
        by_trigger.setdefault(trigger, []).extend(acts)

    abilities: list[dict[str, Any]] = []
    # S・トリガーは cast/ETB 効果にのみ適用される(攻撃時/破壊時は対象外)
    main_trigger = "on_cast" if is_spell else "on_play"
    for trig, acts in by_trigger.items():
        abilities.append({"trigger": trig, "actions": acts})
        if s_trigger and trig == main_trigger:
            abilities.append({"trigger": "s_trigger", "actions": [dict(a) for a in acts]})
    return abilities

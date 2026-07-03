"""カード依存関係チェッカー (死にカード検出).

自動生成デッキで実際に起きた欠陥:
  - マザー・エイリアン「自分のハンターは〜」→ デッキにハンター0枚
  - D2B バブール「ミルクボーイ/D2フィールド」参照 → 両方0枚
  - コレンココ・タンク「パワー12000以上を手札に」→ 該当0枚

これらはルール上決定的に検出できる。カードテキストから
「このカードが機能するためにデッキに必要なもの」を抽出し、
デッキ内で満たされているかを検証する。

方針は保守的: race列が空のDBでは種族の充足を証明できないため、
名前/カードタイプで確認できない依存は「未充足」として扱う。
"""

from __future__ import annotations

import re
from typing import Any


# 依存として扱わない一般語 (ゲームの基本語彙)
GENERIC_TERMS = {
    "クリーチャー", "カード", "呪文", "コスト", "パワー", "マナ", "マナゾーン",
    "シールド", "手札", "山札", "墓地", "バトルゾーン", "ブロッカー", "ターン",
    "プレイヤー", "エレメント", "ゾーン", "進化", "進化クリーチャー", "多色",
    "タップ", "アンタップ", "ドラゴン・W・ブレイカー", "W・ブレイカー",
    "T・ブレイカー", "S・トリガー", "G・ストライク", "名前", "自分", "相手",
    "フィールド", "城", "ツインパクト", "サイキック",
}

# 「種族/カテゴリ参照」を拾うテキストパターン
RACE_REF_PATTERNS = [
    # 自分のハンターはすべて〜 / 自分のドラゴンが〜
    r"自分の(?:他の)?([ァ-ヴー・]{3,12})(?:は|が)すべて",
    r"初めて自分の(?:他の)?([ァ-ヴー・]{3,12})がバトルゾーンに出た時",
    # その中からハンター1枚を手札に / ドラゴンを1枚選び
    r"その中から([ァ-ヴー・]{3,12})(?:を)?1枚(?:を)?(?:選び|手札に)",
    # 自分のドラゴン1体につき
    r"自分の([ァ-ヴー・]{3,12})1[体枚]につき",
    # 進化: 自分のドラゴン1体の上に置く
    r"自分の([ァ-ヴー・]{3,12})1体の上に置く",
]

# カードタイプ依存 (D2フィールド等)
CARD_TYPE_DEPENDENCIES = [
    ("D2フィールド", r"自分のD2フィールドが(?:なければ|あれば|出た時)"),
    ("クロスギア", r"クロスギアを(?:クロス|ジェネレート)"),
]

# 名前参照: 名前に《X》とある
NAME_REF_PATTERN = r"名前に《(.+?)》とある"

# パワー条件付きサーチ: パワー12000以上のクリーチャーを〜手札/バトルゾーン
POWER_FETCH_PATTERN = r"パワー(\d{4,6})以上のクリーチャーを(?:好きな数|1体|1枚)?(?:選び|手札に|バトルゾーンに)"


def _safe_power(value: Any) -> int:
    try:
        return int(re.sub(r"[^0-9]", "", str(value or "0")) or 0)
    except Exception:
        return 0


def extract_dependencies(card: dict[str, Any]) -> list[dict[str, Any]]:
    """カード1枚から「デッキに必要なもの」を抽出する。"""
    text = str(card.get("text") or "")
    own_name = str(card.get("name") or "")
    deps: list[dict[str, Any]] = []

    for pattern in RACE_REF_PATTERNS:
        for match in re.finditer(pattern, text):
            term = match.group(1).strip("・")
            if term and term not in GENERIC_TERMS and term not in own_name:
                deps.append({"kind": "race", "term": term})

    for type_name, pattern in CARD_TYPE_DEPENDENCIES:
        if re.search(pattern, text):
            deps.append({"kind": "card_type", "term": type_name})

    for match in re.finditer(NAME_REF_PATTERN, text):
        term = match.group(1).strip()
        if term and term not in GENERIC_TERMS:
            deps.append({"kind": "name", "term": term})

    for match in re.finditer(POWER_FETCH_PATTERN, text):
        deps.append({"kind": "power_at_least", "term": match.group(1)})

    # 重複除去
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for dep in deps:
        key = (dep["kind"], dep["term"])
        if key not in seen:
            seen.add(key)
            unique.append(dep)
    return unique


def count_satisfying_cards(
    dep: dict[str, Any],
    deck_cards: list[dict[str, Any]],
    owner_name: str,
) -> int:
    """依存を満たすカードの枚数を数える (依存元自身は除外)。

    race列が空のDBでは種族を証明できないため、name/card_type/raceに
    語が現れるカードのみを充足とみなす (保守的)。
    """
    kind = str(dep.get("kind"))
    term = str(dep.get("term"))
    total = 0
    for card in deck_cards:
        name = str(card.get("name") or "")
        if name == owner_name:
            continue
        quantity = int(card.get("quantity") or card.get("count") or 0)
        if kind == "race":
            blob = f"{name};{card.get('card_type', '')};{card.get('race', '')}"
            if term in blob:
                total += quantity
        elif kind == "card_type":
            if term in str(card.get("card_type") or ""):
                total += quantity
        elif kind == "name":
            if term in name:
                total += quantity
        elif kind == "power_at_least":
            threshold = int(term)
            if (
                "クリーチャー" in str(card.get("card_type") or "")
                and _safe_power(card.get("power")) >= threshold
            ):
                total += quantity
    return total


def check_deck_dependencies(
    deck_cards: list[dict[str, Any]],
    min_satisfying: int = 4,
) -> dict[str, Any]:
    """デッキ全体の依存関係を検証する。

    deck_cards の各要素は name/text/card_type/power/quantity(count) を持つ。
    自己完結参照 (自分の名前を参照するカード) は同名カードで充足する。

    Returns:
      dead_cards: 依存が完全に未充足 (0枚) のカード
      weak_cards: 充足枚数が min_satisfying 未満のカード
    """
    dead: list[dict[str, Any]] = []
    weak: list[dict[str, Any]] = []

    for card in deck_cards:
        name = str(card.get("name") or "")
        deps = extract_dependencies(card)
        for dep in deps:
            # 自己名参照 (例: 蓄積された魔力) は自身の枚数で充足
            if dep["kind"] == "name" and dep["term"] in name:
                own_copies = int(card.get("quantity") or card.get("count") or 0)
                others = count_satisfying_cards(dep, deck_cards, name)
                if own_copies + others >= 2:
                    continue
            count = count_satisfying_cards(dep, deck_cards, name)
            record = {
                "card_name": name,
                "dependency": f"{dep['kind']}:{dep['term']}",
                "satisfying_count": count,
            }
            if count == 0:
                dead.append(record)
            elif count < min_satisfying:
                weak.append(record)

    dead_names = sorted({d["card_name"] for d in dead})
    return {
        "dead_cards": dead,
        "weak_cards": weak,
        "dead_card_names": dead_names,
        "has_dead_cards": bool(dead),
        "verdict": "依存欠陥あり" if dead else ("依存やや弱い" if weak else "依存OK"),
    }


# ---------------------------------------------------------------------------
# 勝ち切り手段の実在チェック
# ---------------------------------------------------------------------------
#
# 自動生成デッキで実際に起きた欠陥: ブロッカーと「相手プレイヤーを
# 攻撃できない」持ちで固められ、耐えた後に勝つ手段が存在しない。
# これもテキストから決定的に判定できる。

ATTACK_FORBIDDEN_PATTERNS = [
    "相手プレイヤーを攻撃できない",
    "■攻撃できない",
    "◇攻撃できない",
    "このクリーチャーは攻撃できない",
]

ALT_WIN_PATTERNS = [
    "ゲームに勝つ",
    "勝利する",
    "かわりに自分がゲームに勝つ",
]


def _can_attack_player(card: dict[str, Any]) -> bool:
    card_type = str(card.get("card_type") or "")
    if "クリーチャー" not in card_type:
        return False
    text = str(card.get("text") or "")
    normalized = text.replace("\n", "")
    if "相手プレイヤーを攻撃できない" in normalized:
        return False
    # 「攻撃できない」が無条件で書かれているカードを除外
    # (「〜の場合攻撃できない」のような条件付きは許容)
    for line in text.split("\n"):
        line = line.strip("■◇ ")
        if line == "攻撃できない。" or line == "攻撃できない":
            return False
    return True


THREAT_MARKERS = [
    "W・ブレイカー",
    "T・ブレイカー",
    "Q・ブレイカー",
    "ワールド・ブレイカー",
    "スピードアタッカー",
    "ブロックされない",
    "アンブロッカブル",
]


def _threat_power(card: dict[str, Any]) -> int:
    raw = re.sub(r"[^0-9]", "", str(card.get("power") or "0"))
    try:
        return int(raw or 0)
    except Exception:
        return 0


def _is_real_attacker(card: dict[str, Any]) -> bool:
    """勝ち筋として数えられる打点かを判定する。

    攻撃可能なだけの小型ユーティリティ (2コスト初動等) は勝ち筋ではない。
    パワー5000以上、ブレイカー持ち、SA、ブロック不能のいずれかを要求する。
    """
    if not _can_attack_player(card):
        return False
    text = str(card.get("text") or "")
    if any(marker in text for marker in THREAT_MARKERS):
        return True
    return _threat_power(card) >= 5000


def check_win_capability(
    deck_cards: list[dict[str, Any]],
    min_attackers: int = 6,
    min_alt_win: int = 2,
) -> dict[str, Any]:
    """デッキが物理的に勝てるかを検証する。

    勝ち筋 = 実質的な打点 (パワー5000+/ブレイカー/SA/ブロック不能) が
    十分にいる、または特殊勝利カードがある。どちらも無いデッキは
    どれだけ受けが厚くても勝てない。
    """
    attacker_count = 0
    alt_win_count = 0
    attackers: list[str] = []
    alt_wins: list[str] = []

    for card in deck_cards:
        quantity = int(card.get("quantity") or card.get("count") or 0)
        text = str(card.get("text") or "")
        name = str(card.get("name") or "")
        if any(p in text for p in ALT_WIN_PATTERNS):
            alt_win_count += quantity
            alt_wins.append(name)
        if _is_real_attacker(card):
            attacker_count += quantity
            attackers.append(name)

    can_win = attacker_count >= min_attackers or alt_win_count >= min_alt_win
    return {
        "attacker_count": attacker_count,
        "alt_win_count": alt_win_count,
        "attacker_names": attackers[:15],
        "alt_win_names": alt_wins,
        "can_win": can_win,
        "verdict": (
            "勝ち筋OK" if can_win
            else f"勝ち筋なし (攻撃可能{attacker_count}枚 / 特殊勝利{alt_win_count}枚)"
        ),
    }

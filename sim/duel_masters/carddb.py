"""
duel_masters.carddb
===================
本物の Project MANA カードDB(data/cards.db)から ND可カードを読み込み、
エンジンの CardDef スケルトンに変換する「実DB接続」レイヤー。

役割分担:
  carddb.py   DB から コスト/文明/パワー/種族/基本キーワード を拾い、
              **効果(Ability)を持たない CardDef 骨格** を作る。
  effects.py  その骨格に対し、cid(=カード名)ごとに手書きの効果関数を差す。

つまり「実カードを足す」= DBの実データ(骨格) + 効果関数の登録、に分解される。
骨格だけでもバニラ/キーワード持ちは戦えるので、効果未登録カードも盤面に出せる。

注意: カード効果テキストは自然言語なので自動実行はできない。キーワード
(ブロッカー/SA/S・トリガー/W・ブレイカー)だけテキストから検出し、それ以外の
効果は effects.py で人間が実装する(=ルールエンジンの本質的コスト)。
"""

from __future__ import annotations
import csv
import os
import re
import sqlite3
from typing import Optional, Dict, List

from .engine import (
    CardDef, Card,
    CREATURE, SPELL, FIELD,
    LIGHT, WATER, DARKNESS, FIRE, NATURE,
)

# リポジトリ直下の data/cards.db を既定とする(sim/duel_masters/ から二つ上)
_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data"))
_DEFAULT_DB = os.path.join(_DATA_DIR, "cards.db")
_DEFAULT_SUPERDIM_CSV = os.path.join(_DATA_DIR, "cards_superdim_raw.csv")


# ---- 文明パース ------------------------------------------------------------
# 文明文字列は単一トークンの連結("光水闇火自然"等)。自然/無色のみ2文字なので
# 長いトークンを先に試すグリーディ分解で安全に切り出す。
_CIV_TOKENS = ("自然", "無色", "光", "水", "闇", "火")
_CIV_MAP = {"光": LIGHT, "水": WATER, "闇": DARKNESS, "火": FIRE, "自然": NATURE}
# 無色 は文明制約なし → どのマナでも払える(空集合に寄与させない)


def parse_civs(s: Optional[str]) -> frozenset:
    s = s or ""
    civs = set()
    i = 0
    while i < len(s):
        for tok in _CIV_TOKENS:
            if s.startswith(tok, i):
                if tok in _CIV_MAP:
                    civs.add(_CIV_MAP[tok])
                i += len(tok)
                break
        else:
            i += 1  # 未知文字はスキップ
    return frozenset(civs)


def parse_power(p) -> Optional[int]:
    if p is None:
        return None
    s = str(p).strip()
    return int(s) if s.isdigit() else None


def parse_keywords(text: Optional[str]) -> frozenset:
    """効果テキストから、エンジンが解釈できる基本キーワードだけ検出する。

    「…」で括られたキーワードは「与える/持つ」等の条件付き付与の参照なので
    innate ではない(例: G・G・Gで「スピードアタッカー」を与える)。誤検出を
    避けるため、検出前に「…」のスパンを除去する。
    """
    t = re.sub(r"「[^」]*」", "", text or "")
    kw = set()
    if "ブロッカー" in t:
        kw.add("blocker")
    if "スピードアタッカー" in t:
        kw.add("speed_attacker")
    if "マッハファイター" in t:               # アンタップの相手も攻撃可(=hunting)
        kw.add("hunting")
    if "S・トリガー" in t or "シールド・トリガー" in t:
        kw.add("shield_trigger")
    if "W・ブレイカー" in t:                 # シールドを2枚ブレイク
        kw.add("w_breaker")
    if "T・ブレイカー" in t:                  # シールドを3枚ブレイク
        kw.add("t_breaker")
    if "ワールド・ブレイカー" in t:           # 全シールドをブレイク
        kw.add("world_breaker")
    if "Q・ブレイカー" in t:                  # シールドを4枚ブレイク
        kw.add("q_breaker")
    if "マスター・W・ブレイカー" in t or "マスター・ブレイカー" in t:
        kw.add("master_breaker")            # 3枚以上(MVPでは=2枚扱いでも可)
    return frozenset(kw)


# 進化/NEO/ゴッド/エグザイル等もバトルゾーンに出る「クリーチャー」として扱う。
# 呪文は SPELL。D2フィールド/城/クロスギア/ツインパクト/各種フィールドは MVP 非対応。
def classify_ctype(card_type: Optional[str]) -> Optional[str]:
    ct = card_type or ""
    if ct == "呪文":
        return SPELL
    if "D2フィールド" in ct:           # D2フィールド=フィールドゾーンの常在パーマネント
        return FIELD
    if "クリーチャー" in ct or ct == "ゴッド":
        return CREATURE
    # ツインパクト(クリーチャー／呪文の二面)は MVP ではクリーチャー面の骨格として扱う。
    if "ツインパクト" in ct:
        return CREATURE
    return None  # 非対応タイプ → プールから除外


# ---- ロード ----------------------------------------------------------------

def load_pool(db_path: Optional[str] = None,
              nd_only: bool = True) -> Dict[str, CardDef]:
    """DB → {カード名: CardDef骨格}。再録は最初の1枚のみ。効果は未付与。"""
    db_path = db_path or _DEFAULT_DB
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    q = ("SELECT card_id, name, civilization, cost, card_type, power, race, text "
         "FROM cards")
    if nd_only:
        q += " WHERE nd_legal='1'"
    pool: Dict[str, CardDef] = {}
    for card_id, name, civ, cost, ctype_raw, power, race, text in cur.execute(q):
        if not name or name in pool:        # 再録(同名)はスキップ
            continue
        ct = classify_ctype(ctype_raw)
        if ct is None:                      # MVP非対応タイプ
            continue
        races = tuple(r for r in (race or "").replace("／", "/").split("/") if r)
        # ツインパクトは本文が【LINE】でクリーチャー面/呪文面に分かれる。
        # クリーチャー面のキーワードは face1 のみから判定(呪文面STの誤検出防止)。
        face1 = (text or "").split("【LINE】")[0]
        ctr = ctype_raw or ""
        is_evo = ("進化" in ctr) or ("NEO" in ctr)   # 進化/NEO進化=基盤に重ねる
        is_neo = "NEO" in ctr                         # NEOは基盤無しでも直接召喚できる
        pool[name] = CardDef(
            cid=card_id or name,
            name=name,
            cost=cost if cost is not None else 0,
            civs=parse_civs(civ),
            ctype=ct,
            power=parse_power(power),
            races=races,
            keywords=parse_keywords(face1),
            abilities=(),                   # ← effects.py が後から差す
            text=text or "",
            evolution=is_evo,
            neo=is_neo,
            field=(ct == FIELD),
        )
    con.close()
    return pool


# ---- 超次元ゾーン(サイキック・クリーチャー) ------------------------------

def load_super_pool(csv_path: Optional[str] = None,
                    nd_only: bool = False) -> Dict[str, CardDef]:
    """data/cards_superdim_raw.csv → {名前: CardDef(psychic=True)}。

    サイキック・クリーチャー系のみ採用(ドラグハート・フォートレス/ウエポンは龍解が
    未実装なので除外)。骨格のみ自動、覚醒/特殊効果は effects.py で手書き。
    """
    csv_path = csv_path or _DEFAULT_SUPERDIM_CSV
    pool: Dict[str, CardDef] = {}
    if not os.path.exists(csv_path):
        return pool
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ctype_raw = row.get("card_type", "")
            if "サイキック" not in ctype_raw:      # クリーチャーのサイキックのみ
                continue
            if nd_only and str(row.get("nd_legal", "")) != "1":
                continue
            name = row.get("name") or row.get("card_name") or ""
            if not name or name in pool:           # 同名再録はスキップ
                continue
            civ = row.get("civilization") or row.get("culture") or ""
            race = row.get("race") or row.get("race_text") or ""
            text = row.get("text") or row.get("body_text") or ""
            cost = row.get("cost") or "0"
            races = tuple(r for r in race.replace("／", "/").split("/") if r)
            pool[name] = CardDef(
                cid=row.get("card_id") or name,
                name=name,
                cost=int(cost) if str(cost).isdigit() else 0,
                civs=parse_civs(civ),
                ctype=CREATURE,
                # サイキックは power が空で power_disp 側に数値があることが多い。
                power=parse_power(row.get("power") or row.get("power_disp")),
                races=races,
                keywords=parse_keywords(text),
                abilities=(),
                psychic=True,
                text=text or "",
            )
    return pool


def load_dragheart_pool(csv_path: Optional[str] = None) -> Dict[str, CardDef]:
    """超次元CSVから ドラグハート(ウエポン/フォートレス)を読み込む。

    フォートレスは field=True(フィールドゾーン)、ウエポンは battle 寄りのパーマネント
    として扱う。いずれも psychic=True で離場時は超次元ゾーンへ戻る。龍解後フォームの
    スタッツは公式APIに無いため superdim.register_dragsolve() で手入力する(覚醒と同運用)。
    """
    csv_path = csv_path or _DEFAULT_SUPERDIM_CSV
    pool: Dict[str, CardDef] = {}
    if not os.path.exists(csv_path):
        return pool
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ctype_raw = row.get("card_type", "")
            if "ドラグハート" not in ctype_raw:
                continue
            name = row.get("name") or row.get("card_name") or ""
            if not name or name in pool:
                continue
            civ = row.get("civilization") or row.get("culture") or ""
            race = row.get("race") or row.get("race_text") or ""
            text = row.get("text") or row.get("body_text") or ""
            cost = row.get("cost") or "0"
            races = tuple(r for r in race.replace("／", "/").split("/") if r)
            is_fortress = "フォートレス" in ctype_raw
            pool[name] = CardDef(
                cid=row.get("card_id") or name,
                name=name,
                cost=int(cost) if str(cost).isdigit() else 0,
                civs=parse_civs(civ),
                ctype=FIELD if is_fortress else CREATURE,
                power=parse_power(row.get("power") or row.get("power_disp")),
                races=races,
                keywords=parse_keywords(text),
                abilities=(),
                psychic=True,
                field=is_fortress,
                text=text or "",
            )
    return pool


def build_super_zone(super_pool: Dict[str, CardDef], owner, names: List[str]):
    """名前リスト(最大8)から owner の超次元ゾーンを構築して返す(Cardのリスト)。"""
    zone = []
    for name in names[:8]:
        c = Card(super_pool[name], owner)
        c.zone = "super_zone"
        zone.append(c)
    return zone


# ---- 便利関数(cards.py と同じ使い勝手) -----------------------------------

def make(pool: Dict[str, CardDef], name: str, owner) -> Card:
    return Card(pool[name], owner)


def build_deck(pool: Dict[str, CardDef], owner, decklist):
    """decklist = カード名のリスト(同名4枚まで等の制約はGA側で担保)。"""
    return [make(pool, name, owner) for name in decklist]


def filter_pool(pool: Dict[str, CardDef], *, civ: Optional[str] = None,
                race: Optional[str] = None, ctype: Optional[str] = None,
                max_cost: Optional[int] = None) -> Dict[str, CardDef]:
    """色/種族/タイプ/コストでプールを絞る(アーキタイプ抽出用)。"""
    out = {}
    for name, cd in pool.items():
        if civ is not None and civ not in cd.civs:
            continue
        if race is not None and not any(race in r for r in cd.races):
            continue
        if ctype is not None and cd.ctype != ctype:
            continue
        if max_cost is not None and cd.cost > max_cost:
            continue
        out[name] = cd
    return out

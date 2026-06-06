"""
duel_masters.decks
==================
実メタ(Tier S)デッキを「fitness の相手」として扱うための、多色NDプールと
デッキ定義/検証のフレームワーク。

- build_full_pool(): 火単に限定しない**全ND多色プール**＋超次元プール。ホール召喚
  と覚醒リンクも有効化して返す。Tier Sデッキ(多色)と多色GAの土台。
- DECKS: 名前付き実メタデッキ(メイン40＋超次元8)。カード名はテキストで与える。
- validate_deck(): 各カード名がプール/DBに実在するか検証(誤記・未収録の検出)。
- make_player(): デッキ定義から対戦用 Player を組む(超次元ゾーン込み)。
- play_match(): 2デッキを着席公平に対戦させ勝率を返す(覚醒フックを取り付け済)。

デッキリストの転記は画像から自動化できない(解像度)。ユーザー提供のテキストを
DECKS に入れる運用。validate_deck で実在チェックしてから採用する。
"""
from __future__ import annotations
import random

from . import carddb, effects, superdim, twinpact
from .engine import Game, Player
from .agents import HeuristicAgent, RolloutAgent
from .ismcts import ISMCTSAgent


def heuristic_pilot(name, rng):
    """高速パイロット(GAの大量対戦・既定)。1手評価。"""
    return HeuristicAgent(name, rng)


def eval_pilot(name, rng):
    """忠実評価の正準パイロット(ISMCTS, 80反復/horizon8)。操縦プレイヤーのメイン＋
    攻撃の意思決定列をUCT木で探索し、コントロールの受け・コンボの連鎖を最も正しく回す。
    最も重いので最終評価専用。計測(diag.py)で、これがメタを最も忠実に較正することを確認:
    vs火光アグロで 闇自然0.70→0.95 / 青白0.37→0.73 / スコーラー0.29→0.66、
    スコーラーのコンボ発火も flat の約3倍(追加ターン9→26)。"""
    return ISMCTSAgent(name, rng, iterations=80, horizon=8, max_depth=12)


def eval_pilot_fast(name, rng):
    """忠実評価の軽量版(非決定化ロールアウト r6h10)。ISMCTSより約4倍速い。
    較正は中間(闇自然0.88/青白0.54/スコーラー0.51)。中量の評価に。"""
    return RolloutAgent(name, rng, rollouts=6, horizon=10)


def build_full_pool(nd_only=False):
    """(pool, super_pool)。効果/ホール召喚/覚醒リンク/ツインパクト呪文面を有効化済み。
    既定は AD 含む全カード(実メタ・ガントレットに AD デッキも載せるため)。GAの候補は
    ga.build_pools()(ND火)で別管理なので、探索デッキは ND のまま。"""
    pool = carddb.load_pool(nd_only=nd_only)
    effects.apply_effects(pool)
    superdim.attach_hole_abilities(pool)          # 超次元ホール呪文に召喚能力を付与
    twinpact.attach_twin_spells(pool)             # ツインパクトに呪文面を付与
    super_pool = carddb.load_super_pool()
    superdim.register_builtin_links()             # 覚醒リンク10家系を登録
    return pool, super_pool


# 実メタ(Tier S)デッキ定義。{デッキ名: {"main": {名前:枚数}, "super": {名前:枚数}}}
# ユーザー提供のデュエプレ現環境Tier Sレシピ(2026-06-05)。名前の揺れは resolve_name が吸収。
DECKS: dict = {
    "火光レイド": {
        "main": {
            "ダチッコ・チュリス": 2, "絶対の畏れ 防鎧": 3, "奇石 タスリク": 3,
            "オリオティス・ジャッジ": 4, "超次元サプライズ・ホール": 2,
            "“必駆”蛮触礼亞": 4, "DNA・スパーク": 2, "“乱振”舞神 G・W・D": 2,
            "“轟轟轟”ブランド": 4, "“B-零朱”レイド": 4, "閃光の守護者ホーリー": 2,
            "奇石 ミクセル／ジャミング・チャフ": 4,
            "ゴリガン砕車 ゴルドーザ／ダイナマウス・スクラッパー": 4},
        "super": {"時空の英雄アンタッチャブル": 2, "時空の踊り子マティーニ": 2,
                  "イオの伝道師ガガ・パックン": 2, "時空の戦猫シンカイヤヌス": 2},
    },
    "闇自然デンジャデオン": {
        "main": {
            "刻解人形ジェニー・ジェーン": 4, "凶鬼悪号 デモンスパイン／デーモン・ハンド": 2,
            "傀儡将ボルギーズ／ジェニコの知らない世界": 4, "牙修羅バット／真血染める闇牙": 2,
            "Q.Q.QX.／終葬 5.S.D.": 4, "ナ・チュラルゴ・デンジャー／ナチュラル・トラップ": 4,
            "イチゴッチ・タンク／レッツ・ゴイチゴ": 4,
            "超機動罠 デンジャデオン／地獄極楽トラップ黙示録": 4,
            "龍罠 エスカルデン／マクスカルゴ・トラップ": 4,
            "レレディ・バ・グーバ／ツインパクト・マップ": 4, "コンダマ／魂フエミドロ": 4},
        "super": {},
    },
    "青白コントロール": {   # AD・対アグロの受けデッキ(シャコガイルLO)。超次元/ホールは無い。
        # 正確なレシピ(ユーザー提供)。D2フィールドは実装済みだが、マッド・デッド・ウッドは
        # 闇火でこの光水ベースでは色が合わず召喚不能のため、貝獣パウアー(DB未収録)とまとめて
        # 奇石ミタラシオ(ST受けブロッカー)等で計6枚代替する。
        "main": {
            "エマージェンシー・タイフーン": 4, "終末の時計 ザ・クロック": 4,
            "サイバー・チューン": 4, "トライガード・チャージャー": 4,
            "音感の精霊龍 エメラルーダ": 4, "ノヴァルティ・アメイズ": 4,
            "悪魔神王ディス・バルカミラ": 1, "煌メク聖壁 灰瞳": 2,
            "閃光の守護者ホーリー": 2, "水上第九院 シャコガイル": 2,
            "「黒幕」": 2, "禁断機関 ViVy-R": 1,
            # 貝獣パウアー×2 + マッド・デッド・ウッド×4(計6) の代替(ST受け/ブロッカー)
            "奇石 ミタラシオ": 4, "蒼天の守護者ラ・ウラ・ギガ": 2},
        "super": {},
    },
    "水自然スコーラー": {
        "main": {
            "セイレーン・コンチェルト": 2, "ローラー雪だるま": 4, "シンクロ・スパイラル": 1,
            "豊潤フォージュン": 2, "超宮兵 マノミ": 4, "超宮城 コーラリアン": 3,
            "次元の嵐 スコーラー": 2, "禁断機関 ViVy-R": 2,
            "機術士ディール／「本日のラッキーナンバー！」": 2,
            "龍装者 ヴィヌフィース／究めし優美のブレイン": 4,
            "卍 ギ・ルーギリン 卍/卍獄ブレイン": 4,
            "イチゴッチ・タンク／レッツ・ゴイチゴ": 4,
            "レレディ・バ・グーバ／ツインパクト・マップ": 3, "ふでがき師匠／一筆奏上！": 3},
        "super": {},
    },
}


def decklist(deckname):
    """DECKS の定義を (メイン名リスト, 超次元名リスト) に展開(枚数分くり返す)。"""
    d = DECKS[deckname]
    main = [n for n, c in d["main"].items() for _ in range(c)]
    sup = [n for n, c in d.get("super", {}).items() for _ in range(c)]
    return main, sup


def _canon(s: str) -> str:
    """名前正規化: 卍記号のDB化け(【デ・スザーク】卍【／デ・スザーク】)・スラッシュ・空白を吸収。"""
    return (s.replace("【デ・スザーク】", "").replace("【／デ・スザーク】", "")
            .replace("／", "/").replace("　", " ").strip())


def resolve_name(pool, name):
    """名前の揺れ(全角／半角スラッシュ・卍化け・空白)を吸収して pool のキーに解決。"""
    if name in pool:
        return name
    for c in {name.replace("／", "/"), name.replace("/", "／")}:
        if c in pool:
            return c
    cn = _canon(name)
    for k in pool:                    # 化け文字等は正規化して一致を探す(必要時のみ)
        if _canon(k) == cn:
            return k
    return None


def validate_deck(pool, super_pool, main_names, super_names):
    """(欠けているメイン名, 欠けている超次元名, メイン枚数, 超次元枚数)。"""
    miss_main = sorted({n for n in main_names if resolve_name(pool, n) is None})
    miss_super = sorted({n for n in super_names
                         if resolve_name(super_pool, n) is None})
    return miss_main, miss_super, len(main_names), len(super_names)


def make_player(pool, super_pool, name, agent, main_names, super_names=()):
    p = Player(name, agent)
    main = [resolve_name(pool, n) for n in main_names]
    sup = [resolve_name(super_pool, n) for n in super_names]
    p.deck = carddb.build_deck(pool, p, [n for n in main if n])
    p.super_zone = carddb.build_super_zone(super_pool, p, [n for n in sup if n])
    return p


def play_match(pool, super_pool, deckA, deckB, games=20, seed0=1000,
               max_turns=120, pilot=None):
    """deckA/deckB = (main_names, super_names)。A視点の着席公平な勝率。

    pilot=工場(name, rng)->agent。既定は高速な heuristic_pilot。忠実評価には
    eval_pilot(ロールアウト)を渡す(コントロール/コンボの受け・連鎖を正しく回す)。"""
    pilot = pilot or heuristic_pilot
    s = 0.0
    for k in range(games):
        for swap in (0, 1):           # 先攻/後攻を入れ替えて着席公平に
            rng = random.Random(seed0 + k * 7 + swap)
            pa = make_player(pool, super_pool, "A", pilot("A", rng), *deckA)
            pb = make_player(pool, super_pool, "B", pilot("B", rng), *deckB)
            p0, p1 = (pa, pb) if swap == 0 else (pb, pa)
            w = Game(p0, p1, rng=rng)
            superdim.install_awaken_hook(w)
            winner = w.run(max_turns=max_turns)
            if winner is None:
                s += 0.5
            elif winner is pa:
                s += 1.0
    return s / (2 * games)

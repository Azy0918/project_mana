"""
duel_masters.superdim
=====================
「超次元ホール」呪文の本文(自然言語)から召喚条件を抽出し、CAST 効果として
カード骨格に差し込むレイヤー。

ホールは固定の召喚先を持たず、**自分の超次元ゾーンから条件(コスト/文明/種族/体数)
に合うサイキックを選んで出す**。よって必要なのは「どのサイキックを出すか」の対応表
ではなく、各ホール呪文の**召喚条件のパース**である(召喚先はデッキの8枚ゾーン側)。

本文例:
  「自分の超次元ゾーンからコスト7以下の水、火、または自然の、ハンター・サイキック・
    クリーチャー1枚をバトルゾーンに出す。」
  → max_cost=7, civs={水,火,自然}, races=(ハンター,), count=1
  「自分の超次元ゾーンから火のサイキック・クリーチャーを、コストの合計が8以下に
    なるように2枚まで選び、バトルゾーンに出す。」
  → civs={火}, total_cost=8, count=2

MVP の割り切り: 選択肢(▶)ホールは最初の召喚節のみ採用。覚醒/龍解・付随効果
(ドロー/除去等)は未実装(別途 effects.py)。
"""
from __future__ import annotations
import re

from .engine import (Ability, Static, CardDef, CAST, ON_ATTACK, ON_BATTLE_WIN,
                     ON_TURN_END, ON_LINK,
                     CREATURE, LIGHT, WATER, DARKNESS, FIRE, NATURE)

_CIV_CHARS = {"光", "水", "闇", "火", "自然"}
# 種族修飾の候補(サイキックに付きやすいもの)。本文から該当語を拾う。
_RACE_HINTS = ["ハンター", "エイリアン", "コマンド", "ドラゴン", "オラクル",
               "ヒーロー", "ゴッド", "ガイアール", "オリジン", "ロボ"]

# 召喚節の抽出: 「超次元ゾーンから … バトルゾーンに出す」までを1節とみなす。
# 選択肢(▶)ホールは複数節を持つので finditer で全節を拾い、最も強い節を採る。
_SUMMON_CLAUSE = re.compile(r"超次元ゾーンから(.+?)バトルゾーンに出す")


def _parse_clause(clause: str):
    """単一の召喚節 → spec。"""
    total_cost = None
    mt = re.search(r"コストの合計が(\d+)以下", clause)
    if mt:
        total_cost = int(mt.group(1))

    max_cost = 99
    mc = re.search(r"コスト(\d+)以下", clause)
    if mc:
        max_cost = int(mc.group(1))

    # 二系統コスト「コストAとコストBの…を1枚ずつ」= 2体・合計A+B・各≤max(A,B)
    md = re.search(r"コスト(\d+)とコスト(\d+)", clause)
    if md:
        a, b = int(md.group(1)), int(md.group(2))
        return {"max_cost": max(a, b), "count": 2, "total_cost": a + b,
                "civs": {c for c in _CIV_CHARS if c in clause} or None,
                "races": tuple(r for r in _RACE_HINTS if r in clause) or None}

    # 体数: 「2枚まで」「2体」「1枚」「1枚ずつ」/「好きな数」
    count = 1
    if "好きな数" in clause:
        count = 8
    else:
        mn = re.search(r"(\d+)\s*[枚体]", clause)
        if mn:
            count = int(mn.group(1))

    # total_cost のみ指定(max_cost 無し)なら、1体あたり上限を total_cost に寄せる
    if max_cost == 99 and total_cost is not None:
        max_cost = total_cost

    civs = {c for c in _CIV_CHARS if c in clause} or None
    races = tuple(r for r in _RACE_HINTS if r in clause) or None
    return {"max_cost": max_cost, "count": count, "total_cost": total_cost,
            "civs": civs, "races": races}


def _potency(spec):
    """節の『強さ』近似(選択型でどの節を採るかの比較用)。"""
    if spec["total_cost"] is not None:
        return spec["total_cost"] + spec["count"]
    return spec["max_cost"] * spec["count"]


def parse_hole(text: str):
    """ホール本文 → 召喚spec dict、非該当は None。
    選択肢ホールは全召喚節をパースし、最も強い節を採用する。

    spec = {max_cost, count, total_cost, civs(set|None), races(tuple|None)}
    """
    if not text or "超次元ゾーン" not in text or "バトルゾーンに出す" not in text:
        return None
    flat = text.replace("\n", " ")
    specs = [_parse_clause(m.group(1)) for m in _SUMMON_CLAUSE.finditer(flat)]
    if not specs:
        return None
    return max(specs, key=_potency)


# ---- 覚醒(サイキック → サイキック・スーパー)のリンク抽出 -------------------
# 覚醒後フォームのスタッツは公式Play's APIが独立レコードとして返さない(裏面・
# 詳細APIは403)。よって覚醒後の『名前』だけテキストから取れる。スタッツ/条件は
# 別ソース or 手入力前提。ここではリンク名の抽出と反転メカニズムまでを用意する。
_AWAKEN_LINK = re.compile(r"覚醒(?:リンク)?後[:：]\s*《([^》]+)》")


def parse_awaken_link(text: str):
    """本文から覚醒(リンク)後のカード名を取り出す。無ければ None。"""
    if not text:
        return None
    m = _AWAKEN_LINK.search(text)
    return m.group(1) if m else None


def build_awaken_links(super_pool) -> dict:
    """{サイキック名: 覚醒後名} を全サイキック骨格から構築。"""
    out = {}
    for name, cd in super_pool.items():
        tgt = parse_awaken_link(cd.text)
        if tgt:
            out[name] = tgt
    return out


# 覚醒の手書き登録: name -> (condition(game, card)->bool, awakened CardDef)
# 覚醒後スタッツは API から取れないので、実装するカードはここに手で定義する。
AWAKEN_REGISTRY = {}


def register_awaken(name, condition, awakened_def):
    AWAKEN_REGISTRY[name] = (condition, awakened_def)


def turn_end_awaken(game, player):
    """ターン終了フック: 登録済みサイキックの覚醒条件を満たせば反転させる。"""
    for c in list(player.battle):
        entry = AWAKEN_REGISTRY.get(c.name)
        if not entry:
            continue
        cond, awakened = entry
        if awakened is not None and cond(game, c):
            game.awaken(c, awakened)


def install_awaken_hook(game):
    """Game にターン終了の覚醒/リンク覚醒チェックを取り付ける。"""
    game.turn_end_hooks.append(turn_end_awaken)
    game.turn_end_hooks.append(turn_end_link)


# ---- 覚醒リンク(複数サイキック → 1体) -------------------------------------
# P'S覚醒リンク等: 指定の構成カードが揃うと1体のスーパーフォームに束ねる。
# linked_def(覚醒後スタッツ)は API から取れないので手入力(下記 _GAROWZ 参照)。
#   LINK_REGISTRY[key] = (component_names, linked_def, super_return_names, condition)
LINK_REGISTRY = {}


def register_link_awaken(component_names, linked_def, super_return_names=(),
                         condition=None, key=None):
    LINK_REGISTRY[key or linked_def.name] = (
        tuple(component_names), linked_def, tuple(super_return_names), condition)


def turn_end_link(game, player):
    for comps, linked_def, super_ret, cond in list(LINK_REGISTRY.values()):
        names_in_battle = {c.name for c in player.battle}
        if not all(n in names_in_battle for n in comps):
            continue
        if cond is not None and not cond(game, player):
            continue
        cards = []
        for n in comps:
            cards.append(next(c for c in player.battle if c.name == n))
        game.link_awaken(player, cards, linked_def, super_ret)


def _on_attack_bounce(n: int) -> Ability:
    def f(game, controller, source):
        opp = game.opponent(controller)
        targets = sorted(opp.battle, key=lambda c: -(c.power or 0))[:n]
        for t in list(targets):
            game.bounce(t)
    return Ability(ON_ATTACK, f, f"攻撃時:相手クリーチャー{n}体まで手札へ戻す")


def _on_attack_destroy_weaker() -> Ability:
    def f(game, controller, source):
        opp = game.opponent(controller)
        sp = source.power or 0
        for t in list(opp.battle):
            if (t.power or 0) < sp:
                game.destroy(t)
    return Ability(ON_ATTACK, f, "攻撃時:自身よりパワーの小さい相手を全破壊")


def _on_attack_mill_to(n: int) -> Ability:
    """攻撃時、相手の山札を n 枚残して墓地に置く(ライブラリアウト狙い)。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        moved = 0
        while len(opp.deck) > n:
            c = opp.deck.pop()
            c.zone = "graveyard"
            opp.graveyard.append(c)
            moved += 1
        game.log(f"    効果: 相手の山札を{moved}枚墓地へ(残り{len(opp.deck)})")
    return Ability(ON_ATTACK, f, f"攻撃時:相手山札を{n}枚残して墓地へ")


def _on_attack_draw(n: int) -> Ability:
    def f(game, controller, source):
        game.draw(controller, n)
    return Ability(ON_ATTACK, f, f"攻撃時:カードを{n}枚引く")


def _on_attack_debuff_all(amount: int) -> Ability:
    """攻撃時、相手全クリーチャーのパワーを-amount(0以下は状態起因で破壊)。"""
    def f(game, controller, source):
        opp = game.opponent(controller)
        for c in opp.battle:
            c._power_mod = getattr(c, "_power_mod", 0) - amount
        game.check_state_based()
    return Ability(ON_ATTACK, f, f"攻撃時:相手全体パワー-{amount}")


def _on_attack_recover_spells(n: int) -> Ability:
    def f(game, controller, source):
        spells = [c for c in controller.graveyard if c.ctype == "spell"][:n]
        for c in spells:
            controller.graveyard.remove(c)
            c.zone = "hand"
            controller.hand.append(c)
        if spells:
            game.log(f"    効果: 墓地から呪文{len(spells)}枚を手札へ")
    return Ability(ON_ATTACK, f, f"攻撃時:墓地の呪文を{n}枚まで回収")


_ON_ATTACK_FACTORY = {
    "bounce": lambda arg: _on_attack_bounce(arg or 2),
    "destroy_weaker": lambda arg: _on_attack_destroy_weaker(),
    "mill_to": lambda arg: _on_attack_mill_to(arg if arg is not None else 2),
    "draw": lambda arg: _on_attack_draw(arg or 1),
    "debuff_all": lambda arg: _on_attack_debuff_all(arg or 0),
    "recover_spells": lambda arg: _on_attack_recover_spells(arg or 1),
}


def _on_battle_win_untap(break_n: int = 0) -> Ability:
    def f(game, controller, source):
        source.tapped = False
        opp = game.opponent(controller)
        for _ in range(break_n):
            if opp.shields and source in controller.battle and not game.winner:
                game.break_shield(opp, controller)
    desc = "バトル勝利時:アンタップ" + (f"+{break_n}ブレイク" if break_n else "")
    return Ability(ON_BATTLE_WIN, f, desc)


# ---- 常在効果ファクトリ(覚醒後フォームの複雑能力用) ------------------------

def _st_power_race(race: str, amount: int) -> Static:
    """自分の『他の』指定種族クリーチャー全体に +amount パワー。"""
    def fn(game, src, target):
        if target is src or target.controller is not src.controller:
            return 0
        return amount if any(race in r for r in target.d.races) else 0
    return Static("power", fn, f"自分の他の{race}+{amount}")


def _st_grant_kw_race(race: str, kw: str) -> Static:
    """自分の指定種族クリーチャー全体に keyword を付与。"""
    def fn(game, src, target):
        if target.controller is not src.controller:
            return set()
        return {kw} if any(race in r for r in target.d.races) else set()
    return Static("keywords", fn, f"自分の{race}に{kw}付与")


def _st_no_free_play() -> Static:
    """相手のターン中、相手はコストを払わずクリーチャー/呪文を実行できない(踏み倒しメタ)。"""
    def fn(game, src, player, kind, card):
        if kind != "no_free_play" or player is src.controller:
            return False
        # 相手のターン中、または このクリーチャーの攻撃中
        return game.active() is player or game.attacking is src
    return Static("restrict", fn, "相手のターン中/自分の攻撃中、相手は踏み倒し不可")


def _st_enemy_psychic_cant_attack() -> Static:
    """相手のサイキック・クリーチャーは攻撃できない。"""
    def fn(game, src, player, kind, card):
        if kind != "cant_attack" or player is src.controller:
            return False
        return bool(card and card.d.psychic)
    return Static("restrict", fn, "相手のサイキックは攻撃不可")


def _st_force_block() -> Static:
    """このクリーチャーの攻撃時、相手は可能ならブロックしなければならない(強制ブロック)。"""
    def fn(game, src, player, kind, card):
        if kind != "must_block" or player is src.controller:
            return False
        return game.attacking is src
    return Static("restrict", fn, "攻撃時、相手は可能ならブロック強制")


def _st_untargetable() -> Static:
    """相手はこのクリーチャーを(効果の対象に)選べない。"""
    def fn(game, src, player, kind, card):
        if kind != "untargetable":
            return False
        return card is src and player is not src.controller
    return Static("restrict", fn, "相手はこのクリーチャーを選べない")


def _st_replace_leave_discard() -> Static:
    """離場する時、パワー>0かつ手札があれば最小コストを捨てて生存する(置換)。"""
    def fn(game, src, leaving):
        ctrl = src.controller
        if (game.power_of(src) or 0) > 0 and ctrl.hand:
            cheap = min(ctrl.hand, key=lambda c: c.cost)
            ctrl.hand.remove(cheap)
            cheap.zone = "graveyard"
            ctrl.graveyard.append(cheap)
            return True
        return False
    return Static("replace_leave", fn, "離場時、手札最小コストを捨てて生存(パワー>0)")


_STATIC_FACTORY = {
    "power_race": lambda *a: _st_power_race(a[0], a[1]),
    "grant_kw_race": lambda *a: _st_grant_kw_race(a[0], a[1]),
    "no_free_play": lambda *a: _st_no_free_play(),
    "enemy_psychic_cant_attack": lambda *a: _st_enemy_psychic_cant_attack(),
    "force_block": lambda *a: _st_force_block(),
    "untargetable": lambda *a: _st_untargetable(),
    "replace_leave_discard": lambda *a: _st_replace_leave_discard(),
}


def _on_link_deploy_hunters() -> Ability:
    """リンク時、自分の超次元ゾーンのハンター・サイキックをすべて召喚。"""
    def f(game, controller, source):
        hunters = [c for c in list(controller.super_zone)
                   if any("ハンター" in r for r in c.d.races)]
        for c in hunters:
            controller.super_zone.remove(c)
            game._enter_battle(controller, c, free=True)
        if hunters:
            game.log(f"    効果: 超次元から{len(hunters)}体のハンターを召喚")
    return Ability(ON_LINK, f, "リンク時:超次元ゾーンのハンターを全て召喚")


def _on_turn_end_untap_shield() -> Ability:
    """ターン終了時、自分のクリーチャーをアンタップし、ハンター数だけシールド追加。"""
    def f(game, controller, source):
        n = 0
        for c in controller.battle:
            c.tapped = False
            if any("ハンター" in r for r in c.d.races):
                n += 1
        for _ in range(n):
            if controller.deck:
                card = controller.deck.pop(0)
                card.zone = "shield"
                controller.shields.append(card)
        if n:
            game.log(f"    効果: 全アンタップ+シールド{n}枚追加")
    return Ability(ON_TURN_END, f, "ターン終了時:自分アンタップ+ハンター数シールド化")


_TRIGGER_FACTORY = {
    "deploy_hunters": _on_link_deploy_hunters,
    "untap_shield": _on_turn_end_untap_shield,
}

# 覚醒リンクの実データ表(kamigame デュエプレで確認・ユーザー提供)。
# 覚醒後スタッツは公式APIで取れないので、ここに1家系=1エントリで足していく。
# civs=文明集合、keywords=実効キーワード(ブレイカー等)、components が揃うとリンク、
# super_return=解除時に超次元ゾーンへ戻る構成カード(他はバトルに残る)。
# 複雑な能力(全体パワー修整/踏み倒しメタ/常時バフ等)は MVP 未実装で note に記す。
_LINK_DATA = [
    {
        "name": "死海竜ガロウズ・デビルドラゴン",
        "civs": {WATER, DARKNESS, FIRE}, "cost": 24, "power": 15000,
        "races": ("デビル・コマンド・ドラゴン", "エイリアン"),
        "keywords": ["t_breaker"],
        "components": ["ガロウズ・セブ・カイザー", "竜骨なる者ザビ・リゲル",
                       "ハイドラ・ギルザウルス"],
        "super_return": ["ガロウズ・セブ・カイザー"],
        "on_attack": ("bounce", 2),
        "statics": [("no_free_play",)],   # 相手のターン中、相手は踏み倒し不可
    },
    {
        "name": "激竜王ガイアール・オウドラゴン",
        "civs": {FIRE}, "cost": 24, "power": 25000,
        "races": ("キング・コマンド・ドラゴン", "ハンター"),
        "keywords": ["world_breaker"],
        "components": ["ガイアール・カイザー", "ブーストグレンオー",
                       "ドラゴニック・ピッピー"],
        "super_return": ["ガイアール・カイザー"],
        "on_attack": ("destroy_weaker", None),
    },
    {
        "name": "雲龍 ディス・イズ・大横綱",
        "civs": {DARKNESS, FIRE, NATURE}, "cost": 20, "power": 20000,
        "races": ("リキシ・コマンド・ドラゴン", "エイリアン"),
        "keywords": ["q_breaker"],
        "components": ["横綱 義留の富士", "小結 座美の花", "大関 地男の里"],
        "super_return": ["横綱 義留の富士"],
        "statics": [("power_race", "エイリアン", 5000),    # 他のエイリアン+5000
                    ("force_block",)],                      # 強制ブロック
        "on_battle_win": 0,                                  # バトル勝利時アンタップ
    },
    {
        "name": "唯我独尊ガイアール・オレドラゴン",
        "civs": {LIGHT, WATER, DARKNESS, FIRE, NATURE}, "cost": 30, "power": 26000,
        "races": ("レインボー・コマンド・ドラゴン", "ハンター"),
        "keywords": ["world_breaker", "speed_attacker", "hunting"],
        "components": ["勝利のプリンプリン", "勝利のガイアール・カイザー",
                       "勝利のリュウセイ・カイザー"],
        "super_return": ["勝利のガイアール・カイザー"],
        "on_battle_win": 2,                # バトル勝利時アンタップ+2ブレイク
    },
    {
        "name": "弩級合身！ジェット・カスケード・アタック",
        "civs": {LIGHT, WATER}, "cost": 24, "power": 17000,
        "races": ("リキッド・ピープル", "ハンター"),
        "keywords": ["t_breaker"],
        "components": ["アクア・ジェット＜BOOON・スカイ＞",
                       "アクア・アタック＜BAGOOON・パンツァー＞",
                       "アクア・カスケード＜ZABUUUN・クルーザー＞"],
        "super_return": ["アクア・カスケード＜ZABUUUN・クルーザー＞"],
        "on_attack": [("draw", 3), ("bounce", 3)],
        "note": "バウンスのコスト条件は簡略(3体まで)",
    },
    {
        "name": "バンカラ大親分 メンチ斬ルゾウ",
        "civs": {FIRE, NATURE}, "cost": 24, "power": 17000,
        "races": ("ビースト・コマンド", "ハンター"),
        "keywords": ["t_breaker"],
        "components": ["紅蓮の怒 鬼流院 刃", "魂の大番長「四つ牙」", "カチコミの哲"],
        "super_return": ["紅蓮の怒 鬼流院 刃"],
        "on_link": "deploy_hunters",       # リンク時、超次元のハンターを全召喚
        "note": "AD専用。マナからの展開は超次元ゾーン分のみに簡略。解除戻り先は推定",
    },
    {
        "name": "シャチホコ・GOLDEN・ドラゴン",
        "civs": {LIGHT, DARKNESS, FIRE}, "cost": 39, "power": 39000,
        "races": ("キング・コマンド・ドラゴン", "エイリアン"),
        "keywords": ["world_breaker"],
        "components": ["ホワイト・TENMTH・カイザー", "ブラック・WILLOW・カイザー",
                       "レッド・ABYTHEN・カイザー"],
        "super_return": ["レッド・ABYTHEN・カイザー"],
        "on_attack": [("recover_spells", 3), ("debuff_all", 9000)],
        "statics": [("untargetable",)],    # 相手はこのクリーチャーを選べない
    },
    {
        "name": "星龍王ガイアール・リュウセイドラゴン",
        "civs": {FIRE}, "cost": 20, "power": 17000,
        "races": ("キング・コマンド・ドラゴン", "ハンター"),
        "keywords": ["t_breaker"],
        "components": ["流星のフォーエバー・カイザー", "ウコン・ピッピー",
                       "サコン・ピッピー"],
        "super_return": ["流星のフォーエバー・カイザー"],
        "statics": [("grant_kw_race", "ハンター", "speed_attacker"),
                    ("enemy_psychic_cant_attack",)],
        "note": "攻撃時の追加サイキック召喚は未実装",
    },
    {
        "name": "豪遊！セイント・シャン・メリー",
        "civs": {LIGHT}, "cost": 39, "power": 19500,
        "races": ("シャイニング・コマンド・ドラゴン", "ハンター"),
        "keywords": ["q_breaker", "blocker"],
        "components": ["光器セイント・アヴェ・マリア", "光器シャンデリア",
                       "アルプスの使徒メリーアン"],
        "super_return": ["光器セイント・アヴェ・マリア"],
        "statics": [("replace_leave_discard",)],   # 離脱時、手札を捨てて生存
        "on_turn_end": "untap_shield",             # ターン終了時アンタップ+シールド化
    },
    {
        "name": "絶対絶命 ガロウズ・ゴクドラゴン",
        "civs": {LIGHT, WATER, DARKNESS, FIRE, NATURE}, "cost": 30, "power": 17000,
        "races": ("コマンド・ドラゴン", "エイリアン"),
        "keywords": ["t_breaker"],
        "components": ["激沸騰！オンセン・ガロウズ", "激天下！シャチホコ・カイザー",
                       "激相撲！ツッパリキシ"],
        "super_return": ["激沸騰！オンセン・ガロウズ"],
        "on_attack": ("mill_to", 2), "note": "攻撃時 相手山札を2枚残し墓地へ(LO)",
    },
]


def _norm_on_attack(spec):
    """on_attack は (tag,arg) でも [(tag,arg),...] でも受ける。"""
    if not spec:
        return []
    if isinstance(spec, tuple):
        spec = [spec]
    return list(spec)


def _build_linked_def(d) -> CardDef:
    abilities = []
    for tag, arg in _norm_on_attack(d.get("on_attack")):
        abilities.append(_ON_ATTACK_FACTORY[tag](arg))
    if d.get("on_battle_win") is not None:
        abilities.append(_on_battle_win_untap(d["on_battle_win"]))
    if d.get("on_link"):
        abilities.append(_TRIGGER_FACTORY[d["on_link"]]())
    if d.get("on_turn_end"):
        abilities.append(_TRIGGER_FACTORY[d["on_turn_end"]]())
    statics = tuple(_STATIC_FACTORY[s[0]](*s[1:]) for s in d.get("statics", []))
    return CardDef(
        cid="PS-" + d["name"], name=d["name"], cost=d["cost"],
        civs=frozenset(d["civs"]), ctype=CREATURE, power=d["power"],
        races=tuple(d["races"]), keywords=frozenset(d["keywords"]),
        abilities=tuple(abilities), statics=statics, psychic=True,
        text="/".join(d["keywords"]) + " / 覚醒リンク"
             + (f" / {d['note']}" if d.get("note") else ""))


def register_builtin_links():
    """実データ表 _LINK_DATA から覚醒リンクを一括登録する。"""
    LINK_REGISTRY.clear()
    for d in _LINK_DATA:
        register_link_awaken(
            component_names=tuple(d["components"]),
            linked_def=_build_linked_def(d),
            super_return_names=tuple(d["super_return"]),
            key=d["name"],
        )
    return list(LINK_REGISTRY)


def cast_summon_psychic(spec) -> Ability:
    """召喚spec を実行する CAST 能力。"""
    def fn(game, controller, source):
        game.summon_from_super_zone(
            controller,
            max_cost=spec["max_cost"], count=spec["count"],
            total_cost=spec["total_cost"], civs=spec["civs"],
            races=spec["races"])
    civ = "".join(sorted(spec["civs"])) if spec["civs"] else "無指定"
    desc = (f"超次元召喚(コスト{spec['max_cost']}以下/{civ}/"
            f"{spec['count']}体"
            + (f"/合計{spec['total_cost']}以下" if spec["total_cost"] else "") + ")")
    return Ability(CAST, fn, desc)


def attach_hole_abilities(pool) -> list:
    """pool(name->CardDef) の呪文のうちホールを検出し、召喚CAST能力を付与する。
    CardDef.text(DB本文)から召喚条件をパースする。

    戻り値: 付与できたホール呪文名のリスト。pool は dataclasses.replace で更新。
    """
    import dataclasses
    attached = []
    for name, cd in list(pool.items()):
        if cd.ctype != "spell":
            continue
        spec = parse_hole(cd.text)
        if spec is None:
            continue
        ability = cast_summon_psychic(spec)
        # 既存効果(除去等)は尊重しつつホール召喚を追加
        pool[name] = dataclasses.replace(cd, abilities=cd.abilities + (ability,))
        attached.append(name)
    return attached

"""
duel_masters.engine
===================
デュエル・マスターズ（デュエプレ準拠）のミニ・ルールエンジン。

設計思想:
- カードは「データ + イベントに反応する小さな能力(Ability)」の集合。
  エンジンが ON_SUMMON / ON_ATTACK / CAST / ON_DESTROYED ... を発火し、
  カード側がそれに反応する。新カードは cards.py に部品を足すだけで増える。
- bot/MCTS 用に「現在の意思決定 = Action のリスト」を front に出す。
  各フェーズで agent.decide(game, actions) を呼ぶ統一インターフェース。

実装範囲(MVP): マナ/文明支払い・召喚酔い・攻撃・シールドブレイク・
S・トリガー・ブロッカー・スピードアタッカー・バトル・勝利/デッキアウト判定。
未実装: 常在効果(パワー修整の永続)、複雑なタイミング解決、進化、タップ能力等。
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Callable, Optional, List

# ---- 文明 / カードタイプ / イベント名 ---------------------------------------

LIGHT, WATER, DARKNESS, FIRE, NATURE = "光", "水", "闇", "火", "自然"

CREATURE, SPELL = "creature", "spell"

# イベント名(能力の発火タイミング)
ON_SUMMON = "on_summon"        # クリーチャーがバトルゾーンに出たとき
CAST = "cast"                  # 呪文を唱えたときの本体効果
ON_ATTACK = "on_attack"        # 攻撃するとき
ON_DESTROYED = "on_destroyed"  # 破壊されたとき
ON_BATTLE_WIN = "on_battle_win"  # バトルに勝った(相手を破壊した)とき
ON_TURN_END = "on_turn_end"    # 自分のターン終了時
ON_LINK = "on_link"            # 覚醒リンクが成立したとき


# ---- カード定義 / カード実体 ------------------------------------------------

@dataclass(frozen=True)
class Ability:
    """カードに紐づく能力。event の瞬間に resolve(game, controller, source) が走る。"""
    event: str
    resolve: Callable
    desc: str = ""


@dataclass(frozen=True)
class Static:
    """常在/継続効果。バトルゾーンにある間だけ有効で、エンジンの問い合わせに参加する。
    kind ごとに fn のシグネチャが異なる:
      kind='keywords'     : fn(game, source, target_card) -> set[str]   付与するキーワード
      kind='cost'         : fn(game, source, player, card) -> int       コスト軽減量
      kind='loss_refusal' : fn(game, source, player)       -> bool      その瞬間 player は負けない
    source は常在効果を出している Card 自身。
    """
    kind: str
    fn: Callable
    desc: str = ""


@dataclass(frozen=True)
class CardDef:
    """カードの不変定義(全プレイヤーで共有してよい)。"""
    cid: str
    name: str
    cost: int
    civs: frozenset            # 必要文明の集合
    ctype: str                 # CREATURE / SPELL
    power: Optional[int] = None
    races: tuple = ()
    keywords: frozenset = frozenset()   # 'blocker','speed_attacker','shield_trigger'
    abilities: tuple = ()
    statics: tuple = ()                 # 常在効果(Static)。effects.py が DBスケルトンに差す
    psychic: bool = False               # サイキック等=超次元ゾーン所属。離場時ゾーンへ戻る
    text: str = ""                      # DB本文(効果の自動検出/ホール召喚条件パース用)
    twin_spell: object = None           # ツインパクトの呪文面(別 CardDef)。両面プレイ用


class Card:
    """ゲーム中のカード実体。zone と tapped 等の状態を持つ。"""
    _uid = 0

    def __init__(self, cdef: CardDef, owner: "Player"):
        self.d = cdef
        self.owner = owner
        self.controller = owner
        self.tapped = False
        self.summoning_sick = False
        self.zone = "deck"
        Card._uid += 1
        self.uid = Card._uid

    # 定義への薄いプロキシ
    @property
    def name(self): return self.d.name
    @property
    def cost(self): return self.d.cost
    @property
    def civs(self): return self.d.civs
    @property
    def ctype(self): return self.d.ctype
    @property
    def power(self): return self.d.power
    @property
    def keywords(self): return self.d.keywords

    def __repr__(self):
        return self.name


# ---- プレイヤー -------------------------------------------------------------

class Player:
    def __init__(self, name: str, agent):
        self.name = name
        self.agent = agent
        self.deck: List[Card] = []
        self.hand: List[Card] = []
        self.mana: List[Card] = []
        self.battle: List[Card] = []
        self.shields: List[Card] = []
        self.graveyard: List[Card] = []
        self.super_zone: List[Card] = []   # 超次元ゾーン(最大8)。山札とは別、シャッフル・ドロー対象外
        self.charged_this_turn = False
        self.spells_this_turn = 0          # このターンに唱えた呪文数(G・ゼロ判定用)
        self.no_spell_until = 0            # このターン番号未満は呪文を唱えられない(ロック)

    def __repr__(self):
        return self.name


# ---- 行動(意思決定の最小単位) ---------------------------------------------

@dataclass
class Action:
    kind: str                 # 'charge' | 'play' | 'attack' | 'pass'
    card: Optional[Card] = None
    target: object = None     # 攻撃先: 'player' または Card
    free: bool = False        # G・ゼロ等でコストを払わず召喚/詠唱する
    face: str = "creature"    # ツインパクトを 'creature' か 'spell' のどちらで使うか

    def __repr__(self):
        if self.kind == "pass":
            return "pass"
        if self.kind == "attack":
            tgt = "player" if self.target == "player" else f"{self.target}"
            return f"attack({self.card} -> {tgt})"
        return f"{self.kind}({self.card})"


# ---- ゲーム本体 ------------------------------------------------------------

class Game:
    def __init__(self, p0: Player, p1: Player, verbose: bool = False,
                 rng: Optional[random.Random] = None):
        self.players = [p0, p1]
        self.active_index = 0
        self.turn_count = 0
        self.winner: Optional[Player] = None
        self.verbose = verbose
        self.rng = rng or random.Random()
        self.log_lines: List[str] = []
        # ターン終了時に呼ぶフック群(覚醒チェック等)。fn(game, active_player)。
        self.turn_end_hooks: List[Callable] = []
        self.attacking: Optional[Card] = None   # 現在攻撃中のクリーチャー
        self.pending_extra_turn: Optional[Player] = None  # 追加ターン(スコーラー等)

    # --- ユーティリティ -----------------------------------------------------

    def active(self) -> Player:
        return self.players[self.active_index]

    def opponent(self, p: Player) -> Player:
        return self.players[1 - self.players.index(p)]

    def log(self, msg: str):
        self.log_lines.append(msg)
        if self.verbose:
            print(msg)

    # --- セットアップ -------------------------------------------------------

    def setup(self):
        for p in self.players:
            self.rng.shuffle(p.deck)
            for c in p.deck:
                c.zone = "deck"
            # シールド5枚
            for _ in range(5):
                c = p.deck.pop(0)
                c.zone = "shield"
                p.shields.append(c)
            # 初手5枚
            for _ in range(5):
                self._move_top_to_hand(p)
        self.log(f"--- 開始: {self.players[0]} vs {self.players[1]} ---")

    def _move_top_to_hand(self, p: Player):
        c = p.deck.pop(0)
        c.zone = "hand"
        p.hand.append(c)

    # --- ゾーン移動の基本操作 ----------------------------------------------

    def draw(self, p: Player, n: int = 1):
        for _ in range(n):
            if not p.deck:
                if self.loss_is_prevented(p):
                    self.log(f"{p} は敗北拒否で山札切れでも負けない")
                    return
                self.winner = self.opponent(p)
                self.log(f"{p} は山札切れで敗北")
                return
            self._move_top_to_hand(p)

    def mana_from_deck(self, p: Player, n: int = 1):
        """デッキトップをマナゾーンへ(マナ加速)。"""
        for _ in range(n):
            if not p.deck:
                return
            c = p.deck.pop(0)
            c.zone = "mana"
            c.tapped = False
            p.mana.append(c)
            self.log(f"  {p}: {c} をマナゾーンへ(加速)")

    def charge_mana(self, p: Player, card: Card):
        p.hand.remove(card)
        card.zone = "mana"
        card.tapped = False
        p.mana.append(card)
        p.charged_this_turn = True
        self.log(f"  {p}: {card} をチャージ")

    def _replace_leave(self, card: Card) -> bool:
        """離場の置換効果(Static kind='replace_leave')。True を返すと離場を肩代わり/防止。
        fn(game, source, leaving_card) -> bool。コスト支払い等は fn 内で行う。"""
        for st in card.d.statics:
            if st.kind == "replace_leave" and st.fn(self, card, card):
                self.log(f"  置換効果: {card} はバトルゾーンに残る")
                return True
        return False

    def destroy(self, card: Card):
        ctrl = card.controller
        if card in ctrl.battle:
            if self._replace_leave(card):       # 離脱時生存などの置換効果
                return
            ctrl.battle.remove(card)
            card.tapped = False
            self.log(f"  破壊: {card}")
            self.trigger(ON_DESTROYED, card)
            # 覚醒リンク中のフォームは『リンク解除』で各構成カードを所定の場所へ返す。
            comps = getattr(card, "_link_components", None)
            if comps:
                self._dissolve_link(card, comps)
                return
            # サイキック等は墓地に行かず超次元ゾーン(持ち主)へ戻る。
            if card.d.psychic:
                card.controller = card.owner
                card.zone = "super_zone"
                card.summoning_sick = False
                card.owner.super_zone.append(card)
                self.log(f"    {card} は超次元ゾーンに戻る")
            else:
                card.zone = "graveyard"
                ctrl.graveyard.append(card)

    # --- マナ支払い(文明マッチ) -------------------------------------------

    def _civ_match(self, untapped: List[Card], civs: List[str]):
        """必要文明ごとに別々のマナカードを割り当てられるか(バックトラック)。"""
        used = set()

        def bt(i):
            if i == len(civs):
                return []
            for m in untapped:
                if m.uid in used:
                    continue
                if civs[i] in m.civs:
                    used.add(m.uid)
                    rest = bt(i + 1)
                    if rest is not None:
                        return [m] + rest
                    used.discard(m.uid)
            return None

        return bt(0)

    def can_pay(self, p: Player, card: Card) -> bool:
        untapped = [m for m in p.mana if not m.tapped]
        if len(untapped) < self.cost_of(p, card):
            return False
        return self._civ_match(untapped, list(card.civs)) is not None

    def pay_cost(self, p: Player, card: Card):
        self._pay_cc(p, self.cost_of(p, card), card.civs)

    def _can_pay_cc(self, p: Player, cost: int, civs) -> bool:
        """コストと文明だけで支払可能か(ツインパクト呪文面など、Cardを介さない判定)。"""
        untapped = [m for m in p.mana if not m.tapped]
        if len(untapped) < cost:
            return False
        return self._civ_match(untapped, list(civs)) is not None

    def _pay_cc(self, p: Player, cost: int, civs):
        untapped = [m for m in p.mana if not m.tapped]
        assigned = self._civ_match(untapped, list(civs)) or []
        for m in assigned:
            m.tapped = True
        need = cost - len(assigned)
        for m in untapped:
            if need <= 0:
                break
            if not m.tapped:
                m.tapped = True
                need -= 1

    def can_pay_twin_spell(self, p: Player, card: Card) -> bool:
        ts = card.d.twin_spell
        return bool(ts) and self._can_pay_cc(p, ts.cost, ts.civs)

    def play_twin_spell(self, p: Player, card: Card, free: bool = False):
        """ツインパクトを呪文面として使う。"""
        ts = card.d.twin_spell
        if not free:
            self._pay_cc(p, ts.cost, ts.civs)
        if card in p.hand:
            p.hand.remove(card)
        elif card in p.shields:
            p.shields.remove(card)
        card.controller = p
        p.spells_this_turn += 1
        tag = " (S・トリガー)" if free else ""
        self.log(f"  {p}: 呪文(ツインパクト) {ts.name}{tag}")
        for ab in ts.abilities:
            if ab.event == CAST and self.winner is None:
                ab.resolve(self, p, card)
        card.zone = "graveyard"
        p.graveyard.append(card)

    # --- 常在効果の問い合わせ ----------------------------------------------

    def _all_battle_cards(self) -> List[Card]:
        return self.players[0].battle + self.players[1].battle

    def keywords_of(self, card: Card) -> set:
        """innate + 常在効果で付与された実効キーワード集合。"""
        kw = set(card.d.keywords)
        for src in self._all_battle_cards():
            for st in src.d.statics:
                if st.kind == "keywords":
                    kw |= st.fn(self, src, card)
        return kw

    def cost_of(self, p: Player, card: Card) -> int:
        """コスト軽減を反映した実効コスト。下限は文明数と1の大きい方。"""
        red = 0
        for src in self._all_battle_cards():
            for st in src.d.statics:
                if st.kind == "cost":
                    red += st.fn(self, src, p, card)
        return max(card.cost - red, max(1, len(card.civs)))

    def power_of(self, card: Card) -> Optional[int]:
        """常在(Static kind='power')＋一時(_power_mod)を反映した実効パワー。"""
        base = card.d.power
        if base is None:
            return None
        total = base
        for src in self._all_battle_cards():
            for st in src.d.statics:
                if st.kind == "power":
                    total += st.fn(self, src, card)
        return total + getattr(card, "_power_mod", 0)

    def is_restricted(self, player: Player, kind: str,
                      card: Optional[Card] = None) -> bool:
        """常在(Static kind='restrict')による制限の問い合わせ。
        fn(game, source, player, kind, card) -> bool が一つでも True なら制限。
        例: 'no_free_play'(踏み倒し禁止), 'cant_attack', 'untargetable'。"""
        for src in self._all_battle_cards():
            for st in src.d.statics:
                if st.kind == "restrict" and st.fn(self, src, player, kind, card):
                    return True
        return False

    def check_state_based(self):
        """状態起因処理: 実効パワー0以下のクリーチャーを破壊する(全体-9000等)。"""
        for p in self.players:
            for c in list(p.battle):
                pw = self.power_of(c)
                if pw is not None and pw <= 0:
                    self.log(f"  パワー0以下: {c}")
                    self.destroy(c)

    def break_count(self, card: Card) -> int:
        kw = self.keywords_of(card)
        if "world_breaker" in kw:            # ワールド・ブレイカー=全シールド
            return 99
        if "q_breaker" in kw:                # Q・ブレイカー=4枚
            return 4
        if "master_breaker" in kw:           # マスター(MVPは3枚扱い)
            return 3
        if "t_breaker" in kw:                # T・ブレイカー=3枚
            return 3
        if "w_breaker" in kw:
            return 2
        return 1

    def can_gzero(self, p: Player, card: Card) -> bool:
        """G・ゼロ: 条件(このターンの呪文数等)を満たせばコスト0で召喚できるか。
        カード自身の Static kind='g_zero' fn(game, source, player) -> bool で判定。"""
        if card.zone != "hand":
            return False
        for st in card.d.statics:
            if st.kind == "g_zero" and st.fn(self, card, p):
                return True
        return False

    def request_extra_turn(self, p: Player):
        """追加ターンを予約(スコーラー等。run() が消費する)。"""
        self.pending_extra_turn = p

    def loss_is_prevented(self, p: Player) -> bool:
        """p が今この瞬間、敗北拒否(常在効果)で負けないか。"""
        for src in p.battle:
            for st in src.d.statics:
                if st.kind == "loss_refusal" and st.fn(self, src, p):
                    return True
        return False

    # --- カードを使う -------------------------------------------------------

    def play(self, p: Player, card: Card):
        self.pay_cost(p, card)
        p.hand.remove(card)
        if card.ctype == CREATURE:
            self._enter_battle(p, card, free=False)
        else:
            self._resolve_spell(p, card)

    def _enter_battle(self, p: Player, card: Card, free: bool):
        card.controller = p
        card.zone = "battle"
        card.tapped = False
        card.summoning_sick = True   # 実効SAは legal_attacks 側で keywords_of により判定
        p.battle.append(card)
        tag = " (S・トリガー)" if free else ""
        self.log(f"  {p}: {card} を召喚{tag}")
        self.trigger(ON_SUMMON, card)

    def _resolve_spell(self, p: Player, card: Card, free: bool = False):
        card.controller = p
        p.spells_this_turn += 1            # G・ゼロ等の呪文カウント
        tag = " (S・トリガー)" if free else ""
        self.log(f"  {p}: 呪文 {card}{tag}")
        self.trigger(CAST, card)
        card.zone = "graveyard"
        p.graveyard.append(card)

    def play_free(self, p: Player, card: Card):
        """S・トリガー等でコストを払わず使用。"""
        if card.ctype == CREATURE:
            self._enter_battle(p, card, free=True)
        else:
            self._resolve_spell(p, card, free=True)

    # --- 超次元ゾーンからの召喚(ホール呪文の中核) --------------------------
    def summon_from_super_zone(self, p: Player, *, max_cost: int = 99,
                               count: int = 1, total_cost: Optional[int] = None,
                               civs: Optional[set] = None,
                               races: Optional[tuple] = None) -> List[Card]:
        """p の超次元ゾーンから条件に合うサイキックを最大 count 体、バトルゾーンへ。

        total_cost を指定すると「コストの合計が total_cost 以下」制約も課す。
        どれを出すかは価値(パワー+キーワード)で貪欲に選ぶ(ホールは基本『出せば得』)。
        """
        def matches(c: Card) -> bool:
            if c.cost > max_cost:
                return False
            if civs and not (set(c.civs) & set(civs)):
                return False
            if races and not any(any(r in cr for cr in c.d.races) for r in races):
                return False
            return True

        def value(c: Card) -> int:
            v = c.power or 0
            kw = self.keywords_of(c)
            v += 1500 * len(kw & {"blocker", "w_breaker", "speed_attacker"})
            return v

        summoned: List[Card] = []
        budget = total_cost
        for _ in range(count):
            pool = [c for c in p.super_zone
                    if c not in summoned and matches(c)
                    and (budget is None or c.cost <= budget)]
            if not pool:
                break
            pick = max(pool, key=value)
            summoned.append(pick)
            if budget is not None:
                budget -= pick.cost
        for c in summoned:
            p.super_zone.remove(c)
            self._enter_battle(p, c, free=True)
            self.log(f"    超次元ゾーンから {c} を召喚")
        return summoned

    def awaken(self, card: Card, awakened_def: CardDef):
        """サイキックを覚醒(裏返し)させる。実体(uid/zone/tapped/召喚酔い)は維持し、
        定義だけ覚醒後フォームに差し替える。覚醒後も psychic 扱い(離場で超次元へ)。"""
        old = card.name
        card.d = awakened_def
        self.log(f"  ★覚醒: {old} → {card.name} (P{card.power})")
        # 覚醒時の ON_SUMMON 相当は MVP では発火しない(覚醒後の常在は keywords_of 経由)。
        return card

    def link_awaken(self, player: Player, components: List[Card],
                    linked_def: CardDef, super_return_names: tuple = ()):
        """覚醒リンク: 複数のサイキック(components)を1体の linked_def に束ねる。
        構成カードはバトルから外し、離場時の戻り先(超次元/バトル)を記録しておく。"""
        for c in components:
            if c in player.battle:
                player.battle.remove(c)
        carrier = Card(linked_def, player)
        carrier.zone = "battle"
        carrier.summoning_sick = False     # 構成カードは既に場に居たので酔いなし
        carrier.tapped = False
        carrier._link_components = [
            (c, "super" if c.name in super_return_names else "battle")
            for c in components]
        player.battle.append(carrier)
        self.log(f"  ★覚醒リンク: {'+'.join(c.name for c in components)} "
                 f"→ {carrier.name} (P{carrier.power})")
        self.trigger(ON_LINK, carrier)        # リンク時能力(ハンター大量展開等)
        return carrier

    def _dissolve_link(self, carrier: Card, components):
        """リンク解除: 各構成カードを所定の場所(超次元ゾーン/バトルゾーン裏返し)へ返す。"""
        for comp, dest in components:
            comp.tapped = False
            comp.summoning_sick = False
            comp.controller = comp.owner
            if dest == "super":
                comp.zone = "super_zone"
                comp.owner.super_zone.append(comp)
            else:
                comp.zone = "battle"
                comp.owner.battle.append(comp)
        names = ", ".join(f"{c.name}->{d}" for c, d in components)
        self.log(f"    リンク解除: {names}")

    def bounce(self, card: Card):
        """クリーチャーを持ち主の手札へ戻す(サイキックは超次元ゾーンへ)。"""
        ctrl = card.controller
        if card in ctrl.battle:
            ctrl.battle.remove(card)
        card.tapped = False
        card.controller = card.owner
        if card.d.psychic:
            card.zone = "super_zone"
            card.owner.super_zone.append(card)
        else:
            card.zone = "hand"
            card.owner.hand.append(card)
        self.log(f"  バウンス: {card} を{'超次元ゾーン' if card.d.psychic else '手札'}へ")

    # --- イベント発火 -------------------------------------------------------

    def trigger(self, event: str, source: Card):
        for ab in source.d.abilities:
            if ab.event == event and self.winner is None:
                ab.resolve(self, source.controller, source)

    # --- 攻撃 ---------------------------------------------------------------

    def legal_attacks(self, p: Player) -> List[Action]:
        opp = self.opponent(p)
        out = []
        for c in p.battle:
            if c.tapped:
                continue
            if c.summoning_sick and "speed_attacker" not in self.keywords_of(c):
                continue
            if self.is_restricted(p, "cant_attack", c):   # 相手サイキック攻撃不可等
                continue
            out.append(Action("attack", c, "player"))
            kw = self.keywords_of(c)
            for t in opp.battle:
                # 通常はタップ済みのみ攻撃可。ハンティング持ちはアンタップにも攻撃可。
                if t.tapped or "hunting" in kw:
                    out.append(Action("attack", c, t))
        return out

    def resolve_attack(self, attacker: Card, target):
        attacker.tapped = True
        self.attacking = attacker            # 「このクリーチャーの攻撃中」判定用
        self.log(f"  {attacker.controller}: {attacker} が攻撃")
        self.trigger(ON_ATTACK, attacker)
        if self.winner is not None:
            self.attacking = None
            return
        defender = self.opponent(attacker.controller)

        # ブロッカー判定(防御側が任意で1体タップしてブロック)
        blockers = [c for c in defender.battle
                    if "blocker" in self.keywords_of(c) and not c.tapped]
        if blockers:
            # 強制ブロック(雲龍等): 可能ならブロックを省略できない。
            forced = self.is_restricted(defender, "must_block")
            b = defender.agent.choose_card(
                self, f"{attacker}(P{attacker.power}) をブロックする?",
                blockers, optional=not forced)
            if b is not None:
                b.tapped = True
                self.log(f"  {defender}: {b} でブロック")
                self.battle(attacker, b)
                return

        if target == "player":
            if defender.shields:
                # W・ブレイカー等は複数枚ブレイク(シールド枚数が上限)
                n = min(self.break_count(attacker), len(defender.shields))
                for _ in range(n):
                    if self.winner or attacker not in attacker.controller.battle:
                        break
                    self.break_shield(defender, attacker.controller)
            elif self.loss_is_prevented(defender):
                self.log(f"  {defender} は敗北拒否でダイレクトアタックを耐える")
            else:
                self.winner = attacker.controller
                self.log(f"  ★ ダイレクトアタック! {attacker.controller} の勝ち")
        else:
            self.battle(attacker, target)

    def battle(self, c1: Card, c2: Card):
        p1 = self.power_of(c1) or 0
        p2 = self.power_of(c2) or 0
        self.log(f"  バトル: {c1}(P{p1}) vs {c2}(P{p2})")
        if p1 > p2:
            self.destroy(c2)
            self.trigger(ON_BATTLE_WIN, c1)
        elif p2 > p1:
            self.destroy(c1)
            self.trigger(ON_BATTLE_WIN, c2)
        else:
            self.destroy(c1)
            self.destroy(c2)

    def break_shield(self, defender: Player, breaker: Player):
        # シールドは非公開情報なのでブレイク対象はランダムに選ぶ
        shield = self.rng.choice(defender.shields)
        defender.shields.remove(shield)
        self.log(f"  {breaker}: {defender} のシールドを1枚ブレイク "
                 f"(残り{len(defender.shields)})")
        ts = shield.d.twin_spell
        st_creature = "shield_trigger" in shield.keywords
        st_spell = bool(ts) and "shield_trigger" in ts.keywords
        if (st_creature or st_spell) and \
                not self.is_restricted(defender, "no_free_play"):
            use = defender.agent.choose_yes_no(
                self, f"S・トリガー {shield} を使う?")
            if use:
                self.log(f"  {defender}: S・トリガー発動 → {shield}")
                # トラップ等は呪文面のST。呪文面STがあれば呪文として撃つ。
                if st_spell:
                    self.play_twin_spell(defender, shield, free=True)
                else:
                    self.play_free(defender, shield)
                return
        shield.zone = "hand"
        defender.hand.append(shield)

    # --- ターン進行 ---------------------------------------------------------

    def play_turn(self):
        p = self.active()
        self.turn_count += 1
        self.log(f"\n[T{self.turn_count}] {p} のターン")

        # アンタップ / 召喚酔い解除
        for c in p.battle + p.mana:
            c.tapped = False
        for c in p.battle:
            c.summoning_sick = False
        p.charged_this_turn = False
        p.spells_this_turn = 0

        # ドロー(ゲーム最初のターンのみスキップ)
        if self.turn_count > 1:
            self.draw(p, 1)
            if self.winner:
                return

        # チャージ(任意・1回)
        acts = [Action("charge", c) for c in p.hand] + [Action("pass")]
        a = p.agent.decide(self, acts)
        if a.kind == "charge":
            self.charge_mana(p, a.card)

        # メイン(出せるだけ出す)。G・ゼロ条件を満たすカードは無料でも出せる。
        while self.winner is None:
            spell_ok = self.turn_count >= p.no_spell_until   # 呪文ロック(ジャミング・チャフ等)
            playable = [c for c in p.hand if self.can_pay(p, c)
                        and (spell_ok or c.ctype != SPELL)]
            free_cards = [c for c in p.hand
                          if c not in playable and self.can_gzero(p, c)]
            twin = [c for c in p.hand
                    if self.can_pay_twin_spell(p, c) and spell_ok]
            acts = ([Action("play", c) for c in playable]
                    + [Action("play", c, free=True) for c in free_cards]
                    + [Action("play", c, face="spell") for c in twin]
                    + [Action("pass")])
            a = p.agent.decide(self, acts)
            if a.kind == "pass":
                break
            if a.face == "spell":
                self.play_twin_spell(p, a.card)
            elif a.free:
                p.hand.remove(a.card)
                if a.card.ctype == CREATURE:
                    self._enter_battle(p, a.card, free=True)
                else:
                    self._resolve_spell(p, a.card, free=True)
            else:
                self.play(p, a.card)

        # 攻撃
        while self.winner is None:
            acts = self.legal_attacks(p) + [Action("pass")]
            a = p.agent.decide(self, acts)
            if a.kind == "pass":
                break
            self.resolve_attack(a.card, a.target)
        self.attacking = None

        # ターン終了処理(覚醒チェック等のフック → 各クリーチャーのターン終了能力)
        if self.winner is None:
            for hook in self.turn_end_hooks:
                hook(self, p)
        if self.winner is None:
            for c in list(p.battle):
                self.trigger(ON_TURN_END, c)
        # 一時パワー修整(全体-9000等)はターン終了で消える
        for c in self.players[0].battle + self.players[1].battle:
            if getattr(c, "_power_mod", 0):
                c._power_mod = 0

    def run(self, max_turns: int = 200) -> Optional[Player]:
        self.setup()
        while self.winner is None and self.turn_count < max_turns:
            self.play_turn()
            # 追加ターン(スコーラー等): 同じプレイヤーがもう一度。手番を入れ替えない。
            if self.pending_extra_turn is self.active() and self.winner is None:
                self.pending_extra_turn = None
                self.log(f"  ★追加ターン: {self.active()} がもう一度")
                continue
            self.pending_extra_turn = None
            self.active_index ^= 1
        return self.winner

    # --- 状態の複製(先読みパイロット用) -------------------------------------
    def clone(self) -> "Game":
        """ゲーム状態を複製する。CardDef は共有(不変)、Card/ゾーン/プレイヤーのみコピー。
        先読み(1手適用→評価)に使う。ログ無効・rngは新規。"""
        g = Game.__new__(Game)
        g.active_index = self.active_index
        g.turn_count = self.turn_count
        g.verbose = False
        g.rng = random.Random()
        g.log_lines = []
        g.turn_end_hooks = list(self.turn_end_hooks)
        g.attacking = None
        g.pending_extra_turn = None
        g.winner = None
        g.players = []

        cmap = {}

        def cc(card):
            c2 = cmap.get(card.uid)
            if c2 is not None:
                return c2
            c2 = Card.__new__(Card)
            c2.d = card.d
            c2.tapped = card.tapped
            c2.summoning_sick = card.summoning_sick
            c2.zone = card.zone
            c2.uid = card.uid
            c2._power_mod = getattr(card, "_power_mod", 0)
            cmap[card.uid] = c2
            return c2

        pmap = {}
        for p in self.players:
            p2 = Player.__new__(Player)
            p2.name = p.name
            p2.agent = p.agent
            p2.deck = [cc(c) for c in p.deck]
            p2.hand = [cc(c) for c in p.hand]
            p2.mana = [cc(c) for c in p.mana]
            p2.battle = [cc(c) for c in p.battle]
            p2.shields = [cc(c) for c in p.shields]
            p2.graveyard = [cc(c) for c in p.graveyard]
            p2.super_zone = [cc(c) for c in p.super_zone]
            p2.charged_this_turn = p.charged_this_turn
            p2.spells_this_turn = p.spells_this_turn
            p2.no_spell_until = p.no_spell_until
            p2._extra_turn_used = getattr(p, "_extra_turn_used", False)
            pmap[id(p)] = p2
            g.players.append(p2)

        allcards = []
        for p in self.players:
            allcards += (p.deck + p.hand + p.mana + p.battle + p.shields
                         + p.graveyard + p.super_zone)
        for card in allcards:
            c2 = cmap[card.uid]
            c2.owner = pmap[id(card.owner)]
            c2.controller = pmap[id(card.controller)]
            comps = getattr(card, "_link_components", None)
            if comps:
                new = []
                for comp, dest in comps:
                    comp2 = cc(comp)
                    comp2.owner = pmap[id(comp.owner)]
                    comp2.controller = pmap[id(comp.controller)]
                    new.append((comp2, dest))
                c2._link_components = new

        if self.winner is not None:
            g.winner = pmap[id(self.winner)]
        if self.pending_extra_turn is not None:
            g.pending_extra_turn = pmap[id(self.pending_extra_turn)]
        if self.attacking is not None:
            g.attacking = cmap.get(self.attacking.uid)
        return g

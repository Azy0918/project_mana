"""
duel_masters.agents
===================
パイロット(意思決定)の実装。デッキ評価の質はここの強さで頭打ちになるので、
ここを強くするほど GA は「良いデッキ」を正しく評価できる(MetaStone の知見:
進化デッキが人間最良デッキを超えたのは、AI が各デッキをまともに回せたから)。

 - RandomAgent    : 合法手から一様ランダム(下限ベースライン)
 - GreedyAgent    : 素朴(チャージ→重いの出す→顔殴り)。A/B比較の基準として温存。
 - HeuristicAgent : 盤面評価ヒューリスティック + 候補手スコアリング + リーサル/
                    ブロック判断。MetaStone のデフォルトAIと同型(状態複製の要らない
                    1手評価)。コンボ/敗北拒否/受けを過小評価しにくい。
"""

from __future__ import annotations
import random
import re
from .engine import Action


class RandomAgent:
    def __init__(self, name="Random", rng=None):
        self.name = name
        self.rng = rng or random.Random()

    def decide(self, game, actions):
        return self.rng.choice(actions)

    def choose_card(self, game, prompt, cards, optional=False):
        if optional and self.rng.random() < 0.5:
            return None
        return self.rng.choice(cards) if cards else None

    def choose_yes_no(self, game, prompt):
        return self.rng.random() < 0.5


class GreedyAgent:
    def __init__(self, name="Greedy", rng=None):
        self.name = name
        self.rng = rng or random.Random()

    def decide(self, game, actions):
        kinds = {a.kind for a in actions}

        # チャージ: 重いカードを優先して埋める(軽いカードを手札に残す)
        if "charge" in kinds:
            charges = [a for a in actions if a.kind == "charge"]
            charges.sort(key=lambda a: a.card.cost, reverse=True)
            return charges[0]

        # メイン: 出せる中で最もコストの高いクリーチャー → 加速呪文 →
        #         対象のある除去 → それ以外はパス(腐り防止)
        plays = [a for a in actions if a.kind == "play"]
        if plays:
            me = game.active()
            opp = game.opponent(me)
            creatures = [a for a in plays if a.card.ctype == "creature"]
            if creatures:
                creatures.sort(key=lambda a: a.card.cost, reverse=True)
                return creatures[0]
            # 呪文の取捨
            for a in sorted(plays, key=lambda a: a.card.cost, reverse=True):
                abil = [ab.desc for ab in a.card.d.abilities]
                is_removal = any("破壊" in d for d in abil)
                if is_removal and not opp.battle:
                    continue   # 対象なし除去は温存
                return a
            # 残りはパス
            return next(a for a in actions if a.kind == "pass")

        # 攻撃: とにかく顔(プレイヤー)を殴ってシールドを割る
        atks = [a for a in actions if a.kind == "attack"]
        if atks:
            face = [a for a in atks if a.target == "player"]
            return face[0] if face else atks[0]

        return next(a for a in actions if a.kind == "pass")

    def choose_card(self, game, prompt, cards, optional=False):
        # ブロッカー選択: 攻撃を受けて損しないときだけブロック
        if optional:
            me = game.active()  # 注意: choose_card は防御側だが簡易判定
            # 簡易: シールドが0なら必ずブロック、それ以外はブロックしない
            defender = None
            # 防御側を特定(cards はブロッカー候補=防御側のもの)
            if cards:
                defender = cards[0].controller
            if defender is not None and len(defender.shields) == 0:
                # パワー最大のブロッカーで受ける
                return max(cards, key=lambda c: c.power or 0)
            return None
        # 除去対象: 相手のパワー最大を狙う
        return max(cards, key=lambda c: c.power or 0)

    def choose_yes_no(self, game, prompt):
        return True   # S・トリガーは基本使う


# ---------------------------------------------------------------------------
# HeuristicAgent : 盤面評価 + 候補手スコアリング(MetaStone デフォルトAI同型)
# ---------------------------------------------------------------------------
# 設計: エンジンに clone() が無い(GAは全戦再生で評価する方針)ため、状態を複製
# する先読みはしない。代わりに各フェーズで「その瞬間に最善の1手」を、盤面の価値
# と各手の効果見積りでスコアリングして選ぶ。これだけでも素朴Greedyを大きく上回り、
# コンボ/敗北拒否/受け札を正しく評価できるようになる。

_KW_ATK = {"speed_attacker": 1200, "w_breaker": 1400, "master_breaker": 2600}
_KW_DEF = {"blocker": 1600, "shield_trigger": 300}


def _eff_kw(game, card):
    """常在効果込みの実効キーワード(盤面のカードのみ; 手札は innate で代用)。"""
    try:
        return game.keywords_of(card)
    except Exception:
        return set(card.d.keywords)


def _is_removal(card):
    return any("破壊" in ab.desc for ab in card.d.abilities)


class HeuristicAgent:
    def __init__(self, name="Heuristic", rng=None):
        self.name = name
        self.rng = rng or random.Random()

    # ---- 盤面評価(自分視点。高いほど良い) ------------------------------
    def _evaluate(self, game, me):
        opp = game.opponent(me)
        s = 0.0
        # シールド = 実質ライフ。最重要。
        s += 1800 * len(me.shields) - 1800 * len(opp.shields)
        # 盤面: パワー総和 + 体数(横の制圧力)
        s += sum((c.power or 0) for c in me.battle)
        s -= sum((c.power or 0) for c in opp.battle)
        s += 700 * (len(me.battle) - len(opp.battle))
        # 手札リソース
        s += 250 * (len(me.hand) - len(opp.hand))
        # 使えるマナ(展開力)
        s += 120 * len(me.mana)
        # 敗北拒否が自分で有効なら大きく加点(コンボの肝を過小評価しない)
        if game.loss_is_prevented(me):
            s += 6000
        if game.loss_is_prevented(opp):
            s -= 6000
        # ブロッカー(受けの価値)
        for c in me.battle:
            for k, v in _KW_DEF.items():
                if k in _eff_kw(game, c):
                    s += v * 0.5
        return s

    # ---- フェーズ振り分け ------------------------------------------------
    def decide(self, game, actions):
        kinds = {a.kind for a in actions}
        if "charge" in kinds:
            return self._decide_charge(game, actions)
        if "play" in kinds:
            return self._decide_main(game, actions)
        if "attack" in kinds:
            return self._decide_attack(game, actions)
        return next(a for a in actions if a.kind == "pass")

    # ---- チャージ: 文明被覆を保ったまま余剰/重いカードを埋める ----------
    def _decide_charge(self, game, actions):
        charges = [a for a in actions if a.kind == "charge"]
        if not charges:
            return next(a for a in actions if a.kind == "pass")
        me = game.active()
        hand = me.hand
        # 手札に1枚しかない文明は温存(その色が払えなくなるのを防ぐ)。
        civ_count = {}
        for c in hand:
            for civ in c.civs:
                civ_count[civ] = civ_count.get(civ, 0) + 1

        def charge_score(a):
            c = a.card
            uniq_civ = any(civ_count.get(civ, 0) <= 1 for civ in c.civs)
            dup = sum(1 for h in hand if h.name == c.name) >= 2
            # 重い・色が被っている・手札にダブりがある カードほどマナに置きたい。
            sc = c.cost
            if uniq_civ:
                sc -= 5      # 唯一の色源は手札に残す
            if dup:
                sc += 3
            # G・ゼロのフィニッシャーはマナに置かず手札に温存(コンボの核)。
            if any(st.kind == "g_zero" for st in c.d.statics):
                sc -= 100
            return sc

        return max(charges, key=charge_score)

    # ---- メイン: 各プレイをスコア化、最善を出す。価値が無ければパス ----
    def _gzero_reachable(self, game, me):
        """手札のG・ゼロ・フィニッシャーの条件に、今ターン唱えられる呪文数で届きそうか。"""
        thresholds = []
        for c in me.hand:
            for st in c.d.statics:
                if st.kind == "g_zero" and not game.can_gzero(me, c):
                    m = re.search(r"(\d+)", st.desc)
                    thresholds.append(int(m.group(1)) if m else 99)
        if not thresholds:
            return False
        castable = sum(1 for x in me.hand
                       if (x.ctype == "spell" and game.can_pay(me, x))
                       or game.can_pay_twin_spell(me, x))
        # ランプ呪文を撃てば追加で唱えられる見込みも少し見込む
        return me.spells_this_turn + castable >= min(thresholds)

    def _decide_main(self, game, actions):
        me = game.active()
        opp = game.opponent(me)
        plays = [a for a in actions if a.kind == "play"]
        if not plays:
            return next(a for a in actions if a.kind == "pass")

        opp_max_power = max((c.power or 0 for c in opp.battle), default=0)
        # コンボ計画(G・ゼロ): フィニッシャーが手札にある時、
        #  - 今ターン到達できる(combo) → 安い呪文を連打して数を稼ぐ
        #  - まだ到達できない(hold)    → 燃料呪文は温存し、ドロー/サーチだけ撃って掘る
        payoff = any(st.kind == "g_zero" and not game.can_gzero(me, c)
                     for c in me.hand for st in c.d.statics)
        combo = payoff and self._gzero_reachable(game, me)
        hold = payoff and not combo

        def _is_dig(a):
            abl = (a.card.d.twin_spell.abilities if a.face == "spell"
                   else a.card.d.abilities)
            return any(k in ab.desc for ab in abl
                       for k in ("引く", "回収", "手札に加え", "サーチ"))

        def play_score(a):
            c = a.card
            if a.free:                       # G・ゼロ等の無料召喚は最優先
                return 5000 + (c.power or 0)
            is_spell = a.face == "spell" or c.ctype == "spell"
            if combo and is_spell:           # 連打して呪文数を稼ぐ(安い順)
                cost = (c.d.twin_spell.cost if a.face == "spell" else c.cost)
                return 2500 - cost * 10
            if hold and is_spell and not _is_dig(a):
                return -500                  # 燃料呪文は温存(撃たない)
            if a.face == "spell":            # ツインパクトの呪文面
                ts = c.d.twin_spell
                rem = any(k in ab.desc for ab in ts.abilities
                          for k in ("破壊", "マナゾーンに置", "手札に戻"))
                if rem and opp.battle:
                    return 1100 + opp_max_power * 0.5
                return 700                   # サーチ/ランプ/ドロー等
            if c.ctype == "creature":
                sc = 1000 + (c.power or 0) * 0.5 + c.cost * 80
                for k, v in {**_KW_ATK, **_KW_DEF}.items():
                    if k in c.d.keywords:
                        sc += v
                # 敗北拒否クリーチャーは着地そのものに価値
                if any(st.kind == "loss_refusal" for st in c.d.statics):
                    sc += 4000
                return sc
            # 呪文
            if any("超次元召喚" in ab.desc for ab in c.d.abilities):
                return 1600 + c.cost * 30   # ホール=コスト踏み倒しでサイキック展開、高価値
            if _is_removal(c):
                if not opp.battle:
                    return -1000          # 対象なし除去は温存
                return 1200 + opp_max_power * 0.6
            # その他(加速/ドロー等)は中庸の価値。早く撃って盤面を作る。
            return 600 + c.cost * 30

        best = max(plays, key=play_score)
        if play_score(best) <= 0:
            return next(a for a in actions if a.kind == "pass")
        return best

    # ---- 攻撃: リーサル優先 → 有利な除去 → 顔。受けは温存判断 ----------
    def _decide_attack(self, game, actions):
        me = game.active()
        opp = game.opponent(me)
        attacks = [a for a in actions if a.kind == "attack"]
        if not attacks:
            return next(a for a in actions if a.kind == "pass")

        face = [a for a in attacks if a.target == "player"]
        vs_creature = [a for a in attacks if a.target != "player"]
        blockers = [c for c in opp.battle
                    if "blocker" in _eff_kw(game, c) and not c.tapped]

        # 1) リーサル: 相手シールド0・ブロッカーで止め切れない・敗北拒否なし
        if (len(opp.shields) == 0 and not game.loss_is_prevented(opp)
                and len(face) > len(blockers)):
            return max(face, key=lambda a: game.break_count(a.card))

        # 2) 有利な除去: タップ済みの脅威を一方的に討てるなら討つ
        #    (特に相手ブロッカー/高パワーを除去するとリーサルが近づく)
        good_kills = []
        for a in vs_creature:
            t = a.target
            if (a.card.power or 0) > (t.power or 0):   # 一方的に勝てる
                threat = (t.power or 0)
                if "blocker" in _eff_kw(game, t):
                    threat += 3000
                good_kills.append((threat, a))
        if good_kills:
            # 相手の盤面が薄く顔を詰めた方が良い局面では除去より顔を優先。
            # ただしブロッカー除去は常に価値が高いので優先。
            block_kill = [ga for ga in good_kills
                          if "blocker" in _eff_kw(game, ga[1].target)]
            if block_kill or len(opp.shields) >= 2:
                return max(good_kills, key=lambda x: x[0])[1]

        # 3) 受けの温存: 次ターン相手に殴り返されて危険なら、ブロッカーは1体残す
        hold = self._should_hold_blocker(game, me, opp)
        candidates = face if face else attacks
        if hold:
            kept = None
            usable = []
            for a in candidates:
                if "blocker" in _eff_kw(game, a.card) and kept is None:
                    kept = a       # 最初のブロッカーは攻撃に出さず温存
                    continue
                usable.append(a)
            candidates = usable or candidates  # 全部ブロッカーなら止む無し
        if not candidates:
            return next(a for a in actions if a.kind == "pass")
        # シールド圧を最大化(ブレイク数の多い攻撃を優先)
        return max(candidates, key=lambda a: game.break_count(a.card))

    def _should_hold_blocker(self, game, me, opp):
        """相手の次ターン打点が自分の受けを脅かすならブロッカーを残す。"""
        opp_attackers = [c for c in opp.battle]
        if not opp_attackers:
            return False
        my_defense = len(me.shields) + sum(
            1 for c in me.battle if "blocker" in _eff_kw(game, c))
        # 相手の体数が自分の受けを上回り、自分のシールドが薄い → 守りを残す
        return len(opp_attackers) >= my_defense and len(me.shields) <= 2

    # ---- ブロック判断: リーサル阻止 or 有利トレードのみ受ける ------------
    def choose_card(self, game, prompt, cards, optional=False):
        if optional:   # ブロッカー選択(防御側)
            if not cards:
                return None
            defender = cards[0].controller
            # シールド0でダイレクトの危険 → 必ず最大パワーで受ける
            if len(defender.shields) == 0:
                return max(cards, key=lambda c: c.power or 0)
            # 攻撃者を一方的に討てるブロッカーがいれば受けてトレード勝ち
            # (攻撃者のパワーはプロンプトから取れないので最大ブロッカーで判断)
            best = max(cards, key=lambda c: c.power or 0)
            # シールドに余裕があるうちは安易に受けない(受け札を温存)
            if len(defender.shields) <= 1:
                return best
            return None
        # 除去対象: 最大の脅威(パワー最大、ブロッカーは優先)を狙う
        return max(cards, key=lambda c: (c.power or 0)
                   + (3000 if "blocker" in _eff_kw(game, c) else 0))

    def choose_yes_no(self, game, prompt):
        return True   # S・トリガーは基本使う(無料の価値)


# ---------------------------------------------------------------------------
# LookaheadAgent : 1手先読み(clone→1手適用→盤面評価)でメインフェイズを選ぶ
# ---------------------------------------------------------------------------
# HeuristicAgent はヒューリスティックで手を選ぶが、効果の実結果を見ない(ホールの
# 召喚やコンボの組み立てを過小評価しがち)。LookaheadAgent は各プレイを clone 上で
# 実際に適用し、結果盤面を _evaluate して最善を選ぶ。効果を"実値"で評価できるので、
# 除去/ホール/展開などコントロール・設置系の手順が正しくなる。チャージ/攻撃/選択は
# HeuristicAgent の判断を流用。clone コストがあるので評価(GA)では重い点に注意。

class LookaheadAgent(HeuristicAgent):
    def __init__(self, name="Lookahead", rng=None):
        super().__init__(name, rng)

    def decide(self, game, actions):
        # メインフェイズのみ1手先読み。攻撃/受けは多ターンの読みが要る(1手評価は
        # 近視眼で『殴って即不利を見落とす』)ため HeuristicAgent の手順判断を流用。
        if any(a.kind == "play" for a in actions):
            return self._decide_main_lookahead(game, actions)
        return super().decide(game, actions)

    def _apply_play(self, g, p, card, action):
        if action.face == "spell":
            g.play_twin_spell(p, card)
        elif action.free:
            p.hand.remove(card)
            if card.ctype == "creature":
                g._enter_battle(p, card, free=True)
            else:
                g._resolve_spell(p, card, free=True)
        else:
            g.play(p, card)

    def _decide_main_lookahead(self, game, actions):
        me_idx = game.players.index(game.active())
        pass_act = next(a for a in actions if a.kind == "pass")
        # 基準: 今パスした場合の自盤面評価
        best_a, best_v = pass_act, self._evaluate(game, game.active())
        for a in actions:
            if a.kind != "play":
                continue
            g2 = game.clone()
            me2 = g2.players[me_idx]
            card2 = next((c for c in me2.hand if c.uid == a.card.uid), None)
            if card2 is None:
                continue
            try:
                self._apply_play(g2, me2, card2, a)
            except Exception:
                continue
            v = self._evaluate(g2, g2.players[me_idx])
            if g2.winner is g2.players[me_idx]:
                v += 1_000_000
            elif g2.winner is not None:
                v -= 1_000_000
            if v > best_v:
                best_v, best_a = v, a
        return best_a


# ---------------------------------------------------------------------------
# RolloutAgent : 攻撃判断を「数ターン先までプレイして勝率」で決める(フラットMC)
# ---------------------------------------------------------------------------
# 1手評価が苦手な攻撃/受けを、clone→候補手適用→自ターン終了→以降を高速方策で
# プレイアウトし、勝敗で評価する。「殴ると返り討ちか/受けを残すべきか」を実結果で
# 判断できる。メイン/チャージ/選択は HeuristicAgent を流用。clone+rollout で重い。

class RolloutAgent(HeuristicAgent):
    def __init__(self, name="Rollout", rng=None, rollouts=2, horizon=5):
        super().__init__(name, rng)
        self.rollouts = rollouts
        self.horizon = horizon

    def decide(self, game, actions):
        if any(a.kind == "attack" for a in actions):
            return self._decide_attack_rollout(game, actions)
        return super().decide(game, actions)

    def choose_card(self, game, prompt, cards, optional=False):
        # ブロック判断(防御側・任意)はロールアウトで評価。除去対象等は Heuristic 流用。
        if optional and cards and game.attacking is not None and "ブロック" in prompt:
            return self._rollout_block(game, cards)
        return super().choose_card(game, prompt, cards, optional)

    def _rollout_block(self, game, blockers):
        defender = blockers[0].controller
        def_idx = game.players.index(defender)
        atk_uid = game.attacking.uid
        tgt = game.attack_target
        tgt_uid = getattr(tgt, "uid", None)
        best_opt, best_v = None, None
        for opt in [None] + list(blockers):     # None = ブロックしない
            score = 0.0
            for _ in range(self.rollouts):
                g2 = game.clone()
                g2.players[0].agent = HeuristicAgent("r0")
                g2.players[1].agent = HeuristicAgent("r1")
                d2 = g2.players[def_idx]
                atk2 = next((c for c in g2.opponent(d2).battle
                             if c.uid == atk_uid), None)
                if atk2 is not None:
                    if opt is None:
                        t2 = "player" if tgt == "player" else next(
                            (c for c in d2.battle if c.uid == tgt_uid), "player")
                        g2._resolve_unblocked(atk2, t2, d2)
                    else:
                        b2 = next((c for c in d2.battle if c.uid == opt.uid), None)
                        if b2 is not None:
                            b2.tapped = True
                            g2.battle(atk2, b2)
                if g2.winner is None:           # 攻撃側の残りは近似で飛ばし防御側ターンへ
                    g2.active_index = def_idx
                    g2.skip_rest_of_turn = False
                    g2.play_out_turns(self.horizon)
                score += self._outcome(g2, def_idx)
            v = score / self.rollouts
            if best_v is None or v > best_v:
                best_v, best_opt = v, opt
        return best_opt

    def _outcome(self, g, me_idx):
        me = g.players[me_idx]
        if g.winner is me:
            return 1.0
        if g.winner is None:
            tie = max(-0.49, min(0.49, self._evaluate(g, me) / 100000.0))
            return 0.5 + tie
        return 0.0

    def _decide_attack_rollout(self, game, actions):
        me_idx = game.players.index(game.active())
        pass_act = next(a for a in actions if a.kind == "pass")
        best_a, best_v = pass_act, None
        for a in actions:
            score = 0.0
            for _ in range(self.rollouts):
                g2 = game.clone()
                g2.players[0].agent = HeuristicAgent("r0")   # 高速方策(再帰防止)
                g2.players[1].agent = HeuristicAgent("r1")
                me2 = g2.players[me_idx]
                if a.kind == "attack":
                    atk2 = next((c for c in me2.battle if c.uid == a.card.uid), None)
                    if atk2 is None:
                        score += 0.5
                        continue
                    if a.target == "player":
                        tgt2 = "player"
                    else:
                        tgt2 = next((c for c in g2.opponent(me2).battle
                                     if c.uid == a.target.uid), None)
                        if tgt2 is None:
                            score += 0.5
                            continue
                    try:
                        g2.resolve_attack(atk2, tgt2)
                    except Exception:
                        score += 0.5
                        continue
                if g2.winner is None:        # 自ターン終了→以降をプレイアウト
                    g2.active_index ^= 1
                    g2.play_out_turns(self.horizon)
                score += self._outcome(g2, me_idx)
            v = score / self.rollouts
            if best_v is None or v > best_v:
                best_v, best_a = v, a
        return best_a

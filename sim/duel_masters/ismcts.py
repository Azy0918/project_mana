"""
duel_masters.ismcts
===================
情報集合モンテカルロ木探索(Single-Observer ISMCTS)パイロット。

flat な RolloutAgent は各候補手を独立に少数ロールアウトして評価するだけで、
手順(プレイ列)を木として共有しない=コンボの深い線やカーブの最適化を取りこぼす。
ISMCTSAgent は操縦プレイヤーの**メイン＋攻撃フェイズの意思決定列**にUCT木を張り、
反復ごとに隠匿情報を決定化(determinize)してプレイアウトし、勝敗を経路に逆伝播する。

設計(本エンジンの制約に合わせた実用 SO-ISMCTS):
- 木のノード = 操縦プレイヤーの行動列(自ターン＋探索深度内の将来ターン)に対応。
  決定化のたびに引きが変わるため、ノードは**カード名ベースの行動シグネチャ**で辿り、
  ISMCTS の**可用性カウント(avail)付きUCB**で選択する(隠匿情報で手の集合が変動しても
  公平に評価できる)。
- 1反復 = clone→決定化→木方策(UCB選択＋1ノード展開)で me を駆動、相手は
  HeuristicAgent、葉(frontier)以降はロールアウト方策で終局までプレイアウト→逆伝播。
- 反応窓(ブロック/ST/対象選択)は反復内では高速ヒューリスティック(ネストした
  ロールアウトを避ける)。**実ゲームのブロック判断は親 RolloutAgent の強力なブロック・
  ロールアウトを継承**(コントロールの防御レバーを温存)。
- 速度が本質的に重いので最終評価専用。GA は引き続き高速 HeuristicAgent。
"""
from __future__ import annotations
import math
import random

from .agents import HeuristicAgent, RolloutAgent


# ---- 行動シグネチャ(決定化間で安定なノードキー) ---------------------------
def _sig(action):
    """行動を決定化間で安定なキーに。カードは名前で識別(uidは決定化で変わるため)。"""
    if action.kind == "pass":
        return ("pass",)
    if action.kind == "charge":
        return ("charge", action.card.d.name)
    if action.kind == "attack":
        tgt = "player" if action.target == "player" else ("c:" + action.target.d.name)
        return ("attack", action.card.d.name, tgt)
    if action.kind == "play":
        return ("play", action.card.d.name, action.face, bool(action.free))
    return (action.kind,)


class Node:
    """ISMCTS の木ノード。visits/reward は逆伝播で、avail は選択時に更新。"""
    __slots__ = ("visits", "reward", "avail", "children")

    def __init__(self):
        self.visits = 0
        self.reward = 0.0
        self.avail = 0
        self.children = {}     # sig -> Node


# ---- 木方策エージェント(1反復で me の決定を駆動) ---------------------------
class _TreePlayoutAgent:
    """1反復のあいだ、me の各意思決定を『木の降下/展開→以降ロールアウト』で行う。
    charge と反応窓(ブロック/ST/対象)は高速方策に委譲。path に通過ノードを溜め、
    呼び出し側が逆伝播する。"""

    def __init__(self, root, rollout_policy, max_depth, rng, c):
        self.name = "tree"
        self.root = root
        self.rollout_policy = rollout_policy
        self.max_depth = max_depth
        self.rng = rng
        self.c = c
        # per-iteration 状態
        self.current = root
        self.path = []
        self.in_rollout = False
        self.depth = 0

    # me のメイン/攻撃決定だけ木で選ぶ。それ以外は高速方策。
    def decide(self, game, actions):
        kinds = {a.kind for a in actions}
        if "charge" in kinds:
            return self.rollout_policy.decide(game, actions)
        if not any(k in kinds for k in ("play", "attack")):
            return next(a for a in actions if a.kind == "pass")
        if self.in_rollout:
            return self.rollout_policy.decide(game, actions)
        return self._tree_decide(game, actions)

    def _ucb(self, child):
        if child.visits == 0:
            return float("inf")
        exploit = child.reward / child.visits
        explore = self.c * math.sqrt(math.log(max(1, child.avail)) / child.visits)
        return exploit + explore

    def _tree_decide(self, game, actions):
        node = self.current
        expanded, unexpanded = [], []
        for a in actions:
            sg = _sig(a)
            ch = node.children.get(sg)
            if ch is None:
                unexpanded.append((sg, a))
            else:
                ch.avail += 1
                expanded.append((a, ch))
        if unexpanded:
            sg, a = self.rng.choice(unexpanded)   # 1ノード展開
            child = Node()
            child.avail = 1
            node.children[sg] = child
            self.path.append(child)
            self.current = child
            self.in_rollout = True                # 展開後は以降ロールアウト
            self.depth += 1
            return a
        a, ch = max(expanded, key=lambda x: self._ucb(x[1]))   # UCB選択で降下
        self.path.append(ch)
        self.current = ch
        self.depth += 1
        if self.depth >= self.max_depth:
            self.in_rollout = True
        return a

    # 反応窓は高速方策(ネストしたロールアウトを避ける)
    def choose_card(self, game, prompt, cards, optional=False):
        return self.rollout_policy.choose_card(game, prompt, cards, optional)

    def choose_yes_no(self, game, prompt):
        return self.rollout_policy.choose_yes_no(game, prompt)


# ---- ISMCTS パイロット本体 --------------------------------------------------
class ISMCTSAgent(RolloutAgent):
    """メイン/攻撃の意思決定列を ISMCTS で探索する評価パイロット。
    ブロック判断は親 RolloutAgent のロールアウトを継承(強い防御を温存)。"""

    def __init__(self, name="ISMCTS", rng=None, iterations=120, horizon=8,
                 max_depth=12, c=0.7, determinize=False, determinize_shields=False):
        super().__init__(name, rng, rollouts=1, horizon=horizon,
                         determinize=determinize,
                         determinize_shields=determinize_shields)
        self.iterations = iterations
        self.max_depth = max_depth
        self.c = c

    def decide(self, game, actions):
        kinds = {a.kind for a in actions}
        if "charge" in kinds:                       # チャージは軽いので高速方策
            return HeuristicAgent.decide(self, game, actions)
        if not any(k in kinds for k in ("play", "attack")):
            return next(a for a in actions if a.kind == "pass")
        return self._ismcts(game, actions)

    def _resume(self, g2, me2, phase):
        """決定点(main/attack)からターンの残り＋以降を回す。tree agent が me を駆動。"""
        if phase == "main" and g2.winner is None and not g2.skip_rest_of_turn:
            g2._main_phase(me2)
        if g2.winner is None and not g2.skip_rest_of_turn:
            g2._attack_phase(me2)
        if g2.winner is None:
            g2._end_phase(me2)
        if g2.winner is None:
            if g2.pending_extra_turn is me2:        # 追加ターンは同プレイヤー続行
                g2.pending_extra_turn = None
            else:
                g2.pending_extra_turn = None
                g2.active_index ^= 1
            g2.play_out_turns(self.horizon)

    def _ismcts(self, game, actions):
        me_idx = game.players.index(game.active())
        phase = "main" if any(a.kind == "play" for a in actions) else "attack"
        root = Node()
        for _ in range(self.iterations):
            g2 = game.clone()
            if self.determinize:
                g2.determinize(g2.players[me_idx], shields=self.determinize_shields)
            me2 = g2.players[me_idx]
            opp2 = g2.opponent(me2)
            rollout_pol = HeuristicAgent("ro", force_combo=True)
            agent = _TreePlayoutAgent(root, rollout_pol, self.max_depth,
                                      self.rng, self.c)
            me2.agent = agent
            opp2.agent = HeuristicAgent("op", force_combo=True)
            try:
                self._resume(g2, me2, phase)
            except Exception:
                pass
            reward = self._outcome(g2, me_idx)
            for node in agent.path:
                node.visits += 1
                node.reward += reward
        if not root.children:                       # 探索不能→高速方策
            return HeuristicAgent.decide(self, game, actions)
        best_sig = max(root.children, key=lambda s: root.children[s].visits)
        for a in actions:                           # 最多訪問の根行動を実行
            if _sig(a) == best_sig:
                return a
        return HeuristicAgent.decide(self, game, actions)

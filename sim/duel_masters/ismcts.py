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
- **反応窓(ブロック/S・トリガー/対象選択)も木に載せる=完全木探索**。反復内のプレイアウト中、
  me の将来の防御・トリガー使用・対象選択まで木で計画するので、メイン/攻撃の評価が「自分は
  後で最適に受ける」前提で正しくなる。葉(frontier)以降は高速方策。
- **実ゲームの単発ブロック判断も ISMCTS で探索**(`_ismcts_block`, block_iterations)。相手の
  攻撃時、ブロック決定を根に clone→決定化→選択適用→相手の残り攻撃(防御側=木が以降のブロックも
  判断)→防御側ターン→プレイアウトし、勝率最大の選択を返す。=操縦プレイヤーの全意思決定
  (プレイ・攻撃・ブロック・トリガー・対象)が木探索になる完全なISMCTS。
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


def _block_sig(prompt, opt):
    """ブロック選択のノードキー(木方策と実ゲームのブロック探索で共有し一致させる)。"""
    return ("block", "none") if opt is None else ("block", prompt[:10], opt.d.name)


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

    def __init__(self, root, rollout_policy, max_depth, rng, c,
                 reactions_in_tree=True):
        self.name = "tree"
        self.root = root
        self.rollout_policy = rollout_policy
        self.max_depth = max_depth
        self.rng = rng
        self.c = c
        # reactions_in_tree=False で反応窓(ブロック/ST/対象)を木に載せず高速方策に回す
        # (=旧挙動)。A/B比較・予算が薄い時用。
        self.reactions_in_tree = reactions_in_tree
        # per-iteration 状態
        self.current = root
        self.path = []
        self.in_rollout = False
        self.depth = 0

    # me のメイン/攻撃決定を木で選ぶ。それ以外(charge/pass)は高速方策。
    def decide(self, game, actions):
        kinds = {a.kind for a in actions}
        if "charge" in kinds:
            return self.rollout_policy.decide(game, actions)
        if not any(k in kinds for k in ("play", "attack")):
            return next(a for a in actions if a.kind == "pass")
        if self.in_rollout:
            return self.rollout_policy.decide(game, actions)
        return self._tree_choose([(_sig(a), a) for a in actions])

    def _ucb(self, child):
        if child.visits == 0:
            return float("inf")
        exploit = child.reward / child.visits
        explore = self.c * math.sqrt(math.log(max(1, child.avail)) / child.visits)
        return exploit + explore

    def _tree_choose(self, pairs):
        """pairs=[(sig, option), ...]。木の選択/展開で1つ選び option を返す(汎用)。
        decide/choose_card/choose_yes_no が共通でこれを通り、反応窓も木に載る。"""
        node = self.current
        expanded, unexpanded = [], []
        for sg, opt in pairs:
            ch = node.children.get(sg)
            if ch is None:
                unexpanded.append((sg, opt))
            else:
                ch.avail += 1
                expanded.append((opt, ch))
        if unexpanded:
            sg, opt = self.rng.choice(unexpanded)   # 1ノード展開
            child = Node()
            child.avail = 1
            node.children[sg] = child
            self.path.append(child)
            self.current = child
            self.in_rollout = True                  # 展開後は以降ロールアウト
            self.depth += 1
            return opt
        opt, ch = max(expanded, key=lambda x: self._ucb(x[1]))   # UCB選択で降下
        self.path.append(ch)
        self.current = ch
        self.depth += 1
        if self.depth >= self.max_depth:
            self.in_rollout = True
        return opt

    # 反応窓(ブロック/対象選択)も木に載せる=完全木探索。葉以降は高速方策。
    def choose_card(self, game, prompt, cards, optional=False):
        if self.in_rollout or not cards or not self.reactions_in_tree:
            return self.rollout_policy.choose_card(game, prompt, cards, optional)
        is_block = "ブロック" in prompt
        opts = ([None] if optional else []) + list(cards)
        pairs = []
        for o in opts:
            if is_block:
                sg = _block_sig(prompt, o)
            else:
                sg = ("choose", "none") if o is None else ("choose", prompt[:10], o.d.name)
            pairs.append((sg, o))
        return self._tree_choose(pairs)

    def choose_yes_no(self, game, prompt):
        if self.in_rollout or not self.reactions_in_tree:
            return self.rollout_policy.choose_yes_no(game, prompt)
        pairs = [(("yn", prompt[:14], True), True),
                 (("yn", prompt[:14], False), False)]
        return self._tree_choose(pairs)


# ---- ISMCTS パイロット本体 --------------------------------------------------
class ISMCTSAgent(RolloutAgent):
    """メイン/攻撃の意思決定列を ISMCTS で探索する評価パイロット。
    ブロック判断は親 RolloutAgent のロールアウトを継承(強い防御を温存)。"""

    def __init__(self, name="ISMCTS", rng=None, iterations=120, horizon=8,
                 max_depth=12, c=0.7, determinize=False, determinize_shields=False,
                 reactions_in_tree=True, block_iterations=40):
        super().__init__(name, rng, rollouts=1, horizon=horizon,
                         determinize=determinize,
                         determinize_shields=determinize_shields)
        self.iterations = iterations
        self.max_depth = max_depth
        self.c = c
        self.reactions_in_tree = reactions_in_tree
        # 実ゲームの単発ブロック判断も ISMCTS で探索する(根=ブロック決定)。頻発するので
        # メインより少なめの反復に。0 で親 RolloutAgent のフラットMCブロックに委譲。
        self.block_iterations = block_iterations

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
                                      self.rng, self.c,
                                      reactions_in_tree=self.reactions_in_tree)
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

    # ---- 実ゲームの単発ブロック判断も ISMCTS で探索(根=ブロック決定) ----------
    def choose_card(self, game, prompt, cards, optional=False):
        if (self.block_iterations > 0 and optional and cards
                and game.attacking is not None and "ブロック" in prompt):
            return self._ismcts_block(game, prompt, cards)
        return HeuristicAgent.choose_card(self, game, prompt, cards, optional)

    def _ismcts_block(self, game, prompt, blockers):
        """ブロック決定を根に ISMCTS。選択肢=ノーブロック/各ブロッカー。各反復で
        その選択を適用→相手の残り攻撃(防御側=木agentが以降のブロックも木で判断)→
        防御側ターン→以降をプレイアウトし、勝率の高い選択を返す。"""
        defender = blockers[0].controller
        def_idx = game.players.index(defender)
        atk_uid = game.attacking.uid
        tgt = game.attack_target
        tgt_uid = getattr(tgt, "uid", None)
        root = Node()
        for _ in range(self.block_iterations):
            g2 = game.clone()
            if self.determinize:
                g2.determinize(g2.players[def_idx], shields=self.determinize_shields)
            d2 = g2.players[def_idx]
            opp2 = g2.opponent(d2)
            atk2 = next((c for c in opp2.battle if c.uid == atk_uid), None)
            rollout_pol = HeuristicAgent("ro", force_combo=True)
            agent = _TreePlayoutAgent(root, rollout_pol, self.max_depth,
                                      self.rng, self.c,
                                      reactions_in_tree=self.reactions_in_tree)
            d2.agent = agent
            opp2.agent = HeuristicAgent("op", force_combo=True)
            # 根=このブロック決定(木に問う)。木のブロッカー候補は d2 側の実体に対応付け。
            blk2 = [c for c in d2.battle if c.uid in {b.uid for b in blockers}]
            choice = agent.choose_card(g2, prompt, blk2, optional=True)
            if atk2 is not None:
                if choice is None:
                    t2 = "player" if tgt == "player" else next(
                        (c for c in d2.battle if c.uid == tgt_uid), "player")
                    g2._resolve_unblocked(atk2, t2, d2)
                else:
                    choice.tapped = True
                    g2.battle(atk2, choice)
            # 相手の残り攻撃を続行(防御側=木agentが以降のブロックも木で判断)
            if g2.winner is None:
                g2._attack_phase(opp2)
            if g2.winner is None:
                g2._end_phase(opp2)
            if g2.winner is None:                   # 防御側のターンへ
                g2.active_index = def_idx
                g2.skip_rest_of_turn = False
                g2.play_out_turns(self.horizon)
            reward = self._outcome(g2, def_idx)
            for node in agent.path:
                node.visits += 1
                node.reward += reward
        if not root.children:                       # 探索不能→ロールアウトブロックに委譲
            return self._rollout_block(game, blockers)
        best_sig = max(root.children, key=lambda s: root.children[s].visits)
        if best_sig == _block_sig(prompt, None):
            return None
        for b in blockers:                          # 最多訪問の根ブロック選択を実行
            if _block_sig(prompt, b) == best_sig:
                return b
        return None

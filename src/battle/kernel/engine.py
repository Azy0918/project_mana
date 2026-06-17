from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.effect_executor import EffectExecutor
from src.battle.kernel.policy import AttackChoice, Policy
from src.battle.kernel.state import CreatureInstance, GameState, ManaCard, PlayerState, make_mana_card

OPENING_HAND = 5
SHIELD_COUNT = 5
DEFAULT_MAX_TURNS = 30


def select_mana_payment(
    mana_zone: list[ManaCard],
    card: BattleCard,
    cost: int | None = None,
) -> list[ManaCard] | None:
    """コストと文明拘束を満たすアンタップマナの組み合わせを返す。支払えなければNone。

    文明ごとに最低1枚の一致マナをタップする必要がある(多色カードは全文明ぶん)。
    cost指定時はカード印刷コストの代わりにその値で支払う(軽減・G・ゼロ用)。
    """
    required = card.cost if cost is None else cost
    untapped = [mana for mana in mana_zone if not mana.tapped]
    if required <= 0:
        return []
    if len(untapped) < required:
        return None

    payment: list[ManaCard] = []
    remaining = untapped[:]
    for civilization in card.civilizations:
        match = next(
            (mana for mana in remaining if civilization in mana.card.civilizations and mana not in payment),
            None,
        )
        if match is None:
            return None
        payment.append(match)
        remaining.remove(match)
        if len(payment) >= required:
            break

    for mana in remaining:
        if len(payment) >= required:
            break
        payment.append(mana)

    if len(payment) < required:
        return None
    return payment[:required]


def effective_cost(player: PlayerState, card: BattleCard) -> int:
    """軽減オーラとG・ゼロを考慮した実支払いコスト。"""
    g_zero = card.g_zero_spell_count
    if g_zero is not None and player.spells_cast_this_turn >= g_zero:
        return 0
    g_zero_grave = card.g_zero_grave_count
    if g_zero_grave is not None and len(player.graveyard) >= g_zero_grave:
        return 0
    cost = card.cost
    if card.is_creature:
        reduction = sum(creature.card.summon_cost_reduction for creature in player.battle_zone)
        # B・A・D: 常に軽減を使う前提(代償のターン終了時破壊は召喚時にフラグ付与)
        reduction += card.bad_discount
        if reduction:
            cost = max(1, cost - reduction)
    return cost


def can_play_evolution(player: PlayerState, card: BattleCard) -> bool:
    """進化クリーチャーは場に進化元(味方クリーチャー)が必要。

    進化元の種族・文明条件はデータ不足で厳密判定できないため、「味方クリーチャーが
    1体以上いること」で近似する(無条件の踏み倒しを防ぐ過小評価側=exact-safe)。
    """
    if not card.is_evolution:
        return True
    return any(creature.card.is_creature for creature in player.battle_zone)


def playable_hand_indexes(player: PlayerState) -> list[int]:
    indexes = []
    for index, card in enumerate(player.hand):
        if not can_play_evolution(player, card):
            continue
        if select_mana_payment(player.mana_zone, card, cost=effective_cost(player, card)) is not None:
            indexes.append(index)
    return indexes


@dataclass
class MatchResult:
    winner: int | None
    turns: int
    reason: str
    log: list[dict[str, Any]] = field(default_factory=list)


class DuelEngine:
    """バニラ(効果未実行)対戦を実ルールに沿って完走させる最小ルールカーネル。

    対応範囲: マナチャージ、文明拘束付きコスト支払い、召喚酔い、攻撃、
    ブロッカー、パワー比較バトル、シールドブレイク、ダイレクトアタック、山札切れ。
    カード効果は effects(card_id -> abilities)で渡された承認済みEffectScriptを
    on_cast / on_play / s_trigger / on_attack / on_destroyed の各タイミングで実行する。
    """

    def __init__(
        self,
        deck_a: list[BattleCard],
        deck_b: list[BattleCard],
        policy_a: Policy,
        policy_b: Policy,
        rng: random.Random | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
        keep_log: bool = True,
        effects: dict[str, list[dict[str, Any]]] | None = None,
        state: GameState | None = None,
        fire_source_ids: set[str] | None = None,
    ) -> None:
        self.rng = rng or random.Random()
        self.policies = (policy_a, policy_b)
        self.max_turns = max_turns
        self.keep_log = keep_log
        # プレイヤー別の効果成立カウント(op -> 回数)。keep_logと無関係に集計する。
        # fire_source_ids指定時は発生源カードがその集合に含まれる場合のみ数える
        # (exact限定にして、approxスクリプトが発火指標を荒稼ぎするのを防ぐ)
        self.op_success_counts: tuple[Counter[str], Counter[str]] = (Counter(), Counter())
        self.fire_source_ids = fire_source_ids
        self.executor = EffectExecutor(effects)
        # state指定時は進行中のゲーム状態を引き継ぐ(先読み方策の仮実行用)
        if state is not None:
            self.state = state
        else:
            self.state = GameState(players=(self._setup_player("player_a", deck_a), self._setup_player("player_b", deck_b)))
        for policy in self.policies:
            policy.bind(self)

    def _setup_player(self, name: str, deck: list[BattleCard]) -> PlayerState:
        shuffled = deck[:]
        self.rng.shuffle(shuffled)
        player = PlayerState(name=name)
        player.shields = shuffled[:SHIELD_COUNT]
        player.hand = shuffled[SHIELD_COUNT : SHIELD_COUNT + OPENING_HAND]
        player.deck = shuffled[SHIELD_COUNT + OPENING_HAND :]
        return player

    def _record(self, action: str, **detail: Any) -> None:
        if self.keep_log:
            self.state.record(action, **detail)

    def run(self) -> MatchResult:
        state = self.state
        while not state.finished:
            state.turn += 1
            if state.turn > self.max_turns:
                state.finished = True
                state.finish_reason = "turn_limit"
                break
            self._play_turn()
            if not state.finished:
                # 追加ターン: 無限ループ防止のため1プレイヤー3回まで
                if state.extra_turn_pending and state.active_player.extra_turns_taken < 3:
                    state.active_player.extra_turns_taken += 1
                    state.extra_turn_pending = False
                    self._record("extra_turn", player=state.active_player.name)
                else:
                    state.extra_turn_pending = False
                    state.active_index = state.opponent_index
        return MatchResult(
            winner=state.winner,
            turns=min(state.turn, self.max_turns),
            reason=state.finish_reason,
            log=state.log,
        )

    def _play_turn(self) -> None:
        state = self.state
        player = state.active_player
        policy = self.policies[state.active_index]

        player.untap_all()
        player.spells_cast_this_turn = 0

        # 「自分のターン開始時」誘発(自壊デメリット等)
        for creature in list(player.battle_zone):
            if self.executor.has_trigger(creature.card, "on_turn_start"):
                self.executor.run(self, state.active_index, "on_turn_start", creature.card)
            if state.finished:
                return

        # 先攻1ターン目はドローなし
        if not (state.turn == 1 and state.active_index == 0):
            if not self._draw(player):
                return

        charge_index = policy.choose_charge(state, player)
        if charge_index is not None and 0 <= charge_index < len(player.hand):
            card = player.hand.pop(charge_index)
            player.mana_zone.append(make_mana_card(card))
            self._record("charge", card=card.name)

        self._main_phase(player, policy)
        self._attack_phase(player, policy)

        # 「自分のターン終了時」誘発
        if not state.finished:
            for creature in list(player.battle_zone):
                if self.executor.has_trigger(creature.card, "on_turn_end"):
                    self.executor.run(self, state.active_index, "on_turn_end", creature.card)
                if state.finished:
                    break

        # B・A・D等のターン終了時破壊
        if not state.finished:
            for creature in [c for c in player.battle_zone if c.temporary]:
                self._record("end_of_turn_destroy", card=creature.card.name)
                self.destroy_creature(state.active_index, creature)

        # 一時パワー修整をリセット(「そのターン」の効果はターン終了で消える)
        for pl in state.players:
            for creature in pl.battle_zone:
                creature.power_modifier = 0

        # timing="end_of_turn" の遅延効果を解決する
        if not state.finished and state.deferred_end_of_turn:
            deferred, state.deferred_end_of_turn = state.deferred_end_of_turn, []
            for controller_index, source_card, action in deferred:
                if state.finished:
                    break
                self.executor._execute_action(self, controller_index, "end_of_turn", source_card, action)

    def _draw(self, player: PlayerState) -> bool:
        return self.draw_for(self.state.players.index(player))

    def draw_for(self, player_index: int) -> bool:
        """指定プレイヤーが1枚ドローする。山札切れならそのプレイヤーの敗北。"""
        state = self.state
        player = state.players[player_index]
        if not player.deck:
            state.finished = True
            state.winner = 1 - player_index
            state.finish_reason = "deckout"
            self._record("deckout", loser=player.name)
            return False
        card = player.deck.pop(0)
        player.hand.append(card)
        self._record("draw")
        return True

    def record_effect(
        self,
        controller_index: int | None = None,
        source_card_id: str | None = None,
        **detail: Any,
    ) -> None:
        # 効果の成立(対象が確定した実行)はログ無効時も常時カウントする。
        # 探索の選別関数が「エンジンが実際に回ったか」を安価に観測するために使う。
        if (
            controller_index is not None
            and "target" in detail
            and detail.get("op")
            and (self.fire_source_ids is None or source_card_id in self.fire_source_ids)
        ):
            self.op_success_counts[controller_index][detail["op"]] += 1
        if self.keep_log:
            self.state.record("effect", **detail)

    def _spell_cast_blocked(self, card: BattleCard) -> bool:
        """この呪文(またはS・トリガー呪文)が、場の「誰も呪文を唱えられない」系で封じられているか。

        ロックは「誰も」=両プレイヤーに及ぶため、両者の場のクリーチャーを走査する。
        お騒がせチューザ型はタップ状態のときのみ有効。アルカディアス型は文明例外、
        その他はコスト上限を考慮する。
        """
        if not card.is_spell:
            return False
        for owner in self.state.players:
            for creature in owner.battle_zone:
                spec = creature.card.spell_lock
                if spec is None:
                    continue
                civ_keep, max_cost, requires_tapped = spec
                if requires_tapped and not creature.tapped:
                    continue
                if max_cost is not None and card.cost > max_cost:
                    continue
                if civ_keep is not None and civ_keep in card.civilizations:
                    continue
                return True
        return False

    def _main_phase(self, player: PlayerState, policy: Policy) -> None:
        state = self.state
        while True:
            playable = [i for i in playable_hand_indexes(player) if not self._spell_cast_blocked(player.hand[i])]
            if not playable:
                return
            choice = policy.choose_main_action(state, player, playable)
            if choice is None or choice not in playable:
                return
            card = player.hand.pop(choice)
            pay_cost = effective_cost(player, card)
            payment = select_mana_payment(player.mana_zone, card, cost=pay_cost)
            if payment is None:
                player.hand.insert(choice, card)
                return
            for mana in payment:
                mana.tapped = True
            if card.is_creature:
                # 進化クリーチャーは進化元の上に乗る: 味方1体を消費する(ボディの格上げ)
                if card.is_evolution:
                    bases = [c for c in player.battle_zone if c.card.is_creature]
                    if bases:
                        base = min(bases, key=lambda c: c.card.power)
                        player.battle_zone.remove(base)
                instance = CreatureInstance(
                    card=card,
                    summoned_turn=state.turn,
                    temporary=card.bad_discount > 0,
                    tapped=card.enters_tapped,
                )
                player.battle_zone.append(instance)
                self._record("summon", card=card.name, cost=pay_cost)
                self.executor.run(self, state.active_index, "on_play", card)
                # 「相手のクリーチャーがバトルゾーンに出た時」誘発: 相手側のクリーチャーを通知
                opp_idx = state.opponent_index
                for watcher in list(state.players[opp_idx].battle_zone):
                    if self.executor.has_trigger(watcher.card, "on_opponent_creature_enter"):
                        self.executor.run(self, opp_idx, "on_opponent_creature_enter", watcher.card)
                    if state.finished:
                        break
            else:
                player.graveyard.append(card)
                player.spells_cast_this_turn += 1
                self._record("cast_spell", card=card.name, cost=pay_cost)
                self.executor.run(self, state.active_index, "on_cast", card)
                # 「自分が呪文を唱えた時」誘発: 自分のバトルゾーンのクリーチャーを通知
                for creature in list(player.battle_zone):
                    if self.executor.has_trigger(creature.card, "on_spell_cast"):
                        self.executor.run(self, state.active_index, "on_spell_cast", creature.card)
                    if state.finished:
                        break
                # 「相手が呪文を唱えた時」誘発: 非詠唱側(相手)のクリーチャーを通知
                opp_idx = state.opponent_index
                for creature in list(state.players[opp_idx].battle_zone):
                    if self.executor.has_trigger(creature.card, "on_opponent_spell_cast"):
                        self.executor.run(self, opp_idx, "on_opponent_spell_cast", creature.card)
                    if state.finished:
                        break
                # チャージャー: 解決後、墓地ではなくマナゾーンへ
                if card.is_charger and card in player.graveyard:
                    player.graveyard.remove(card)
                    player.mana_zone.append(make_mana_card(card))
            if state.finished:
                return

    def _attack_phase(self, player: PlayerState, policy: Policy) -> None:
        state = self.state
        while not state.finished:
            choices = self._legal_attacks(player)
            if not choices:
                return
            attack = policy.choose_attack(state, player, choices)
            if attack is None:
                # 「可能なら毎ターン攻撃する」クリーチャーは攻撃を強制(デメリットの忠実化)
                forced = next(
                    (ch for ch in choices
                     if "可能なら毎ターン攻撃" in player.battle_zone[ch.attacker_index].card.text),
                    None,
                )
                if forced is None:
                    return
                attack = forced
            attacker_card = player.battle_zone[attack.attacker_index].card
            self._resolve_attack(player, attack)
            if state.finished:
                return
            # 攻撃の終わりに発動するトリガー(自己破壊等)
            self.executor.run(self, state.active_index, "on_attack_end", attacker_card)

    def _legal_attacks(self, player: PlayerState) -> list[AttackChoice]:
        state = self.state
        choices: list[AttackChoice] = []
        opponent = state.opponent
        guardmen = opponent.guardman_creatures()
        for index, creature in enumerate(player.battle_zone):
            if creature.card.cannot_attack:
                continue
            # SA付与オーラ: 召喚酔いでも攻撃可能(タップ済みは不可)
            sa_aura = (not creature.tapped) and player.has_keyword(creature, "スピードアタッカー")
            can_atk = creature.can_attack(state.turn) or sa_aura
            can_atk_cr = creature.can_attack_creature(state.turn) or sa_aura
            if guardmen:
                # ガードマンが存在する場合、必ずそちらを攻撃しなければならない
                for gm_index, gm in enumerate(opponent.battle_zone):
                    if gm in guardmen and can_atk_cr:
                        choices.append(AttackChoice(attacker_index=index, target_creature_index=gm_index))
            else:
                if can_atk and not creature.card.cannot_attack_player:
                    choices.append(AttackChoice(attacker_index=index, target_creature_index=None))
                if can_atk_cr:
                    for target_index, target in enumerate(opponent.battle_zone):
                        if target.tapped:
                            choices.append(AttackChoice(attacker_index=index, target_creature_index=target_index))
        return choices

    def _resolve_attack(self, player: PlayerState, attack: AttackChoice) -> None:
        state = self.state
        opponent = state.opponent
        opponent_policy = self.policies[state.opponent_index]
        attacker = player.battle_zone[attack.attacker_index]
        attacker.tapped = True

        self.executor.run(self, state.active_index, "on_attack", attacker.card)
        # プレイヤーへの攻撃宣言時の追加誘発(「相手プレイヤーを攻撃する時」)
        if attack.target_creature_index is None and self.executor.has_trigger(
            attacker.card, "on_attack_player"
        ):
            self.executor.run(self, state.active_index, "on_attack_player", attacker.card)
        if state.finished or attacker not in player.battle_zone:
            return

        # on_attack が他のクリーチャーを除去してインデックスがずれた場合に再計算する
        try:
            current_attacker_index = player.battle_zone.index(attacker)
        except ValueError:
            return
        if current_attacker_index != attack.attacker_index:
            attack = AttackChoice(
                attacker_index=current_attacker_index,
                target_creature_index=attack.target_creature_index,
            )

        blockers = [] if attacker.card.is_unblockable else opponent.untapped_blockers()
        if blockers:
            blocker_choice = opponent_policy.choose_blocker(state, opponent, attack, blockers)
            if blocker_choice is not None and 0 <= blocker_choice < len(blockers):
                blocker = blockers[blocker_choice]
                blocker.tapped = True
                self._record("block", attacker=attacker.card.name, blocker=blocker.card.name)
                def_idx = state.players.index(opponent)
                if self.executor.has_trigger(blocker.card, "on_block"):
                    self.executor.run(self, def_idx, "on_block", blocker.card)
                self._battle(player, attacker, opponent, blocker)
                return

        if attack.target_creature_index is not None:
            if attack.target_creature_index >= len(opponent.battle_zone):
                return
            target = opponent.battle_zone[attack.target_creature_index]
            self._record("attack_creature", attacker=attacker.card.name, target=target.card.name)
            # 「このクリーチャーが攻撃された時」誘発(攻撃対象になった防御側)
            if self.executor.has_trigger(target.card, "on_attacked"):
                self.executor.run(self, state.opponent_index, "on_attacked", target.card)
                if (
                    state.finished
                    or target not in opponent.battle_zone
                    or attacker not in player.battle_zone
                ):
                    return
            self._battle(player, attacker, opponent, target)
            return

        if opponent.shields:
            self._break_shields(opponent, attacker)
            return

        state.finished = True
        state.winner = state.active_index
        state.finish_reason = "direct_attack"
        self._record("direct_attack", attacker=attacker.card.name)

    def _strigger_locked(self, shield: BattleCard) -> bool:
        """シールドのS・トリガーが、場の「誰も〜のS・トリガーを使えない」でロックされているか。

        ロックは「誰も」=全体に及ぶため、両プレイヤーの場のクリーチャーを走査する。
        シールドの文明のいずれかがロック対象文明に含まれれば発動不可(手札に加わる)。
        """
        locked: set[str] = set()
        for player in self.state.players:
            for creature in player.battle_zone:
                locked.update(creature.card.strigger_lock_civs)
        if not locked:
            return False
        return any(civ in locked for civ in shield.civilizations)

    def _break_shields(self, opponent: PlayerState, attacker: CreatureInstance) -> None:
        state = self.state
        opponent_index = state.players.index(opponent)
        break_count = min(attacker.card.breaker_count, len(opponent.shields))
        broken = []
        for _ in range(break_count):
            # トリガー効果(シールド回収等)で枚数が変わりうるため毎回確認する
            if state.finished or not opponent.shields:
                break
            shield = opponent.shields.pop()
            broken.append(shield.name)
            # シールド焼却: 手札にもトリガーにもならず墓地へ
            if attacker.card.is_shield_burner:
                opponent.graveyard.append(shield)
                continue
            # S・トリガー持ちは即時使用する(現状の命令セットは有利効果のみのため常に使用)
            # ただし、文明ロック・攻撃者のper-break無効化・呪文ロックが掛かっていれば発動しない
            # (S・トリガー呪文の発動は「唱える」ため、呪文ロック下では不発=手札へ)
            strigger_blocked = (
                self._strigger_locked(shield)
                or attacker.card.disables_broken_strigger
                or self._spell_cast_blocked(shield)
            )
            if self.executor.has_trigger(shield, "s_trigger") and not strigger_blocked:
                self._record("s_trigger", card=shield.name)
                if shield.is_creature:
                    opponent.battle_zone.append(CreatureInstance(card=shield, summoned_turn=state.turn))
                else:
                    opponent.graveyard.append(shield)
                self.executor.run(self, opponent_index, "s_trigger", shield)
            else:
                # S・トリガー不所持、またはロック(「誰も〜のS・トリガーを使えない」)で手札へ
                opponent.hand.append(shield)
        self._record("break_shield", attacker=attacker.card.name, broken=broken)
        # 「このクリーチャーがシールドをブレイクした時」誘発(1回以上ブレイクした攻撃で1回)
        if broken and self.executor.has_trigger(attacker.card, "on_shield_break"):
            self.executor.run(self, state.active_index, "on_shield_break", attacker.card)

    def _battle(
        self,
        attacking_player: PlayerState,
        attacker: CreatureInstance,
        defending_player: PlayerState,
        defender: CreatureInstance,
    ) -> None:
        attacker_power = attacker.current_attack_power
        defender_power = defender.current_power
        atk_idx = self.state.players.index(attacking_player)
        def_idx = self.state.players.index(defending_player)
        # スレイヤーはパワーに関係なくバトル相手を破壊する(オーラ付与も考慮)
        atk_wins = attacker_power >= defender_power or attacking_player.has_keyword(attacker, "スレイヤー")
        def_wins = defender_power >= attacker_power or defending_player.has_keyword(defender, "スレイヤー")
        if atk_wins:
            self.destroy_creature(def_idx, defender)
        if def_wins:
            self.destroy_creature(atk_idx, attacker)
        # 「バトルに勝った時」誘発(相手を破壊し自身は生存)
        if atk_wins and not def_wins and attacker in attacking_player.battle_zone:
            if self.executor.has_trigger(attacker.card, "on_win"):
                self.executor.run(self, atk_idx, "on_win", attacker.card)
        if def_wins and not atk_wins and defender in defending_player.battle_zone:
            if self.executor.has_trigger(defender.card, "on_win"):
                self.executor.run(self, def_idx, "on_win", defender.card)
        self._record(
            "battle",
            attacker=attacker.card.name,
            attacker_power=attacker_power,
            defender=defender.card.name,
            defender_power=defender_power,
        )

    def destroy_creature(self, owner_index: int, creature: CreatureInstance) -> None:
        owner = self.state.players[owner_index]
        if creature not in owner.battle_zone:
            return
        # 置換効果: 破壊されるかわりにマナ/手札へ(=破壊扱いにならず、on_destroyedも誘発しない)
        replacement = creature.card.destroy_replacement
        if replacement is not None:
            owner.battle_zone.remove(creature)
            if replacement == "mana":
                owner.mana_zone.append(make_mana_card(creature.card))
            elif replacement == "hand":
                owner.hand.append(creature.card)
            elif replacement == "deck_bottom":
                owner.deck.append(creature.card)
            return
        owner.battle_zone.remove(creature)
        owner.graveyard.append(creature.card)
        # 破壊時のタップ状態をコンテキストとして渡す(「タップ状態で破壊された時」条件用)
        self.executor.run(self, owner_index, "on_destroyed", creature.card, context={"tapped": creature.tapped})

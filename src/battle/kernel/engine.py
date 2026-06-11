from __future__ import annotations

import random
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
    cost = card.cost
    if card.is_creature:
        reduction = sum(creature.card.summon_cost_reduction for creature in player.battle_zone)
        # B・A・D: 常に軽減を使う前提(代償のターン終了時破壊は召喚時にフラグ付与)
        reduction += card.bad_discount
        if reduction:
            cost = max(1, cost - reduction)
    return cost


def playable_hand_indexes(player: PlayerState) -> list[int]:
    indexes = []
    for index, card in enumerate(player.hand):
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
    ) -> None:
        self.rng = rng or random.Random()
        self.policies = (policy_a, policy_b)
        self.max_turns = max_turns
        self.keep_log = keep_log
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

        # B・A・D等のターン終了時破壊
        if not state.finished:
            for creature in [c for c in player.battle_zone if c.temporary]:
                self._record("end_of_turn_destroy", card=creature.card.name)
                self.destroy_creature(state.active_index, creature)

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

    def record_effect(self, **detail: Any) -> None:
        if self.keep_log:
            self.state.record("effect", **detail)

    def _main_phase(self, player: PlayerState, policy: Policy) -> None:
        state = self.state
        while True:
            playable = playable_hand_indexes(player)
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
                instance = CreatureInstance(
                    card=card,
                    summoned_turn=state.turn,
                    temporary=card.bad_discount > 0,
                    tapped=card.enters_tapped,
                )
                player.battle_zone.append(instance)
                self._record("summon", card=card.name, cost=pay_cost)
                self.executor.run(self, state.active_index, "on_play", card)
            else:
                player.graveyard.append(card)
                player.spells_cast_this_turn += 1
                self._record("cast_spell", card=card.name, cost=pay_cost)
                self.executor.run(self, state.active_index, "on_cast", card)
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
                return
            self._resolve_attack(player, attack)

    def _legal_attacks(self, player: PlayerState) -> list[AttackChoice]:
        state = self.state
        choices: list[AttackChoice] = []
        opponent = state.opponent
        for index, creature in enumerate(player.battle_zone):
            if creature.card.cannot_attack:
                continue
            if creature.can_attack(state.turn) and not creature.card.cannot_attack_player:
                choices.append(AttackChoice(attacker_index=index, target_creature_index=None))
            if creature.can_attack_creature(state.turn):
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
        if state.finished or attacker not in player.battle_zone:
            return

        blockers = [] if attacker.card.is_unblockable else opponent.untapped_blockers()
        if blockers:
            blocker_choice = opponent_policy.choose_blocker(state, opponent, attack, blockers)
            if blocker_choice is not None and 0 <= blocker_choice < len(blockers):
                blocker = blockers[blocker_choice]
                blocker.tapped = True
                self._record("block", attacker=attacker.card.name, blocker=blocker.card.name)
                self._battle(player, attacker, opponent, blocker)
                return

        if attack.target_creature_index is not None:
            if attack.target_creature_index >= len(opponent.battle_zone):
                return
            target = opponent.battle_zone[attack.target_creature_index]
            self._record("attack_creature", attacker=attacker.card.name, target=target.card.name)
            self._battle(player, attacker, opponent, target)
            return

        if opponent.shields:
            self._break_shields(opponent, attacker)
            return

        state.finished = True
        state.winner = state.active_index
        state.finish_reason = "direct_attack"
        self._record("direct_attack", attacker=attacker.card.name)

    def _break_shields(self, opponent: PlayerState, attacker: CreatureInstance) -> None:
        state = self.state
        opponent_index = state.players.index(opponent)
        break_count = min(attacker.card.breaker_count, len(opponent.shields))
        broken = []
        for _ in range(break_count):
            if state.finished:
                break
            shield = opponent.shields.pop()
            broken.append(shield.name)
            # シールド焼却: 手札にもトリガーにもならず墓地へ
            if attacker.card.is_shield_burner:
                opponent.graveyard.append(shield)
                continue
            # S・トリガー持ちは即時使用する(現状の命令セットは有利効果のみのため常に使用)
            if self.executor.has_trigger(shield, "s_trigger"):
                self._record("s_trigger", card=shield.name)
                if shield.is_creature:
                    opponent.battle_zone.append(CreatureInstance(card=shield, summoned_turn=state.turn))
                else:
                    opponent.graveyard.append(shield)
                self.executor.run(self, opponent_index, "s_trigger", shield)
            else:
                opponent.hand.append(shield)
        self._record("break_shield", attacker=attacker.card.name, broken=broken)

    def _battle(
        self,
        attacking_player: PlayerState,
        attacker: CreatureInstance,
        defending_player: PlayerState,
        defender: CreatureInstance,
    ) -> None:
        attacker_power = attacker.card.attack_power
        defender_power = defender.card.power
        # スレイヤーはパワーに関係なくバトル相手を破壊する
        if attacker_power >= defender_power or attacker.card.is_slayer:
            self.destroy_creature(self.state.players.index(defending_player), defender)
        if defender_power >= attacker_power or defender.card.is_slayer:
            self.destroy_creature(self.state.players.index(attacking_player), attacker)
        self._record(
            "battle",
            attacker=attacker.card.name,
            attacker_power=attacker_power,
            defender=defender.card.name,
            defender_power=defender_power,
        )

    def destroy_creature(self, owner_index: int, creature: CreatureInstance) -> None:
        owner = self.state.players[owner_index]
        if creature in owner.battle_zone:
            owner.battle_zone.remove(creature)
            owner.graveyard.append(creature.card)
            self.executor.run(self, owner_index, "on_destroyed", creature.card)

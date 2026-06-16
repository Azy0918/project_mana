from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.state import CreatureInstance, ManaCard, PlayerState, make_mana_card

if TYPE_CHECKING:
    from src.battle.kernel.engine import DuelEngine

# 1トリガー連鎖あたりの効果解決数上限(無限ループ防止)
MAX_RESOLUTIONS_PER_CHAIN = 20


class EffectExecutor:
    """承認済みEffectScriptをゲーム状態に対して実行する。

    クリーチャー対象の効果はコントローラーの方策(choose_effect_target)に
    対象選択を問い合わせ、未指定なら最大パワー優先のヒューリスティックで選ぶ。
    """

    def __init__(self, effects: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.effects = effects or {}
        self._chain_depth = 0

    def abilities_for(self, card: BattleCard, trigger: str) -> list[dict[str, Any]]:
        return [
            ability
            for ability in self.effects.get(card.card_id, [])
            if ability.get("trigger") == trigger
        ]

    def has_trigger(self, card: BattleCard, trigger: str) -> bool:
        return bool(self.abilities_for(card, trigger))

    def run(
        self,
        engine: "DuelEngine",
        controller_index: int,
        trigger: str,
        card: BattleCard,
        context: dict[str, Any] | None = None,
    ) -> None:
        abilities = self.abilities_for(card, trigger)
        if not abilities:
            return
        is_chain_root = self._chain_depth == 0
        try:
            for ability in abilities:
                for action in ability.get("actions", []):
                    if engine.state.finished or self._chain_depth >= MAX_RESOLUTIONS_PER_CHAIN:
                        return
                    self._chain_depth += 1
                    self._execute_action(engine, controller_index, trigger, card, action, context)
        finally:
            if is_chain_root:
                self._chain_depth = 0

    def _execute_action(
        self,
        engine: "DuelEngine",
        controller_index: int,
        trigger: str,
        card: BattleCard,
        action: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> None:
        op = action.get("op")
        count = int(action.get("count", 1))
        controller = engine.state.players[controller_index]
        engine.record_effect(trigger=trigger, card=card.name, op=op, count=count)

        # 自ターン限定の効果(ドゥリケン型「自分のターン中に破壊された時」)
        if action.get("own_turn_only") and engine.state.active_index != controller_index:
            return

        # 数えて判定できる条件(マナ武装・墓地枚数・革命など)
        condition = action.get("condition")
        if condition is not None and not self._condition_met(controller, condition, context):
            return

        # ターン終了時タイミングの効果はエンジンの遅延キューに積む(阿修羅型の正確な再現)
        if action.get("timing") == "end_of_turn":
            deferred = dict(action)
            deferred.pop("timing")
            engine.state.deferred_end_of_turn.append((controller_index, card, deferred))
            return

        if op == "draw":
            for _ in range(count):
                if not engine.draw_for(controller_index):
                    return
        elif op == "deck_top_to_mana":
            for _ in range(count):
                if not controller.deck:
                    return
                controller.mana_zone.append(make_mana_card(controller.deck.pop(0)))
        elif op == "look_and_take":
            # 山札の上からlook枚を見て、条件に合うものをtake枚まで手札に加え、残りをrest_zoneへ。
            # 探索/インパルス系の忠実模擬。選択は貪欲(高コスト優先)で最適プレイを近似する。
            look = int(action.get("look", 1))
            take = int(action.get("take", 1))
            card_filter = action.get("card_filter")
            civ = action.get("civilization")
            max_cost = action.get("max_cost")
            rest_zone = action.get("rest_zone", "deck_bottom")
            revealed = [controller.deck.pop(0) for _ in range(min(look, len(controller.deck)))]

            def _matches(card: BattleCard) -> bool:
                if card_filter == "creature" and not card.is_creature:
                    return False
                if card_filter == "spell" and not card.is_spell:
                    return False
                if civ is not None and civ not in card.civilizations:
                    return False
                if max_cost is not None and card.cost > max_cost:
                    return False
                return True

            candidates = sorted([c for c in revealed if _matches(c)], key=lambda c: c.cost, reverse=True)
            taken = candidates[:take]
            for c in taken:
                controller.hand.append(c)
                revealed.remove(c)
            for c in revealed:
                if rest_zone == "grave":
                    controller.graveyard.append(c)
                elif rest_zone == "mana":
                    controller.mana_zone.append(make_mana_card(c))
                else:  # deck_bottom
                    controller.deck.append(c)
        elif op == "destroy_creature":
            target_player_index = self._target_player_index(controller_index, action)
            target_player = engine.state.players[target_player_index]
            max_power = action.get("max_power")
            max_cost = action.get("max_cost")
            target_filter = action.get("target_filter")
            if action.get("target") == "source":
                # 「このクリーチャー(自身)を破壊する」= 効果元の実体を破壊
                src = next((c for c in controller.battle_zone if c.card is card), None)
                if src is None:
                    src = next((c for c in controller.battle_zone if c.card.card_id == card.card_id), None)
                if src is not None:
                    engine.destroy_creature(controller_index, src)
                return
            for _ in range(count):
                pool = target_player.battle_zone
                if max_cost is not None:
                    pool = [creature for creature in pool if creature.card.cost <= max_cost]
                if target_filter == "blocker":
                    pool = [creature for creature in pool if creature.card.is_blocker]
                if action.get("chooser") == "opponent" and pool:
                    # 「相手は自身のクリーチャーを破壊する」= 相手の最適行動(最弱を差し出す)
                    target = min(pool, key=lambda c: c.card.power)
                else:
                    target = self._select_target(engine, controller_index, op, pool, max_power=max_power)
                if target is None:
                    return
                engine.destroy_creature(target_player_index, target)
        elif op == "bounce_creature":
            target_player_index = self._target_player_index(controller_index, action)
            target_player = engine.state.players[target_player_index]
            max_cost = action.get("max_cost")
            for _ in range(count):
                pool = target_player.battle_zone
                if max_cost is not None:
                    pool = [c for c in pool if c.card.cost <= max_cost]
                target = self._select_target(engine, controller_index, op, pool)
                if target is None:
                    return
                target_player.battle_zone.remove(target)
                target_player.hand.append(target.card)
        elif op == "modify_power":
            # 一時パワー増減。結果が0以下になったクリーチャーは破壊(DM裁定)。
            target_player_index = self._target_player_index(controller_index, action)
            target_player = engine.state.players[target_player_index]
            delta = int(action.get("delta", 0))
            max_power = action.get("max_power")
            for _ in range(count):
                pool = list(target_player.battle_zone)
                if max_power is not None:
                    pool = [c for c in pool if c.card.power <= max_power]
                if not pool:
                    return
                if delta < 0:
                    # 除去できる(現パワー≤|delta|)クリーチャーを優先、その中で最大パワーを狙う
                    killable = [c for c in pool if c.current_power + delta <= 0]
                    target = max(killable or pool, key=lambda c: c.current_power)
                else:
                    target = max(pool, key=lambda c: c.current_power)
                target.power_modifier += delta
                if target.current_power <= 0 and target in target_player.battle_zone:
                    engine.destroy_creature(target_player_index, target)
        elif op == "tap_creature":
            target_player_index = self._target_player_index(controller_index, action)
            target_player = engine.state.players[target_player_index]
            for _ in range(count):
                candidates = [creature for creature in target_player.battle_zone if not creature.tapped]
                target = self._select_target(engine, controller_index, op, candidates)
                if target is None:
                    return
                target.tapped = True
        elif op == "add_shield":
            for _ in range(count):
                if not controller.deck:
                    return
                controller.shields.append(controller.deck.pop(0))
        elif op == "discard_opponent_hand":
            opponent = engine.state.players[1 - controller_index]
            for _ in range(count):
                if not opponent.hand:
                    return
                index = engine.rng.randrange(len(opponent.hand))
                opponent.graveyard.append(opponent.hand.pop(index))
        elif op == "deck_top_to_grave":
            # scope="opponent" で相手の山札を削る(山札切れ=敗北の誘発)
            tp = engine.state.players[self._target_player_index(controller_index, action)] \
                if action.get("scope") == "opponent" else controller
            for _ in range(count):
                if not tp.deck:
                    return
                tp.graveyard.append(tp.deck.pop(0))
        elif op == "grave_to_hand":
            card_filter = action.get("card_filter")
            for _ in range(count):
                pool = controller.graveyard
                if card_filter == "creature":
                    pool = [e for e in pool if e.is_creature]
                elif card_filter == "spell":
                    pool = [e for e in pool if e.is_spell]
                if not pool:
                    return
                target_card = max(pool, key=lambda entry: entry.cost)
                controller.graveyard.remove(target_card)
                controller.hand.append(target_card)
        elif op == "summon_from_hand":
            max_cost = action.get("max_cost")
            for _ in range(count):
                candidates = [
                    entry
                    for entry in controller.hand
                    if entry.is_creature and (max_cost is None or entry.cost <= max_cost)
                ]
                if not candidates:
                    return
                target_card = max(candidates, key=lambda entry: (entry.cost, entry.power))
                controller.hand.remove(target_card)
                controller.battle_zone.append(
                    CreatureInstance(card=target_card, summoned_turn=engine.state.turn)
                )
                self.run(engine, controller_index, "on_play", target_card)
                if engine.state.finished:
                    return
        elif op == "send_creature_to_mana":
            target_player_index = self._target_player_index(controller_index, action)
            target_player = engine.state.players[target_player_index]
            for _ in range(count):
                target = self._select_target(engine, controller_index, op, target_player.battle_zone)
                if target is None:
                    return
                target_player.battle_zone.remove(target)
                target_player.mana_zone.append(make_mana_card(target.card))
        elif op == "summon_from_mana":
            # scope=opponent は「相手のマナから相手のバトルゾーンに出させる」(父なる大地型の妨害)
            target_player_index = self._target_player_index(controller_index, {"scope": action.get("scope", "self")})
            target_player = engine.state.players[target_player_index]
            max_cost = action.get("max_cost")
            exclude_evolution = bool(action.get("exclude_evolution"))
            name_self = bool(action.get("name_self"))
            civ_filter = action.get("civilizations")
            for _ in range(count):
                candidates = [
                    mana
                    for mana in target_player.mana_zone
                    if mana.card.is_creature
                    and (max_cost is None or mana.card.cost <= max_cost)
                    and not (exclude_evolution and mana.card.is_evolution)
                    and not (name_self and mana.card.name != card.name)
                    and (civ_filter is None or any(c in civ for civ in mana.card.civilizations for c in civ_filter))
                ]
                if not candidates:
                    return
                if target_player_index != controller_index:
                    # 使用者が選ぶ=相手にとって最も無害な1体(最弱)を出させる
                    target_mana = min(candidates, key=lambda mana: (mana.card.cost, mana.card.power))
                else:
                    target_mana = max(candidates, key=lambda mana: (mana.card.cost, mana.card.power))
                target_player.mana_zone.remove(target_mana)
                target_player.battle_zone.append(
                    CreatureInstance(card=target_mana.card, summoned_turn=engine.state.turn)
                )
                if target_player_index == controller_index:
                    # 自分側の踏み倒しのみエンジン発火として計数する
                    engine.record_effect(controller_index=controller_index, source_card_id=card.card_id, trigger=trigger, card=card.name, op=op, target=target_mana.card.name)
                self.run(engine, target_player_index, "on_play", target_mana.card)
                if engine.state.finished:
                    return
        elif op == "summon_from_grave":
            max_cost = action.get("max_cost")
            exclude_self = bool(action.get("exclude_self"))
            name_self = bool(action.get("name_self"))
            exclude_evolution = bool(action.get("exclude_evolution"))
            race_filter = action.get("race")
            civ_filter = action.get("civilizations")
            grant_speed = bool(action.get("speed_attacker"))
            for _ in range(count):
                candidates = [
                    entry
                    for entry in controller.graveyard
                    if entry.is_creature
                    and (max_cost is None or entry.cost <= max_cost)
                    and not (exclude_self and entry.name == card.name)
                    and not (name_self and entry.name != card.name)
                    and not (exclude_evolution and entry.is_evolution)
                    and (race_filter is None or race_filter in entry.race)
                    and (civ_filter is None or any(c in civ for civ in entry.civilizations for c in civ_filter))
                ]
                if not candidates:
                    return
                target_card = max(candidates, key=lambda entry: (entry.cost, entry.power))
                controller.graveyard.remove(target_card)
                controller.battle_zone.append(
                    CreatureInstance(card=target_card, summoned_turn=engine.state.turn, granted_speed=grant_speed)
                )
                engine.record_effect(controller_index=controller_index, source_card_id=card.card_id, trigger=trigger, card=card.name, op=op, target=target_card.name)
                self.run(engine, controller_index, "on_play", target_card)
                if engine.state.finished:
                    return
        elif op == "burn_opponent_shield":
            opponent = engine.state.players[1 - controller_index]
            for _ in range(count):
                if not opponent.shields:
                    return
                # 墓地に置く=手札に加えずS・トリガーも使わせない
                opponent.graveyard.append(opponent.shields.pop())
        elif op == "cast_from_grave":
            # MRC型: 墓地の呪文を無償で唱え、解決後は山札の一番下へ置く
            max_cost = action.get("max_cost")
            civ_filter = action.get("civilizations")
            for _ in range(count):
                spells = [
                    entry for entry in controller.graveyard
                    if entry.is_spell
                    and (max_cost is None or entry.cost <= max_cost)
                    and (civ_filter is None or any(c in civ for civ in entry.civilizations for c in civ_filter))
                    and self.has_trigger(entry, "on_cast")
                ]
                if not spells:
                    return
                spell = max(spells, key=lambda entry: entry.cost)
                controller.graveyard.remove(spell)
                engine.record_effect(controller_index=controller_index, source_card_id=card.card_id, trigger=trigger, card=card.name, op=op, target=spell.name)
                self.run(engine, controller_index, "on_cast", spell)
                controller.deck.append(spell)
                if engine.state.finished:
                    return
        elif op == "extra_turn":
            engine.state.extra_turn_pending = True
        elif op == "discard_own_hand":
            for _ in range(count):
                if not controller.hand:
                    return
                policy = engine.policies[controller_index]
                index = policy.choose_discard(engine.state, controller, controller.hand)
                if index is None or not (0 <= index < len(controller.hand)):
                    index = engine.rng.randrange(len(controller.hand))
                controller.graveyard.append(controller.hand.pop(index))
        elif op == "own_shield_to_hand":
            for _ in range(count):
                if not controller.shields:
                    return
                controller.hand.append(controller.shields.pop())
        elif op == "hand_to_mana":
            for _ in range(count):
                if not controller.hand:
                    return
                target_card = max(controller.hand, key=lambda entry: entry.cost)
                controller.hand.remove(target_card)
                controller.mana_zone.append(make_mana_card(target_card))
        elif op == "grave_to_mana":
            card_filter = action.get("card_filter")
            for _ in range(count):
                pool = controller.graveyard
                if card_filter == "creature":
                    pool = [e for e in pool if e.is_creature]
                elif card_filter == "spell":
                    pool = [e for e in pool if e.is_spell]
                if not pool:
                    return
                target_card = max(pool, key=lambda entry: entry.cost)
                controller.graveyard.remove(target_card)
                controller.mana_zone.append(make_mana_card(target_card))
        elif op == "grave_to_deck":
            moved = 0
            while controller.graveyard and moved < count:
                controller.deck.append(controller.graveyard.pop())
                moved += 1
            if moved:
                engine.rng.shuffle(controller.deck)
        elif op == "mana_to_hand":
            for _ in range(count):
                untapped = [mana for mana in controller.mana_zone if not mana.tapped]
                if not untapped:
                    return
                target_mana = max(untapped, key=lambda mana: (mana.card.cost, mana.card.power))
                controller.mana_zone.remove(target_mana)
                controller.hand.append(target_mana.card)
        elif op == "untap_creature":
            if action.get("target") == "source":
                src = next((c for c in controller.battle_zone if c.card is card), None) \
                    or next((c for c in controller.battle_zone if c.card.card_id == card.card_id), None)
                if src is not None:
                    src.tapped = False
                return
            target_player_index = self._target_player_index(controller_index, {"scope": action.get("scope", "self")})
            target_player = engine.state.players[target_player_index]
            for _ in range(count):
                candidates = [creature for creature in target_player.battle_zone if creature.tapped]
                target = self._select_target(engine, controller_index, op, candidates)
                if target is None:
                    return
                target.tapped = False
        elif op == "destroy_mana":
            # マナゾーン破壊(ドルバロム型)。keep_civ指定時はその文明を持つカードを残し、
            # それ以外を墓地へ。scope="both"で両者に適用(対称効果)。exact-safe。
            keep_civ = action.get("keep_civ")
            for pidx in self._scope_player_indices(controller_index, action):
                player = engine.state.players[pidx]
                kept, removed = [], []
                for mana in player.mana_zone:
                    if keep_civ is not None and keep_civ in mana.card.civilizations:
                        kept.append(mana)
                    else:
                        removed.append(mana)
                player.mana_zone = kept
                player.graveyard.extend(m.card for m in removed)
        elif op == "destroy_creatures_nonciv":
            # 指定文明を持たないクリーチャーをすべて破壊(ドルバロム後段)。scope="both"対応。
            keep_civ = action.get("keep_civ")
            for pidx in self._scope_player_indices(controller_index, action):
                player = engine.state.players[pidx]
                doomed = [
                    cr for cr in list(player.battle_zone)
                    if keep_civ is None or keep_civ not in cr.card.civilizations
                ]
                for cr in doomed:
                    if cr in player.battle_zone:
                        engine.destroy_creature(pidx, cr)
                    if engine.state.finished:
                        return

    @staticmethod
    def _condition_met(
        controller: PlayerState,
        condition: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> bool:
        """数えるだけで判定できる発動条件(マナ武装・墓地枚数・革命・タップ状態)を評価する。"""
        kind = condition.get("kind")
        if kind == "source_tapped":
            # 「タップ状態で破壊された時」(クラッシュ覇道型)。文脈がなければ不発
            return bool((context or {}).get("tapped"))
        count = int(condition.get("count", 0))
        if kind == "mana_civ_at_least":
            civ = condition.get("civilization", "")
            matched = sum(
                1 for mana in controller.mana_zone
                if any(civ in c for c in mana.card.civilizations)
            )
            return matched >= count
        if kind == "mana_at_least":
            return len(controller.mana_zone) >= count
        if kind == "mana_multicolor_at_least":
            return sum(1 for m in controller.mana_zone if m.card.is_multicolor) >= count
        if kind == "mana_at_most":
            return len(controller.mana_zone) <= count
        if kind == "grave_at_least":
            return len(controller.graveyard) >= count
        if kind == "shields_at_most":
            return len(controller.shields) <= count
        if kind == "shields_at_least":
            return len(controller.shields) >= count
        if kind == "hand_at_most":
            return len(controller.hand) <= count
        if kind == "hand_at_least":
            return len(controller.hand) >= count
        return False  # 未知の条件は不発(過小評価側)

    def _select_target(
        self,
        engine: "DuelEngine",
        controller_index: int,
        op: str,
        creatures: list[CreatureInstance],
        max_power: int | None = None,
    ) -> CreatureInstance | None:
        """効果対象をコントローラーの方策に問い合わせる。Noneなら最大パワー優先。"""
        candidates = creatures
        if max_power is not None:
            candidates = [creature for creature in creatures if creature.card.power <= max_power]
        if not candidates:
            return None
        policy = engine.policies[controller_index]
        choice = policy.choose_effect_target(
            engine.state, engine.state.players[controller_index], op, candidates
        )
        if choice is not None and 0 <= choice < len(candidates):
            return candidates[choice]
        return self._pick_strongest(candidates)

    @staticmethod
    def _target_player_index(controller_index: int, action: dict[str, Any]) -> int:
        scope = action.get("scope", "opponent")
        return controller_index if scope == "self" else 1 - controller_index

    @staticmethod
    def _scope_player_indices(controller_index: int, action: dict[str, Any]) -> list[int]:
        """scope="both"/"all"なら両者、"self"なら自分、その他は相手のindex列を返す。"""
        scope = action.get("scope", "opponent")
        if scope in ("both", "all", "all_players"):
            return [controller_index, 1 - controller_index]
        if scope == "self":
            return [controller_index]
        return [1 - controller_index]

    @staticmethod
    def _pick_strongest(
        creatures: list[CreatureInstance],
        max_power: int | None = None,
    ) -> CreatureInstance | None:
        candidates = creatures
        if max_power is not None:
            candidates = [creature for creature in creatures if creature.card.power <= max_power]
        if not candidates:
            return None
        return max(candidates, key=lambda creature: creature.card.power)

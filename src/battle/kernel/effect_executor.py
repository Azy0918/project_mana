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

    def run(self, engine: "DuelEngine", controller_index: int, trigger: str, card: BattleCard) -> None:
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
                    self._execute_action(engine, controller_index, trigger, card, action)
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
    ) -> None:
        op = action.get("op")
        count = int(action.get("count", 1))
        controller = engine.state.players[controller_index]
        engine.record_effect(trigger=trigger, card=card.name, op=op, count=count)

        if op == "draw":
            for _ in range(count):
                if not engine.draw_for(controller_index):
                    return
        elif op == "deck_top_to_mana":
            for _ in range(count):
                if not controller.deck:
                    return
                controller.mana_zone.append(make_mana_card(controller.deck.pop(0)))
        elif op == "destroy_creature":
            target_player_index = self._target_player_index(controller_index, action)
            target_player = engine.state.players[target_player_index]
            max_power = action.get("max_power")
            for _ in range(count):
                target = self._select_target(engine, controller_index, op, target_player.battle_zone, max_power=max_power)
                if target is None:
                    return
                engine.destroy_creature(target_player_index, target)
        elif op == "bounce_creature":
            target_player_index = self._target_player_index(controller_index, action)
            target_player = engine.state.players[target_player_index]
            for _ in range(count):
                target = self._select_target(engine, controller_index, op, target_player.battle_zone)
                if target is None:
                    return
                target_player.battle_zone.remove(target)
                target_player.hand.append(target.card)
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
            for _ in range(count):
                if not controller.deck:
                    return
                controller.graveyard.append(controller.deck.pop(0))
        elif op == "grave_to_hand":
            for _ in range(count):
                if not controller.graveyard:
                    return
                target_card = max(controller.graveyard, key=lambda entry: entry.cost)
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
            max_cost = action.get("max_cost")
            for _ in range(count):
                candidates = [
                    mana
                    for mana in controller.mana_zone
                    if mana.card.is_creature and (max_cost is None or mana.card.cost <= max_cost)
                ]
                if not candidates:
                    return
                target_mana = max(candidates, key=lambda mana: (mana.card.cost, mana.card.power))
                controller.mana_zone.remove(target_mana)
                controller.battle_zone.append(
                    CreatureInstance(card=target_mana.card, summoned_turn=engine.state.turn)
                )
                self.run(engine, controller_index, "on_play", target_mana.card)
                if engine.state.finished:
                    return
        elif op == "summon_from_grave":
            max_cost = action.get("max_cost")
            for _ in range(count):
                candidates = [
                    entry
                    for entry in controller.graveyard
                    if entry.is_creature and (max_cost is None or entry.cost <= max_cost)
                ]
                if not candidates:
                    return
                target_card = max(candidates, key=lambda entry: (entry.cost, entry.power))
                controller.graveyard.remove(target_card)
                controller.battle_zone.append(
                    CreatureInstance(card=target_card, summoned_turn=engine.state.turn)
                )
                engine.record_effect(trigger=trigger, card=card.name, op=op, target=target_card.name)
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
        elif op == "extra_turn":
            engine.state.extra_turn_pending = True
        elif op == "discard_own_hand":
            for _ in range(count):
                if not controller.hand:
                    return
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
        elif op == "mana_to_hand":
            for _ in range(count):
                untapped = [mana for mana in controller.mana_zone if not mana.tapped]
                if not untapped:
                    return
                target_mana = max(untapped, key=lambda mana: (mana.card.cost, mana.card.power))
                controller.mana_zone.remove(target_mana)
                controller.hand.append(target_mana.card)
        elif op == "untap_creature":
            target_player_index = self._target_player_index(controller_index, {"scope": action.get("scope", "self")})
            target_player = engine.state.players[target_player_index]
            for _ in range(count):
                candidates = [creature for creature in target_player.battle_zone if creature.tapped]
                target = self._select_target(engine, controller_index, op, candidates)
                if target is None:
                    return
                target.tapped = False

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

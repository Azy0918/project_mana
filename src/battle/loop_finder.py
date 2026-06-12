from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from src.battle.effects.store import load_approved_effects_map
from src.battle.kernel.cards import battle_card_from_dict
from src.battle.kernel.effect_executor import MAX_RESOLUTIONS_PER_CHAIN
from src.battle.kernel.engine import DuelEngine
from src.battle.kernel.policy import Policy
from src.battle.kernel.state import CreatureInstance
from src.battle.combo_mine import _load_cards, _ops_of
from src.battle.rating.store import DEFAULT_DB_PATH

# ループ探索器(第一弾): サガ型「相互蘇生+自壊」構造の検出。
# 背景・実在ループの構造分解は docs/loop_research.md を参照。
# 判定はデュエプレ準拠で「無限」ではなく「反復上限への到達」をループ署名とする。


class _NullPolicy(Policy):
    def choose_charge(self, state, player):
        return None

    def choose_main_action(self, state, player, playable):
        return None

    def choose_attack(self, state, player, choices):
        return None

    def choose_blocker(self, state, player, attack, blockers):
        return None


def _revive_spec(abilities: list[dict[str, Any]]) -> dict[str, Any] | None:
    """on_playの蘇生(summon_from_grave)仕様を返す(なければNone)。"""
    for ability in abilities:
        if ability.get("trigger") != "on_play":
            continue
        for action in ability.get("actions", []):
            if action.get("op") == "summon_from_grave":
                return {
                    "max_cost": action.get("max_cost"),
                    "exclude_self": bool(action.get("exclude_self")),
                    "race": action.get("race"),
                }
    return None


def _cast_spec(abilities: list[dict[str, Any]]) -> dict[str, Any] | None:
    """on_attackの墓地詠唱(cast_from_grave)仕様を返す(なければNone)。"""
    for ability in abilities:
        if ability.get("trigger") != "on_attack":
            continue
        for action in ability.get("actions", []):
            if action.get("op") == "cast_from_grave":
                return {"max_cost": action.get("max_cost"), "civilizations": action.get("civilizations")}
    return None


def _spell_revive_spec(abilities: list[dict[str, Any]]) -> dict[str, Any] | None:
    """on_castの蘇生仕様(呪文側)を返す(なければNone)。"""
    for ability in abilities:
        if ability.get("trigger") != "on_cast":
            continue
        for action in ability.get("actions", []):
            if action.get("op") == "summon_from_grave":
                return {
                    "max_cost": action.get("max_cost"),
                    "civilizations": action.get("civilizations"),
                    "exclude_evolution": bool(action.get("exclude_evolution")),
                    "speed_attacker": bool(action.get("speed_attacker")),
                }
    return None


def _civ_match(civ_filter: list[str] | None, card: dict[str, Any]) -> bool:
    if civ_filter is None:
        return True
    civ = str(card.get("civilization") or "")
    return any(c in civ for c in civ_filter)


def _has_self_destroy(abilities: list[dict[str, Any]]) -> bool:
    for ability in abilities:
        if ability.get("trigger") != "on_play":
            continue
        for action in ability.get("actions", []):
            if action.get("op") == "destroy_creature" and action.get("scope") == "self":
                return True
    return False


def find_loop_candidates(db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    """静的スクリーニング: 相互(または自己)蘇生が成立しうるカード対を列挙する。

    - 自己型: Xの蘇生上限がX自身のコストを許容(サガ構造。同名2枚で回る)
    - 相互型: AがBを蘇生でき、BがAを蘇生できる
    自壊(destroy scope self)を併せ持つものは「無限型候補」、なければ「有限増殖型」。
    """
    # ループ探索は近似禁止: 精密変換(fidelity='exact')のみを対象とする
    effects = load_approved_effects_map(db_path, exact_only=True)
    cards = _load_cards(db_path)

    revivers: list[tuple[str, dict[str, Any], bool]] = []  # (card_id, 蘇生仕様, self_destroy)
    for card_id, abilities in effects.items():
        card = cards.get(card_id)
        if card is None:
            continue
        is_creature = "クリーチャー" in str(card["card_type"]) or "ツインパクト" in str(card["card_type"])
        if not is_creature:
            continue
        spec = _revive_spec(abilities)
        if spec is not None:
            revivers.append((card_id, spec, _has_self_destroy(abilities)))

    def fits(spec: dict[str, Any], target: dict[str, Any]) -> bool:
        if spec["max_cost"] is not None and int(target["cost"] or 0) > spec["max_cost"]:
            return False
        if spec["race"] is not None and spec["race"] not in str(target.get("race") or ""):
            return False
        return True

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()

    for a_id, a_spec, a_sd in revivers:
        # 自己型: 自分自身(同名の別コピー)を釣れる(exclude_selfなら不可)
        if not a_spec["exclude_self"] and fits(a_spec, cards[a_id]):
            key = (a_id,)
            if key not in seen:
                seen.add(key)
                candidates.append(
                    {
                        "kind": "自己蘇生型" + ("(無限候補)" if a_sd else "(有限増殖)"),
                        "chain": [a_id],
                        "names": [cards[a_id]["name"]],
                        "infinite_candidate": a_sd,
                    }
                )
        # 相互型(別名カード同士ならexclude_selfは妨げにならない)
        for b_id, b_spec, b_sd in revivers:
            if b_id <= a_id or cards[b_id]["name"] == cards[a_id]["name"]:
                continue
            if fits(a_spec, cards[b_id]) and fits(b_spec, cards[a_id]):
                key = (a_id, b_id)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(
                    {
                        "kind": "相互蘇生型" + ("(無限候補)" if (a_sd or b_sd) else "(有限増殖)"),
                        "chain": [a_id, b_id],
                        "names": [cards[a_id]["name"], cards[b_id]["name"]],
                        "infinite_candidate": a_sd or b_sd,
                    }
                )

    # 呪文再装填型(MRC族): 攻撃時詠唱エンジンE ↔ Eを蘇生できる呪文S
    from src.battle.kernel.cards import battle_card_from_dict

    engines = []
    spells = []
    for card_id, abilities in effects.items():
        card = cards.get(card_id)
        if card is None:
            continue
        bc = battle_card_from_dict(card)
        if bc.is_creature:
            spec = _cast_spec(abilities)
            if spec is not None:
                engines.append((card_id, spec, bc))
        elif bc.is_spell:
            spec = _spell_revive_spec(abilities)
            if spec is not None:
                spells.append((card_id, spec, bc))

    for e_id, e_spec, e_card in engines:
        for s_id, s_spec, s_card in spells:
            # EがSを詠唱できるか
            if e_spec["max_cost"] is not None and s_card.cost > e_spec["max_cost"]:
                continue
            if not _civ_match(e_spec["civilizations"], cards[s_id]):
                continue
            # SがEを蘇生できるか
            if s_spec["max_cost"] is not None and e_card.cost > s_spec["max_cost"]:
                continue
            if s_spec["exclude_evolution"] and e_card.is_evolution:
                continue
            if not _civ_match(s_spec["civilizations"], cards[e_id]):
                continue
            key = (e_id, s_id)
            if key in seen:
                continue
            seen.add(key)
            one_shot = s_spec["speed_attacker"]
            candidates.append(
                {
                    "kind": "呪文再装填型" + ("(ワンショット候補)" if one_shot else "(持続型)"),
                    "chain": [e_id, s_id],
                    "names": [cards[e_id]["name"], cards[s_id]["name"]],
                    "infinite_candidate": one_shot,
                }
            )
    return candidates


def verify_loop_candidate(
    chain_ids: list[str],
    db_path: Path = DEFAULT_DB_PATH,
    copies_in_grave: int = 3,
    seed: int = 1,
) -> dict[str, Any]:
    """動的検証: 墓地にコピーを仕込んで起点を着地させ、連鎖の反復回数を実測する。

    実行器の連鎖上限(MAX_RESOLUTIONS_PER_CHAIN)に到達したら「ループ署名あり」。
    """
    effects = load_approved_effects_map(db_path, exact_only=True)
    cards = _load_cards(db_path)
    loop_cards = [battle_card_from_dict(cards[cid]) for cid in chain_ids]

    filler = [
        battle_card_from_dict(
            {"card_id": f"F{i}", "name": f"埋め{i}", "civilization": "闇", "cost": 2,
             "card_type": "クリーチャー", "power": "2000", "text": ""}
        )
        for i in range(40)
    ]
    engine = DuelEngine(filler, filler, _NullPolicy(), _NullPolicy(),
                        rng=random.Random(seed), effects=effects)
    state = engine.state
    state.turn = 5
    player = state.players[0]
    # 墓地にループ部品のコピーを仕込む
    for card in loop_cards:
        player.graveyard.extend([card] * copies_in_grave)

    starter = loop_cards[0]
    player.battle_zone.append(CreatureInstance(card=starter, summoned_turn=state.turn))
    engine.executor.run(engine, 0, "on_play", starter)

    revive_events = [
        entry for entry in state.log
        if entry.get("action") == "effect"
        and entry.get("op") == "summon_from_grave"
        and "target" in entry  # 実際に蘇生が発生したレコードのみ(宣言レコードは除外)
    ]
    chain_hits_cap = engine.executor._chain_depth == 0 and len(
        [e for e in state.log if e.get("action") == "effect"]
    ) >= MAX_RESOLUTIONS_PER_CHAIN
    return {
        "chain": chain_ids,
        "revive_count": len(revive_events),
        "resolution_cap": MAX_RESOLUTIONS_PER_CHAIN,
        "hits_cap": chain_hits_cap,
        "revived_names": [entry.get("target") for entry in revive_events][:10],
    }


def verify_engine_candidate(
    chain_ids: list[str],
    db_path: Path = DEFAULT_DB_PATH,
    seed: int = 1,
) -> dict[str, Any]:
    """呪文再装填型の動的検証: エンジン1体+墓地(呪文4・エンジン3)から攻撃フェイズを実走。"""
    from src.battle.kernel.policy import GreedyPolicy

    effects = load_approved_effects_map(db_path, exact_only=True)
    cards = _load_cards(db_path)
    engine_card = battle_card_from_dict(cards[chain_ids[0]])
    spell_card = battle_card_from_dict(cards[chain_ids[1]])

    filler = [
        battle_card_from_dict(
            {"card_id": f"F{i}", "name": f"埋め{i}", "civilization": "闇", "cost": 2,
             "card_type": "クリーチャー", "power": "2000", "text": ""}
        )
        for i in range(40)
    ]
    engine = DuelEngine(filler, filler, GreedyPolicy(), GreedyPolicy(),
                        rng=random.Random(seed), effects=effects)
    state = engine.state
    state.turn = 8
    player = state.players[0]
    player.battle_zone.append(CreatureInstance(card=engine_card, summoned_turn=7))
    player.graveyard.extend([spell_card] * 4 + [engine_card] * 3)
    shields_before = len(state.players[1].shields)
    engine._attack_phase(player, engine.policies[0])

    casts = [e for e in state.log if e.get("op") == "cast_from_grave" and "target" in e]
    revives = [e for e in state.log if e.get("op") == "summon_from_grave" and "target" in e]
    return {
        "chain": chain_ids,
        "cast_count": len(casts),
        "revive_count": len(revives),
        "shields_taken": shields_before - len(state.players[1].shields),
        "hits_cap": False,
        "one_turn_kill": state.finished and state.finish_reason == "direct_attack",
        "revived_names": [e.get("target") for e in revives][:6],
    }


def mine_loops(db_path: Path = DEFAULT_DB_PATH, verify_top: int = 20) -> dict[str, Any]:
    """静的候補の列挙と動的検証をまとめて実行する。"""
    candidates = find_loop_candidates(db_path)
    # 無限候補を先に検証する
    candidates.sort(key=lambda c: (not c["infinite_candidate"], len(c["chain"])))
    results = []
    for candidate in candidates[:verify_top]:
        if candidate["kind"].startswith("呪文再装填型"):
            verification = verify_engine_candidate(candidate["chain"], db_path=db_path)
        else:
            verification = verify_loop_candidate(candidate["chain"], db_path=db_path)
        results.append({**candidate, **verification})
    results.sort(key=lambda r: (-int(bool(r.get("one_turn_kill"))), -int(r["hits_cap"]), -r["revive_count"]))
    return {"static_candidates": len(candidates), "verified": results}

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
from src.battle.combo_mine import _load_cards, _ops_of, _action_param
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


def _revive_limit(abilities: list[dict[str, Any]]) -> tuple[bool, int | None]:
    """on_playの蘇生(summon_from_grave)を持つか、その蘇生コスト上限を返す。"""
    for ability in abilities:
        if ability.get("trigger") != "on_play":
            continue
        for action in ability.get("actions", []):
            if action.get("op") == "summon_from_grave":
                return True, action.get("max_cost")
    return False, None


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
    effects = load_approved_effects_map(db_path)
    cards = _load_cards(db_path)

    revivers: list[tuple[str, int | None, bool]] = []  # (card_id, max_cost, self_destroy)
    for card_id, abilities in effects.items():
        card = cards.get(card_id)
        if card is None:
            continue
        is_creature = "クリーチャー" in str(card["card_type"]) or "ツインパクト" in str(card["card_type"])
        if not is_creature:
            continue
        has_revive, max_cost = _revive_limit(abilities)
        if has_revive:
            revivers.append((card_id, max_cost, _has_self_destroy(abilities)))

    def fits(max_cost: int | None, cost: int) -> bool:
        return max_cost is None or cost <= max_cost

    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()

    for a_id, a_limit, a_sd in revivers:
        a_cost = int(cards[a_id]["cost"] or 0)
        # 自己型: 自分自身(同名の別コピー)を釣れる
        if fits(a_limit, a_cost):
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
        # 相互型
        for b_id, b_limit, b_sd in revivers:
            if b_id <= a_id:
                continue
            b_cost = int(cards[b_id]["cost"] or 0)
            if fits(a_limit, b_cost) and fits(b_limit, a_cost):
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
    effects = load_approved_effects_map(db_path)
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


def mine_loops(db_path: Path = DEFAULT_DB_PATH, verify_top: int = 20) -> dict[str, Any]:
    """静的候補の列挙と動的検証をまとめて実行する。"""
    candidates = find_loop_candidates(db_path)
    # 無限候補を先に検証する
    candidates.sort(key=lambda c: (not c["infinite_candidate"], len(c["chain"])))
    results = []
    for candidate in candidates[:verify_top]:
        verification = verify_loop_candidate(candidate["chain"], db_path=db_path)
        results.append({**candidate, **verification})
    results.sort(key=lambda r: (-int(r["hits_cap"]), -r["revive_count"]))
    return {"static_candidates": len(candidates), "verified": results}

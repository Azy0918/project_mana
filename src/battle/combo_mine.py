from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.battle.effects.store import load_approved_effects_map
from src.battle.rating.meta_rating import rate_deck_against_meta
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.chain_validator import validate_chain_playable

# コンボ発掘: 承認済みEffectScriptの命令の組み合わせから「イネーブラー→ペイオフ」
# のチェーン候補を機械的に提案し、一人回し(実コスト+効果再生)で成立率を検証する。
# 役割構成レベルではなくカード固有の相互作用レベルの探索器(docs/sim_findings参照)。


def _ops_of(abilities: list[dict[str, Any]]) -> set[str]:
    return {action.get("op") for ability in abilities for action in ability.get("actions", [])}


def _first_action(abilities: list[dict[str, Any]], op: str) -> dict[str, Any] | None:
    for ability in abilities:
        for action in ability.get("actions", []):
            if action.get("op") == op:
                return action
    return None


def _playable_abilities(card: dict[str, Any], abilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """カーネルが実際に発火させるトリガーの能力だけを返す。

    打点を持つツインパクトはクリーチャーとしてプレイされるため、呪文面の
    on_castは現カーネルでは死にコード(デーケン/ルソー問題)。これを環として
    提案すると成立率0%の幻のチェーンになる。
    """
    card_type = str(card.get("card_type") or "")
    is_pure_spell = "呪文" in card_type and "クリーチャー" not in card_type and "ツインパクト" not in card_type
    trigger = "on_cast" if is_pure_spell else "on_play"
    return [ability for ability in abilities if ability.get("trigger") == trigger]


def _is_evolution_card(card: dict[str, Any]) -> bool:
    return "進化" in str(card.get("card_type") or "")


def _matches_revive_filter(payoff: dict[str, Any], action: dict[str, Any] | None) -> bool:
    """蘇生/踏み倒しアクションのフィルタ(コスト・進化除外・文明)をペイオフが満たすか。"""
    if action is None:
        return False
    max_cost = action.get("max_cost")
    if max_cost is not None and int(payoff.get("cost") or 0) > max_cost:
        return False
    if action.get("exclude_evolution") and _is_evolution_card(payoff):
        return False
    civ_filter = action.get("civilizations")
    if civ_filter is not None:
        payoff_civs = str(payoff.get("civilization") or "")
        if not any(civ in payoff_civs for civ in civ_filter):
            return False
    return True


def _load_cards(db_path: Path) -> dict[str, dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT card_id, name, civilization, cost, card_type, power, text FROM cards"
        ).fetchall()
    return {row["card_id"]: dict(row) for row in rows}


def _civ_overlap(*cards: dict[str, Any]) -> bool:
    """チェーンの全カードを1〜3文明で運用できるか(支払い現実性の粗いチェック)。"""
    civs = set()
    for card in cards:
        civs.update(c.strip() for c in str(card.get("civilization", "")).split("/") if c.strip())
    return len(civs) <= 3


def _payoff_score(card: dict[str, Any], abilities: list[dict[str, Any]] | None) -> float:
    """ペイオフの質: 複数ブレイク・パワー・承認済み効果の数で採点(コスト順だとネタカードが上位に来る)。"""
    text = str(card.get("text") or "")
    power = 0
    try:
        import re as re_module

        match = re_module.search(r"\d+", str(card.get("power") or ""))
        power = int(match.group()) if match else 0
    except Exception:
        power = 0
    breaker = 3 if "T・ブレイカー" in text else (2 if "W・ブレイカー" in text else 1)
    effect_count = sum(len(a.get("actions", [])) for a in (abilities or []))
    return breaker * 10 + power / 1000 + effect_count * 4


def propose_chains(
    db_path: Path = DEFAULT_DB_PATH,
    max_proposals: int = 30,
) -> list[dict[str, Any]]:
    """イネーブラー×ペイオフのチェーン候補を提案する(検証前の仮説リスト)。

    チェーンの環(イネーブラー)はexactスクリプトのみから抽出する。
    approxスクリプトはscope欠落などの誤読で実在しないコンボを捏造するため
    (例: 父なる大地の旧approxが生んだid=23、loop-findと同じfidelityゲート)。
    """
    effects = load_approved_effects_map(db_path, exact_only=True)
    cards = _load_cards(db_path)

    mills: list[tuple[str, int]] = []        # (card_id, 落とす枚数)
    reanimators: list[tuple[str, int | None]] = []  # (card_id, max_cost)
    creature_reanimators: list[tuple[str, int | None]] = []  # 蘇生能力持ちクリーチャー(2段目の中継ぎ)
    mana_cheats: list[tuple[str, int | None]] = []
    ramps: list[str] = []
    payoffs: list[str] = []

    for card_id, abilities in effects.items():
        card = cards.get(card_id)
        if card is None:
            continue
        # カーネルが実際に発火させるトリガーの能力だけを環の候補にする
        playable = _playable_abilities(card, abilities)
        ops = _ops_of(playable)
        cost = int(card["cost"] or 0)
        is_creature = "クリーチャー" in str(card["card_type"]) or "ツインパクト" in str(card["card_type"])
        if "deck_top_to_grave" in ops and cost <= 5:
            action = _first_action(playable, "deck_top_to_grave")
            count = (action or {}).get("count", 1)
            if int(count) >= 2:
                mills.append((card_id, int(count)))
        if "summon_from_grave" in ops and cost <= 7:
            reanimators.append((card_id, _first_action(playable, "summon_from_grave")))
        if "summon_from_grave" in ops and is_creature:
            creature_reanimators.append((card_id, _first_action(playable, "summon_from_grave")))
        if "summon_from_mana" in ops and cost <= 7:
            action = _first_action(playable, "summon_from_mana")
            # 父なる大地型(相手のマナから出させる妨害)は自分の踏み倒しではない
            if action is not None and action.get("scope") != "opponent":
                mana_cheats.append((card_id, action))
        if "deck_top_to_mana" in ops and cost <= 4:
            ramps.append(card_id)

    # ペイオフ: 高コストかつ承認済み効果(または複数ブレイク)を持つクリーチャー
    for card_id, card in cards.items():
        cost = int(card["cost"] or 0)
        text = str(card["text"] or "")
        is_creature = "クリーチャー" in str(card["card_type"]) or "ツインパクト" in str(card["card_type"])
        if not is_creature or cost < 7:
            continue
        if card_id in effects or "ブレイカー" in text:
            payoffs.append(card_id)
    payoffs.sort(key=lambda cid: -_payoff_score(cards[cid], effects.get(cid)))

    proposals: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    # 種類別クォータ: 1段型が枠を使い切って多段型が提案されない事態を防ぐ
    quota = max(1, max_proposals // 3)
    kind_counts: dict[str, int] = {}

    def add(kind: str, enabler_ids: list[str], payoff_id: str) -> None:
        key = tuple(enabler_ids + [payoff_id])
        if key in seen or len(proposals) >= max_proposals or kind_counts.get(kind, 0) >= quota:
            return
        chain_cards = [cards[cid] for cid in enabler_ids + [payoff_id]]
        if not _civ_overlap(*chain_cards):
            return
        seen.add(key)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        proposals.append(
            {
                "kind": kind,
                "chain": list(key),
                "names": [cards[cid]["name"] for cid in key],
            }
        )

    # リアニメイト型: 墓地肥やし → 蘇生 → 大型(蘇生フィルタ: コスト・進化除外・文明を満たすもの)
    for mill_id, _count in mills:
        for rean_id, rean_action in reanimators:
            for payoff_id in payoffs:
                if not _matches_revive_filter(cards[payoff_id], rean_action):
                    continue
                add("リアニメイト", [mill_id, rean_id], payoff_id)
                break

    # マナ踏み倒し型: マナ加速 → マナから展開 → 大型
    for ramp_id in ramps[:10]:
        for cheat_id, cheat_action in mana_cheats:
            for payoff_id in payoffs:
                if not _matches_revive_filter(cards[payoff_id], cheat_action):
                    continue
                add("マナ踏み倒し", [ramp_id, cheat_id], payoff_id)
                break

    # 二段リアニメイト型: 肥やし → 蘇生呪文 → 蘇生能力持ちクリーチャー(中継ぎ) → 超大型
    # 1段目の蘇生制限内に収まる中継ぎが、自身の蘇生でさらに大きいペイオフを釣り上げる
    for mill_id, _count in mills[:5]:
        for rean_id, rean_action in reanimators[:8]:
            for mid_id, mid_action in creature_reanimators:
                mid_cost = int(cards[mid_id]["cost"] or 0)
                if not _matches_revive_filter(cards[mid_id], rean_action):
                    continue
                if mid_id in (mill_id, rean_id):
                    continue
                for payoff_id in payoffs:
                    payoff_cost = int(cards[payoff_id]["cost"] or 0)
                    if not _matches_revive_filter(cards[payoff_id], mid_action):
                        continue
                    # 中継ぎより重いペイオフが釣れる場合のみ二段の意味がある
                    if payoff_cost <= mid_cost:
                        continue
                    before = len(proposals)
                    add("二段リアニメイト", [mill_id, rean_id, mid_id], payoff_id)
                    if len(proposals) > before:
                        break

    return proposals


def _build_combo_deck(
    chain_ids: list[str],
    cards: dict[str, dict[str, Any]],
    effects: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """コンボ3種×4枚+同文明の承認済みドロー/ランプで40枚の検証用デッキを組む。"""
    deck: list[dict[str, Any]] = []
    civs: set[str] = set()
    for card_id in chain_ids:
        card = dict(cards[card_id])
        card["quantity"] = 4
        deck.append(card)
        civs.update(c.strip() for c in str(card["civilization"]).split("/") if c.strip())

    fillers = []
    for card_id, abilities in effects.items():
        if card_id in chain_ids or card_id not in cards:
            continue
        card = cards[card_id]
        card_civs = {c.strip() for c in str(card["civilization"]).split("/") if c.strip()}
        if not card_civs.issubset(civs):
            continue
        cost = int(card["cost"] or 0)
        ops = _ops_of(abilities)
        if cost <= 4 and ({"draw", "deck_top_to_mana", "deck_top_to_grave"} & ops):
            fillers.append((cost, card_id))
    fillers.sort()
    total = 4 * len(chain_ids)
    for _cost, card_id in fillers:
        if total >= 40:
            break
        card = dict(cards[card_id])
        card["quantity"] = min(4, 40 - total)
        deck.append(card)
        total += card["quantity"]
    return deck if total >= 40 else []


def mine_combos(
    db_path: Path = DEFAULT_DB_PATH,
    max_proposals: int = 30,
    trials: int = 300,
    max_turns: int = 8,
    games: int = 60,
    seed: int | None = None,
    rate_top: int = 3,
) -> dict[str, Any]:
    """チェーン提案→一人回し成立検証→上位のみメタ判定、の発掘パイプライン。"""
    effects = load_approved_effects_map(db_path)
    cards = _load_cards(db_path)
    proposals = propose_chains(db_path, max_proposals=max_proposals)

    validated: list[dict[str, Any]] = []
    for proposal in proposals:
        deck = _build_combo_deck(proposal["chain"], cards, effects)
        if not deck:
            continue
        result = validate_chain_playable(
            proposal["chain"], deck, trials=trials, max_turns=max_turns, seed=seed, effects=effects
        )
        validated.append(
            {
                **proposal,
                "success_rate": result["success_rate"],
                "completion_turns": result["completion_turn_distribution"],
                "deck": deck,
            }
        )
    validated.sort(key=lambda entry: -entry["success_rate"])

    for entry in validated[:rate_top]:
        if entry["success_rate"] <= 0:
            break
        rating = rate_deck_against_meta(
            entry["deck"], f'コンボ検証_{entry["names"][-1]}', db_path=db_path,
            games_per_pair=games, seed=seed, effects=effects, save=False,
        )
        entry["strength_score"] = rating["strength_score"]
        entry["matchups"] = rating["details"]

    return {"proposals": len(proposals), "validated": validated}

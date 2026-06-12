"""ComboPolicyのMRC型対応の効果測定(アブレーション)。

id=20「黒単ロマノフサイン・再誕」をメタ全デッキ相手に回し、
操作方策ごとの平均勝率(=絶対強さスコア相当)を比較する。

2026-06の測定結果(詳細は docs/loop_research.md 第七弾):
  greedy(基準)                 43.0
  combo_old(G・ゼロのみ)       43.0
  combo_discard_only             41.2
  combo_charge_only(全保護)    28.4  ← 選択効果でマナ詰まり
  エンジン限定保護               45.8  ← 採用
  +蘇生呪文優先                  47.5  ← 採用(combo_mrc最終形)
  +エンジン先制攻撃              40.8  ← 不採用(貪欲の戦闘判断を潰す)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.battle.effects.store import load_approved_effects_map
from src.battle.kernel.combo import ComboPolicy
from src.battle.kernel.policy import GreedyPolicy
from src.battle.rating.meta_rating import load_meta_battle_decks
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.runner import simulate_matches

GAMES_PER_PAIR = 100
SEED = 20260612


class ComboNoMRC(ComboPolicy):
    """墓地適性を無効化した比較用ComboPolicy(G・ゼロ対応のみ)。"""

    def bind(self, engine: object) -> None:
        self._grave_good = set()


class ComboDiscardOnly(ComboPolicy):
    """選択捨てのみ有効(チャージ保護は無効)の比較用。"""

    def choose_charge(self, state, player):
        return GreedyPolicy.choose_charge(self, state, player)


class ComboChargeOnly(ComboPolicy):
    """チャージ保護のみ有効(捨て札はランダム)の比較用。"""

    def choose_discard(self, state, player, hand):
        return None


class ComboNoRevivePriority(ComboPolicy):
    """蘇生呪文優先を無効化した比較用。"""

    def _engine_assembly_action(self, player, playable):
        return None


class ComboReviveValue(ComboPolicy):
    """蘇生呪文の発動条件を一般化した試作: 墓地に蘇生対象(進化でないクリーチャー)が
    いれば、エンジン不在でも蘇生呪文を優先して唱える。"""

    def _engine_assembly_action(self, player, playable):
        base = super()._engine_assembly_action(player, playable)
        if base is not None:
            return base
        if not self._revive_spells:
            return None
        if not any(card.is_creature and not card.is_evolution for card in player.graveyard):
            return None
        revives = [i for i in playable if player.hand[i].card_id in self._revive_spells]
        if revives:
            return max(revives, key=lambda i: player.hand[i].cost)
        return None


def main() -> None:
    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--deck-id", type=int, default=20)
    args = arg_parser.parse_args()
    with sqlite3.connect(DEFAULT_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT deck_name, deck_cards_json FROM generated_decks WHERE id = ?", (args.deck_id,)
        ).fetchone()
    deck = json.loads(row["deck_cards_json"])
    effects = load_approved_effects_map(DEFAULT_DB_PATH)
    meta_decks, warnings = load_meta_battle_decks(DEFAULT_DB_PATH)
    for warning in warnings:
        print(f"warning: {warning}")
    print(f'deck: {row["deck_name"]} (id={args.deck_id}) / opponents: {len(meta_decks)} / games/pair: {GAMES_PER_PAIR}')

    policies = {
        "combo_mrc": ComboPolicy,
        "combo_revive_value": ComboReviveValue,
    }
    results: dict[str, dict] = {}
    for label, policy_cls in policies.items():
        details = []
        wins = games = 0
        for index, meta in enumerate(meta_decks):
            summary = simulate_matches(
                deck,
                meta["cards"],
                games=GAMES_PER_PAIR,
                seed=SEED + index,
                policy_a=policy_cls(),
                policy_b=GreedyPolicy(),
                effects=effects,
            )
            wins += summary.wins_a
            games += summary.games
            details.append((meta["deck_name"], summary.win_rate_a))
        score = round(wins / games * 100, 1)
        results[label] = {"score": score, "details": details}
        print(f"\n[{label}] 絶対強さスコア: {score}")
        for name, rate in details:
            print(f"  vs {name}: {rate:.1%}")

    print("\n=== まとめ ===")
    for label, entry in results.items():
        print(f'{label}: {entry["score"]}')


if __name__ == "__main__":
    main()

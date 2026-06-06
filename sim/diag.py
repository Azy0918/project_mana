"""パイロット較正の診断ハーネス。
コンボ指標(最大呪文/ターン・追加ターン発火・スコーラー/フィニッシャー無料召喚)と
コントロール vs アグロ勝率を、任意のパイロットで測る。各改善の効果をここで定量化する。

使い方:
  PYTHONPATH=. PYTHONUTF8=1 python diag.py            # 既定の全指標
  from diag import measure, PILOTS
"""
from __future__ import annotations
import random
import time

from duel_masters import decks, superdim
from duel_masters.engine import Game
from duel_masters.agents import HeuristicAgent, RolloutAgent


# ---- パイロット工場(name, rng)->agent ---------------------------------------
def _heuristic(name, rng):
    return HeuristicAgent(name, rng)


def _rollout(rollouts=2, horizon=5):
    def make(name, rng):
        return RolloutAgent(name, rng, rollouts=rollouts, horizon=horizon)
    return make


PILOTS = {
    "heuristic": _heuristic,
    "rollout_r2h5": _rollout(2, 5),
    "rollout_r3h6": _rollout(3, 6),
}


# ---- 計測 -------------------------------------------------------------------
def _install_spell_counter(game):
    """ターン終了フックで各ターンの呪文数を記録(最大呪文/ターンの算出用)。"""
    game._max_spells = 0

    def hook(g, p):
        # clone() は turn_end_hooks を引き継ぐが _max_spells は持たない → 防御的に。
        cur = getattr(g, "_max_spells", 0)
        if p.spells_this_turn > cur:
            g._max_spells = p.spells_this_turn
    game.turn_end_hooks.append(hook)


def measure(deckA, deckB, pilotA, pilotB, games=30, seed0=500, max_turns=120,
            combo_side="A"):
    """deckA/deckB=デッキ名。A視点の着席公平勝率＋A(またはB)のコンボ指標。"""
    pool, super_pool = decks.build_full_pool(nd_only=False)
    dA, dB = decks.decklist(deckA), decks.decklist(deckB)
    fA = PILOTS[pilotA] if isinstance(pilotA, str) else pilotA
    fB = PILOTS[pilotB] if isinstance(pilotB, str) else pilotB

    winsA = ties = 0
    max_spells = extra_turns = finisher_free = 0
    t0 = time.time()
    n = 0
    for k in range(games):
        for swap in (0, 1):
            rng = random.Random(seed0 + k * 7 + swap)
            pa = decks.make_player(pool, super_pool, "A", fA("A", rng), *dA)
            pb = decks.make_player(pool, super_pool, "B", fB("B", rng), *dB)
            p0, p1 = (pa, pb) if swap == 0 else (pb, pa)
            g = Game(p0, p1, rng=rng)
            superdim.install_awaken_hook(g)
            _install_spell_counter(g)
            w = g.run(max_turns=max_turns)
            n += 1
            if w is pa:
                winsA += 1
            elif w is None:
                ties += 1
            log = "\n".join(g.log_lines)
            max_spells = max(max_spells, g._max_spells)
            extra_turns += log.count("追加ターンを獲得")
            finisher_free += sum(log.count(s) for s in
                                 ("スコーラー を召喚", "スコーラー を召喚 (S・トリガー)"))
    dt = time.time() - t0
    return {
        "winrateA": (winsA + 0.5 * ties) / n,
        "max_spells_turn": max_spells,
        "extra_turn_fires": extra_turns,
        "finisher_free_casts": finisher_free,
        "sec_per_game": dt / n,
        "games": n,
    }


def _fmt(d):
    return (f"勝率A={d['winrateA']:.3f}  最大呪文/T={d['max_spells_turn']}  "
            f"追加ターン={d['extra_turn_fires']}  スコーラー無料={d['finisher_free_casts']}  "
            f"({d['sec_per_game']*1000:.0f}ms/戦)")


def main():
    print("=== ベースライン診断 ===")
    print("[コンボ: 水自然スコーラー vs 火光レイド] (A=スコーラー)")
    for pilot in ("heuristic", "rollout_r2h5"):
        d = measure("水自然スコーラー", "火光レイド", pilot, "heuristic", games=20)
        print(f"  {pilot:14s} {_fmt(d)}")

    print("[コントロール: 青白 vs 火光レイド] (A=青白)")
    for pilot in ("heuristic", "rollout_r2h5", "rollout_r3h6"):
        d = measure("青白コントロール", "火光レイド", pilot, "heuristic", games=20)
        print(f"  {pilot:14s} 勝率A={d['winrateA']:.3f}  ({d['sec_per_game']*1000:.0f}ms/戦)")

    print("[コントロール: 闇自然 vs 火光レイド] (A=闇自然)")
    for pilot in ("heuristic", "rollout_r2h5"):
        d = measure("闇自然デンジャデオン", "火光レイド", pilot, "heuristic", games=20)
        print(f"  {pilot:14s} 勝率A={d['winrateA']:.3f}  ({d['sec_per_game']*1000:.0f}ms/戦)")


if __name__ == "__main__":
    main()

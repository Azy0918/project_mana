from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.battle.effects.store import load_approved_effects_map
from src.battle.kernel.combo import ComboPolicy
from src.battle.rating.meta_rating import load_meta_battle_decks
from src.battle.rating.store import DEFAULT_DB_PATH
from src.battle.sim.chain_validator import validate_chain_playable
from src.battle.sim.runner import simulate_matches
from src.evaluate_deck import evaluate_deck
from src.evolutionary_search import _civilization_matches, _deck_counter, _group_deck, _mutate, _repair
from src.generate_deck import DECK_SIZE, MAX_COPIES
from src.search_cards import search_cards

from collections import Counter


def _initial_deck(
    pool: list[dict[str, Any]],
    cards_by_id: dict[str, dict[str, Any]],
    rng: random.Random,
    max_card_types: int,
) -> list[dict[str, Any]]:
    """少数のカード種に複数枚ずつ割り当てた、人間のデッキに近い初期個体を作る。

    max_card_types >= デッキ枚数 のときは1枚刺し主体で生成する(ハイランダー型探索モード)。
    """
    counter: Counter[str] = Counter()
    if max_card_types >= DECK_SIZE:
        for card in rng.sample(pool, min(DECK_SIZE, len(pool))):
            counter[card["card_id"]] = 1
    else:
        candidates = rng.sample(pool, min(max(1, max_card_types), len(pool)))
        for card in candidates:
            if sum(counter.values()) >= DECK_SIZE:
                break
            quantity = min(rng.choice([2, 3, 4, 4]), DECK_SIZE - sum(counter.values()))
            counter[card["card_id"]] = quantity
    repaired = _repair(counter, pool, cards_by_id, rng)
    return _group_deck(repaired, cards_by_id)


def _consolidating_mutate(
    deck: list[dict[str, Any]],
    pool: list[dict[str, Any]],
    cards_by_id: dict[str, dict[str, Any]],
    rng: random.Random,
    max_card_types: int,
) -> list[dict[str, Any]]:
    """通常変異に「集約」を加える: 1枚刺しを既存カードの追加コピーへ置き換え、
    種類数が上限を超えたら最少枚数の種類を他へ吸収する(ソフト制約)。

    max_card_types >= デッキ枚数 のときは集約を行わない(ハイランダー型探索モード)。"""
    mutated = _mutate(deck, pool, cards_by_id, rng)
    if max_card_types >= DECK_SIZE:
        return mutated
    counter = _deck_counter(mutated)

    for _ in range(rng.randint(0, 2)):
        singles = [card_id for card_id, count in counter.items() if count == 1]
        if not singles:
            break
        remove_id = rng.choice(singles)
        targets = [
            card_id for card_id, count in counter.items() if card_id != remove_id and count < MAX_COPIES
        ]
        if not targets:
            break
        del counter[remove_id]
        counter[rng.choice(targets)] += 1

    while len(counter) > max_card_types:
        smallest = min(counter, key=lambda card_id: counter[card_id])
        moved = counter.pop(smallest)
        for _ in range(moved):
            targets = [card_id for card_id, count in counter.items() if count < MAX_COPIES]
            if not targets:
                break
            counter[rng.choice(targets)] += 1

    repaired = _repair(counter, pool, cards_by_id, rng)
    return _group_deck(repaired, cards_by_id)


def _simulated_metrics(
    deck: list[dict[str, Any]],
    opponents: list[dict[str, Any]],
    games: int,
    seed: float,
    effects: dict[str, list[dict[str, Any]]] | None,
) -> tuple[float, float]:
    """対メタ勝率と、エンジン系効果(墓地詠唱・蘇生)が成立した試合の割合を返す。"""
    wins = 0
    total = 0
    fired = 0.0
    for index, opponent in enumerate(opponents):
        summary = simulate_matches(
            deck,
            opponent["cards"],
            games=games,
            seed=int(seed * 100000) + index,
            effects=effects,
            policy_a=ComboPolicy(),
            policy_b=ComboPolicy(),
        )
        wins += summary.wins_a
        total += summary.games
        fired += summary.engine_fire_rate_a * summary.games
    if not total:
        return 0.0, 0.0
    return wins / total, fired / total


def _opponents_for_generation(
    shuffled_meta: list[dict[str, Any]],
    generation: int,
    sim_opponents: int,
    rotation_period: int = 1,
) -> list[dict[str, Any]]:
    """選別相手をローテーションする(スライディングウィンドウ)。

    固定相手への過適合を抑えるため、全メタデッキが周期的に選別に登場する。
    rotation_period 世代ごとに窓を1つずらす(毎世代の全交代は選別シグナルを
    揺らして収束を遅らせるため、緩やかな交代を既定とする)。
    """
    if len(shuffled_meta) <= sim_opponents:
        return shuffled_meta
    window = (generation - 1) // max(1, rotation_period)
    start = window % len(shuffled_meta)
    return [shuffled_meta[(start + i) % len(shuffled_meta)] for i in range(sim_opponents)]


def save_to_generated_decks(
    deck: list[dict[str, Any]],
    deck_name: str,
    strategy_note: str,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    """探索成果をアプリの生成デッキ一覧(generated_decks)に保存する。

    Streamlitの「生成デッキ保存・比較」画面や `rate-generated` から参照できる。
    generated_deck_store はpandas依存のため、ここでは直接SQLで書き込む。
    """
    summary = evaluate_deck(deck)
    role_counts = summary.get("role_counts", {})
    cost_curve = summary.get("cost_curve", {})
    total_cards = sum(cost_curve.values()) or 1
    average_cost = sum(int(cost) * count for cost, count in cost_curve.items()) / total_cards
    tag_counts = summary.get("tag_counts", {})
    civilizations = "/".join(sorted(summary.get("civilization_counts", {}).keys()))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS generated_decks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                deck_name TEXT NOT NULL,
                format TEXT,
                civilizations TEXT,
                deck_type TEXT,
                focus_tags TEXT,
                avoid_tags TEXT,
                strategy_note TEXT,
                deck_size INTEGER,
                deck_cards_json TEXT,
                condition_score INTEGER,
                civilization_match_rate REAL,
                starter_count INTEGER,
                defense_count INTEGER,
                finisher_count INTEGER,
                removal_count INTEGER,
                draw_count INTEGER,
                average_cost REAL,
                evaluation_score REAL,
                novelty_score REAL,
                meta_score REAL,
                candidate_origin TEXT
            )
            """
        )
        cursor = conn.execute(
            """
            INSERT INTO generated_decks (
                created_at, deck_name, format, civilizations, deck_type,
                focus_tags, avoid_tags, strategy_note, deck_size, deck_cards_json,
                condition_score, civilization_match_rate, starter_count, defense_count,
                finisher_count, removal_count, draw_count, average_cost,
                evaluation_score, novelty_score, meta_score, candidate_origin
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                deck_name,
                "ND",
                civilizations,
                "ハイブリッド探索",
                "",
                "",
                strategy_note,
                summary.get("total_cards", 40),
                json.dumps(deck, ensure_ascii=False),
                None,
                None,
                role_counts.get("初動", 0),
                role_counts.get("受け札", 0),
                role_counts.get("フィニッシャー", 0),
                tag_counts.get("除去", 0),
                tag_counts.get("ドロー", 0),
                round(average_cost, 2),
                summary.get("score", 0),
                summary.get("novelty_score", 0),
                summary.get("meta_score", 0),
                "hybrid_search",
            ),
        )
        return int(cursor.lastrowid)


def _enforce_locked(
    deck: list[dict[str, Any]],
    locked_card_ids: list[str],
    pool: list[dict[str, Any]],
    cards_by_id: dict[str, dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """コンボ核などの固定カードを4枚ずつ維持する(進化が骨格を淘汰しないように)。"""
    counter = _deck_counter(deck)
    for card_id in locked_card_ids:
        counter[card_id] = MAX_COPIES
    repaired = _repair(counter, pool, cards_by_id, rng)
    # _repairが40枚調整で固定カードを削った場合は他を削って戻す
    for card_id in locked_card_ids:
        while repaired[card_id] < MAX_COPIES:
            others = [cid for cid, n in repaired.items() if cid not in locked_card_ids and n > 0]
            if not others:
                break
            victim = rng.choice(others)
            repaired[victim] -= 1
            if repaired[victim] <= 0:
                del repaired[victim]
            repaired[card_id] += 1
    return _group_deck(repaired, cards_by_id)


def run_hybrid_search(
    db_path: Path = DEFAULT_DB_PATH,
    generations: int = 8,
    population_size: int = 12,
    civilizations: list[str] | None = None,
    seed: int | None = None,
    sim_games: int = 30,
    sim_opponents: int = 3,
    sim_weight: float = 0.7,
    rotate_opponents: bool = True,
    rotation_period: int = 3,
    max_card_types: int = 16,
    seed_deck: list[dict[str, Any]] | None = None,
    locked_card_ids: list[str] | None = None,
    chain: list[str] | None = None,
    chain_weight: float = 0.3,
    engine_weight: float = 0.0,
) -> dict[str, Any]:
    """世代内選別に厳密シミュレーション勝率を使う進化探索。

    各候補を「対メタ勝率×100 × sim_weight + ヒューリスティック評価 × (1-sim_weight)」で
    採点する。ヒューリスティック単独では見逃される実戦的に強い候補を残すための探索
    (背景は docs/sim_findings_2026-06.md)。

    rotate_opponents=True(既定)では選別相手を世代ごとにローテーションし、
    特定の相手への過適合を抑える。Falseは固定相手(従来動作)。

    engine_weight > 0 のときは「エンジン発火率(墓地詠唱・蘇生が成立した試合の割合)」を
    適応度に加え、勝ちながらエンジンも回る方向の進化圧をかける。背景:
    ロックだけでは進化がコンボ部品を荷物にしたままアグロ化する
    (docs/loop_research.md 第九弾)。
    """
    rng = random.Random(seed)
    sim_weight = max(0.0, min(1.0, sim_weight))
    locked = list(locked_card_ids or [])

    all_cards = search_cards(db_path)
    if not all_cards:
        return {"best": None, "history": [], "warnings": ["カードDBが空です"]}
    pool = [card for card in all_cards if _civilization_matches(card, civilizations or [])] or all_cards
    cards_by_id = {card["card_id"]: card for card in all_cards}

    meta_decks, warnings = load_meta_battle_decks(db_path)
    if not meta_decks:
        return {"best": None, "history": [], "warnings": warnings + ["対戦相手となるメタデッキがありません"]}
    shuffled_meta = meta_decks[:]
    rng.shuffle(shuffled_meta)
    fixed_opponents = shuffled_meta[: min(sim_opponents, len(shuffled_meta))]
    effects = load_approved_effects_map(db_path)

    size = max(2, population_size)
    if seed_deck:
        # コンボ骨格などを起点に周辺を進化させる: 半分はシードの変異、半分は新規
        half = max(1, size // 2)
        population = [seed_deck] + [
            _consolidating_mutate(seed_deck, pool, cards_by_id, rng, max_card_types)
            for _ in range(half - 1)
        ]
        population += [_initial_deck(pool, cards_by_id, rng, max_card_types) for _ in range(size - len(population))]
    else:
        population = [_initial_deck(pool, cards_by_id, rng, max_card_types) for _ in range(size)]

    history: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    elite_count = max(1, len(population) // 3)

    for generation in range(1, max(1, generations) + 1):
        if rotate_opponents:
            opponents = _opponents_for_generation(shuffled_meta, generation, sim_opponents, rotation_period)
        else:
            opponents = fixed_opponents
        evaluated = []
        for deck in population:
            heuristic = float(evaluate_deck(deck)["score"])
            win_rate, fire_rate = _simulated_metrics(deck, opponents, sim_games, rng.random(), effects)
            assembly = 0.0
            if chain:
                # コンボ成立率を選別関数に組み込み、安定性を上げる方向の進化圧をかける
                assembly = validate_chain_playable(
                    chain, deck, trials=60, max_turns=8,
                    seed=int(rng.random() * 100000), effects=effects,
                )["success_rate"]
            # 適応度 = 勝率 + chain成立率 + エンジン発火率 + ヒューリスティックの加重合成。
            # chain/engineの比重はsim_weightから差し引く(勝率と同じ「実走シグナル」のため)
            chain_share = chain_weight if chain else 0.0
            engine_share = max(0.0, engine_weight)
            win_share = max(0.0, sim_weight - chain_share - engine_share)
            heuristic_share = max(0.0, 1 - win_share - chain_share - engine_share)
            combined = round(
                win_rate * 100 * win_share
                + assembly * 100 * chain_share
                + fire_rate * 100 * engine_share
                + heuristic * heuristic_share,
                2,
            )
            evaluated.append(
                {
                    "deck": deck,
                    "heuristic_score": heuristic,
                    "sim_win_rate": round(win_rate, 4),
                    "engine_fire_rate": round(fire_rate, 4),
                    "assembly_rate": round(assembly, 4),
                    "combined_score": combined,
                }
            )
        evaluated.sort(key=lambda item: item["combined_score"], reverse=True)
        top = evaluated[0]
        if best is None or top["combined_score"] > best["combined_score"]:
            best = top
        history.append(
            {
                "generation": generation,
                "best_combined": top["combined_score"],
                "best_sim_win_rate": top["sim_win_rate"],
                "best_engine_fire_rate": top.get("engine_fire_rate", 0.0),
                "best_assembly_rate": top.get("assembly_rate", 0.0),
                "best_heuristic": top["heuristic_score"],
                "opponents": [deck["deck_name"] for deck in opponents],
            }
        )

        elites = [entry["deck"] for entry in evaluated[:elite_count]]
        next_population = elites[:]
        while len(next_population) < len(population):
            parent = rng.choice(elites)
            child = _consolidating_mutate(parent, pool, cards_by_id, rng, max_card_types)
            if locked:
                child = _enforce_locked(child, locked, pool, cards_by_id, rng)
            next_population.append(child)
        population = next_population

    return {
        "best": best,
        "history": history,
        "opponents": sorted({name for entry in history for name in entry["opponents"]}),
        "rotate_opponents": rotate_opponents,
        "sim_weight": sim_weight,
        "sim_games": sim_games,
        "warnings": warnings,
    }

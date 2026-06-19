from __future__ import annotations

import json
import random
import re
import sqlite3
import unittest
from pathlib import Path

from src.battle.kernel.cards import BattleCard
from src.battle.kernel.engine import DuelEngine
from src.battle.kernel.policy import Policy
from src.battle.kernel.state import CreatureInstance
from src.battle.rating.store import DEFAULT_DB_PATH

# exact 化されたカードは「現実と1対1」で忠実に動くことが前提。ここでは DB 上の全 exact
# カードについて、(1) 使う op がすべてエンジンで実行可能か、(2) 各トリガーが実行時に
# 例外を出さないか、を検証する。マラソンで積み上げた exact 群の退行を防ぐ防壁。

_EXECUTOR_SRC = (
    Path(__file__).resolve().parent.parent
    / "src" / "battle" / "kernel" / "effect_executor.py"
)


def _supported_ops() -> set[str]:
    src = _EXECUTOR_SRC.read_text(encoding="utf-8")
    return set(re.findall(r'op == "([a-z_]+)"', src))


def _ops_in_actions(actions: list[dict]) -> set[str]:
    ops: set[str] = set()
    for action in actions:
        op = action.get("op")
        if op:
            ops.add(op)
        if op == "modal_choice":
            for option in action.get("options", []):
                ops |= _ops_in_actions(option)
    return ops


def _load_exact_cards() -> list[tuple[str, str, list[dict]]]:
    if not Path(DEFAULT_DB_PATH).exists():
        return []
    con = sqlite3.connect(DEFAULT_DB_PATH)
    try:
        rows = con.execute(
            "select c.name, c.card_type, e.effect_json "
            "from cards c join card_effects e on c.card_id = e.card_id "
            "where e.fidelity = 'exact'"
        ).fetchall()
    finally:
        con.close()
    out: list[tuple[str, str, list[dict]]] = []
    for name, card_type, ej in rows:
        try:
            abilities = json.loads(ej).get("abilities", [])
        except (ValueError, TypeError):
            continue
        out.append((name, card_type or "クリーチャー", abilities))
    return out


class _Stub(Policy):
    def choose_charge(self, state, player):
        return None

    def choose_main_action(self, state, player, playable):
        return None

    def choose_attack(self, state, player, choices):
        return None

    def choose_blocker(self, state, player, attack, blockers):
        return None


def _filler(name: str, index: int, civ: str = "火") -> BattleCard:
    return BattleCard(
        card_id=name, name=name, civilizations=(civ,),
        cost=(index % 6) + 1, card_type="クリーチャー", power=((index % 6) + 1) * 1000,
    )


def _deck(civ: str = "火") -> list[BattleCard]:
    return [_filler(f"{civ}{i:02d}", i, civ) for i in range(40)]


class ExactCardsExecutableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.exact = _load_exact_cards()
        cls.supported = _supported_ops()

    def test_all_exact_ops_are_executable(self) -> None:
        if not self.exact:
            self.skipTest("cards.db not available")
        offenders: dict[str, list[str]] = {}
        for name, _ct, abilities in self.exact:
            for ability in abilities:
                for op in _ops_in_actions(ability.get("actions", [])):
                    if op != "modal_choice" and op not in self.supported:
                        offenders.setdefault(op, []).append(name)
        self.assertEqual(
            offenders, {},
            msg=f"exact cards use ops the executor cannot handle: "
                f"{ {op: names[:3] for op, names in offenders.items()} }",
        )

    def test_all_exact_triggers_execute_without_crashing(self) -> None:
        if not self.exact:
            self.skipTest("cards.db not available")
        crashes: list[str] = []
        for name, card_type, abilities in self.exact:
            if not abilities:
                continue
            card = BattleCard(
                card_id=name, name=name, civilizations=("火",),
                cost=5, card_type=card_type, power=5000,
            )
            for trigger in {a.get("trigger") for a in abilities}:
                try:
                    engine = DuelEngine(
                        _deck(), _deck("水"), _Stub(), _Stub(),
                        rng=random.Random(7), effects={name: abilities},
                    )
                    for pi in (0, 1):
                        zone = engine.state.players[pi].battle_zone
                        for k in range(3):
                            zone.append(CreatureInstance(
                                card=_filler(f"bz{pi}{k}", k, "水" if pi else "火"),
                                summoned_turn=1,
                            ))
                    engine.state.players[0].battle_zone.append(
                        CreatureInstance(card=card, summoned_turn=1)
                    )
                    engine.executor.run(engine, 0, trigger, card)
                except Exception as exc:  # noqa: BLE001 - report which card/trigger broke
                    crashes.append(f"{name} [{trigger}]: {exc!r}")
        self.assertEqual(crashes, [], msg=f"exact card effects crashed: {crashes[:10]}")


if __name__ == "__main__":
    unittest.main()

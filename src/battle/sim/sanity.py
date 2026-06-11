from __future__ import annotations

from typing import Any

from src.battle.kernel.cards import BattleCard
from src.battle.sim.runner import simulate_matches

# 実戦ログなしでシミュレーターの妥当性を監視するための方向性チェック。
# 「明らかに正しいはずの定性的な関係」が破れたら、カーネルや方策の退行を疑う。


def _card(name: str, cost: int, power: int = 0, card_type: str = "クリーチャー", text: str = "", civ: str = "火") -> BattleCard:
    return BattleCard(
        card_id=name, name=name, civilizations=(civ,), cost=cost,
        card_type=card_type, power=power, text=text,
    )


def _curve_deck(civ: str = "火") -> list[BattleCard]:
    return [
        _card(f"{civ}曲線{i}", cost=(i % 5) + 1, power=((i % 5) + 1) * 1000, civ=civ)
        for i in range(40)
    ]


def run_sanity_checks(games: int = 200, seed: int = 1) -> list[dict[str, Any]]:
    """方向性チェック一式を実行し、各チェックの結果を返す。"""
    checks: list[dict[str, Any]] = []

    def add(name: str, win_rate: float, expect: str, threshold: float) -> None:
        passed = win_rate > threshold if expect == ">" else win_rate < threshold
        checks.append(
            {
                "name": name,
                "win_rate_a": round(win_rate, 3),
                "expect": f"{expect} {threshold}",
                "passed": passed,
            }
        )

    # 1. 整ったカーブは鈍重(6コストのみ)デッキに勝ち越す
    heavy = [_card(f"鈍重{i}", cost=6, power=6000) for i in range(40)]
    s = simulate_matches(_curve_deck(), heavy, games=games, seed=seed)
    add("カーブデッキ > 6コスト単一デッキ", s.win_rate_a, ">", 0.65)

    # 2. 軽量速攻はさらに重い(7コストのみ)デッキを轢き切る
    rush = [_card(f"速攻{i}", cost=(i % 2) + 1, power=((i % 2) + 1) * 1000) for i in range(40)]
    heavier = [_card(f"超鈍重{i}", cost=7, power=9000) for i in range(40)]
    s = simulate_matches(rush, heavier, games=games, seed=seed)
    add("軽量速攻 > 7コスト単一デッキ", s.win_rate_a, ">", 0.8)

    # 3. S・トリガー除去を積んだ側は、同型のバニラ構成に勝ち越す
    effects = {
        f"トリガー除去{i}": [
            {"trigger": "s_trigger", "actions": [{"op": "destroy_creature", "count": 1, "scope": "opponent"}]},
            {"trigger": "on_cast", "actions": [{"op": "destroy_creature", "count": 1, "scope": "opponent"}]},
        ]
        for i in range(8)
    }
    with_triggers = _curve_deck()[:32] + [
        _card(f"トリガー除去{i}", cost=4, card_type="呪文", text="S・トリガー") for i in range(8)
    ]
    s = simulate_matches(with_triggers, _curve_deck(), games=games, seed=seed, effects=effects)
    add("トリガー除去入り > 同型バニラ", s.win_rate_a, ">", 0.55)

    # 4. ブロッカー8枚を積んだ側は速攻への勝率がバニラ同型より高い
    blockers = _curve_deck()[:32] + [
        _card(f"壁{i}", cost=3, power=4000, text="ブロッカー このクリーチャーは攻撃できない。") for i in range(8)
    ]
    s_wall = simulate_matches(blockers, rush, games=games, seed=seed)
    s_vanilla = simulate_matches(_curve_deck(), rush, games=games, seed=seed)
    checks.append(
        {
            "name": "ブロッカー入りは対速攻勝率がバニラ同型より高い",
            "win_rate_a": round(s_wall.win_rate_a, 3),
            "expect": f"> バニラ {round(s_vanilla.win_rate_a, 3)}",
            "passed": s_wall.win_rate_a > s_vanilla.win_rate_a,
        }
    )

    # 5. 同一デッキのミラーは五分(45〜55%)に収まる(先攻交代の公平性)
    s = simulate_matches(_curve_deck(), _curve_deck("水"), games=games, seed=seed)
    mirror = simulate_matches(_curve_deck(), [
        _card(f"火曲線B{i}", cost=(i % 5) + 1, power=((i % 5) + 1) * 1000) for i in range(40)
    ], games=games, seed=seed)
    checks.append(
        {
            "name": "実質ミラーの勝率が45〜55%に収まる",
            "win_rate_a": round(mirror.win_rate_a, 3),
            "expect": "0.45〜0.55",
            "passed": 0.45 <= mirror.win_rate_a <= 0.55,
        }
    )

    # 6. 同一ステータスでW・ブレイカーの有無だけが違えば、持つ側が勝ち越す
    #    (カーブを変えずキーワードだけ付与して交絡を避ける)
    base = _curve_deck()
    breakers = [
        _card(card.name + "WB", cost=card.cost, power=card.power, text="W・ブレイカー")
        if card.cost == 5
        else card
        for card in base
    ]
    # ブレイクは相手の手札を増やすため、バニラ環境では利得が小さいのが正常。
    # 「大きく不利になっていないこと」を退行検知の下限として監視する。
    s = simulate_matches(breakers, base, games=games, seed=seed)
    add("W・ブレイカー付与(同ステータス)が不利になっていない", s.win_rate_a, ">", 0.45)

    return checks

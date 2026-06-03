"""ケロヨン・カルテット4体特殊勝利デッキの簡易ゴールドフィッシュ検証。

相手の妨害が無い理想盤面で、マナ加速→ケロヨン連続召喚で「何ターン目に
ケロヨンが4体並ぶか」をモンテカルロで測る。speed寄り構成の実効性確認用。

簡略モデル:
- 毎ターン1ドロー+1チャージ(手札からマナゾーンへ、ケロヨンは温存)
- マナ加速カードはプレイすると即マナ+1(山札からマナゾーン、当ターンも使用可)
- アクロパッド(コスト軽減)は各ターン最初のケロヨン召喚を-1(多色は最低3)
- ケロヨンは召喚するとゲーム外から1枚手札に補充、盤面+1
- 盤面ケロヨン4体になった次のターン開始時に勝利
- 受け札(defense)はソロでは使わずチャージ要員扱い

実行: python -m scripts.simulate_keroyon
"""
from __future__ import annotations

import random
import statistics
from collections import Counter


def build_deck() -> list[dict]:
    deck: list[dict] = []

    def add(name, count, cost, kind, ramp=0):
        for _ in range(count):
            deck.append({"name": name, "cost": cost, "kind": kind, "ramp": ramp})

    add("ケロヨン・カルテット", 4, 4, "keroyon")
    add("フェアリー・ライフ", 4, 2, "ramp", 1)
    add("霞み妖精ジャスミン", 4, 2, "ramp", 1)
    add("フェアリー・ミラクル", 4, 3, "ramp", 1)
    add("霊騎幻獣ウルコス", 4, 3, "ramp", 1)
    add("豊潤フォージュン", 2, 3, "ramp_draw", 1)  # マナ加速+条件ドロー
    add("海獣妖精マグナリア", 3, 3, "ramp_draw", 1)  # マナ加速orドロー(アクセス安定)
    add("虹彩奪取 アクロパッド", 4, 2, "reducer")
    add("フェアリー・シャワー", 4, 4, "ramp_draw", 1)  # サーチ+マナ(手打ち)
    add("時を戻す水時計", 2, 1, "defense")
    add("アクア・サーファー", 3, 6, "defense")
    add("スパイラル・スライダー", 2, 2, "defense")
    return deck


def simulate_once(rng: random.Random, max_turns: int = 20) -> int | None:
    deck = build_deck()
    rng.shuffle(deck)
    hand = deck[:5]
    pos = 5
    mana_total = 0
    board_keroyon = 0
    reducers = 0

    for turn in range(1, max_turns + 1):
        if board_keroyon >= 4:
            return turn

        # ドロー
        if pos < len(deck):
            hand.append(deck[pos])
            pos += 1

        # チャージ(ケロヨン以外を優先、無ければケロヨン)
        if hand:
            idx = next((i for i, c in enumerate(hand) if c["kind"] != "keroyon"), 0)
            hand.pop(idx)
            mana_total += 1

        avail = mana_total
        first_keroyon = True
        progressed = True
        while progressed:
            progressed = False
            # 1) マナ加速を最優先(ramp_drawはドローも行いアクセスを安定させる)
            for i, c in enumerate(hand):
                if c["kind"] in ("ramp", "ramp_draw") and c["cost"] <= avail:
                    avail -= c["cost"]
                    mana_total += c["ramp"]
                    avail += c["ramp"]
                    if c["kind"] == "ramp_draw" and pos < len(deck):
                        hand.append(deck[pos])
                        pos += 1
                    hand.pop(i)
                    progressed = True
                    break
            if progressed:
                continue
            # 2) コスト軽減を設置
            for i, c in enumerate(hand):
                if c["kind"] == "reducer" and c["cost"] <= avail:
                    avail -= c["cost"]
                    reducers += 1
                    hand.pop(i)
                    progressed = True
                    break
            if progressed:
                continue
            # 3) ケロヨン召喚
            for i, c in enumerate(hand):
                if c["kind"] == "keroyon":
                    cost = c["cost"]
                    if first_keroyon and reducers >= 1:
                        cost = max(3, cost - 1)
                    if cost <= avail:
                        avail -= cost
                        board_keroyon += 1
                        hand.pop(i)
                        hand.append({"name": "ケロヨン・カルテット", "cost": 4, "kind": "keroyon"})
                        first_keroyon = False
                        progressed = True
                        break

    return None


def main() -> None:
    rng = random.Random(20260604)
    trials = 5000
    win_turns: list[int] = []
    dist: Counter[str] = Counter()

    for _ in range(trials):
        t = simulate_once(rng)
        if t is None:
            dist["未達(20T)"] += 1
        else:
            win_turns.append(t)
            dist[f"{t}T"] += 1

    print(f"試行回数: {trials}")
    print(f"勝利(4体到達)率: {len(win_turns)/trials*100:.1f}%")
    if win_turns:
        print(f"平均勝利ターン: {statistics.mean(win_turns):.2f}")
        print(f"中央値: {int(statistics.median(win_turns))}T")
        print(f"最速: {min(win_turns)}T / 最遅: {max(win_turns)}T")
    print("--- 勝利ターン分布 ---")
    for key in sorted(dist, key=lambda k: (k == "未達(20T)", int(k.rstrip("T")) if k[0].isdigit() else 999)):
        cnt = dist[key]
        bar = "#" * int(cnt / trials * 100)
        print(f"  {key:>9}: {cnt:>4} ({cnt/trials*100:4.1f}%) {bar}")


if __name__ == "__main__":
    main()

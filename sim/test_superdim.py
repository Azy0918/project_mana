"""超次元ゾーン実装の動作テスト。
パース / ゾーン召喚 / 破壊時のゾーン帰還 / ホール詠唱の一連を検証する。"""
import random

from duel_masters import carddb, superdim
from duel_masters.engine import Game, Player, CAST, CardDef, CREATURE
from duel_masters.agents import HeuristicAgent

PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {label}")
    else:
        FAIL += 1
        print(f"  NG  {label}")


def main():
    pool = carddb.load_pool()              # ND メイン
    spool = carddb.load_super_pool()        # サイキック骨格
    attached = superdim.attach_hole_abilities(pool)
    print(f"サイキック骨格 {len(spool)} 種 / ホール召喚を付与した呪文 {len(attached)} 件")

    # --- パース検査(実本文) ---
    samples = attached[:5]
    for name in samples:
        spec = superdim.parse_hole(pool[name].text)
        print(f"  parse {name}: {spec}")
    check(len(attached) >= 3, "ND プールに3件以上のホールを検出")
    check(all(superdim.parse_hole(pool[n].text) for n in attached),
          "付与した全ホールが再パース可能")

    # --- ゾーン召喚 / 帰還(エンジン直接) ---
    rng = random.Random(1)
    p0 = Player("A", HeuristicAgent("A", rng))
    p1 = Player("B", HeuristicAgent("B", rng))
    zone_names = list(spool)[:8]
    p0.super_zone = carddb.build_super_zone(spool, p0, zone_names)
    g = Game(p0, p1, rng=rng)

    before = len(p0.super_zone)
    summoned = g.summon_from_super_zone(p0, max_cost=99, count=1)
    check(len(summoned) == 1, "1体召喚できた")
    check(len(p0.super_zone) == before - 1, "超次元ゾーンが1枚減った")
    check(summoned and summoned[0] in p0.battle, "召喚体がバトルゾーンに居る")
    check(summoned and summoned[0].zone == "battle", "zone=battle になった")

    psy = summoned[0]
    g.destroy(psy)
    check(psy in p0.super_zone, "破壊後に超次元ゾーンへ戻った")
    check(psy not in p0.battle, "破壊後バトルゾーンに居ない")
    check(psy.zone == "super_zone", "zone=super_zone に戻った")
    check(len(p0.graveyard) == 0, "墓地には行っていない")

    # --- 合計コスト制約の召喚 ---
    p0.super_zone = carddb.build_super_zone(spool, p0, zone_names)
    s2 = g.summon_from_super_zone(p0, count=8, total_cost=10)
    check(sum(c.cost for c in s2) <= 10, f"合計コスト制約を満たす(合計{sum(c.cost for c in s2)})")
    check(len(s2) >= 1, "合計コスト型でも1体以上出た")

    # --- ホール詠唱の一連(CAST能力経由) ---
    # civs 指定の緩いホールを1つ選び、その条件を満たすゾーンを用意して詠唱
    cast_ok = False
    for name in attached:
        cd = pool[name]
        spec = superdim.parse_hole(cd.text)
        cands = [n for n, c in spool.items()
                 if c.cost <= spec["max_cost"]
                 and (not spec["civs"] or set(c.civs) & spec["civs"])
                 and (not spec["races"]
                      or any(any(r in cr for cr in c.races) for r in spec["races"]))]
        if len(cands) >= 2:
            pc = Player("C", HeuristicAgent("C", rng))
            pd = Player("D", HeuristicAgent("D", rng))
            pc.super_zone = carddb.build_super_zone(spool, pc, cands[:8])
            gg = Game(pc, pd, rng=rng)
            hole = carddb.make(pool, name, pc)
            n_before = len(pc.battle)
            for ab in cd.abilities:
                if ab.event == CAST:
                    ab.resolve(gg, pc, hole)
            if len(pc.battle) > n_before:
                cast_ok = True
                print(f"  詠唱 {name} → 召喚 {[str(c) for c in pc.battle]}")
                break
    check(cast_ok, "ホール詠唱でサイキックが場に出た")

    # --- パーサ精度: 選択型/二系統コストホール ---
    if "超次元ガロウズ・ホール" in pool:
        gh = superdim.parse_hole(pool["超次元ガロウズ・ホール"].text)
        check(gh is not None and gh["max_cost"] != 99,
              f"選択型ホールで max_cost を取得(gh={gh})")
        check(gh is not None and gh["count"] >= 2,
              "二系統コスト『1枚ずつ』を2体と解釈")

    # --- 覚醒: リンク抽出 / 反転メカニズム / ターン終了フック ---
    links = superdim.build_awaken_links(spool)
    print(f"覚醒リンク抽出: {len(links)} 件 (例: "
          + ", ".join(f"{k}→{v}" for k, v in list(links.items())[:2]) + ")")
    check(len(links) >= 5, "覚醒リンク(前→後名)を5件以上抽出")
    if "ガロウズ・セブ・カイザー" in spool:
        tgt = superdim.parse_awaken_link(spool["ガロウズ・セブ・カイザー"].text)
        check(tgt == "死海竜ガロウズ・デビルドラゴン", f"ガロウズの覚醒後名を抽出(={tgt})")

    # 反転メカニズム: 手書きの覚醒後フォーム(スタッツはAPI制約で手入力前提)
    base_name = list(spool)[0]
    awem = Player("E", HeuristicAgent("E", rng))
    awem.super_zone = carddb.build_super_zone(spool, awem, [base_name])
    awo = Player("F", HeuristicAgent("F", rng))
    gA = Game(awem, awo, rng=rng)
    superdim.install_awaken_hook(gA)
    summ = gA.summon_from_super_zone(awem, count=1)
    on_field = summ[0]
    uid0 = on_field.uid
    awakened_def = CardDef(cid="AWK", name="《覚醒後デモ》", cost=on_field.cost,
                           civs=on_field.civs, ctype=CREATURE,
                           power=(on_field.power or 0) + 5000,
                           keywords=frozenset({"w_breaker"}), psychic=True)
    superdim.register_awaken(on_field.name, lambda gm, c: True, awakened_def)
    superdim.turn_end_awaken(gA, awem)
    check(on_field.name == "《覚醒後デモ》", "ターン終了フックで覚醒(反転)した")
    check(on_field.uid == uid0, "覚醒しても実体(uid)は同一")
    check(on_field.power == (awakened_def.power), "覚醒後パワーに更新された")
    # 覚醒後も離場で超次元ゾーンへ戻る
    gA.destroy(on_field)
    check(on_field in awem.super_zone, "覚醒後も破壊で超次元ゾーンへ戻る")
    superdim.AWAKEN_REGISTRY.clear()

    print(f"\n{'ALL PASS' if FAIL == 0 else 'FAILED'} ({PASS} ok / {FAIL} ng)")
    return FAIL == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)

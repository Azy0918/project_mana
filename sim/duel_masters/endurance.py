"""
duel_masters.endurance
=======================
GA(ga.py)を**壁時計時間でぶん回す「耐久モード」**。evolve() の構成要素を流用
しつつ、長時間の無人運転で効くものを足してある:

  1) 連続進化      : 世代を跨いで個体群を持ち越し、エポックを重ねて探索を続ける。
  2) 殿堂(HoF)     : これまでの最良デッキを保存(deck_key で重複排除)。
  3) 共進化        : ガントレットに HoF を定期注入。固定相手への過学習(=じゃんけん
                     勝ち)を抑える。選択圧は base+HoF、順位付けは base のみ(安定軸)。
  4) チェックポイント: エポックごとに JSON とレポートを UTF-8 で原子的に保存。
                     途中でプロセスが落ちても直前のエポックまでの発見は残る。

判定土台は nd_legal(carddb)、対象軸はビートジョッキー敗北拒否(火単)。
発見デッキは「ルールエンジンのバグでだけ勝つ」可能性があるので、最後は人間が再生検証。

使い方:
  PYTHONPATH=sim python -m duel_masters.endurance --hours 4
  PYTHONPATH=sim python -m duel_masters.endurance --hours 0.02   # スモークテスト(~1分)
"""
from __future__ import annotations
import argparse
import json
import os
import random
import time
from collections import Counter
from datetime import datetime, timezone, timedelta

from . import ga
from . import gauntlet as gauntlet_mod

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_dur(sec: float) -> str:
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}"


def _atomic_write(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _deck_payload(pool, deck) -> dict:
    """JSON 用にデッキを {cards:{name:n}, lines:[...]} へ。"""
    return {
        "cards": dict(deck),
        "lines": ga.describe(pool, deck).splitlines(),
    }


class Endurance:
    def __init__(self, *, hours, pop, games, gens_per_epoch, elite_frac,
                 hof_size, hof_inject, seed, outdir, log):
        self.hours = hours
        self.pop = pop
        self.games = games
        self.gens_per_epoch = gens_per_epoch
        self.elite_frac = elite_frac
        self.hof_size = hof_size
        self.hof_inject = hof_inject
        self.seed = seed
        self.outdir = outdir
        self._log_path = log

        self.rng = random.Random(seed)
        self.pool, self.cand = ga.build_pools()
        # 安定した順位付け軸: 人間風アーキタイプ・ガントレット(戦略の異なる固定4デッキ)。
        named = gauntlet_mod.build_human_gauntlet(self.pool, self.cand)
        self.gauntlet_names = [nm for nm, _ in named]
        self.base_gauntlet = [d for _, d in named]
        # HoF: [(ref_fitness, deck)] を ref_fitness 降順で保持。
        self.hof = []
        self.population = [ga.random_deck(self.cand, self.rng)
                           for _ in range(self.pop)]
        # base ガントレットに対する適応度キャッシュ(安定・全期間有効)。
        self._ref_cache = {}

    # ---- 適応度 ----------------------------------------------------------
    def fit_ref(self, ind):
        """base ガントレットに対する勝率(安定・HoF 順位と報告用)。"""
        k = ga.deck_key(ind)
        c = self._ref_cache.get(k)
        if c is None:
            c = ga.fitness(self.pool, ind, self.base_gauntlet, games=self.games)
            self._ref_cache[k] = c
        return c

    # ---- ログ ------------------------------------------------------------
    def log(self, msg: str) -> None:
        line = f"[{_now_jst()}] {msg}"
        print(line, flush=True)
        if self._log_path:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    # ---- HoF -------------------------------------------------------------
    def _update_hof(self, candidates) -> None:
        seen = {ga.deck_key(d) for _, d in self.hof}
        for deck in candidates:
            k = ga.deck_key(deck)
            if k in seen:
                continue
            seen.add(k)
            self.hof.append((self.fit_ref(deck), Counter(deck)))
        self.hof.sort(key=lambda t: t[0], reverse=True)
        del self.hof[self.hof_size:]

    def _injected_gauntlet(self):
        inject = [d for _, d in self.hof[:self.hof_inject]]
        return self.base_gauntlet + inject

    # ---- 1エポック(数世代の進化) ----------------------------------------
    def _run_epoch(self, epoch, deadline):
        gauntlet = self._injected_gauntlet()
        evo_cache = {}  # この共進化ガントレットに対する適応度(エポック内のみ有効)

        def fit_evo(ind):
            k = ga.deck_key(ind)
            v = evo_cache.get(k)
            if v is None:
                v = ga.fitness(self.pool, ind, gauntlet, games=self.games)
                evo_cache[k] = v
            return v

        n_elite = max(1, int(self.pop * self.elite_frac))
        gens_done = 0
        for g in range(self.gens_per_epoch):
            if time.time() >= deadline:
                break
            scored = sorted(self.population, key=fit_evo, reverse=True)
            best = scored[0]
            med = fit_evo(scored[len(scored) // 2])
            self.log(f"  epoch {epoch} gen {g}: best(evo) {fit_evo(best):.3f} "
                     f"median {med:.3f} / best(ref) {self.fit_ref(best):.3f} "
                     f"[gauntlet {len(gauntlet)} / 評価 {len(self._ref_cache)}]")
            newpop = list(scored[:n_elite])
            while len(newpop) < self.pop:
                a = ga._tournament(scored, fit_evo, self.rng)
                b = ga._tournament(scored, fit_evo, self.rng)
                child = ga.mutate(ga.crossover(a, b, self.cand, self.rng),
                                  self.cand, self.rng)
                newpop.append(child)
            self.population = newpop
            gens_done = g + 1

        # このエポックの上位を HoF 候補に。
        top = sorted(self.population, key=self.fit_ref, reverse=True)[:n_elite]
        self._update_hof(top)
        return gens_done

    # ---- チェックポイント ------------------------------------------------
    def checkpoint(self, *, epoch, elapsed, remaining, total_gens, reason):
        best_ref, best_deck = self.hof[0]
        payload = {
            "schema": "mana-endurance/1",
            "updated_jst": _now_jst(),
            "reason": reason,
            "config": {
                "hours": self.hours, "pop": self.pop, "games": self.games,
                "gens_per_epoch": self.gens_per_epoch,
                "elite_frac": self.elite_frac, "hof_size": self.hof_size,
                "hof_inject": self.hof_inject, "seed": self.seed,
            },
            "progress": {
                "epoch": epoch, "total_generations": total_gens,
                "elapsed": _fmt_dur(elapsed), "remaining": _fmt_dur(remaining),
                "decks_evaluated": len(self._ref_cache),
            },
            "best": {"ref_fitness": best_ref, **_deck_payload(self.pool, best_deck)},
            "hall_of_fame": [
                {"rank": i + 1, "ref_fitness": fitv,
                 **_deck_payload(self.pool, d)}
                for i, (fitv, d) in enumerate(self.hof)
            ],
        }
        _atomic_write(os.path.join(self.outdir, "checkpoint.json"),
                      json.dumps(payload, ensure_ascii=False, indent=2))
        self._write_report(payload)

    def _write_report(self, payload):
        b = payload["best"]
        lines = [
            "Project MANA — GA 耐久モード 発見デッキ",
            "=" * 52,
            f"更新(JST): {payload['updated_jst']}   理由: {payload['reason']}",
            f"経過 {payload['progress']['elapsed']} / 残り "
            f"{payload['progress']['remaining']}   "
            f"エポック {payload['progress']['epoch']}  "
            f"累計世代 {payload['progress']['total_generations']}  "
            f"評価デッキ {payload['progress']['decks_evaluated']}",
            "",
            f"■ 暫定ベスト  base勝率 {b['ref_fitness']:.3f}",
            *b["lines"],
            "",
            "■ 殿堂 (Hall of Fame)  ※base固定ガントレット勝率で順位付け",
        ]
        for h in payload["hall_of_fame"]:
            lines.append(f"  #{h['rank']}  base勝率 {h['ref_fitness']:.3f}  "
                         f"({sum(h['cards'].values())}枚 "
                         f"{len(h['cards'])}種)")
        _atomic_write(os.path.join(self.outdir, "report.txt"),
                      "\n".join(lines) + "\n")

    # ---- メインループ ----------------------------------------------------
    def run(self):
        start = time.time()
        deadline = start + self.hours * 3600
        self.log(f"耐久モード開始: {self.hours}時間 / pop={self.pop} "
                 f"games={self.games} gens/epoch={self.gens_per_epoch} "
                 f"seed={self.seed}")
        self.log(f"出力先: {self.outdir}")
        self.log(f"候補カード {len(self.cand)} 種 / 人間風ガントレット "
                 f"{len(self.base_gauntlet)} デッキ: "
                 + " / ".join(self.gauntlet_names))

        epoch = 0
        total_gens = 0
        reason = "completed"
        try:
            while time.time() < deadline:
                epoch += 1
                gens = self._run_epoch(epoch, deadline)
                total_gens += gens
                elapsed = time.time() - start
                remaining = max(0.0, deadline - time.time())
                if self.hof:
                    self.checkpoint(epoch=epoch, elapsed=elapsed,
                                    remaining=remaining, total_gens=total_gens,
                                    reason="running")
                    best_ref = self.hof[0][0]
                    self.log(f"epoch {epoch} 完了: HoF最良(base勝率) "
                             f"{best_ref:.3f} / 殿堂 {len(self.hof)}件 / "
                             f"残り {_fmt_dur(remaining)}")
        except KeyboardInterrupt:
            reason = "interrupted"
            self.log("中断シグナルを受信。最終チェックポイントを書き出します。")

        elapsed = time.time() - start
        if self.hof:
            self.checkpoint(epoch=epoch, elapsed=elapsed, remaining=0.0,
                            total_gens=total_gens, reason=reason)
            best_ref, best_deck = self.hof[0]
            self.log(f"=== 終了({reason}) 経過 {_fmt_dur(elapsed)} / "
                     f"累計 {total_gens} 世代 / 評価 {len(self._ref_cache)} デッキ ===")
            self.log(f"最良デッキ base勝率 {best_ref:.3f}:")
            for ln in ga.describe(self.pool, best_deck).splitlines():
                self.log(ln)
        else:
            self.log("HoF が空のまま終了しました(実行時間が短すぎる可能性)。")
        return self.hof


def main():
    ap = argparse.ArgumentParser(description="Project MANA GA 耐久モード")
    ap.add_argument("--hours", type=float, default=4.0, help="壁時計の実行時間")
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--games", type=int, default=8,
                    help="1対戦相手あたりの試行数(先攻/後攻 各この数)")
    ap.add_argument("--gens-per-epoch", type=int, default=5)
    ap.add_argument("--elite-frac", type=float, default=0.25)
    ap.add_argument("--hof-size", type=int, default=10)
    ap.add_argument("--hof-inject", type=int, default=3,
                    help="ガントレットに注入する HoF 上位数(共進化)")
    ap.add_argument("--seed", type=int, default=None,
                    help="省略時は時刻ベース(毎回違う探索)")
    ap.add_argument("--outdir", type=str, default=None,
                    help="省略時は sim/runs/endurance_<JST時刻>/")
    args = ap.parse_args()

    seed = args.seed if args.seed is not None else int(time.time()) & 0x7FFFFFFF
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # sim/
    if args.outdir:
        outdir = args.outdir
    else:
        stamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
        outdir = os.path.join(here, "runs", f"endurance_{stamp}")
    os.makedirs(outdir, exist_ok=True)

    eng = Endurance(
        hours=args.hours, pop=args.pop, games=args.games,
        gens_per_epoch=args.gens_per_epoch, elite_frac=args.elite_frac,
        hof_size=args.hof_size, hof_inject=args.hof_inject, seed=seed,
        outdir=outdir, log=os.path.join(outdir, "log.txt"),
    )
    eng.run()


if __name__ == "__main__":
    main()

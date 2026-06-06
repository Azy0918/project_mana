"""
src.fetch_superdim_cards
========================
公式DMPS API から「超次元ゾーン」のカード(サイキック・クリーチャー/ドラグハート等)を
取得して CSV に書き出す。

背景: 既定の検索(card_type[]=ALL)は超次元ゾーンを返さず、メインDB(5178枚)に
サイキック・クリーチャーは0件だった。調査の結果、card_type[] に超次元ゾーンの
種別値を明示すると取得できると判明(各カードは super_dimensional_zone_flag=1)。

出力は fetch_dmps_official_cards.normalize_card と同じスキーマなので、メインの
取り込み経路(import_cards / repair) にそのまま乗せられる。SSL傍受環境では
MANA_INSECURE_SSL=1 を併用([[dmps-fetch-ssl-bypass]])。

使い方:
  MANA_INSECURE_SSL=1 python -m src.fetch_superdim_cards --out data/cards_superdim_raw.csv
"""
from __future__ import annotations
import argparse
import csv
from pathlib import Path

from src.fetch_dmps_official_cards import (
    make_session, fetch_page, post_json, parse_form_params,
    deep_find_cards, deep_find_total, normalize_card,
    TOKEN_URL, FORM_URL, SEARCH_URL,
)

# 超次元ゾーンに置かれる card_type 値の候補。0件のものは自動でスキップする。
SUPERDIM_CARD_TYPES = [
    "サイキック・クリーチャー",
    "サイキック・スーパー・クリーチャー",
    "ドラグハート・クリーチャー",
    "ドラグハート・フォートレス",
    "ドラグハート・ウエポン",
]


def fetch_card_type(session, base, csrf, card_type, *, limit=50, sleep=0.2):
    """指定 card_type の全カードをページ送りで取得(card_id で重複排除)。"""
    import time
    drop = {"page", "limit", "csrf", "card_type[]"}
    base_params = [(k, v) for k, v in base if k not in drop]
    base_params.append(("card_type[]", card_type))

    all_cards, seen = [], set()
    page = 1
    total = None
    while True:
        params = base_params + [("csrf", csrf), ("limit", str(limit)),
                                ("page", str(page))]
        r = session.post(SEARCH_URL, data=params, timeout=45)
        if r.status_code != 200:
            break
        obj = r.json()
        if total is None:
            total = deep_find_total(obj)
        cards = deep_find_cards(obj)
        if not cards:
            break
        added = 0
        for c in cards:
            cid = str(c.get("card_id", ""))
            if cid and cid in seen:
                continue
            if cid:
                seen.add(cid)
            all_cards.append(c)
            added += 1
        if added == 0:
            break
        if total and len(all_cards) >= total:
            break
        page += 1
        time.sleep(sleep)
    return all_cards, total


def write_csv(path: Path, cards):
    rows = [normalize_card(c) for c in cards]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="公式DMPS APIから超次元ゾーンのカードを取得")
    ap.add_argument("--out", default="data/cards_superdim_raw.csv")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--sleep", type=float, default=0.2)
    args = ap.parse_args()

    session = make_session()
    html = fetch_page(session)
    token = post_json(session, TOKEN_URL)
    form = post_json(session, FORM_URL)
    csrf = (token or {}).get("csrf") or (form or {}).get("csrf")
    if not csrf:
        raise RuntimeError("csrf を取得できませんでした。")
    base = parse_form_params(html)

    all_cards, seen_ids = [], set()
    per_type = {}
    for ct in SUPERDIM_CARD_TYPES:
        cards, total = fetch_card_type(session, base, csrf, ct,
                                       limit=args.limit, sleep=args.sleep)
        # zone_flag=1 のみ採用(保険: 想定外の混入を弾く)
        cards = [c for c in cards
                 if str(c.get("super_dimensional_zone_flag", "")) == "1"]
        new = 0
        for c in cards:
            cid = str(c.get("card_id", ""))
            if cid and cid in seen_ids:
                continue
            if cid:
                seen_ids.add(cid)
            all_cards.append(c)
            new += 1
        per_type[ct] = (len(cards), new)
        print(f"  {ct}: 取得 {len(cards)} (新規 {new}) / API total={total}")

    out = Path(args.out)
    write_csv(out, all_cards)
    print(f"\n超次元ゾーン合計 {len(all_cards)} 枚 → {out}")
    # 種族の有無や文明の分布を軽く確認
    from collections import Counter
    civs = Counter(normalize_card(c)["civilization"] for c in all_cards)
    print("文明分布:", dict(civs))
    nd = Counter(normalize_card(c)["nd_legal"] for c in all_cards)
    print("nd_legal分布:", dict(nd))


if __name__ == "__main__":
    main()

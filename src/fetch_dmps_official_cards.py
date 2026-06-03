from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


BASE = "https://dmps.takaratomy.co.jp"
CARD_PAGE = f"{BASE}/card/"
FORM_URL = f"{BASE}/api1.0/plays/form.json"
TOKEN_URL = f"{BASE}/api1.0/plays/token.json"
SEARCH_URL = f"{BASE}/api1.0/plays/search.json"
GET_CARD_URL = f"{BASE}/api1.0/plays/cards"

DEFAULT_OUT = Path("data/cards_dmps_official_raw.csv")
DEFAULT_DEBUG = Path("data/reports/dmps_api_debug_v2")

CARD_FIELDS = [
    "card_id",
    "card_name",
    "card_yomi",
    "culture",
    "cost",
    "card_type",
    "power",
    "power_disp",
    "power_attacker",
    "mana",
    "rare",
    "race",
    "race_text",
    "body_text",
    "flavor_text",
    "illustrator",
    "voice_actor",
    "series_title",
    "create_disp",
    "break_disp",
    "super_dimensional_spell_text",
    "super_dimensional_spell_related_cards",
    "psychic_creature_related_cards",
    "twinpact_related_cards",
    "related_cards",
    "final_forbidden_field_css",
]


class FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_card_form = False
        self.form_depth = 0
        self.params: list[tuple[str, str]] = []
        self.current_select_name: str | None = None
        self.current_select_has_selected = False

    def handle_starttag(self, tag: str, attrs_raw: list[tuple[str, str | None]]) -> None:
        attrs = {k: (v if v is not None else "") for k, v in attrs_raw}

        if tag == "form":
            form_id = attrs.get("id", "")
            form_class = attrs.get("class", "")
            # The search form is the only large card search form. Be permissive.
            if "cardSearch" in form_id or "cardSearch" in form_class or "form" in form_id.lower():
                self.in_card_form = True
                self.form_depth = 1
            elif not self.in_card_form:
                # Some markup may not use <form id=...>. We will still collect all inputs in page later
                pass
            return

        if self.in_card_form and tag in {"div", "section", "fieldset"}:
            self.form_depth += 1

        # If there is no actual form wrapper, collect globally; official JS uses formElem.
        collect = self.in_card_form or True

        if tag == "input" and collect:
            name = attrs.get("name", "")
            if not name:
                return
            typ = attrs.get("type", "text").lower()
            value = attrs.get("value", "")
            if typ in {"checkbox", "radio"}:
                if "checked" in attrs:
                    self.params.append((name, value))
            elif typ in {"submit", "button", "image", "reset", "file"}:
                return
            else:
                self.params.append((name, value))

        elif tag == "select" and collect:
            self.current_select_name = attrs.get("name", "") or None
            self.current_select_has_selected = False

        elif tag == "option" and self.current_select_name and collect:
            if "selected" in attrs:
                self.params.append((self.current_select_name, attrs.get("value", "")))
                self.current_select_has_selected = True

        elif tag == "textarea" and collect:
            name = attrs.get("name", "")
            if name:
                self.params.append((name, ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "select":
            self.current_select_name = None
            self.current_select_has_selected = False

        if self.in_card_form:
            if tag in {"div", "section", "fieldset"} and self.form_depth > 0:
                self.form_depth -= 1
            if tag == "form":
                self.in_card_form = False
                self.form_depth = 0


def unique_params(params: list[tuple[str, str]]) -> list[tuple[str, str]]:
    # Keep duplicates for [] arrays, but remove exact duplicates.
    seen = set()
    out = []
    for k, v in params:
        item = (k, v)
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36 Project-MANA",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": BASE,
            "Referer": CARD_PAGE,
            "X-Requested-With": "XMLHttpRequest",
        }
    )
    # SSL傍受環境（社内プロキシ/セキュリティソフト）で公開カードDBを取得する場合に限り、
    # MANA_INSECURE_SSL=1 で証明書検証を明示的に無効化できる。既定は検証あり。
    if os.environ.get("MANA_INSECURE_SSL") == "1":
        s.verify = False
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
    return s


def fetch_page(session: requests.Session) -> str:
    r = session.get(CARD_PAGE, timeout=30)
    r.raise_for_status()
    if not r.encoding:
        r.encoding = r.apparent_encoding
    return r.text


def post_json(session: requests.Session, url: str, data: Any = None, headers: dict[str, str] | None = None) -> Any:
    r = session.post(url, data=data, headers=headers or {}, timeout=45)
    # Save enough context on failure at caller if needed.
    r.raise_for_status()
    return r.json()


def parse_form_params(html: str) -> list[tuple[str, str]]:
    parser = FormParser()
    parser.feed(html)
    params = unique_params(parser.params)

    # The official Vue app's serializeArray() may include names not found because of Vue templates.
    # Add safe defaults that do not filter anything.
    # These names are visible in the page/template and harmless if ignored.
    defaults = [
        ("keyword", ""),
        ("keyword_type", ""),
        ("card_name", ""),
        ("card_yomi", ""),
        ("artist", ""),
        ("illustrator", ""),
        ("voice_actor", ""),
        ("cost_min", ""),
        ("cost_max", ""),
        ("power_min", ""),
        ("power_max", ""),
    ]
    existing_names = {k for k, _ in params}
    for k, v in defaults:
        if k not in existing_names:
            params.append((k, v))

    return params


def deep_find_cards(obj: Any) -> list[dict[str, Any]]:
    if isinstance(obj, dict) and isinstance(obj.get("cards"), list):
        return [v for v in obj["cards"] if isinstance(v, dict)]
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict) and isinstance(obj["result"].get("cards"), list):
        return [v for v in obj["result"]["cards"] if isinstance(v, dict)]

    best: list[dict[str, Any]] = []

    def walk(x: Any) -> None:
        nonlocal best
        if isinstance(x, list):
            dicts = [v for v in x if isinstance(v, dict)]
            if dicts:
                score = sum(("card_id" in d) + ("card_name" in d) + ("body_text" in d) for d in dicts[:20])
                if score and len(dicts) > len(best):
                    best = dicts
            for v in x:
                walk(v)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)

    walk(obj)
    return best


def deep_find_total(obj: Any) -> int | None:
    if isinstance(obj, dict):
        for key in ["number", "total", "count", "total_count"]:
            v = obj.get(key)
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isdigit():
                return int(v)
        r = obj.get("result")
        if isinstance(r, dict):
            for key in ["number", "total", "count", "total_count"]:
                v = r.get(key)
                if isinstance(v, int):
                    return v
                if isinstance(v, str) and v.isdigit():
                    return int(v)
    return None


def build_search_params(base_params: list[tuple[str, str]], csrf: str, page: int, limit: int) -> list[tuple[str, str]]:
    params = [(k, v) for k, v in base_params if k not in {"csrf", "limit", "page"}]
    params.extend([
        ("csrf", csrf),
        ("limit", str(limit)),
        ("page", str(page)),
    ])
    return params


def try_search(session: requests.Session, base_params: list[tuple[str, str]], csrf: str, debug_dir: Path) -> tuple[list[tuple[str, str]], Any]:
    debug_dir.mkdir(parents=True, exist_ok=True)

    attempts = []
    variants = []

    # Variant A: exact JS style: data includes csrf; no special header.
    variants.append(("data_csrf", {}, build_search_params(base_params, csrf, 1, 50)))

    # Variant B: token in header too.
    variants.append(("data_csrf_header", {"X-CSRF-Token": csrf}, build_search_params(base_params, csrf, 1, 50)))

    # Variant C: minimal but correct names.
    variants.append(("minimal", {}, [("csrf", csrf), ("limit", "50"), ("page", "1")]))

    # Variant D: header + minimal.
    variants.append(("minimal_header", {"X-CSRF-Token": csrf}, [("csrf", csrf), ("limit", "50"), ("page", "1")]))

    # Variant E: no csrf in data, header only.
    variants.append(("header_only", {"X-CSRF-Token": csrf}, [("limit", "50"), ("page", "1")]))

    for idx, (name, headers, params) in enumerate(variants, start=1):
        try:
            r = session.post(SEARCH_URL, data=params, headers=headers, timeout=45)
            info = {
                "idx": idx,
                "name": name,
                "status_code": r.status_code,
                "url": r.url,
                "headers": headers,
                "params_head": params[:30],
                "text_head": r.text[:1000],
            }
            attempts.append(info)
            (debug_dir / f"search_attempt_{idx:02d}_{name}.txt").write_text(r.text[:200000], encoding="utf-8", errors="replace")

            if r.status_code == 200:
                obj = r.json()
                (debug_dir / f"search_attempt_{idx:02d}_{name}.json").write_text(
                    json.dumps(obj, ensure_ascii=False, indent=2)[:500000],
                    encoding="utf-8",
                )
                cards = deep_find_cards(obj)
                if cards:
                    (debug_dir / "working_search_variant.json").write_text(
                        json.dumps({"name": name, "headers": headers, "params": params}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    (debug_dir / "search_attempts_summary.json").write_text(
                        json.dumps(attempts, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    return params, obj
        except Exception as exc:
            attempts.append({"idx": idx, "name": name, "error": repr(exc)})

    (debug_dir / "search_attempts_summary.json").write_text(
        json.dumps(attempts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    raise RuntimeError("search.jsonの公式JS方式POSTでもカード配列を取得できませんでした。dmps_api_debug_v2を確認してください。")


def join_races(raw: dict[str, Any]) -> str:
    """公式APIは種族を race1〜race4 に分けて返す（未設定は "-"）。/ 区切りで結合する。"""
    races: list[str] = []
    for i in range(1, 5):
        value = raw.get(f"race{i}")
        text = "" if value is None else str(value).strip()
        if text and text != "-":
            races.append(text)
    return "/".join(races)


def normalize_card(raw: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, str] = {}
    for field in CARD_FIELDS:
        v = raw.get(field, "")
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        out[field] = "" if v is None else str(v)

    race_joined = join_races(raw)

    out["name"] = out.get("card_name", "") or str(raw.get("name", ""))
    out["civilization"] = out.get("culture", "")
    out["race"] = race_joined or out.get("race", "") or out.get("race_text", "")
    out["race_text"] = race_joined or out.get("race_text", "")
    out["keyword"] = "" if raw.get("keyword") is None else str(raw.get("keyword", ""))
    # 公式APIの new_division=1 がND（ニュー・ディビジョン）使用可フラグ。
    out["nd_legal"] = "1" if str(raw.get("new_division", "")).strip() == "1" else "0"
    out["text"] = out.get("body_text", "")
    out["tags"] = ""
    out["source"] = "dmps_official_api"
    out["source_url"] = SEARCH_URL
    return out


def fetch_all(session: requests.Session, working_params: list[tuple[str, str]], first_obj: Any, csrf: str, limit: int, sleep: float, debug_dir: Path) -> tuple[list[dict[str, Any]], int | None]:
    total = deep_find_total(first_obj)
    first_cards = deep_find_cards(first_obj)

    all_cards = []
    seen_ids = set()

    def add_cards(cards: list[dict[str, Any]]) -> int:
        added = 0
        for c in cards:
            cid = str(c.get("card_id", ""))
            if cid and cid in seen_ids:
                continue
            if cid:
                seen_ids.add(cid)
            all_cards.append(c)
            added += 1
        return added

    add_cards(first_cards)

    if total:
        max_pages = math.ceil(total / limit) + 2
    else:
        max_pages = 300

    base_without_page = [(k, v) for k, v in working_params if k not in {"page", "limit"}]

    for page in range(2, max_pages + 1):
        time.sleep(sleep)
        params = base_without_page + [("limit", str(limit)), ("page", str(page))]
        r = session.post(SEARCH_URL, data=params, timeout=45)
        if r.status_code != 200:
            (debug_dir / f"page_{page:03d}_error.txt").write_text(r.text[:5000], encoding="utf-8", errors="replace")
            break
        obj = r.json()
        cards = deep_find_cards(obj)
        if not cards:
            break
        added = add_cards(cards)
        if added == 0:
            break
        if total and len(all_cards) >= total:
            break

    return all_cards, total


def write_csv(path: Path, cards: list[dict[str, Any]]) -> None:
    rows = [normalize_card(c) for c in cards]
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys()) if rows else [*CARD_FIELDS, "name", "civilization", "race", "text", "tags", "source", "source_url"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch official DMPS card list using the same POST style as card/js/index.js.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--debug", default=str(DEFAULT_DEBUG))
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--sleep", type=float, default=0.15)
    args = parser.parse_args()

    out = Path(args.out)
    debug_dir = Path(args.debug)
    debug_dir.mkdir(parents=True, exist_ok=True)

    session = make_session()
    html = fetch_page(session)
    (debug_dir / "card_page.html").write_text(html, encoding="utf-8")

    base_params = parse_form_params(html)
    (debug_dir / "parsed_form_params.json").write_text(json.dumps(base_params, ensure_ascii=False, indent=2), encoding="utf-8")

    token = post_json(session, TOKEN_URL)
    form = post_json(session, FORM_URL)
    (debug_dir / "token.json").write_text(json.dumps(token, ensure_ascii=False, indent=2), encoding="utf-8")
    (debug_dir / "form.json").write_text(json.dumps(form, ensure_ascii=False, indent=2), encoding="utf-8")

    csrf = token.get("csrf") if isinstance(token, dict) else None
    if not csrf and isinstance(form, dict):
        csrf = form.get("csrf")
    if not csrf:
        raise RuntimeError("csrf を取得できませんでした。")

    working_params, first_obj = try_search(session, base_params, csrf, debug_dir)
    cards, total = fetch_all(session, working_params, first_obj, csrf, args.limit, args.sleep, debug_dir)

    write_csv(out, cards)

    summary = {
        "output": str(out),
        "cards_written": len(cards),
        "total_reported_by_api": total,
        "sample_names": [normalize_card(c).get("name", "") for c in cards[:30]],
    }
    (debug_dir / "fetch_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("official_api_csv:", out)
    print("cards_written:", len(cards))
    print("total_reported_by_api:", total)
    print("debug_dir:", debug_dir)
    for name in summary["sample_names"][:20]:
        print(" -", name)


if __name__ == "__main__":
    main()

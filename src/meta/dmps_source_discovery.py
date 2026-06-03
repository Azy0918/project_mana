from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    import requests
except Exception as exc:
    print("requests が必要です。先に `python -m pip install requests` を実行してください。")
    raise


DEFAULT_URL = "https://dmps.takaratomy.co.jp/card/"
DEFAULT_OUT_DIR = Path("data/reports/dmps_source_discovery")


def fetch_text(url: str, timeout: int = 30) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 Project-MANA-source-discovery/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml,application/json,text/javascript,*/*",
    }
    res = requests.get(url, headers=headers, timeout=timeout)
    res.raise_for_status()
    # Prefer server encoding if present, otherwise requests guesses.
    if not res.encoding:
        res.encoding = res.apparent_encoding
    return res.text


def unique(seq):
    seen = set()
    out = []
    for x in seq:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def extract_assets(html: str, base_url: str) -> dict[str, list[str]]:
    js = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
    css = re.findall(r'<link[^>]+href=["\']([^"\']+\.css[^"\']*)["\']', html, flags=re.I)
    json_refs = re.findall(r'["\']([^"\']+\.json[^"\']*)["\']', html, flags=re.I)
    card_refs = re.findall(r'["\']([^"\']*(?:card|cards|cardlist|card_list|api)[^"\']*)["\']', html, flags=re.I)

    return {
        "js": unique([urljoin(base_url, x) for x in js]),
        "css": unique([urljoin(base_url, x) for x in css]),
        "json_refs": unique([urljoin(base_url, x) for x in json_refs]),
        "card_like_refs": unique([urljoin(base_url, x) for x in card_refs if len(x) < 220]),
    }


def extract_candidates_from_js(js_text: str, js_url: str) -> dict[str, list[str]]:
    patterns = {
        "absolute_urls": r'https?://[^"\'\s<>]+',
        "json_paths": r'["\']([^"\']+\.json(?:\?[^"\']*)?)["\']',
        "api_like_paths": r'["\']([^"\']*(?:api|card|cards|cardlist|card_list|search)[^"\']*)["\']',
        "ajax_like": r'(?:url|href|src)\s*:\s*["\']([^"\']+)["\']',
    }

    result = {}
    for key, pat in patterns.items():
        values = re.findall(pat, js_text, flags=re.I)
        clean = []
        for v in values:
            if isinstance(v, tuple):
                v = v[0]
            if not v:
                continue
            if len(v) > 260:
                continue
            if v.startswith("http"):
                clean.append(v)
            else:
                clean.append(urljoin(js_url, v))
        result[key] = unique(clean)
    return result


def maybe_fetch_json(url: str):
    try:
        text = fetch_text(url, timeout=20)
        stripped = text.strip()
        if not stripped:
            return None
        if stripped[0] in "[{":
            return json.loads(stripped)
    except Exception:
        return None
    return None


def count_card_like_json(data) -> tuple[int, list[str]]:
    """Return rough card count and sample names."""
    names = []

    def walk(obj):
        if isinstance(obj, dict):
            # Common possible keys.
            for key in ["name", "card_name", "title"]:
                v = obj.get(key)
                if isinstance(v, str) and v.strip():
                    names.append(v.strip())
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    return len(names), names[:20]


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover the official DMPS card data source used by dmps.takaratomy.co.jp/card/.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--fetch-js", action="store_true", default=True)
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    html = fetch_text(args.url)
    (out_dir / "card_page.html").write_text(html, encoding="utf-8")

    assets = extract_assets(html, args.url)
    (out_dir / "discovered_assets.json").write_text(
        json.dumps(assets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("HTML length:", len(html))
    print("JS files:", len(assets["js"]))
    for u in assets["js"]:
        print("JS:", u)

    print("\nJSON refs in HTML:", len(assets["json_refs"]))
    for u in assets["json_refs"][:50]:
        print("JSON:", u)

    print("\nCard/API-like refs in HTML:", len(assets["card_like_refs"]))
    for u in assets["card_like_refs"][:80]:
        print("REF:", u)

    js_results = {}
    json_probe_results = {}

    for js_url in assets["js"]:
        try:
            js_text = fetch_text(js_url)
        except Exception as exc:
            print("JS fetch failed:", js_url, exc)
            continue

        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", urlparse(js_url).path.strip("/"))[-160:] or "script.js"
        (out_dir / f"js_{safe_name}.txt").write_text(js_text, encoding="utf-8")

        cand = extract_candidates_from_js(js_text, js_url)
        js_results[js_url] = cand

        print("\n== JS CANDIDATES ==", js_url)
        for key, values in cand.items():
            print(key, len(values))
            for v in values[:50]:
                print(" ", v)

        for values in cand.values():
            for u in values:
                if ".json" in u.lower() or "card" in u.lower() or "api" in u.lower():
                    data = maybe_fetch_json(u)
                    if data is not None:
                        count, samples = count_card_like_json(data)
                        json_probe_results[u] = {
                            "type": type(data).__name__,
                            "card_like_name_count": count,
                            "sample_names": samples,
                        }
                        print("\nPOSSIBLE JSON DATA:", u)
                        print("type:", type(data).__name__, "name_count:", count)
                        print("samples:", samples[:10])

    (out_dir / "js_candidate_refs.json").write_text(
        json.dumps(js_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "json_probe_results.json").write_text(
        json.dumps(json_probe_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nOUTPUT_DIR:", out_dir)
    print("Next: upload discovered_assets.json, js_candidate_refs.json, and json_probe_results.json if possible.")


if __name__ == "__main__":
    main()

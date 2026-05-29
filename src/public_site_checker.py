from __future__ import annotations

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_EXPECTED_KEYWORDS = ["Project MANA"]


def check_public_site(
    url: str,
    expected_keywords: list[str] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    url = url.strip()
    expected_keywords = expected_keywords if expected_keywords is not None else DEFAULT_EXPECTED_KEYWORDS
    if not url:
        return {
            "ok": False,
            "status": "NG",
            "url": url,
            "status_code": None,
            "content_length": 0,
            "keyword_hits": {},
            "issues": ["URLが空です。"],
            "warnings": [],
        }

    issues: list[str] = []
    warnings: list[str] = []
    status_code = None
    body = ""

    try:
        request = Request(url, headers={"User-Agent": "Project-MANA-release-checker/1.0"})
        with urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            raw = response.read(300_000)
            body = raw.decode("utf-8", errors="replace")
    except HTTPError as exc:
        status_code = int(exc.code)
        issues.append(f"HTTPエラー: {exc.code}")
    except URLError as exc:
        issues.append(f"接続エラー: {exc.reason}")
    except Exception as exc:
        issues.append(f"公開URL確認に失敗しました: {exc}")

    if status_code is not None and not (200 <= status_code < 400):
        issues.append(f"HTTPステータスが正常範囲外です: {status_code}")

    keyword_hits = {keyword: keyword in body for keyword in expected_keywords if keyword}
    missing_keywords = [keyword for keyword, hit in keyword_hits.items() if not hit]
    if missing_keywords and status_code is not None and 200 <= status_code < 400:
        warnings.append(
            "初期HTML内で見つからないキーワードがあります。StreamlitではJS描画のため警告扱いです: "
            + " / ".join(missing_keywords)
        )

    ok = not issues
    return {
        "ok": ok,
        "status": "OK" if ok else "NG",
        "url": url,
        "status_code": status_code,
        "content_length": len(body),
        "keyword_hits": keyword_hits,
        "issues": issues,
        "warnings": warnings,
    }

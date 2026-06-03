from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import ssl
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from src.import_cards import DEFAULT_CSV_PATH, DEFAULT_DB_PATH
from src.real_card_db_builder import REQUIRED_COLUMNS, build_real_cards_db, normalize_real_cards


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = ROOT_DIR / "data" / "raw"
DEFAULT_RAW_JSONL_PATH = DEFAULT_RAW_DIR / "official_cards.jsonl"
DEFAULT_RAW_CSV_PATH = DEFAULT_RAW_DIR / "official_cards.csv"
OFFICIAL_CARD_SEARCH_URL = "https://dm.takaratomy.co.jp/card/"
OFFICIAL_CARD_DETAIL_URL = "https://dm.takaratomy.co.jp/card/detail/"
USER_AGENT = "ProjectMANA/0.1 official-card-db-builder (+local personal use)"

FIELD_LABELS = [
    "カードの種類",
    "文明",
    "レアリティ",
    "パワー",
    "コスト",
    "マナ",
    "種族",
    "イラストレーター",
    "特殊能力",
    "フレーバー",
]


class _VisiblePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: list[str] = []
        self.links: list[str] = []
        self.images: list[dict[str, str]] = []
        self.title = ""
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag == "img":
            self.images.append(
                {
                    "src": attrs_dict.get("src", ""),
                    "alt": attrs_dict.get("alt", ""),
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
            self.title = _clean_text(" ".join(self._title_parts))

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        value = _clean_text(data)
        if not value:
            return
        if self._in_title:
            self._title_parts.append(value)
        self.tokens.append(value)


def scrape_official_cards(
    pages: int = 1,
    start_page: int = 1,
    limit: int | None = None,
    delay_seconds: float = 1.5,
    raw_jsonl_path: Path = DEFAULT_RAW_JSONL_PATH,
    raw_csv_path: Path = DEFAULT_RAW_CSV_PATH,
    resume: bool = True,
    verify_ssl: bool = True,
) -> list[dict[str, Any]]:
    raw_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if not resume and raw_jsonl_path.exists():
        raw_jsonl_path.unlink()
    known_records = _load_jsonl(raw_jsonl_path) if resume else []
    seen_urls = {record["url"] for record in known_records if record.get("url")}

    urls = discover_official_card_urls(
        pages=pages,
        start_page=start_page,
        delay_seconds=delay_seconds,
        verify_ssl=verify_ssl,
    )
    if limit is not None:
        urls = urls[:limit]

    records = list(known_records)
    with raw_jsonl_path.open("a", encoding="utf-8") as f:
        for url in urls:
            if url in seen_urls:
                continue
            try:
                detail_html = fetch_url_with_retries(url, verify_ssl=verify_ssl, delay_seconds=delay_seconds)
                record = parse_card_detail_html(detail_html, url)
            except Exception as exc:
                _safe_print(f"ERROR: {url} {exc}")
                time.sleep(delay_seconds)
                continue
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            records.append(record)
            seen_urls.add(url)
            time.sleep(delay_seconds)

    write_records_csv(records, raw_csv_path)
    return records


def scrape_official_cards_until(
    target_count: int,
    start_page: int = 1,
    page_batch_size: int = 5,
    delay_seconds: float = 2.0,
    raw_jsonl_path: Path = DEFAULT_RAW_JSONL_PATH,
    raw_csv_path: Path = DEFAULT_RAW_CSV_PATH,
    resume: bool = True,
    verify_ssl: bool = True,
) -> list[dict[str, Any]]:
    raw_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if not resume and raw_jsonl_path.exists():
        raw_jsonl_path.unlink()

    records = _load_jsonl(raw_jsonl_path) if resume else []
    seen_urls = {record["url"] for record in records if record.get("url")}
    current_page = max(start_page, len(records) // 50) if resume else start_page
    empty_batches = 0

    while len(records) < target_count:
        urls = discover_official_card_urls(
            pages=page_batch_size,
            start_page=current_page,
            delay_seconds=delay_seconds,
            verify_ssl=verify_ssl,
        )
        current_page += page_batch_size

        new_urls = [url for url in urls if url not in seen_urls]
        if not new_urls:
            empty_batches += 1
            if empty_batches >= 5:
                break
            continue
        empty_batches = 0

        with raw_jsonl_path.open("a", encoding="utf-8") as f:
            for url in new_urls:
                if len(records) >= target_count:
                    break
                detail_html = fetch_url(url, verify_ssl=verify_ssl)
                record = parse_card_detail_html(detail_html, url)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                records.append(record)
                seen_urls.add(url)
                _safe_print(f"{len(records)}/{target_count}: {record.get('name', '')}")
                time.sleep(delay_seconds)

        write_records_csv(records, raw_csv_path)

    write_records_csv(records, raw_csv_path)
    return records


def discover_official_card_urls(
    pages: int = 1,
    start_page: int = 1,
    delay_seconds: float = 1.5,
    verify_ssl: bool = True,
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for page_number in range(start_page, start_page + pages):
        search_url = build_search_url(page_number)
        search_html = fetch_url_with_retries(
            search_url,
            verify_ssl=verify_ssl,
            form_data=build_search_form_data(page_number),
            delay_seconds=delay_seconds,
        )
        for detail_url in extract_detail_urls(search_html):
            if detail_url not in seen:
                seen.add(detail_url)
                urls.append(detail_url)
        time.sleep(delay_seconds)
    return urls


def build_search_url(page_number: int) -> str:
    return f"{OFFICIAL_CARD_SEARCH_URL}?pagenum={page_number}"


def build_search_form_data(page_number: int) -> dict[str, Any]:
    return {
        "suggest": "on",
        "keyword_type[]": ["card_name", "card_ruby", "card_text"],
        "culture_cond[]": ["単色", "多色"],
        "pagenum": str(page_number),
        "samename": "show",
        "sort": "release_new",
    }


def build_legacy_search_url(page_number: int) -> str:
    search_params = {
        "suggest": "on",
        "keyword_type": ["card_name", "card_ruby", "card_text"],
        "culture_cond": ["単色", "多色"],
        "pagenum": str(page_number),
        "samename": "show",
        "sort": "release_new",
    }
    return f"{OFFICIAL_CARD_SEARCH_URL}?{urlencode({'v': json.dumps(search_params, ensure_ascii=False)})}"


def fetch_url(
    url: str,
    timeout: int = 30,
    verify_ssl: bool = True,
    form_data: dict[str, Any] | None = None,
) -> str:
    encoded_data = None
    headers = {"User-Agent": USER_AGENT}
    if form_data is not None:
        encoded_data = urlencode(form_data, doseq=True).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(url, data=encoded_data, headers=headers)
    context = None if verify_ssl else ssl._create_unverified_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_url_with_retries(
    url: str,
    timeout: int = 30,
    verify_ssl: bool = True,
    form_data: dict[str, Any] | None = None,
    delay_seconds: float = 2.0,
    max_retries: int = 4,
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return fetch_url(
                url,
                timeout=timeout,
                verify_ssl=verify_ssl,
                form_data=form_data,
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            wait_seconds = delay_seconds * attempt
            _safe_print(f"RETRY {attempt}/{max_retries}: {url} {exc}")
            time.sleep(wait_seconds)
    raise RuntimeError(f"取得に失敗しました: {url} / {last_error}")


def extract_detail_urls(page_html: str) -> list[str]:
    parser = _parse_visible_page(page_html)
    candidates = list(parser.links)
    candidates.extend(re.findall(r"""["']([^"']*card/detail/\?id=[^"']+)["']""", page_html))
    candidates.extend(re.findall(r"""["']([^"']*card/detail\?id=[^"']+)["']""", page_html))

    urls: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        absolute_url = urljoin(OFFICIAL_CARD_SEARCH_URL, html.unescape(candidate))
        parsed = urlparse(absolute_url)
        if "/card/detail" not in parsed.path:
            continue
        query = parse_qs(parsed.query)
        official_id = (query.get("id") or [""])[0]
        if not official_id:
            continue
        normalized_url = f"{OFFICIAL_CARD_DETAIL_URL}?id={official_id}"
        if normalized_url not in seen:
            seen.add(normalized_url)
            urls.append(normalized_url)
    return urls


def parse_card_detail_html(page_html: str, url: str) -> dict[str, Any]:
    parser = _parse_visible_page(page_html)
    title = parser.title.split("|", 1)[0].strip()
    card_name, print_code = _split_title(title)
    official_id = _official_id_from_url(url)
    faces = _parse_faces(parser.tokens)
    image_url = _find_card_image_url(parser.images)

    return {
        "official_id": official_id,
        "url": url,
        "name": card_name,
        "print_code": print_code,
        "image_url": image_url,
        "faces": faces,
        **_flatten_faces(faces),
    }


def records_to_cards_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for index, record in enumerate(records, start=1):
        row = {
            "card_id": f"DMOFF-{index:05d}",
            "name": record.get("name", ""),
            "civilization": record.get("civilization", ""),
            "cost": record.get("cost", ""),
            "card_type": record.get("card_type", ""),
            "power": record.get("power", ""),
            "race": record.get("race", ""),
            "text": record.get("text", "") or record.get("flavor", "") or record.get("name", ""),
            "tags": "",
            "official_id": record.get("official_id", ""),
            "print_code": record.get("print_code", ""),
            "rarity": record.get("rarity", ""),
            "mana": record.get("mana", ""),
            "illustrator": record.get("illustrator", ""),
            "flavor": record.get("flavor", ""),
            "image_url": record.get("image_url", ""),
            "url": record.get("url", ""),
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    normalized = normalize_real_cards(df)
    for extra_column in [
        "official_id",
        "print_code",
        "rarity",
        "mana",
        "illustrator",
        "flavor",
        "image_url",
        "url",
    ]:
        normalized[extra_column] = df.get(extra_column, "")
    return normalized


def write_records_csv(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = records_to_cards_dataframe(records)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def build_app_db_from_official_csv(
    official_csv_path: Path = DEFAULT_RAW_CSV_PATH,
    output_csv_path: Path = DEFAULT_CSV_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> int:
    return build_real_cards_db(official_csv_path, output_csv_path, db_path)


def _parse_visible_page(page_html: str) -> _VisiblePageParser:
    parser = _VisiblePageParser()
    parser.feed(page_html)
    return parser


def _parse_faces(tokens: list[str]) -> list[dict[str, str]]:
    starts = [index for index, token in enumerate(tokens) if token == "カードの種類"]
    faces = []
    for face_number, start_index in enumerate(starts):
        end_index = starts[face_number + 1] if face_number + 1 < len(starts) else len(tokens)
        segment = tokens[start_index:end_index]
        face = {
            "card_type": _value_after_label(segment, "カードの種類", FIELD_LABELS),
            "civilization": _value_after_label(segment, "文明", FIELD_LABELS),
            "rarity": _value_after_label(segment, "レアリティ", FIELD_LABELS),
            "power": _value_after_label(segment, "パワー", FIELD_LABELS),
            "cost": _value_after_label(segment, "コスト", FIELD_LABELS),
            "mana": _value_after_label(segment, "マナ", FIELD_LABELS),
            "race": _value_after_label(segment, "種族", FIELD_LABELS),
            "illustrator": _value_after_label(segment, "イラストレーター", FIELD_LABELS),
            "text": _block_after_label(segment, "特殊能力", ["フレーバー", "商品情報", "同名カード"]),
            "flavor": _block_after_label(segment, "フレーバー", ["商品情報", "同名カード", "このカードのよくある質問"]),
        }
        faces.append(face)
    return faces


def _value_after_label(segment: list[str], label: str, labels: list[str]) -> str:
    if label not in segment:
        return ""
    start = segment.index(label) + 1
    values = []
    for token in segment[start:]:
        if token in labels:
            break
        values.append(token)
    return _clean_text(" ".join(values))


def _block_after_label(segment: list[str], label: str, stop_labels: list[str]) -> str:
    if label not in segment:
        return ""
    start = segment.index(label) + 1
    values = []
    for token in segment[start:]:
        if token in stop_labels:
            break
        values.append(token)
    return "\n".join(_clean_text(value) for value in values if _clean_text(value))


def _flatten_faces(faces: list[dict[str, str]]) -> dict[str, str]:
    return {
        "card_type": "/".join(_unique(face.get("card_type", "") for face in faces)),
        "civilization": "/".join(_unique(face.get("civilization", "") for face in faces)),
        "rarity": "/".join(_unique(face.get("rarity", "") for face in faces)),
        "power": "/".join(_unique(face.get("power", "") for face in faces)),
        "cost": _first_non_empty(face.get("cost", "") for face in faces),
        "mana": _first_non_empty(face.get("mana", "") for face in faces),
        "race": "/".join(_unique(face.get("race", "") for face in faces)),
        "illustrator": "/".join(_unique(face.get("illustrator", "") for face in faces)),
        "text": "\n---\n".join(face.get("text", "") for face in faces if face.get("text", "")),
        "flavor": "\n---\n".join(face.get("flavor", "") for face in faces if face.get("flavor", "")),
    }


def _split_title(title: str) -> tuple[str, str]:
    match = re.match(r"^(?P<name>.+?)\((?P<code>[^()]*)\)$", title)
    if not match:
        return title, ""
    return match.group("name").strip(), match.group("code").strip()


def _official_id_from_url(url: str) -> str:
    return (parse_qs(urlparse(url).query).get("id") or [""])[0]


def _find_card_image_url(images: list[dict[str, str]]) -> str:
    for image in images:
        src = image.get("src", "")
        if "cardimage" in src.lower():
            return urljoin(OFFICIAL_CARD_SEARCH_URL, src)
    for image in images:
        src = image.get("src", "")
        alt = image.get("alt", "")
        if src and "card" in src.lower() and not src.endswith(".svg"):
            return urljoin(OFFICIAL_CARD_SEARCH_URL, src)
        if src and alt and "ロゴ" not in alt:
            return urljoin(OFFICIAL_CARD_SEARCH_URL, src)
    return ""


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _unique(values: Any) -> list[str]:
    result = []
    for value in values:
        value = _clean_text(str(value))
        if value and value not in result:
            result.append(value)
    return result


def _first_non_empty(values: Any) -> str:
    for value in values:
        value = _clean_text(str(value))
        if value:
            return value
    return ""


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()


def _safe_print(value: str) -> None:
    print(str(value).encode("cp932", errors="replace").decode("cp932"), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="公式カード検索から実カードデータを取得します。")
    parser.add_argument("--pages", type=int, default=1, help="検索結果ページ数")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None, help="詳細取得件数の上限")
    parser.add_argument("--target-count", type=int, default=None, help="目標件数までバッチ取得します")
    parser.add_argument("--page-batch-size", type=int, default=5, help="バッチ取得時にまとめて巡回する検索結果ページ数")
    parser.add_argument("--delay", type=float, default=1.5, help="アクセス間隔秒")
    parser.add_argument("--raw-jsonl", type=Path, default=DEFAULT_RAW_JSONL_PATH)
    parser.add_argument("--raw-csv", type=Path, default=DEFAULT_RAW_CSV_PATH)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="SSL証明書検証を無効にします。ローカル証明書問題の試験用です。",
    )
    parser.add_argument("--build-app-db", action="store_true")
    parser.add_argument("--app-csv", type=Path, default=DEFAULT_CSV_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    if args.target_count is not None:
        records = scrape_official_cards_until(
            target_count=args.target_count,
            start_page=args.start_page,
            page_batch_size=args.page_batch_size,
            delay_seconds=args.delay,
            raw_jsonl_path=args.raw_jsonl,
            raw_csv_path=args.raw_csv,
            resume=not args.no_resume,
            verify_ssl=not args.insecure,
        )
    else:
        records = scrape_official_cards(
            pages=args.pages,
            start_page=args.start_page,
            limit=args.limit,
            delay_seconds=args.delay,
            raw_jsonl_path=args.raw_jsonl,
            raw_csv_path=args.raw_csv,
            resume=not args.no_resume,
            verify_ssl=not args.insecure,
        )
    print(f"{len(records)} official card records written to {args.raw_csv}")

    if args.build_app_db:
        count = build_app_db_from_official_csv(args.raw_csv, args.app_csv, args.db)
        print(f"{count} official cards imported to {args.db}")


if __name__ == "__main__":
    main()

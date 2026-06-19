from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_CSV = ROOT / "tools" / "ep01_voice_audition_candidates.csv"
LINES_CSV = ROOT / "tools" / "ep01_voice_audition_lines.csv"
OUT_DIR = ROOT / "previews" / "voice_auditions" / "ep01"
DEFAULT_TITLE = "第1話 声決め試聴"
API = "http://127.0.0.1:10101"


def slug(text: str) -> str:
    value = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return value or "voice"


def post_json(url: str, payload: dict | None = None, attempts: int = 4) -> bytes:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data=data, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=120) as res:
                return res.read()
        except Exception as error:  # noqa: BLE001 - retry on any transport error
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    raise last_error if last_error else RuntimeError("post_json failed")


def audio_query(text: str, speaker_id: int) -> dict:
    params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
    raw = post_json(f"{API}/audio_query?{params}")
    return json.loads(raw.decode("utf-8"))


def synthesize(query: dict, speaker_id: int) -> bytes:
    params = urllib.parse.urlencode({"speaker": speaker_id})
    return post_json(f"{API}/synthesis?{params}", query)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 13th Register voice-audition clips + page via AivisSpeech.")
    parser.add_argument("--candidates", type=Path, default=CANDIDATES_CSV, help="candidate定義CSV")
    parser.add_argument("--lines", type=Path, default=LINES_CSV, help="キャラ別の代表セリフCSV")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="出力ディレクトリ")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="ページタイトル")
    parser.add_argument("--delay", type=float, default=0.4, help="各生成後の小休止秒")
    args = parser.parse_args()

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = {row["character"]: row for row in read_csv(args.lines)}
    candidates = read_csv(args.candidates)
    manifest: list[dict[str, str]] = []
    failures: list[str] = []

    for row in candidates:
        character = row["character"]
        line = lines[character]["text"]
        speaker_id = int(row["style_id"])
        order = int(row["order"])
        file_name = (
            f"{slug(character)}_{order:02d}_{slug(row['speaker_name'])}_{slug(row['style_name'])}_{speaker_id}.wav"
        )
        out_path = out_dir / file_name

        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"skip {out_path}")
        else:
            try:
                query = audio_query(line, speaker_id)
                for key in (
                    "speedScale",
                    "intonationScale",
                    "tempoDynamicsScale",
                    "pitchScale",
                    "volumeScale",
                    "prePhonemeLength",
                    "postPhonemeLength",
                ):
                    query[key] = float(row[key])
                query["outputSamplingRate"] = 44100
                query["outputStereo"] = False
                out_path.write_bytes(synthesize(query, speaker_id))
                print(f"wrote {out_path}")
                time.sleep(args.delay)
            except Exception as error:  # noqa: BLE001 - keep batch going, report later
                failures.append(file_name)
                print(f"WARN failed {file_name}: {error}")
                continue

        manifest.append(
            {
                "character": character,
                "order": str(order),
                "speaker_name": row["speaker_name"],
                "style_name": row["style_name"],
                "style_id": row["style_id"],
                "file": file_name,
                "text": line,
                "notes": row["notes"],
            }
        )

    manifest_path = out_dir / "manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["character", "order", "speaker_name", "style_name", "style_id", "file", "text", "notes"],
        )
        writer.writeheader()
        writer.writerows(manifest)

    title = args.title
    html_parts = [
        "<!doctype html>",
        '<html lang="ja">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(title)}</title>",
        "<style>",
        "body{font-family:system-ui,'Yu Gothic',Meiryo,sans-serif;margin:24px;background:#101316;color:#f4f4f0;}",
        "h1{font-size:24px;} h2{margin-top:34px;border-top:1px solid #343a40;padding-top:20px;}",
        ".item{padding:12px 0;border-bottom:1px solid #262b31;} .meta{color:#b8c0c8;font-size:13px;margin-bottom:6px;}",
        "audio{width:100%;max-width:720px;} code{color:#d8edff;}",
        "</style>",
        "</head><body>",
        f"<h1>{html.escape(title)}</h1>",
        "<p>各キャラごとに、上から順番に聞いて候補を選ぶための一覧です。</p>",
    ]
    current = None
    for item in manifest:
        if item["character"] != current:
            current = item["character"]
            html_parts.append(f"<h2>{html.escape(current)}</h2>")
            html_parts.append(f"<p>{html.escape(item['text'])}</p>")
        html_parts.append('<div class="item">')
        html_parts.append(
            f"<div class=\"meta\"><strong>{html.escape(item['order'])}.</strong> "
            f"{html.escape(item['speaker_name'])} / {html.escape(item['style_name'])} "
            f"<code>{html.escape(item['style_id'])}</code> - {html.escape(item['notes'])}</div>"
        )
        html_parts.append(f'<audio controls src="{html.escape(item["file"])}"></audio>')
        html_parts.append("</div>")
    html_parts.append("</body></html>")
    (out_dir / "index.html").write_text("\n".join(html_parts), encoding="utf-8")
    print(f"wrote {manifest_path}")
    print(f"wrote {out_dir / 'index.html'}")
    if failures:
        print(f"FAILURES ({len(failures)}): " + ", ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

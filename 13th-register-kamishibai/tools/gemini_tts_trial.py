import argparse
import base64
import csv
import json
import os
import re
import sys
import wave
from pathlib import Path

import requests

try:
    import certifi
except ImportError:  # pragma: no cover - optional local dependency
    certifi = None


DEFAULT_MODEL = "gemini-3.1-flash-tts-preview"
DEFAULT_VOICE = "Kore"
DEFAULT_CSV = Path("13th-register-kamishibai/assets/ep01_dialogue_edit.csv")
DEFAULT_OUT_DIR = Path("outputs/gemini_tts_trial")
ENV_FILES = (Path(".env.local"), Path(".env"))


SPEAKER_STYLE = {
    "ミナ": "落ち着いた若い女性。淡々として無表情、低めのテンションで、コンビニ夜勤の先輩らしく自然に読む。",
    "タクミ": "若い男性。驚きとツッコミが多いが、叫びすぎず、深夜コンビニの小声感を少し残して読む。",
    "ナレーション": "静かな語り。深夜のコンビニSFコメディとして、落ち着いて少し不思議に読む。",
    "第十三レジ": "無機質なレジ端末。感情を抑え、機械的で淡々と読む。",
    "未来の会社員": "疲れた若い男性会社員。恐縮していて、少し弱った声で読む。",
    "座木山辰哉": "55歳の常連客。眠そうで飄々としていて、普通のことのように変な内容を読む。",
}


def api_key() -> str:
    for path in ENV_FILES:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip().lstrip("\ufeff") in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}:
                key = value.strip().strip('"').strip("'")
                if key:
                    return key

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise SystemExit(
            "GEMINI_API_KEY or GOOGLE_API_KEY is not set. "
            "Create a key at https://aistudio.google.com/apikey and set it in this shell."
        )
    return key


def wav_rate(mime_type: str) -> int:
    match = re.search(r"rate=(\d+)", mime_type or "")
    return int(match.group(1)) if match else 24000


def write_audio(data: bytes, mime_type: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if "wav" in (mime_type or "").lower():
        out_path.write_bytes(data)
        return

    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(wav_rate(mime_type))
        wav_file.writeframes(data)


def build_prompt(text: str, speaker: str) -> str:
    style = SPEAKER_STYLE.get(speaker, "自然な日本語の会話として読む。")
    return (
        f"{style}\n"
        "次のセリフだけを日本語で読み上げる。説明や前置きは読まない。\n"
        f"セリフ: {text}"
    )


def synthesize(text: str, speaker: str, out_path: Path, model: str, voice: str) -> dict:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key(),
    }
    payload = {
        "contents": [{"parts": [{"text": build_prompt(text, speaker)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice,
                    }
                }
            },
        },
    }
    verify = certifi.where() if certifi else True
    response = requests.post(endpoint, headers=headers, json=payload, timeout=120, verify=verify)
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini TTS failed: {response.status_code} {response.text}")

    result = response.json()
    part = result["candidates"][0]["content"]["parts"][0]
    inline_data = part["inlineData"]
    audio = base64.b64decode(inline_data["data"])
    mime_type = inline_data.get("mimeType", "")
    write_audio(audio, mime_type, out_path)
    return {
        "out": str(out_path),
        "speaker": speaker,
        "voice": voice,
        "model": model,
        "mimeType": mime_type,
        "text": text,
    }


def rows_from_csv(path: Path, limit: int) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            text = (row.get("reading_hiragana") or row.get("reading") or row.get("dialogue") or "").strip()
            if not text:
                continue
            rows.append(
                {
                    "id": row.get("id") or f"line_{len(rows) + 1:03d}",
                    "speaker": row.get("speaker") or "",
                    "text": text,
                }
            )
            if len(rows) >= limit:
                break
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Gemini TTS trial for 13th Register lines.")
    parser.add_argument("--text", help="Text to synthesize. If omitted, rows are read from CSV.")
    parser.add_argument("--speaker", default="ナレーション")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    if args.text:
        jobs = [{"id": "sample", "speaker": args.speaker, "text": args.text}]
    else:
        jobs = rows_from_csv(args.csv, args.limit)

    manifest = []
    for job in jobs:
        safe_speaker = re.sub(r'[\\/:*?"<>|]', "_", job["speaker"] or "unknown")
        out_path = args.out_dir / f"{job['id']}_{safe_speaker}_{args.voice}.wav"
        manifest.append(synthesize(job["text"], job["speaker"], out_path, args.model, args.voice))
        print(out_path)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(manifest_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise

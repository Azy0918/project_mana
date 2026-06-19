from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAST_CSV = ROOT / "tools" / "ep01_voice_cast_selected.csv"
SCRIPT_CSV = ROOT / "tools" / "ep01_full_voice_script.csv"
OUT_DIR = ROOT / "tools" / "output_audio" / "ep01_full_voice"
RAW_DIR = OUT_DIR / "raw"
API = "http://127.0.0.1:10101"
RATE = 44100

PARAM_KEYS = (
    "speedScale",
    "intonationScale",
    "tempoDynamicsScale",
    "pitchScale",
    "volumeScale",
    "prePhonemeLength",
    "postPhonemeLength",
)


def slug(text: str) -> str:
    value = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE).strip("_")
    return value or "x"


def post_json(url: str, payload: dict | None = None, attempts: int = 4) -> bytes:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, data=data, method="POST", headers=headers)
            with urllib.request.urlopen(req, timeout=120) as res:
                return res.read()
        except Exception as error:  # noqa: BLE001 - retry on transient transport errors
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    raise last_error if last_error else RuntimeError("post_json failed")


def audio_query(text: str, speaker_id: int) -> dict:
    params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
    return json.loads(post_json(f"{API}/audio_query?{params}").decode("utf-8"))


def synthesize(query: dict, speaker_id: int) -> bytes:
    params = urllib.parse.urlencode({"speaker": speaker_id})
    return post_json(f"{API}/synthesis?{params}", query)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize 13th Register episode-1 full voice via AivisSpeech.")
    parser.add_argument("--cast", type=Path, default=CAST_CSV)
    parser.add_argument("--script", type=Path, default=SCRIPT_CSV)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--delay", type=float, default=0.3)
    args = parser.parse_args()

    out_dir: Path = args.out
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    cast = {row["character"]: row for row in read_csv(args.cast)}
    rows = read_csv(args.script)

    clips: list[dict] = []
    failures: list[str] = []

    for row in rows:
        if (row.get("role") or "").lower() == "sfx":
            continue
        character = row["character"]
        if character not in cast:
            continue
        line_id = row["id"]
        text = row["text"]
        info = cast[character]
        speaker_id = int(info["style_id"])
        try:
            query = audio_query(text, speaker_id)
            for key in PARAM_KEYS:
                query[key] = float(info[key])
            query["outputSamplingRate"] = RATE
            query["outputStereo"] = False
            clip_path = raw_dir / f"{line_id}_{slug(character)}.wav"
            clip_path.write_bytes(synthesize(query, speaker_id))
            with wave.open(str(clip_path), "rb") as wav_in:
                frames = wav_in.getnframes()
                framerate = wav_in.getframerate()
                pcm = wav_in.readframes(frames)
            duration = frames / float(framerate) if framerate else 0.0
            clips.append(
                {
                    "id": line_id,
                    "character": character,
                    "speaker": f"{info['speaker_name']} / {info['style_name']}",
                    "text": text,
                    "pcm": pcm,
                    "duration": duration,
                    "pause_ms": int(row.get("pause_after_ms") or 0),
                    "clip": f"raw/{clip_path.name}",
                }
            )
            print(f"wrote {clip_path.name}  ({duration:.2f}s, +{int(row.get('pause_after_ms') or 0)}ms)  [{character}]")
            time.sleep(args.delay)
        except Exception as error:  # noqa: BLE001 - keep batch going, report later
            failures.append(line_id)
            print(f"WARN failed {line_id} ({character}): {error}")

    # Concatenate into one continuous track with pauses, and build a timeline.
    full_path = out_dir / "ep01_full_voice.wav"
    timeline: list[dict] = []
    cursor = 0.0
    with wave.open(str(full_path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        for clip in clips:
            out.writeframes(clip["pcm"])
            start = cursor
            end = cursor + clip["duration"]
            cursor = end
            timeline.append(
                {
                    "id": clip["id"],
                    "character": clip["character"],
                    "speaker": clip["speaker"],
                    "text": clip["text"],
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "clip": clip["clip"],
                }
            )
            if clip["pause_ms"] > 0:
                silence = b"\x00\x00" * int(RATE * clip["pause_ms"] / 1000)
                out.writeframes(silence)
                cursor += clip["pause_ms"] / 1000.0

    (out_dir / "ep01_full_voice_timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("=" * 56)
    print(f"voiced lines: {len(clips)} / total non-SE lines")
    print(f"full track: {full_path}  ({cursor:.1f}s)")
    print(f"timeline: {out_dir / 'ep01_full_voice_timeline.json'}")
    print("cast: " + ", ".join(f"{k}={v['speaker_name']}" for k, v in cast.items()))
    if failures:
        print(f"FAILURES ({len(failures)}): " + ", ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

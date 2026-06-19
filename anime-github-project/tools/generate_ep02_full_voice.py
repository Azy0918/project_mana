from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path


# Repo root is two levels up from anime-github-project/tools/.
REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
MANIFEST = REPO_ROOT / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_ep02.json"
CAST_CSV = TOOLS_DIR / "ep01_voice_cast_selected.csv"
OUT_DIR = REPO_ROOT / "outputs" / "ep02_voice_reading_hiragana"
FULL_NAME = "ep02_full_voice_reading_hiragana.wav"
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


def get_json(url: str, attempts: int = 3) -> object:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=30) as res:
                return json.loads(res.read().decode("utf-8"))
        except Exception as error:  # noqa: BLE001 - retry on transient transport errors
            last_error = error
            time.sleep(1.0 * (attempt + 1))
    raise last_error if last_error else RuntimeError("get_json failed")


def audio_query(text: str, speaker_id: int) -> dict:
    params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
    return json.loads(post_json(f"{API}/audio_query?{params}").decode("utf-8"))


def synthesize(query: dict, speaker_id: int) -> bytes:
    params = urllib.parse.urlencode({"speaker": speaker_id})
    return post_json(f"{API}/synthesis?{params}", query)


def read_cast_params(path: Path) -> dict[int, dict[str, float]]:
    """Map style_id -> {param: float} from the confirmed cast table."""
    params_by_style: dict[int, dict[str, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            try:
                style_id = int(row["style_id"])
            except (KeyError, ValueError):
                continue
            params_by_style[style_id] = {
                key: float(row[key]) for key in PARAM_KEYS if row.get(key) not in (None, "")
            }
    return params_by_style


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synthesize a full-episode voice track from a reading-hiragana manifest via AivisSpeech."
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--cast", type=Path, default=CAST_CSV)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--full-name", default=FULL_NAME)
    parser.add_argument("--delay", type=float, default=0.3)
    parser.add_argument("--reuse-existing", action="store_true", help="Reuse existing non-empty clip WAVs.")
    parser.add_argument(
        "--force-character",
        action="append",
        default=[],
        help="Regenerate this character even when --reuse-existing is set. Can be repeated.",
    )
    parser.add_argument(
        "--force-id",
        action="append",
        default=[],
        help="Regenerate this manifest line id even when --reuse-existing is set. Can be repeated.",
    )
    args = parser.parse_args()

    out_dir: Path = args.out
    clips_dir = out_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    params_by_style = read_cast_params(args.cast)

    # Pre-flight: verify every style_id in the manifest is served by the running engine.
    available: set[int] = set()
    try:
        speakers = get_json(f"{API}/speakers")
        for speaker in speakers:  # type: ignore[union-attr]
            for style in speaker.get("styles", []):
                available.add(int(style["id"]))
    except Exception as error:  # noqa: BLE001 - validation is best-effort
        print(f"WARN could not fetch /speakers for validation: {error}")
    if available:
        missing = sorted({int(e["style_id"]) for e in entries} - available)
        if missing:
            print(f"WARN style_id(s) not available in engine: {missing}")

    clips: list[dict] = []
    failures: list[str] = []

    for entry in entries:
        line_id = entry["id"]
        character = entry["character"]
        speaker_id = int(entry["style_id"])
        text = entry["synthesis_text"]  # reading-hiragana is what we voice
        pause_ms = int(entry.get("pause_after_ms") or 0)
        force = character in set(args.force_character) or line_id in set(args.force_id)
        # Honor the clip path declared in the manifest (repo-root relative, backslashes on Windows).
        clip_rel = str(entry.get("clip") or "").replace("\\", "/")
        clip_path = (REPO_ROOT / clip_rel) if clip_rel else (clips_dir / f"{line_id}_{character}.wav")
        clip_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if args.reuse_existing and not force and clip_path.exists() and clip_path.stat().st_size > 0:
                print(f"reuse {clip_path.name}")
            else:
                query = audio_query(text, speaker_id)
                for key, value in params_by_style.get(speaker_id, {}).items():
                    query[key] = value
                query["outputSamplingRate"] = RATE
                query["outputStereo"] = False
                clip_path.write_bytes(synthesize(query, speaker_id))
            with wave.open(str(clip_path), "rb") as wav_in:
                frames = wav_in.getnframes()
                framerate = wav_in.getframerate()
                pcm = wav_in.readframes(frames)
            duration = frames / float(framerate) if framerate else 0.0
            clips.append(
                {
                    "id": line_id,
                    "cut": entry.get("cut"),
                    "character": character,
                    "speaker": f"{entry.get('speaker_name', '')} / {entry.get('style_name', '')}",
                    "text": entry.get("text"),
                    "synthesis_text": text,
                    "pcm": pcm,
                    "duration": duration,
                    "pause_ms": pause_ms,
                    "clip": clip_rel or clip_path.name,
                }
            )
            print(f"wrote {clip_path.name}  ({duration:.2f}s, +{pause_ms}ms)  [{character}]")
            time.sleep(args.delay)
        except Exception as error:  # noqa: BLE001 - keep batch going, report later
            failures.append(line_id)
            print(f"WARN failed {line_id} ({character}): {error}")

    # Concatenate clips into one continuous track with pauses, and build a timeline.
    full_path = out_dir / args.full_name
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
                    "cut": clip["cut"],
                    "character": clip["character"],
                    "speaker": clip["speaker"],
                    "text": clip["text"],
                    "synthesis_text": clip["synthesis_text"],
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "clip": clip["clip"],
                }
            )
            if clip["pause_ms"] > 0:
                silence = b"\x00\x00" * int(RATE * clip["pause_ms"] / 1000)
                out.writeframes(silence)
                cursor += clip["pause_ms"] / 1000.0

    timeline_path = out_dir / (Path(args.full_name).stem + "_timeline.json")
    timeline_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 56)
    print(f"voiced lines: {len(clips)} / {len(entries)}")
    print(f"full track: {full_path}  ({cursor:.1f}s)")
    print(f"timeline: {timeline_path}")
    if failures:
        print(f"FAILURES ({len(failures)}): " + ", ".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

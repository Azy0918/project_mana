from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment


ROOT = Path(__file__).resolve().parent
REMOTION_ROOT = ROOT / "remotion-anime"
ASSET_AUDIO_DIR = REMOTION_ROOT / "public" / "assets" / "13th-register" / "audio"
SRC_DIR = ROOT / "output_aivis_voice"
PV_NARR_DIR = ROOT / "output_aivis_pv_narration_nise"


@dataclass(frozen=True)
class ClipSpec:
    source: str
    number: str
    cast: str
    label: str
    pause_ms: int = 220


CLIPS: list[ClipSpec] = [
    ClipSpec("pv", "001", "ナレーション", "午前2時3分。", 260),
    ClipSpec("pv", "003", "ナレーション", "ただし、この店には、夜だけ開くレジがある。", 220),
    ClipSpec("pv", "004", "ナレーション", "その名は、だいじゅうさんレジ。", 360),
    ClipSpec("main", "020", "タクミ", "はい……はい？", 180),
    ClipSpec("main", "023", "ミナ", "だいじゅうさんレジ。", 160),
    ClipSpec("main", "049", "第十三レジ", "だいじゅうさんレジ。ただいま営業中。", 320),
    ClipSpec("pv", "007", "ナレーション", "現れたのは、2074年から来た、疲れきった会社員。", 220),
    ClipSpec("main", "080", "未来の会社員", "はい。2074年から来ました。", 180),
    ClipSpec("main", "093", "未来の会社員", "AI上司、ヒト上司、合成上司、過去の自分からの引き継ぎメモ。全部、上司です。", 220),
    ClipSpec("main", "105", "第十三レジ", "警告。誤った返品処理により、人類生存率がさんてんにぱーせんと低下します。", 300),
    ClipSpec("pv", "014", "ナレーション", "深夜2時20分まで、残りわずか。", 260),
    ClipSpec("main", "215", "第十三レジ", "未来とは、だいたい雑なメモの積み重ねです。", 260),
    ClipSpec("pv", "016", "ナレーション", "だいじゅうさんレジ。", 180),
    ClipSpec("pv", "017", "ナレーション", "これは、どこにでもあるコンビニで、たぶん今夜も起きている話。", 0),
]


def load_log(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return {row["番号"]: row for row in csv.DictReader(file)}


def clip_path(spec: ClipSpec, main_log: dict[str, dict[str, str]], pv_log: dict[str, dict[str, str]]) -> Path:
    if spec.source == "main":
        row = main_log[spec.number]
        return ROOT / row["output_file"]
    row = pv_log[spec.number]
    return ROOT / row["output_file"]


def build_assets(output_wav: Path, timeline_ts: Path) -> None:
    main_log = load_log(SRC_DIR / "generation_log.csv")
    pv_log = load_log(PV_NARR_DIR / "generation_log.csv")
    ASSET_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    cursor_ms = 0
    events: list[dict[str, object]] = []
    combined = AudioSegment.silent(duration=380, frame_rate=44100)
    cursor_ms += len(combined)

    for spec in CLIPS:
        audio = AudioSegment.from_file(clip_path(spec, main_log, pv_log)).set_channels(1).set_frame_rate(44100)
        start_ms = cursor_ms
        duration_ms = len(audio)
        combined += audio
        cursor_ms += duration_ms
        if spec.pause_ms:
            combined += AudioSegment.silent(duration=spec.pause_ms, frame_rate=44100)
            cursor_ms += spec.pause_ms
        events.append(
            {
                "number": spec.number,
                "cast": spec.cast,
                "text": spec.label,
                "direction": "PV trailer",
                "startMs": start_ms,
                "durationMs": duration_ms,
            }
        )

    target_ms = 60050
    if len(combined) < target_ms:
        combined += AudioSegment.silent(duration=target_ms - len(combined), frame_rate=44100)
    else:
        combined = combined[:target_ms]

    combined.export(output_wav, format="wav")

    payload = {
        "fps": 30,
        "durationMs": target_ms,
        "events": events,
    }
    timeline_ts.write_text(
        "import type { TimelineBundle } from \"./timeline\";\n\n"
        "export const trailerTimeline: TimelineBundle = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Remotion trailer voice audio and timeline from generated Aivis wavs.")
    parser.add_argument("--output-wav", type=Path, default=ASSET_AUDIO_DIR / "trailer_voice.wav")
    parser.add_argument("--timeline-ts", type=Path, default=REMOTION_ROOT / "src" / "trailerTimeline.ts")
    args = parser.parse_args()
    build_assets(args.output_wav, args.timeline_ts)
    print(f"wrote {args.output_wav}")
    print(f"wrote {args.timeline_ts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

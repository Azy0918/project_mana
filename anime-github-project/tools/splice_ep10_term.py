from __future__ import annotations

"""EP10 term-unification splice: 歴史メモ -> 履歴メモ in line ep10_v002.

ep10_v002 quotes EP1's receipt ("...歴史メモ、一件..."). Since EP1 now says
履歴メモ, EP10 must match. The reading changes れきしめも->りれきめも (same mora
count), so the new clip is speed-matched to the OLD clip duration and written
byte-for-byte into the same segment — every other line stays bit-identical and
no re-timing is needed. Player text (scene_manifest + reading manifest) is
updated in both trees.
"""

import io
import json
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
KAMI = REPO / "13th-register-kamishibai"
SITE = REPO / "site"
ASSET = "assets/ep10_full_voice_reading_hiragana.wav"
SCENE = "scene_manifest_ep10.json"
READING = "assets/manifest_reading_hiragana_ep10.json"
API = "http://127.0.0.1:10101"
LINE_ID = "ep10_v002"
STYLE = 2029042368
PAUSE_MS = 450
RATE = 44100


def _open(req, attempts=5):
    last = None
    for k in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def synth_pcm(reading: str, speed: float) -> bytes:
    q = urllib.parse.urlencode({"text": reading, "speaker": STYLE})
    query = json.loads(_open(urllib.request.Request(f"{API}/audio_query?{q}", data=b"", method="POST")).decode())
    query["speedScale"] = speed
    query["outputSamplingRate"] = RATE
    query["outputStereo"] = False
    body = json.dumps(query, ensure_ascii=False).encode("utf-8")
    p = urllib.parse.urlencode({"speaker": STYLE})
    wav = _open(urllib.request.Request(f"{API}/synthesis?{p}", data=body, method="POST",
                                       headers={"Content-Type": "application/json"}))
    time.sleep(0.3)
    with wave.open(io.BytesIO(wav), "rb") as w:
        return w.readframes(w.getnframes())


def main() -> int:
    scene = json.loads((KAMI / SCENE).read_text(encoding="utf-8"))
    row = next(r for r in scene if r["id"] == LINE_ID)
    i = scene.index(row)
    seg_start = row["start"]
    seg_end = scene[i + 1]["start"] if i + 1 < len(scene) else row["end"]

    with wave.open(str(KAMI / ASSET), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2)
        pcm = w.readframes(w.getnframes())
    bpf = 2
    s = round(seg_start * RATE) * bpf
    e = round(seg_end * RATE) * bpf
    seg_frames = (e - s) // bpf
    pause_frames = round(PAUSE_MS / 1000 * RATE)
    target_clip_frames = seg_frames - pause_frames

    new_reading = row["reading"].replace("れきしめも", "りれきめも")
    # measure at default speed, then speed-match to fill target_clip_frames exactly
    d1 = len(synth_pcm(new_reading, 1.0)) // bpf
    speed = max(0.5, min(2.0, d1 / target_clip_frames))
    clip = synth_pcm(new_reading, speed)
    clip_frames = len(clip) // bpf
    print(f"old segment {seg_end - seg_start:.3f}s | target clip {target_clip_frames/RATE:.3f}s "
          f"| default {d1/RATE:.3f}s -> speed {speed:.3f} -> new {clip_frames/RATE:.3f}s")

    # assemble exact-length segment: clip + silence padded/trimmed to seg_frames
    seg = bytearray(clip[: seg_frames * bpf])
    if len(seg) < seg_frames * bpf:
        seg += b"\x00\x00" * (seg_frames - len(seg) // bpf)
    new_pcm = pcm[:s] + bytes(seg) + pcm[e:]
    assert len(new_pcm) == len(pcm), (len(new_pcm), len(pcm))

    for base in (KAMI, SITE):
        wp = base / ASSET
        if base is KAMI or wp.exists():
            with wave.open(str(wp), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
                w.writeframes(new_pcm)
            print(f"wav -> {wp}")
        # update player text (dialogue + reading) in scene + reading manifests
        for rel, dkey, rkey in ((SCENE, "dialogue", "reading"), (READING, "text", "synthesis_text")):
            p = base / rel
            if not (base is KAMI or p.exists()):
                continue
            data = json.loads(p.read_text(encoding="utf-8"))
            for r in data:
                if r["id"] == LINE_ID:
                    r[dkey] = r[dkey].replace("歴史メモ", "履歴メモ")
                    r[rkey] = r[rkey].replace("れきしめも", "りれきめも")
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"text -> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

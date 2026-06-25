from __future__ import annotations

"""Tempo-preserving EP01 audio splice.

Keep the original (approved) EP01 voice track byte-for-byte for every unchanged
line, and replace only the 4 revised lines (Mina memo x2, Takumi tsukkomi,
receipt narration). The 4 new clips are synthesized at speedScale=SPEED so they
match the surrounding original tempo (measured median over 87 unchanged lines).

Outputs (overwrite): the EP01 full wav + contiguous timeline under
outputs/ep01_voice_reading_hiragana/, consumed by build_ep01_revision.py scene.
"""

import json
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path


def _open(req, attempts=5):
    last = None
    for k in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - retry transient transport errors
            last = e
            time.sleep(1.5 * (k + 1))
    raise last

REPO = Path(__file__).resolve().parents[2]
KAMI = REPO / "13th-register-kamishibai"
ASSET = KAMI / "assets" / "ep01_full_voice_reading_hiragana_mina_mao.wav"   # original, untouched
OLD_SCENE = KAMI / "scene_manifest.json"                                    # original 90-line boundaries
MANIFEST = KAMI / "assets" / "manifest_reading_hiragana_mina_mao.json"      # edited 91-line
OUT_DIR = REPO / "outputs" / "ep01_voice_reading_hiragana"
FULL = OUT_DIR / "ep01_full_voice_reading_hiragana_mina_mao.wav"
TIMELINE = OUT_DIR / "ep01_full_voice_reading_hiragana_mina_mao_timeline.json"
API = "http://127.0.0.1:10101"
SPEED = 1.089

CHANGED = {"ep01_v066_g2", "ep01_v068", "ep01_v076"}  # in-place replacements
INSERT_AFTER = {"ep01_v066_g2": "ep01_v066_g3"}        # new line emitted right after g2


def synth(text: str, style_id: int, rate: int) -> bytes:
    q = urllib.parse.urlencode({"text": text, "speaker": style_id})
    qreq = urllib.request.Request(f"{API}/audio_query?{q}", data=b"", method="POST")
    query = json.loads(_open(qreq).decode("utf-8"))
    query["speedScale"] = SPEED
    query["outputSamplingRate"] = rate
    query["outputStereo"] = False
    body = json.dumps(query, ensure_ascii=False).encode("utf-8")
    p = urllib.parse.urlencode({"speaker": style_id})
    req = urllib.request.Request(f"{API}/synthesis?{p}", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    wav_bytes = _open(req)
    time.sleep(0.3)
    # strip the 44-byte WAV header -> raw PCM
    import io
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getframerate() == rate and w.getnchannels() == 1 and w.getsampwidth() == 2
        return w.readframes(w.getnframes())


def main() -> int:
    man = {r["id"]: r for r in json.loads(MANIFEST.read_text(encoding="utf-8"))}
    old = json.loads(OLD_SCENE.read_text(encoding="utf-8"))

    with wave.open(str(ASSET), "rb") as w:
        rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        nframes = w.getnframes()
        pcm = w.readframes(nframes)
    print(f"original: {rate}Hz ch{ch} sw{sw} frames={nframes} ({nframes/rate:.2f}s)")
    assert ch == 1 and sw == 2, "expected mono 16-bit"
    bytes_per_frame = sw * ch

    def sidx(sec: float) -> int:
        return max(0, min(nframes, round(sec * rate))) * bytes_per_frame

    def silence(pause_ms: int) -> bytes:
        return b"\x00\x00" * int(rate * pause_ms / 1000)

    # synth the revised clips (g2, g3, v068, v076) at matched tempo
    new_pcm: dict[str, bytes] = {}
    for cid in ("ep01_v066_g2", "ep01_v066_g3", "ep01_v068", "ep01_v076"):
        r = man[cid]
        new_pcm[cid] = synth(r["synthesis_text"], int(r["style_id"]), rate)
        print(f"synth {cid}: {len(new_pcm[cid])/bytes_per_frame/rate:.2f}s  (speed {SPEED})")

    out = bytearray()
    timeline = []
    cursor = 0.0  # seconds

    def emit(line_id: str, character: str, seg: bytes):
        nonlocal cursor
        dur = len(seg) / bytes_per_frame / rate
        out.extend(seg)
        timeline.append({"id": line_id, "character": character,
                         "start": round(cursor, 3), "end": round(cursor + dur, 3)})
        cursor += dur

    n = len(old)
    for i, r in enumerate(old):
        iid = r["id"]
        if iid in CHANGED:
            pause = int(man[iid].get("pause_after_ms") or 0)
            emit(iid, r["speaker"], new_pcm[iid] + silence(pause))
            if iid in INSERT_AFTER:
                g = INSERT_AFTER[iid]
                gp = int(man[g].get("pause_after_ms") or 0)
                emit(g, man[g]["character"], new_pcm[g] + silence(gp))
        else:
            s = sidx(r["start"])
            e = sidx(old[i + 1]["start"]) if i + 1 < n else len(pcm)
            emit(iid, r["speaker"], pcm[s:e])

    FULL.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(FULL), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(out))
    TIMELINE.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"spliced -> {FULL}  ({cursor:.2f}s, {len(timeline)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

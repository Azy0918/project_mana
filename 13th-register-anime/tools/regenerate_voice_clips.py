"""
第十三レジ EP01 音声クリップ再生成スクリプト
AivisSpeech API (localhost:10101) を使って manifest の synthesis_text から
全クリップを再合成し、フルWAV + scene_manifest.json を生成します。

使い方:
  python regenerate_voice_clips.py

出力:
  output_voice/clips/                                           - 各クリップ WAV
  output_voice/ep01_full_voice_reading_hiragana_mina_mao.wav   - 結合済みフルWAV
  output_voice/scene_manifest.json                             - タイムスタンプ更新済みマニフェスト
"""

import json
import struct
import time
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

# ===== 設定 =====
AIVIS_BASE = "http://localhost:10101"
OUTPUT_DIR = Path(__file__).parent / "output_voice"
CLIPS_DIR = OUTPUT_DIR / "clips"
FULL_WAV = OUTPUT_DIR / "ep01_full_voice_reading_hiragana_mina_mao.wav"
OUT_SCENE_MANIFEST = OUTPUT_DIR / "scene_manifest.json"

MANIFEST_LOCAL = Path(__file__).parent.parent.parent / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_mina_mao.json"
MANIFEST_URL = "https://raw.githubusercontent.com/Azy0918/project_mana/gh-pages/13th-register-kamishibai/assets/manifest_reading_hiragana_mina_mao.json"

SCENE_MANIFEST_LOCAL = Path(__file__).parent.parent.parent / "13th-register-kamishibai" / "scene_manifest.json"
SCENE_MANIFEST_URL = "https://raw.githubusercontent.com/Azy0918/project_mana/gh-pages/13th-register-kamishibai/scene_manifest.json"
# =================


def load_json(local: Path, url: str):
    if local.exists():
        print(f"ローカルから読み込み: {local}")
        with open(local, encoding="utf-8") as f:
            return json.load(f)
    print(f"URLから取得: {url}")
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))


def aivis_synthesis(text: str, speaker_id: int, retry: int = 3) -> bytes:
    params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
    query_url = f"{AIVIS_BASE}/audio_query?{params}"
    query_data = None
    for attempt in range(retry):
        try:
            req = urllib.request.Request(query_url, method="POST")
            with urllib.request.urlopen(req, timeout=30) as r:
                query_data = r.read()
            break
        except Exception as e:
            if attempt == retry - 1:
                raise
            print(f"  audio_query 失敗 ({attempt+1}/{retry}): {e}")
            time.sleep(2)

    synth_url = f"{AIVIS_BASE}/synthesis?speaker={speaker_id}"
    req = urllib.request.Request(
        synth_url, data=query_data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    for attempt in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            if attempt == retry - 1:
                raise
            print(f"  synthesis 失敗 ({attempt+1}/{retry}): {e}")
            time.sleep(2)


def wav_duration_sec(wav_bytes: bytes) -> float:
    """WAV バイト列から再生時間（秒）を計算"""
    sample_rate = struct.unpack_from("<I", wav_bytes, 24)[0]
    channels = struct.unpack_from("<H", wav_bytes, 22)[0]
    bits = struct.unpack_from("<H", wav_bytes, 34)[0]
    bytes_per_sample = bits // 8
    data_size = struct.unpack_from("<I", wav_bytes, 40)[0]
    total_samples = data_size // (channels * bytes_per_sample)
    return total_samples / sample_rate


def add_silence(wav_bytes: bytes, ms: int) -> bytes:
    if ms <= 0:
        return wav_bytes
    sample_rate = struct.unpack_from("<I", wav_bytes, 24)[0]
    channels = struct.unpack_from("<H", wav_bytes, 22)[0]
    bits = struct.unpack_from("<H", wav_bytes, 34)[0]
    bytes_per_sample = bits // 8
    silence_samples = int(sample_rate * ms / 1000)
    silence_data = b"\x00" * (silence_samples * channels * bytes_per_sample)
    body = wav_bytes[44:] + silence_data
    data_size = len(body)
    header = bytearray(wav_bytes[:44])
    struct.pack_into("<I", header, 4, 36 + data_size)
    struct.pack_into("<I", header, 40, data_size)
    return bytes(header) + body


def get_wav_duration_ffprobe(path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def concat_wavs_ffmpeg(clip_paths: list, output: Path):
    list_file = OUTPUT_DIR / "_concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
           "-i", str(list_file), "-c", "copy", str(output)]
    print("\nffmpeg で結合中...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("ffmpeg エラー:", result.stderr[-500:])
        raise RuntimeError("ffmpeg 結合失敗")
    list_file.unlink(missing_ok=True)
    print(f"結合完了: {output}")


def build_scene_manifest(scene_manifest_base: list, clip_timing: dict) -> list:
    """
    scene_manifest_base の各エントリの start/end を
    clip_timing[id] = (start_sec, end_sec) で上書きした新しいリストを返す
    """
    updated = []
    for entry in scene_manifest_base:
        vid = entry["id"]
        new_entry = dict(entry)
        if vid in clip_timing:
            new_entry["start"] = round(clip_timing[vid][0], 3)
            new_entry["end"] = round(clip_timing[vid][1], 3)
        updated.append(new_entry)
    return updated


def main():
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_json(MANIFEST_LOCAL, MANIFEST_URL)
    scene_manifest_base = load_json(SCENE_MANIFEST_LOCAL, SCENE_MANIFEST_URL)
    print(f"manifest: {len(manifest)} エントリ / scene_manifest: {len(scene_manifest_base)} エントリ")

    try:
        with urllib.request.urlopen(f"{AIVIS_BASE}/version", timeout=5) as r:
            version = json.loads(r.read())
        print(f"AivisSpeech バージョン: {version}")
    except Exception as e:
        print(f"AivisSpeech に接続できません: {e}")
        return

    # id → クリップパス の順序付きリスト（結合順）
    ordered_clips = []  # [(vid, clip_path)]
    errors = []

    for i, entry in enumerate(manifest):
        vid = entry["id"]
        text = entry.get("synthesis_text", "").strip()
        speaker_id = entry.get("style_id")
        pause_ms = entry.get("pause_after_ms", 0)
        character = entry.get("character", "")

        if entry.get("clip") is None or not text or speaker_id is None:
            print(f"  [{i+1:02d}/{len(manifest)}] {vid} ({character}) — スキップ")
            continue

        clip_path = CLIPS_DIR / f"{vid}.wav"

        if clip_path.exists():
            print(f"  [{i+1:02d}/{len(manifest)}] {vid} — キャッシュ済み")
        else:
            print(f"  [{i+1:02d}/{len(manifest)}] {vid} ({character}) 合成: {text[:40]}")
            try:
                wav_bytes = aivis_synthesis(text, speaker_id)
                if pause_ms > 0:
                    wav_bytes = add_silence(wav_bytes, pause_ms)
                clip_path.write_bytes(wav_bytes)
                time.sleep(0.1)
            except Exception as e:
                print(f"    !! エラー: {e}")
                errors.append((vid, str(e)))
                continue

        ordered_clips.append((vid, clip_path))

    print(f"\n合成完了: {len(ordered_clips)} クリップ / エラー: {len(errors)} 件")
    if errors:
        for vid, err in errors:
            print(f"  {vid}: {err}")

    if not ordered_clips:
        return

    # タイムスタンプ計算（各クリップの実際の長さを測定）
    print("\nタイムスタンプ計算中...")
    clip_timing = {}  # id → (start, end)
    cursor = 0.0
    for vid, clip_path in ordered_clips:
        dur = get_wav_duration_ffprobe(clip_path)
        clip_timing[vid] = (cursor, cursor + dur)
        cursor += dur

    # フルWAV結合
    clip_paths = [p for _, p in ordered_clips]
    concat_wavs_ffmpeg(clip_paths, FULL_WAV)

    # scene_manifest.json 更新
    updated_scene_manifest = build_scene_manifest(scene_manifest_base, clip_timing)
    OUT_SCENE_MANIFEST.write_text(
        json.dumps(updated_scene_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"scene_manifest 更新: {OUT_SCENE_MANIFEST}")

    size_mb = FULL_WAV.stat().st_size / 1024 / 1024
    total_dur = cursor
    print(f"\n完成:")
    print(f"  WAV: {FULL_WAV} ({size_mb:.1f} MB, {total_dur:.1f}秒)")
    print(f"  manifest: {OUT_SCENE_MANIFEST}")
    print(f"\n次のステップ（gh-pages ブランチにコピーして push）:")
    print(f"  {FULL_WAV}")
    print(f"  → 13th-register-kamishibai/assets/ep01_full_voice_reading_hiragana_mina_mao.wav")
    print(f"  {OUT_SCENE_MANIFEST}")
    print(f"  → 13th-register-kamishibai/scene_manifest.json")


if __name__ == "__main__":
    main()

"""
第十三レジ EP01 音声クリップ再生成スクリプト
AivisSpeech API (localhost:10101) を使って manifest の synthesis_text から
全クリップを再合成し、フルWAVに結合します。

使い方:
  python regenerate_voice_clips.py

出力:
  output_voice/clips/   - 各クリップ WAV
  output_voice/ep01_full_voice_reading_hiragana_mina_mao.wav  - 結合済みフルWAV
"""

import json
import time
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

# ===== 設定 =====
AIVIS_BASE = "http://localhost:10101"
OUTPUT_DIR = Path(__file__).parent / "output_voice"
CLIPS_DIR = OUTPUT_DIR / "clips"
FULL_WAV = OUTPUT_DIR / "ep01_full_voice_reading_hiragana_mina_mao.wav"

# manifest JSONのパス（gh-pagesのローカルクローンがあればそちらを指定、なければURLから取得）
MANIFEST_LOCAL = Path(__file__).parent.parent.parent / "13th-register-kamishibai" / "assets" / "manifest_reading_hiragana_mina_mao.json"
MANIFEST_URL = "https://raw.githubusercontent.com/Azy0918/project_mana/gh-pages/13th-register-kamishibai/assets/manifest_reading_hiragana_mina_mao.json"
# =================


def load_manifest():
    if MANIFEST_LOCAL.exists():
        print(f"manifest をローカルから読み込み: {MANIFEST_LOCAL}")
        with open(MANIFEST_LOCAL, encoding="utf-8") as f:
            return json.load(f)
    print(f"manifest をURLから取得: {MANIFEST_URL}")
    with urllib.request.urlopen(MANIFEST_URL) as r:
        return json.loads(r.read().decode("utf-8"))


def aivis_synthesis(text: str, speaker_id: int, retry: int = 3) -> bytes:
    """AivisSpeech API でテキストを音声合成して WAV バイト列を返す"""
    # Step1: audio_query
    params = urllib.parse.urlencode({"text": text, "speaker": speaker_id})
    query_url = f"{AIVIS_BASE}/audio_query?{params}"
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

    # Step2: synthesis
    synth_url = f"{AIVIS_BASE}/synthesis?speaker={speaker_id}"
    req = urllib.request.Request(
        synth_url,
        data=query_data,
        method="POST",
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


def add_silence(wav_bytes: bytes, ms: int) -> bytes:
    """WAV の末尾に無音を追加して返す（簡易版: 同じヘッダで無音PCMを付加）"""
    if ms <= 0:
        return wav_bytes
    # WAV ヘッダから sample_rate と channels を読む
    import struct
    sample_rate = struct.unpack_from("<I", wav_bytes, 24)[0]
    channels = struct.unpack_from("<H", wav_bytes, 22)[0]
    bits = struct.unpack_from("<H", wav_bytes, 34)[0]
    bytes_per_sample = bits // 8
    silence_samples = int(sample_rate * ms / 1000)
    silence_data = b"\x00" * (silence_samples * channels * bytes_per_sample)

    # 元データ本体（44バイト以降）+ 無音を結合してヘッダ更新
    body = wav_bytes[44:] + silence_data
    data_size = len(body)
    file_size = 36 + data_size

    import io
    buf = io.BytesIO(wav_bytes[:44])
    buf.seek(0)
    header = bytearray(buf.read(44))
    struct.pack_into("<I", header, 4, file_size)
    struct.pack_into("<I", header, 40, data_size)
    return bytes(header) + body


def concat_wavs_ffmpeg(clip_paths: list, output: Path):
    """ffmpeg の concat で WAV を結合"""
    list_file = OUTPUT_DIR / "_concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(output),
    ]
    print(f"\nffmpeg で結合中...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("ffmpeg エラー:", result.stderr[-500:])
        raise RuntimeError("ffmpeg 結合失敗")
    list_file.unlink(missing_ok=True)
    print(f"結合完了: {output}")


def main():
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    print(f"エントリ数: {len(manifest)}")

    # API 疎通確認
    try:
        with urllib.request.urlopen(f"{AIVIS_BASE}/version", timeout=5) as r:
            version = json.loads(r.read())
        print(f"AivisSpeech バージョン: {version}")
    except Exception as e:
        print(f"AivisSpeech に接続できません: {e}")
        print(f"  → {AIVIS_BASE} が起動しているか確認してください")
        return

    clip_paths = []
    errors = []

    for i, entry in enumerate(manifest):
        vid = entry["id"]
        text = entry.get("synthesis_text", "").strip()
        speaker_id = entry.get("style_id")
        pause_ms = entry.get("pause_after_ms", 0)
        character = entry.get("character", "")

        # SE など clip=null のエントリはスキップ
        if entry.get("clip") is None or not text or speaker_id is None:
            print(f"  [{i+1:02d}/{len(manifest)}] {vid} ({character}) — スキップ (SE/null)")
            continue

        clip_path = CLIPS_DIR / f"{vid}.wav"

        if clip_path.exists():
            print(f"  [{i+1:02d}/{len(manifest)}] {vid} — キャッシュ済みスキップ")
            clip_paths.append(clip_path)
            continue

        print(f"  [{i+1:02d}/{len(manifest)}] {vid} ({character}) 合成中: {text[:40]}")
        try:
            wav_bytes = aivis_synthesis(text, speaker_id)
            if pause_ms > 0:
                wav_bytes = add_silence(wav_bytes, pause_ms)
            clip_path.write_bytes(wav_bytes)
            clip_paths.append(clip_path)
            time.sleep(0.1)  # API 負荷軽減
        except Exception as e:
            print(f"    !! エラー: {e}")
            errors.append((vid, str(e)))

    print(f"\n合成完了: {len(clip_paths)} クリップ / エラー: {len(errors)} 件")
    if errors:
        print("エラー一覧:")
        for vid, err in errors:
            print(f"  {vid}: {err}")

    if not clip_paths:
        print("結合するクリップがありません。終了します。")
        return

    concat_wavs_ffmpeg(clip_paths, FULL_WAV)
    size_mb = FULL_WAV.stat().st_size / 1024 / 1024
    print(f"\n完成: {FULL_WAV}")
    print(f"  サイズ: {size_mb:.1f} MB")
    print(f"\n次のステップ:")
    print(f"  {FULL_WAV}")
    print(f"  → gh-pages の 13th-register-kamishibai/assets/ にコピーして push")


if __name__ == "__main__":
    main()

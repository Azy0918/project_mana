# -*- coding: utf-8 -*-
"""『深夜二時の第十三レジ』 Gemini TTS 声サンプル一括生成 CLI。

Streamlit を使わずにコマンドラインで音声サンプルを生成し、スマホ試聴用の
HTML ページ(voice_samples/index.html)も出力する。生成物は gh-pages に
置けば公開URLでスマホ再生できる。

使い方:
    # キャラごとに候補ボイスを複数生成(全キャラ・各3声)
    python tools/gen_voice_samples.py --voices 3

    # 1キャラだけ・声を指定して生成
    python tools/gen_voice_samples.py --character ミナ --voice Kore --voice Leda

APIキー:
    --api-key で渡すか、.env / 環境変数 GEMINI_API_KEY を使う。
    SSL証明書エラー対策で既定は検証無効(--secure で有効化)。
"""
from __future__ import annotations

import argparse
import io
import re
import sys
import wave
from pathlib import Path

APP = Path(__file__).resolve()
REPO = APP.parents[1]                       # anime-github-project ルート
ENV_PATH = REPO / ".env"
OUT_DIR = REPO / "voice_samples"            # 生成WAV + index.html

MODEL_DEFAULT = "gemini-2.5-flash-preview-tts"

# audition アプリと同じキャラ定義(セリフ・スタイル・既定候補)
CHARACTERS: dict[str, dict] = {
    "ナレーション": dict(slug="narration", default_voice="Charon",
        candidates=["Charon", "Iapetus", "Algenib"],
        line="午前二時三分。国道沿いのコンビニは、冷蔵ケースの音だけで静かだった。",
        style="落ち着いた深夜のナレーション。淡々と、少しだけ温かく、ゆっくり読む。"),
    "タクミ": dict(slug="takumi", default_voice="Puck",
        candidates=["Puck", "Zephyr", "Fenrir"],
        line="コンビニって、夜になるとレジが増えるんですか。",
        style="若い男性の新人バイト。素朴で少し戸惑い気味、軽いツッコミ口調。"),
    "ミナ": dict(slug="mina", default_voice="Kore",
        candidates=["Kore", "Leda", "Autonoe"],
        line="夜勤だから。",
        style="淡々とした女性の先輩。低めで落ち着き、感情を抑えた素っ気ない口調。"),
    "汗田竜司": dict(slug="asada", default_voice="Iapetus",
        candidates=["Iapetus", "Enceladus", "Charon"],
        line="理屈としては近い。",
        style="五十四歳の男性技術者。低く落ち着いた声、理知的で誠実。"),
    "第十三レジ": dict(slug="register13", default_voice="Algieba",
        candidates=["Algieba", "Umbriel", "Rasalgethi"],
        line="第十三レジ。ただいま営業中。",
        style="機械的で無表情なレジ端末の合成音声。平板で淡々、少し不思議で近未来的。"),
    "ナビ": dict(slug="navi", default_voice="Despina",
        candidates=["Despina", "Erinome", "Aoede"],
        line="次の異常地点。冷凍庫。",
        style="カーナビの音声案内。クリアで事務的、合成音声らしい平坦さ。"),
    "未来の会社員": dict(slug="future_employee", default_voice="Enceladus",
        candidates=["Enceladus", "Iapetus", "Orus"],
        line="返品、お願いします。レシートは五十年後に発行されます。",
        style="疲れた未来のサラリーマン。やや低く力ない、丁寧だが平淡。"),
    "座木山辰哉": dict(slug="zakiyama", default_voice="Fenrir",
        candidates=["Fenrir", "Puck", "Zubenelgenubi"],
        line="コピー、白黒でいいよ。色がつくと、記憶が増えるから。",
        style="風変わりな常連の男性。マイペースで飄々とした、味のある口調。"),
    "唐沢栄治": dict(slug="karasawa", default_voice="Orus",
        candidates=["Orus", "Algenib", "Charon"],
        line="時空処理でも、一会計三分以内でお願いします。",
        style="本部のSV。きびきびと事務的、数字を重視する現実的な口調。"),
    "トラック運転手": dict(slug="truck_driver", default_voice="Algenib",
        candidates=["Algenib", "Orus", "Fenrir"],
        line="荷物、未来便って書いてあるんですけど、ここで合ってますか。",
        style="中年男性のトラック運転手。素朴で人懐っこい、やや戸惑った口調。"),
}


def load_env_key() -> str | None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH)
        load_dotenv()
    except Exception:
        pass
    import os
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return key.strip() if key else None


def parse_rate_from_mime(mime: str | None, default: int = 24000) -> int:
    if not mime:
        return default
    m = re.search(r"rate=(\d+)", mime)
    return int(m.group(1)) if m else default


def pcm_to_wav_bytes(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def generate_tts(api_key: str, model: str, voice: str, text: str, style: str,
                 insecure_ssl: bool = True) -> bytes:
    from google import genai
    from google.genai import types
    import httpx
    try:
        import certifi
        verify = False if insecure_ssl else certifi.where()
    except Exception:
        verify = not insecure_ssl
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(httpx_client=httpx.Client(verify=verify, timeout=90.0)),
    )
    prompt = f"{style.strip()}\n\n{text.strip()}" if style.strip() else text.strip()
    resp = client.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
        ),
    )
    cands = getattr(resp, "candidates", None)
    if not cands:
        raise RuntimeError("候補なし")
    parts = cands[0].content.parts if cands[0].content else None
    if not parts:
        raise RuntimeError("パートなし(安全フィルタの可能性)")
    inline = getattr(parts[0], "inline_data", None)
    if not inline or not inline.data:
        raise RuntimeError("音声データが空")
    rate = parse_rate_from_mime(getattr(inline, "mime_type", None))
    return pcm_to_wav_bytes(inline.data, rate=rate)


def scan_existing_results() -> list[dict]:
    """OUT_DIR にある wav を走査して results 形式(全て ok=True)に変換する。"""
    slug2ch = {info["slug"]: (ch, info["line"]) for ch, info in CHARACTERS.items()}
    found: list[dict] = []
    for wav in sorted(OUT_DIR.glob("*.wav")):
        stem = wav.stem  # {slug}_{voice}
        for slug, (ch, line) in slug2ch.items():
            if stem.startswith(slug + "_"):
                voice = stem[len(slug) + 1:]
                found.append(dict(character=ch, slug=slug, line=line,
                                  voice=voice, file=wav.name, ok=True, err=""))
                break
    return found


def merge_results(disk: list[dict], run: list[dict]) -> list[dict]:
    """ディスク走査結果に、今回失敗(ok=False)した分を重複なく加える。"""
    have = {(r["slug"], r["voice"]) for r in disk}
    out = list(disk)
    for r in run:
        if not r["ok"] and (r["slug"], r["voice"]) not in have:
            out.append(r)
    return out


def build_index_html(results: list[dict]) -> str:
    """results: [{character, slug, line, voice, file, ok, err}] からスマホ試聴ページを作る。"""
    # キャラ定義順に並べる
    order = {ch: i for i, ch in enumerate(CHARACTERS)}
    results = sorted(results, key=lambda r: (order.get(r["character"], 99), r["voice"]))
    by_char: dict[str, list[dict]] = {}
    for r in results:
        by_char.setdefault(r["character"], []).append(r)
    cards = []
    for ch, items in by_char.items():
        line = items[0]["line"]
        rows = []
        for r in items:
            if r["ok"]:
                rows.append(
                    f'<div class="row"><span class="vn">{r["voice"]}</span>'
                    f'<audio controls preload="none" src="{r["file"]}"></audio></div>'
                )
            else:
                rows.append(
                    f'<div class="row err"><span class="vn">{r["voice"]}</span>'
                    f'<span class="e">生成失敗: {r["err"]}</span></div>'
                )
        cards.append(
            f'<section class="card"><h2>{ch}</h2>'
            f'<p class="line">「{line}」</p>{"".join(rows)}</section>'
        )
    return (
        '<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">'
        '<meta name="google" content="notranslate"><meta name="viewport" '
        'content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<title>第十三レジ ｜ 声サンプル試聴</title><style>'
        ':root{--bg:#05070b;--panel:#101720;--line:#26384a;--text:#edf7ff;--muted:#98a7b8;--cyan:#53e5ff}'
        '*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);'
        'font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.6;padding:20px 14px 60px}'
        '.wrap{max-width:560px;margin:0 auto}h1{font-size:18px;margin:2px 0 4px}'
        '.note{color:var(--muted);font-size:12.5px;margin:0 0 18px}'
        '.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:14px;margin:0 0 14px}'
        '.card h2{font-size:15px;margin:0 0 2px;color:var(--cyan)}'
        '.line{font-size:12.5px;color:var(--muted);margin:0 0 10px}'
        '.row{display:flex;align-items:center;gap:10px;margin:8px 0}'
        '.vn{flex:0 0 96px;font-size:12px;font-weight:700}'
        'audio{flex:1;height:34px}.err .e{color:#ff9aa2;font-size:12px}'
        '</style></head><body><div class="wrap">'
        '<h1>🎙️ 深夜二時の第十三レジ ｜ 声サンプル試聴</h1>'
        '<p class="note">各キャラの候補ボイスです。再生して、採用したい声を選んでください。'
        '「○○キャラは△△」と伝えてもらえれば確定保存します。</p>'
        + "".join(cards) +
        '</div></body></html>'
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", default=None, help="未指定なら .env / 環境変数を使う")
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--character", action="append", help="対象キャラ(複数可)。未指定で全キャラ")
    ap.add_argument("--voice", action="append", help="使うボイス(複数可)。未指定で各キャラの候補")
    ap.add_argument("--voices", type=int, default=0, help="各キャラ候補の先頭N声に絞る(0=全候補)")
    ap.add_argument("--throttle", type=float, default=7.0, help="各生成の間隔秒(10req/分対策)")
    ap.add_argument("--force", action="store_true", help="既存wavも上書き再生成")
    ap.add_argument("--secure", action="store_true", help="SSL検証を有効化(既定は無効)")
    args = ap.parse_args()

    api_key = args.api_key or load_env_key()
    if not api_key:
        print("APIキーがありません。--api-key か .env の GEMINI_API_KEY を設定してください。", file=sys.stderr)
        return 2

    import time
    targets = args.character or list(CHARACTERS.keys())
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for ch in targets:
        info = CHARACTERS.get(ch)
        if not info:
            print(f"未知のキャラ: {ch}", file=sys.stderr)
            continue
        voices = args.voice or info["candidates"]
        if args.voices > 0:
            voices = voices[: args.voices]
        for v in voices:
            fname = f'{info["slug"]}_{v}.wav'
            if not args.force and (OUT_DIR / fname).exists():
                print(f"スキップ(既存): {ch} / {v}")
                results.append(dict(character=ch, slug=info["slug"], line=info["line"],
                                    voice=v, file=fname, ok=True, err=""))
                continue
            print(f"生成中: {ch} / {v} ...", flush=True)
            for attempt in range(2):  # 429 は1回だけリトライ
                try:
                    wav = generate_tts(api_key, args.model, v, info["line"], info["style"],
                                       insecure_ssl=not args.secure)
                    (OUT_DIR / fname).write_bytes(wav)
                    results.append(dict(character=ch, slug=info["slug"], line=info["line"],
                                        voice=v, file=fname, ok=True, err=""))
                    print(f"  OK -> voice_samples/{fname}")
                    break
                except Exception as e:  # noqa: BLE001
                    msg = str(e)
                    if "RESOURCE_EXHAUSTED" in msg and "per" in msg.lower() and attempt == 0:
                        wait = 62
                        print(f"  レート上限。{wait}秒待って再試行…", flush=True)
                        time.sleep(wait)
                        continue
                    results.append(dict(character=ch, slug=info["slug"], line=info["line"],
                                        voice=v, file=fname, ok=False, err=msg[:120]))
                    print(f"  失敗: {e}", file=sys.stderr)
                    break
            time.sleep(args.throttle)  # 10req/分の上限を避ける

    # index は OUT_DIR 上の全 wav から再構築(過去ぶんも含めて一覧化)
    merged = merge_results(scan_existing_results(), results)
    (OUT_DIR / "index.html").write_text(build_index_html(merged), encoding="utf-8")
    ok = sum(1 for r in merged if r["ok"])
    print(f"\n完了: 音声 {ok} 本を一覧化。失敗 {sum(1 for r in merged if not r['ok'])} 件。"
          f" 一覧: voice_samples/index.html")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

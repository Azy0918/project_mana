# -*- coding: utf-8 -*-
"""『深夜二時の第十三レジ』 Gemini TTS 音声オーディションアプリ。

キャラクターごとに Gemini TTS の声(プリセットボイス)を聞き比べ、採用した声を
voices.yaml に保存する Streamlit アプリ。

起動:
    streamlit run tools/gemini_voice_audition_app.py

前提:
    - .env に GEMINI_API_KEY=... を置く(コードに直書きしない)
    - pip install -r requirements.txt
"""

from __future__ import annotations

import io
import re
import wave
from datetime import datetime
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# パス・定数
# ---------------------------------------------------------------------------
APP = Path(__file__).resolve()
REPO = APP.parents[1]                       # anime-github-project ルート
VOICES_YAML = REPO / "voices.yaml"
OUT_DIR = REPO / "assets" / "voice_tests"   # 生成WAVの保存先
ENV_PATH = REPO / ".env"

# Gemini TTS 対応モデル(プレビュー)
MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
]

# Gemini TTS のプリセットボイス(30種)。声色は実際に聞いて選ぶ。
VOICES = [
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird", "Zubenelgenubi",
    "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
]

# キャラクター定義: 表示名 -> (ファイル用slug, 確認用セリフ, 既定スタイル指示, 候補ボイス初期値)
CHARACTERS: dict[str, dict] = {
    "ナレーション": dict(
        slug="narration", default_voice="Charon",
        line="午前二時三分。",
        style="落ち着いた深夜のナレーション。淡々と、少しだけ温かく、ゆっくり読む。"),
    "タクミ": dict(
        slug="takumi", default_voice="Puck",
        line="コンビニって夜になるとレジが増えるんですか。",
        style="若い男性の新人バイト。素朴で少し戸惑い気味、軽いツッコミ口調。"),
    "ミナ": dict(
        slug="mina", default_voice="Kore",
        line="夜勤だから。",
        style="淡々とした女性の先輩。低めで落ち着き、感情を抑えた素っ気ない口調。"),
    "汗田竜司": dict(
        slug="asada", default_voice="Iapetus",
        line="理屈としては近い。",
        style="五十四歳の男性技術者。低く落ち着いた声、理知的で誠実。"),
    "第十三レジ": dict(
        slug="register13", default_voice="Algieba",
        line="第十三レジ。ただいま営業中。",
        style="機械的で無表情なレジ端末の合成音声。平板で淡々、少し不思議で近未来的。"),
    "ナビ": dict(
        slug="navi", default_voice="Despina",
        line="次の異常地点。冷凍庫。",
        style="カーナビの音声案内。クリアで事務的、合成音声らしい平坦さ。"),
    "未来の会社員": dict(
        slug="future_employee", default_voice="Enceladus",
        line="返品、お願いします。",
        style="疲れた未来のサラリーマン。やや低く力ない、丁寧だが平淡。"),
    "座木山辰哉": dict(
        slug="zakiyama", default_voice="Fenrir",
        line="コピー、白黒でいいよ。色がつくと記憶が増えるから。",
        style="風変わりな常連の男性。マイペースで飄々とした、味のある口調。"),
    "唐沢栄治": dict(
        slug="karasawa", default_voice="Orus",
        line="時空処理でも、一会計三分以内でお願いします。",
        style="店長気質の男性。きびきびと事務的、現実的で少し早口。"),
    "トラック運転手": dict(
        slug="truck_driver", default_voice="Algenib",
        line="荷物、未来便って書いてあるんですけど、ここで合ってますか。",
        style="中年男性のトラック運転手。素朴で人懐っこい、やや戸惑った口調。"),
}


# ---------------------------------------------------------------------------
# 補助関数
# ---------------------------------------------------------------------------
def load_env_key() -> str | None:
    """.env と環境変数から GEMINI_API_KEY を読む(コードに直書きしない)。"""
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH)
        load_dotenv()  # カレントの .env もフォールバックで読む
    except Exception:
        pass
    import os
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return key.strip() if key else None


def load_voices_yaml() -> dict:
    """voices.yaml を読む。無ければ空の構造を返す。"""
    if not VOICES_YAML.exists():
        return {"characters": {}}
    try:
        import yaml
        data = yaml.safe_load(VOICES_YAML.read_text(encoding="utf-8")) or {}
        data.setdefault("characters", {})
        return data
    except Exception as e:  # noqa: BLE001
        st.warning(f"voices.yaml の読み込みに失敗しました: {e}")
        return {"characters": {}}


def save_voices_yaml(data: dict) -> None:
    """voices.yaml へ保存(日本語をそのまま、キー順維持)。"""
    import yaml
    VOICES_YAML.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def pcm_to_wav_bytes(pcm: bytes, rate: int = 24000, channels: int = 1, width: int = 2) -> bytes:
    """Gemini TTS が返す生PCMを WAV バイト列に包む(既定 24kHz/16bit/mono)。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def parse_rate_from_mime(mime: str | None, default: int = 24000) -> int:
    """mime 例 'audio/L16;rate=24000' からサンプルレートを取り出す。"""
    if not mime:
        return default
    m = re.search(r"rate=(\d+)", mime)
    return int(m.group(1)) if m else default


def generate_tts(api_key: str, model: str, voice: str, text: str, style: str,
                 insecure_ssl: bool = True) -> tuple[bytes, int]:
    """Gemini TTS で音声を生成し (wav_bytes, rate) を返す。失敗時は例外。"""
    from google import genai
    from google.genai import types

    # ローカルの証明書エラー(SSL: CERTIFICATE_VERIFY_FAILED)対策。
    # insecure_ssl=True で検証を無効化、False で certifi のCAバンドルを使う。
    # 注意: client_args={"verify": ...} は当環境では効かず、httpx_client を
    # 直接渡す方式でのみ SSL 検証を制御できる(実機検証済み)。
    import httpx
    try:
        import certifi
        verify = False if insecure_ssl else certifi.where()
    except Exception:
        verify = not insecure_ssl
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            httpx_client=httpx.Client(verify=verify, timeout=60.0),
        ),
    )
    # スタイル指示があれば自然言語で前置きし、その後に読ませるセリフを置く
    prompt = f"{style.strip()}\n\n{text.strip()}" if style.strip() else text.strip()

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                )
            ),
        ),
    )

    # 安全に音声パートを取り出す
    cands = getattr(resp, "candidates", None)
    if not cands:
        raise RuntimeError("音声が返りませんでした(候補なし)。プロンプトや権限を確認してください。")
    parts = cands[0].content.parts if cands[0].content else None
    if not parts:
        raise RuntimeError("音声が返りませんでした(パートなし)。安全フィルタの可能性があります。")
    inline = getattr(parts[0], "inline_data", None)
    if not inline or not inline.data:
        raise RuntimeError("音声データが空です。モデル名がTTS対応か確認してください。")

    rate = parse_rate_from_mime(getattr(inline, "mime_type", None))
    return pcm_to_wav_bytes(inline.data, rate=rate), rate


def safe_filename(character: str, voice: str) -> str:
    """character_voice_timestamp.wav 形式のファイル名(ASCIIスラッグ)。"""
    slug = CHARACTERS.get(character, {}).get("slug") or re.sub(r"\W+", "_", character)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{slug}_{voice}_{ts}.wav"


# ---------------------------------------------------------------------------
# 画面
# ---------------------------------------------------------------------------
st.set_page_config(page_title="第十三レジ Gemini TTS オーディション", page_icon="🎙️", layout="wide")
st.title("🎙️ 第十三レジ ｜ Gemini TTS 音声オーディション")
st.caption("キャラクターごとに Gemini TTS の声を聞き比べ、採用した声を voices.yaml に保存します。")

api_key = load_env_key()
if not api_key:
    st.warning(
        "GEMINI_API_KEY が未設定です。下の欄に貼り付けてください"
        "（このセッションのみ使用・保存しません）。または `.env` に `GEMINI_API_KEY=...` を設定。"
    )
    api_key = (st.text_input(
        "Gemini APIキーを貼り付け",
        type="password",
        key="api_key_field",
        placeholder="AIza... を貼り付け",
        help="https://aistudio.google.com/apikey で取得",
    ) or "").strip()
    if api_key:
        st.success("APIキーを受け付けました。生成できます。")
    else:
        st.info("👆 キーを貼り付けると「生成して再生」が有効になります。")

voices_data = load_voices_yaml()

# ---- 左サイドバー: キャラ選択・ボイス・モデル ----
with st.sidebar:
    st.header("1. キャラクター選択")
    character = st.radio("キャラクター", list(CHARACTERS.keys()), label_visibility="collapsed")
    info = CHARACTERS[character]

    saved = voices_data["characters"].get(character, {})
    st.header("2. 音声候補")
    default_voice = saved.get("voice") or info["default_voice"]
    voice = st.selectbox(
        "ボイス(プルダウン)", VOICES,
        index=VOICES.index(default_voice) if default_voice in VOICES else 0,
    )
    model = st.selectbox(
        "モデル", MODELS,
        index=MODELS.index(saved["model"]) if saved.get("model") in MODELS else 0,
    )
    insecure_ssl = st.checkbox(
        "🔓 SSL検証を無効化（証明書エラー時）", value=True,
        help="社内ネットワーク等で CERTIFICATE_VERIFY_FAILED が出る場合に有効。ローカル用途のみ。",
    )
    if saved.get("voice"):
        st.success(f"現在の採用: {saved['voice']} / {saved.get('model', '')}")
    else:
        st.info("未採用(初期候補を表示中)")

# ---- メイン: セリフ入力・生成・採用 ----
left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader(f"3. セリフ入力 — {character}")
    style = st.text_area(
        "演技指示(スタイル) ※任意。声の方向づけに使われます",
        value=saved.get("style") or info["style"], height=80,
    )
    text = st.text_area("セリフ", value=info["line"], height=120)

    gen = st.button("▶ 生成して再生", type="primary", disabled=not api_key, use_container_width=True)
    if gen:
        if not text.strip():
            st.warning("セリフを入力してください。")
        else:
            try:
                with st.spinner(f"{voice} で生成中..."):
                    wav_bytes, rate = generate_tts(api_key, model, voice, text, style, insecure_ssl=insecure_ssl)
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                fname = safe_filename(character, voice)
                fpath = OUT_DIR / fname
                fpath.write_bytes(wav_bytes)
                # 直近の生成結果をセッションに保持(採用ボタンで参照)
                st.session_state["last"] = dict(
                    character=character, voice=voice, model=model, style=style,
                    text=text, path=str(fpath), rate=rate, wav=wav_bytes,
                )
                st.success(f"生成しました: {fname}  ({rate}Hz)")
            except ModuleNotFoundError:
                st.error("`google-genai` が未インストールです。`pip install -r requirements.txt` を実行してください。")
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "CERTIFICATE_VERIFY_FAILED" in msg:
                    st.error("SSL証明書エラーです。サイドバーの「SSL検証を無効化」をONにして再実行してください。")
                elif "RESOURCE_EXHAUSTED" in msg or "credits are depleted" in msg or "429" in msg:
                    st.error("APIの残高/クレジットが不足しています(429)。Google AI Studio の課金・残高を確認するか、無料枠で使えるキーに切り替えてください。")
                elif any(k in msg for k in ("401", "403", "API key", "PERMISSION", "UNAUTHENTICATED")):
                    st.error("APIキーが無効か権限がありません。https://aistudio.google.com/apikey で AIza… 形式のキーを発行して入れ替えてください。")
                else:
                    st.error(f"生成に失敗しました: {e}")
                st.exception(e)

    # 直近の生成結果を再生 + 保存(ダウンロード) + 採用
    last = st.session_state.get("last")
    if last and last["character"] == character:
        st.audio(last["wav"], format="audio/wav")
        st.caption(f"保存先: `{last['path']}`")
        st.download_button(
            "⬇ WAVを保存(ダウンロード)", data=last["wav"],
            file_name=Path(last["path"]).name, mime="audio/wav",
        )
        if st.button("★ この声を採用", use_container_width=True):
            voices_data["characters"][character] = dict(
                voice=last["voice"], model=last["model"], style=last["style"],
                sample=last["path"], line=last["text"],
                updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            try:
                save_voices_yaml(voices_data)
                st.success(f"{character} の声を「{last['voice']}」で採用し voices.yaml に保存しました。")
            except ModuleNotFoundError:
                st.error("`PyYAML` が未インストールです。`pip install -r requirements.txt` を実行してください。")
            except Exception as e:  # noqa: BLE001
                st.error(f"保存に失敗しました: {e}")

with right:
    st.subheader("7. 保存済み設定 (voices.yaml)")
    chars = voices_data.get("characters", {})
    if not chars:
        st.info("まだ採用された声はありません。")
    else:
        rows = [
            {
                "キャラ": name,
                "ボイス": v.get("voice", ""),
                "モデル": (v.get("model", "") or "").replace("gemini-2.5-", ""),
                "更新": v.get("updated_at", ""),
            }
            for name, v in chars.items()
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
        with st.expander("voices.yaml の中身を表示"):
            st.code(VOICES_YAML.read_text(encoding="utf-8") if VOICES_YAML.exists() else "(未作成)",
                    language="yaml")

st.divider()
st.caption(
    "※ APIキーは .env から読み込み、コードや画面には保存しません。"
    " 生成WAVは assets/voice_tests/ に character_voice_timestamp.wav 形式で保存されます。"
)

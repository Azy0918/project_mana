# -*- coding: utf-8 -*-
"""Google Cloud Text-to-Speech 経由の Gemini-TTS 合成。
AI Studio版(generativelanguage, RPD=100/日)の代替。Cloud TTSは分単位上限で
日次ハードキャップが無く、空応答(パートなし)も起きにくい。
認証: サービスアカウントJSON(.env GOOGLE_APPLICATION_CREDENTIALS、無ければ既定パス)。
当環境のSSL証明書問題のため検証は無効化(verify=False)。"""
import os, io, base64, wave, warnings, time
warnings.filterwarnings("ignore")
import httpx, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

SA_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or r"C:\Users\qvf03\qvf03636-b99ee45380ba.json"
SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
RATE = 24000

_sess = requests.Session(); _sess.verify = False
_client = httpx.Client(verify=False, timeout=120)
_creds = None


def _token():
    global _creds
    if _creds is None:
        _creds = service_account.Credentials.from_service_account_file(SA_PATH, scopes=SCOPES)
    if not _creds.valid:
        _creds.refresh(Request(session=_sess))
    return _creds.token


def synth(text, voice, model="gemini-2.5-flash-tts", prompt="", lang="ja-JP", rate=RATE,
          pitch=0.0, speaking_rate=1.0):
    """1行合成。(pcm_bytes, framerate) を返す。失敗時 RuntimeError。
    pitch: 半音単位(-20〜20、+で高く=若く可愛く)。speaking_rate: 0.25〜4.0。"""
    inp = {"text": text}
    if prompt:
        inp["prompt"] = prompt
    ac = {"audioEncoding": "LINEAR16", "sampleRateHertz": rate}
    if pitch:
        ac["pitch"] = pitch
    if speaking_rate and speaking_rate != 1.0:
        ac["speakingRate"] = speaking_rate
    body = {"input": inp,
            "voice": {"languageCode": lang, "name": voice, "model_name": model},
            "audioConfig": ac}
    r = _client.post(ENDPOINT, json=body,
                     headers={"Authorization": "Bearer " + _token(), "Content-Type": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    j = r.json()
    if "audioContent" not in j:
        raise RuntimeError("audioContent無し: " + str(j)[:200])
    wav = base64.b64decode(j["audioContent"])
    with wave.open(io.BytesIO(wav), "rb") as w:
        fr = w.getframerate(); pcm = w.readframes(w.getnframes())
    return pcm, fr


def synth_safe(text, voice, model="gemini-2.5-flash-tts", prompt="", lang="ja-JP",
               rate=RATE, max_retry=8, wait=35, pitch=0.0, speaking_rate=1.0):
    """分単位上限(429)は待って再試行。日次の壁が無いので最終的に通る。"""
    last = ""
    for _ in range(max_retry):
        try:
            return synth(text, voice, model, prompt, lang, rate, pitch, speaking_rate)
        except RuntimeError as e:
            last = str(e)
            if last.startswith("429") or "RESOURCE_EXHAUSTED" in last or "per minute" in last.lower() or "per_minute" in last.lower():
                time.sleep(wait); continue
            raise
    raise RuntimeError("429リトライ上限: " + last[:120])

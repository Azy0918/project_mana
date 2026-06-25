#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第十三レジ 起動音(サウンドロゴ)を Python だけで合成する。3バージョン出力。

『深夜二時の第十三レジ』用。普通のコンビニPOSレジが未来システムへ接続する瞬間を、
ホラーにならず「温かい / 少し不思議 / 近未来 / 深夜の静けさ」で表現する約3秒の音。

共通構成:
  0.00-0.15s  POSバーコード読取音「ピッ♪」(高め・短い)
  0.15-0.45s  レシートプリンタ「ジジッ」(短い機械ノイズ)
  0.45-1.80s  柔らかい未来シンセ(E-G-B、徐々に広がる)
  1.80-2.20s  ガラスのような小さなベル「ティン♪」
  2.20-3.00s  残響のみ、静かに消える

3バージョン(同じアイデンティティで方向性違い):
  v1 warm   : 温かい標準。バランス型のサウンドロゴ本命。
  v2 bright : 近未来・きらめき強め。上の倍音とベルを明るく、残響は浅め。
  v3 quiet  : 深夜・静けさ寄り。暗め/柔らかめ、残響深め、控えめで親密。

出力: <repo>/assets/sfx/register13_start_v{1,2,3}.wav と register13_start.wav(=v1)
       48000Hz / 24bit / ステレオ
依存: numpy のみ(必須)。soundfile があれば書き出しに使用、無ければ標準 wave で24bit出力。
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# 基本設定
# ---------------------------------------------------------------------------
SR = 48_000           # サンプリングレート
DUR = 3.0             # 全体の長さ(秒)
N = int(SR * DUR)     # 全サンプル数
RNG = np.random.default_rng(1313)   # 再現性のための固定シード(第十三→1313)

# 音名→周波数(平均律 A4=440)
E4, G4, B4, E5, B5, E6, G6, B6 = 329.628, 391.995, 493.883, 659.255, 987.767, 1318.510, 1567.982, 1975.533

# 倍音セット
HARM_BODY = [(1, 1.0), (2, 0.35), (3, 0.12)]   # 温かいパッド本体
HARM_AIR = [(1, 0.6), (2, 0.5), (4, 0.25)]     # 上に重ねる煌めき層


# ---------------------------------------------------------------------------
# 小道具(エンベロープ・オシレータ・フィルタ・リバーブ)
# ---------------------------------------------------------------------------
def env_ad(length, attack, decay, curve=2.0):
    """アタック→ディケイ(指数)の短いエンベロープ。打楽器/ベル系に使う。"""
    e = np.zeros(length)
    a = max(1, int(attack * SR))
    e[:a] = np.linspace(0.0, 1.0, a)
    d = length - a
    if d > 0:
        e[a:] = np.exp(-np.linspace(0.0, curve, d) * 3.0)
    return e


def env_asr(length, attack, release, sustain_level=1.0):
    """アタック→サスティン→リリースの滑らかなエンベロープ。パッド系に使う。"""
    e = np.full(length, sustain_level)
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    e[:a] = sustain_level * (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, a)))   # cosで滑らかに
    if r < length:
        e[length - r:] = sustain_level * (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, r)))
    return e


def place(buf, sig, start_sec):
    """buf(モノ)へ sig を start_sec の位置から加算合成(末尾はクリップ)。"""
    s = int(start_sec * SR)
    e = min(len(buf), s + len(sig))
    if s < len(buf):
        buf[s:e] += sig[: e - s]


def detuned_partial(freq, length, cents, harmonics):
    """わずかにデチューンした2基音 + 倍音を足した、温かみのある音色を作る。"""
    out = np.zeros(length)
    tt = np.arange(length) / SR
    for det in (-cents, cents):                 # ±デチューンで厚みとコーラス感
        f = freq * (2.0 ** (det / 1200.0))
        ph = RNG.uniform(0, 2 * np.pi)
        for k, amp in harmonics:                # 倍音(k倍, 振幅amp)
            out += amp * np.sin(2 * np.pi * f * k * tt + ph)
    return out / (2 * sum(a for _, a in harmonics))


def lp_kernel(cutoff, n=129):
    """簡易ローパス用のFIRカーネル(sinc×窓)。ノイズ整形やIRの暗さ調整に使う。"""
    m = np.arange(n) - (n - 1) / 2
    h = np.sinc(2 * (cutoff / SR) * m) * np.hanning(n)
    return h / h.sum()


def spectral_filter(x, hp=45.0, lp=14000.0):
    """周波数領域で高域/低域をなだらかに整える(ランブル除去・デジタル臭の角取り)。"""
    Nx = len(x)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(Nx, 1 / SR)
    hp_mask = np.clip((f - hp * 0.6) / (hp - hp * 0.6 + 1e-9), 0, 1)
    lp_mask = np.clip((lp * 1.25 - f) / (lp * 1.25 - lp + 1e-9), 0, 1)
    return np.fft.irfft(X * (hp_mask * lp_mask), Nx)


def fft_convolve(x, ir):
    """FFT畳み込み(リバーブIRの適用)。"""
    L = len(x) + len(ir) - 1
    nfft = 1 << (L - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, nfft) * np.fft.rfft(ir, nfft), nfft)[:L]


def make_reverb_ir(seconds, decay, dark):
    """指数減衰ノイズ→暗めにフィルタした、自然な部屋鳴りのインパルス応答。"""
    L = int(seconds * SR)
    tt = np.arange(L) / SR
    ir = RNG.standard_normal(L) * np.exp(-tt / decay)
    pre = int(0.012 * SR)
    ir[:pre] *= np.linspace(0, 1, pre)                       # 短いプリディレイ
    ir = np.convolve(ir, lp_kernel(dark, 129), mode="same")  # 高域を落として柔らかく
    ir /= np.max(np.abs(ir)) + 1e-9
    return ir * 0.9


# ---------------------------------------------------------------------------
# パート1: POSバーコード読取音「ピッ♪」 0.00-0.15s
# ---------------------------------------------------------------------------
def pos_beep(cfg):
    length = int(0.13 * SR)
    tt = np.arange(length) / SR
    f0 = cfg["beep_f0"]
    sig = np.sin(2 * np.pi * f0 * tt) + 0.18 * np.sin(2 * np.pi * f0 * 2 * tt)  # 高め+芯
    e = env_ad(length, attack=0.002, decay=0.11, curve=2.4)
    a = int(0.0015 * SR)
    e[:a] *= np.linspace(0, 1, a)                             # 角の無いアタック
    return cfg["beep_amp"] * sig * e


# ---------------------------------------------------------------------------
# パート2: レシートプリンタ「ジジッ」 0.15-0.45s
# ---------------------------------------------------------------------------
def printer_buzz(cfg):
    length = int(0.30 * SR)
    tt = np.arange(length) / SR
    noise = RNG.standard_normal(length)
    noise = np.convolve(noise, lp_kernel(4200, 129), mode="same")   # 中高域の機械ノイズ
    noise -= np.convolve(noise, lp_kernel(700, 129), mode="same")   # 低域を抜いて軽く
    am = 0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 92.0 * tt))          # ~92Hzのラトル(ジジ…)
    body = 0.25 * np.sin(2 * np.pi * 230.0 * tt)                     # わずかな機械的ボディ
    seg = env_ad(length, 0.004, 0.06, 3.0)                          # 「ジ」
    g = int(0.16 * SR)
    seg[g:] += env_ad(length - g, 0.004, 0.07, 3.0)                 # 「ジッ」(二度打ち)
    return cfg["buzz_amp"] * (noise * am + body) * seg


# ---------------------------------------------------------------------------
# パート3: 柔らかい未来シンセ E-G-B  0.45-1.80s(リリースで~2.2まで尾を引く)
# ---------------------------------------------------------------------------
def future_pad(cfg):
    length = int(1.75 * SR)
    out = np.zeros(length)
    ag = cfg["air_gain"]

    # (周波数, 入りの遅延, 倍音セット, 音量, アタック秒) — 低い順に点灯=アルペジオ的に広がる
    notes = [
        (E4, 0.00, HARM_BODY, 0.42, 0.22),
        (G4, 0.16, HARM_BODY, 0.36, 0.22),
        (B4, 0.32, HARM_BODY, 0.40, 0.22),
        (E5, 0.50, HARM_AIR, 0.20 * ag, 0.30),   # 煌めき(遅れて広がる)
        (B5, 0.70, HARM_AIR, 0.14 * ag, 0.34),
    ]
    if cfg.get("top_note"):                        # v2: さらに上の煌めきを追加
        notes.append((E6, 0.90, HARM_AIR, 0.10 * ag, 0.36))

    for freq, delay, harm, amp, atk in notes:
        ds = int(delay * SR)
        tone = detuned_partial(freq, length - ds, cents=5.0, harmonics=harm)
        out[ds:] += amp * tone * env_asr(length - ds, attack=atk, release=0.55)

    lo, hi = cfg["swell"]                           # 全体の膨らみ(crescendo)
    out *= np.linspace(lo, hi, length) ** 1.5

    sub = cfg["sub"] * np.sin(2 * np.pi * 164.814 * (np.arange(length) / SR))  # 温かい土台(E3)
    out += sub * env_asr(length, attack=0.4, release=0.6)
    return 0.5 * out


# ---------------------------------------------------------------------------
# パート4: ガラスのベル「ティン♪」 1.80-2.20s(残響は後段で付与)
# ---------------------------------------------------------------------------
def glass_bell(cfg):
    length = int(1.05 * SR)
    tt = np.arange(length) / SR
    f0 = cfg["bell_f0"]
    # ベルらしい非整数倍音(ガラス的なきらめき)
    partials = [(1.00, 1.00, 0.85), (2.01, 0.55, 0.70),
                (3.01, 0.32, 0.55), (4.20, 0.18, 0.45), (5.43, 0.10, 0.40)]
    sig = np.zeros(length)
    for ratio, amp, dec in partials:
        sig += amp * np.sin(2 * np.pi * f0 * ratio * tt) * np.exp(-tt / (dec * cfg["bell_dec"]))
    return cfg["bell_amp"] * sig * env_ad(length, attack=0.003, decay=0.95, curve=1.2)


# ---------------------------------------------------------------------------
# 合成・ミックス・マスタリング
# ---------------------------------------------------------------------------
def soft_clip(x, drive):
    """tanh による軽いサチュレーション(ピークを丸めて温かく、デジタル割れを防ぐ)。"""
    return np.tanh(x * drive) / np.tanh(drive)


def build(cfg):
    dry = np.zeros(N)         # 残響をかけない素の信号
    wet = np.zeros(N)         # 残響に送る信号

    beep = pos_beep(cfg)
    buzz = printer_buzz(cfg)
    pad = future_pad(cfg)
    bell = glass_bell(cfg)

    place(dry, beep, 0.00); place(dry, buzz, 0.15); place(dry, pad, 0.45); place(dry, bell, 1.80)
    # 残響送り: 未来シンセとベル中心(ピッ/ジジは控えめ)
    place(wet, pad, 0.45); place(wet, bell, 1.80); place(wet, beep * 0.25, 0.00)

    # ステレオ用に左右でわずかに異なるIRを使い、自然な広がりを作る
    irL = make_reverb_ir(cfg["rev_sec"], cfg["rev_dec"], cfg["rev_dark"])
    irR = make_reverb_ir(cfg["rev_sec"], cfg["rev_dec"] * 0.9, cfg["rev_dark"] * 0.93)
    revL = fft_convolve(wet, irL)[:N]
    revR = fft_convolve(wet, irR)[:N]

    rm = cfg["rev_mix"]
    stereo = np.vstack([dry + rm * revL, dry + rm * revR])

    # マスタリング: 高低域整え → サチュレーション → 正規化 → フェード
    for i in range(2):
        stereo[i] = spectral_filter(stereo[i], hp=45.0, lp=cfg["master_lp"])
    stereo = soft_clip(stereo, drive=cfg["drive"])
    stereo *= cfg["peak"] / (np.max(np.abs(stereo)) + 1e-9)

    fo = int(0.14 * SR)                              # 末尾を確実に無音へ
    stereo[:, N - fo:] *= 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, fo))
    fi = int(0.001 * SR)
    stereo[:, :fi] *= np.linspace(0, 1, fi)
    return stereo


# ---------------------------------------------------------------------------
# 3バージョンのパラメータ
# ---------------------------------------------------------------------------
VARIANTS = {
    "v1": dict(  # warm: 温かい標準(本命)
        beep_f0=2637.0, beep_amp=0.50, buzz_amp=0.16,
        air_gain=1.0, top_note=False, swell=(0.55, 1.0), sub=0.10,
        bell_f0=E6, bell_amp=0.32, bell_dec=1.0,
        rev_mix=0.33, rev_sec=1.25, rev_dec=0.34, rev_dark=6500.0,
        master_lp=14000.0, drive=1.25, peak=0.89,
    ),
    "v2": dict(  # bright: 近未来・きらめき強め
        beep_f0=2793.8, beep_amp=0.50, buzz_amp=0.15,
        air_gain=1.5, top_note=True, swell=(0.50, 1.0), sub=0.08,
        bell_f0=G6, bell_amp=0.34, bell_dec=1.15,
        rev_mix=0.27, rev_sec=1.20, rev_dec=0.30, rev_dark=8200.0,
        master_lp=16500.0, drive=1.20, peak=0.89,
    ),
    "v3": dict(  # quiet: 深夜・静けさ寄り
        beep_f0=2489.0, beep_amp=0.34, buzz_amp=0.12,
        air_gain=0.6, top_note=False, swell=(0.50, 0.82), sub=0.13,
        bell_f0=B5, bell_amp=0.26, bell_dec=1.25,
        rev_mix=0.46, rev_sec=1.65, rev_dec=0.52, rev_dark=5000.0,
        master_lp=11000.0, drive=1.30, peak=0.84,
    ),
}


# ---------------------------------------------------------------------------
# 24bit WAV 書き出し(soundfile があれば使用、無ければ標準 wave)
# ---------------------------------------------------------------------------
def write_wav_24(path: Path, stereo: np.ndarray) -> str:
    inter = np.ascontiguousarray(stereo.T.astype(np.float64))  # (N, 2) インターリーブ
    try:
        import soundfile as sf
        sf.write(str(path), inter, SR, subtype="PCM_24")
        return "soundfile"
    except Exception:
        # 標準 wave で24bit(3byte/サンプル, リトルエンディアン2の補数)を書く
        ints = np.round(np.clip(inter, -1.0, 1.0) * (2 ** 23 - 1)).astype("<i4")
        raw = bytearray(ints.tobytes())   # 4byte/サンプル
        del raw[3::4]                      # 各サンプルの最上位byteを落として3byte化
        with wave.open(str(path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(3)
            w.setframerate(SR)
            w.writeframes(bytes(raw))
        return "wave"


def main() -> int:
    out_dir = Path(__file__).resolve().parents[1] / "assets" / "sfx"
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, cfg in VARIANTS.items():
        stereo = build(cfg)
        out = out_dir / f"register13_start_{name}.wav"
        backend = write_wav_24(out, stereo)
        peak_db = 20 * np.log10(np.max(np.abs(stereo)) + 1e-12)
        rms_db = 20 * np.log10(np.sqrt(np.mean(stereo ** 2)) + 1e-12)
        print(f"{name}: {out.name}  ({backend}, {SR}Hz/24bit/stereo, "
              f"{stereo.shape[1]/SR:.3f}s, peak={peak_db:.1f}dBFS, rms={rms_db:.1f}dBFS)")
        if name == "v1":   # 仕様どおりの既定ファイル名(=v1)も用意
            write_wav_24(out_dir / "register13_start.wav", stereo)

    print(f"-> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

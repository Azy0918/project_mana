# 第十三レジ PV 人物アニメ化 実装案

作成日: 2026-06-15

## 結論

今の `make_new_pv_video.py` は、静止画にカメラ移動、雨、発光、スキャン線を足す構造になっている。
この延長だけでは「アニメっぽいPV」にはなるが、「アニメ」には届きにくい。

視聴者がアニメとして認識するには、最低でも以下のどれかが必要。

1. 目パチ、視線、眉、口などの顔の変化
2. 手を伸ばす、スキャンする、ボタンを押すなどの行動の変化
3. 体の重心移動、振り向き、後ずさりなどの姿勢の変化

一番現実的な次の到達点は、全身アニメではなく、
「人物クローズアップを数枚のキーフレームで動かす」方式。

## 現状の限界

現在の素材は、基本的に1カット1枚の完成絵。
完成絵の上からPillowで線を重ねる方式では、機械画面やスキャン光は動かせるが、人間の顔や手を自然に動かすのは難しい。

理由:

- 顔のパーツ位置が少しズレるだけで違和感が大きい
- 目や口の上書きは、元絵の線と二重になりやすい
- 腕や体を変形させると、背景や服の輪郭も歪む
- 1枚絵から隠れている部分を補完できない

そのため、人物を動かすには「差分画像」または「レイヤー分解」が必要。

## 実装レベル別案

### レベル1: キーフレーム差分方式

同じ構図で、少しだけ状態が違う画像を3から5枚作る。
それを連番フレームとして切り替え、間を短いクロスフェードでつなぐ。

例:

- タクミ close-up
  - `takumi_react_01_neutral.png`
  - `takumi_react_02_blink.png`
  - `takumi_react_03_mouth_open.png`
  - `takumi_react_04_look_left.png`

- ミナ close-up
  - `mina_calm_01_open.png`
  - `mina_calm_02_blink.png`
  - `mina_calm_03_look_down.png`

- 手元スキャン
  - `scan_01_before.png`
  - `scan_02_beam_on.png`
  - `scan_03_after.png`

メリット:

- 実装しやすい
- 既存の動画生成スクリプトに組み込みやすい
- 破綻しても差し替えが簡単

デメリット:

- 画像生成時に顔や服が微妙に変わる可能性がある
- 口パクとしては簡易的
- 本格的な体の動きには向かない

推奨度: 高い。

## レベル2: パーツ分解方式

1枚の人物絵を以下のようなパーツに分ける。

- 背景
- 頭
- 体
- 目
- 口
- 前髪
- 手

レンダー時に各パーツを少しだけ移動、回転、拡大縮小して合成する。

想定ディレクトリ:

```text
outputs/pv_character_layers/
  takumi_closeup/
    bg.png
    body.png
    head.png
    eye_open.png
    eye_closed.png
    mouth_closed.png
    mouth_open.png
```

実装イメージ:

- 目パチ: `eye_open` と `eye_closed` を数フレームで切り替え
- 口パク: `mouth_closed` と `mouth_open` を音声タイミング風に切り替え
- 呼吸: 胸や肩を1から2px上下
- 驚き: 頭を数px後ろへ、目を少し大きく、口を開く

メリット:

- 同じ顔のまま動かしやすい
- 口パク、目パチ、揺れが自然
- 一度作ると再利用しやすい

デメリット:

- パーツ分解が一番手間
- 元絵の隠れ部分を補う必要がある
- 自動切り抜きだけでは品質が足りない可能性がある

推奨度: 中から高。
工数をかけるなら最も堅実。

## レベル3: ComfyUI / AnimateDiff / OpenPose方式

ComfyUIやAnimateDiff系で、既存画像から数秒の動画を生成する。

狙える動き:

- 目パチ
- 髪揺れ
- 手を少し動かす
- 振り向き
- 口パク風

メリット:

- うまくいけば最もアニメっぽい
- 背景ごと自然に動く可能性がある

デメリット:

- セットアップが重い
- モデル導入、VRAM、依存関係が必要
- 顔や服が崩れる可能性がある
- 同一キャラ維持には追加調整が必要

推奨度: 中。
最終的には試す価値があるが、今のPV制作パイプラインの中核にするには不安定。

## レベル4: Blender / Grease Pencil / Live2D的な手作業リグ

人物を2Dパーツに分けて、手作業でリグを組む。

メリット:

- 破綻が少ない
- 一番制御しやすい
- ちゃんと作れば作品資産になる

デメリット:

- 工数が大きい
- 1分PV全体に入れるにはかなり時間が必要

推奨度: 長期的には高い。
ただし今すぐのPV改善では、まず1キャラ1カットの試作から始める。

## このプロジェクトでの推奨ロードマップ

### Phase 1: 手元アニメを本物のキーフレーム化

最初に人物の顔ではなく、手元を動かす。
顔より崩れが目立ちにくく、PV内の行動が増える。

作る素材:

- `pv_cut_19_hand_scan_before.png`
- `pv_cut_20_hand_scan_touch.png`
- `pv_cut_21_hand_scan_after.png`

実装:

- `Scene` に `frame_sequence` 的な概念を追加
- 1シーン内で3枚を切り替える
- 既存のスキャンビームと併用

期待効果:

- 今の「絵に光が乗る」から「手元が動作している」に近づく

### Phase 2: タクミのリアクション差分

次にタクミの顔を動かす。
ツッコミ役なので、PV内で一番動かす価値がある。

作る素材:

- `takumi_react_01.png`: 通常
- `takumi_react_02.png`: 目を見開く
- `takumi_react_03.png`: 口を開く
- `takumi_react_04.png`: 少し引く

実装:

- 既存の `pv_cut_07_takumi_closeup.png` を差し替え候補にする
- 3から4フレームを0.2から0.4秒単位で切り替える
- 完全な口パクではなく、リアクションアニメとして使う

期待効果:

- 「人が動いた」と視聴者が感じやすい

### Phase 3: ミナの低温リアクション

ミナは派手に動かさない。
まばたき、視線だけでよい。

作る素材:

- `mina_calm_01.png`: 通常
- `mina_calm_02.png`: まばたき
- `mina_calm_03.png`: 視線を下げる

期待効果:

- タクミとの温度差が出る

### Phase 4: 未来の会社員の疲れた動き

未来の会社員は肩を落とす、袋を持ち直す、俯く。

期待効果:

- キャラ説明がナレーション頼みではなくなる

## スクリプト実装案

`Scene` を拡張する。

```python
@dataclass(frozen=True)
class Scene:
    image: str
    seconds: float
    start_zoom: float
    end_zoom: float
    pan_x: float
    pan_y: float
    label: str = ""
    label_at: str = "none"
    sequence: tuple[str, ...] = ()
    sequence_mode: str = "hold"
```

`sequence` がある場合は、現在の `source = loaded[scene.image]` ではなく、ローカル時間に応じて画像を選ぶ。

```python
def select_scene_source(scene, local_t):
    if not scene.sequence:
        return loaded[scene.image]
    index = int(local_t * len(scene.sequence)) % len(scene.sequence)
    return loaded[scene.sequence[index]]
```

より自然にするならクロスフェードを入れる。

```python
def blend_sequence_frame(images, local_t):
    pos = local_t * (len(images) - 1)
    i = int(pos)
    frac = pos - i
    return Image.blend(images[i], images[min(i + 1, len(images) - 1)], frac)
```

## まず試作すべき最小構成

次の1カットだけでよい。

```text
タクミのリアクション 3枚差分
```

理由:

- 人が動く印象が一番強い
- ツッコミ役なので動きがキャラに合う
- PV内で「これはアニメだ」と感じる入口になる

ただし、顔の一貫性が崩れる可能性がある。
失敗した場合は手元アニメ3枚差分へ切り替える。

## 判断

工数をかけて本当にアニメに寄せるなら、
次は `--advanced-animation` の延長ではなく、
キーフレーム差分またはパーツ分解に移るべき。

最短の推奨:

1. タクミのリアクション差分3枚を作る
2. `Scene.sequence` を実装する
3. 既存PVに1カットだけ差し込んで比較する
4. 成功したらミナ、未来の会社員へ広げる


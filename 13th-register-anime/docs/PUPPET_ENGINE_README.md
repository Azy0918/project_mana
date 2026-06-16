# Puppet Motion Engine

`puppet_motion_engine.py` は、動画生成から人物の動的処理だけを切り出したエンジンです。

## 目的

- 1枚絵の人物に、Vtuber/Live2D風の微細な動きを重ねる
- 動画生成とは独立して、リグ座標や口パクを調整できるようにする
- 将来的に透過パーツ化した顔、前髪、口、目、腕を同じAPIで扱えるようにする

## 現在できること

- フェザーマスクによる人物パッチの揺れ
- 顔まわりの目パチ
- 音声RMSに連動した口パク風の口形変化
- 顔ハイライト
- `motion_scale` による身体パーツの動き抑制
- 視線の微揺れ、目のキャッチライト、複数段階の口形
- `MotionContext` による `local_t`、`global_frame`、`audio_level` の受け渡し
- `render_frame()` による1フレーム単位のエンジン単体描画
- `describe()` による登録リグの一覧取得

## 中核API

```python
from puppet_motion_engine import MotionContext, create_default_engine

engine = create_default_engine(1280, 720)
context = MotionContext(local_t=0.5, global_frame=45, audio_level=0.8)
frame = engine.render_frame(frame, "pv_cut_07_takumi_closeup.png", context)
```

`local_t` はカット内の進行度です。`0.0` が開始、`1.0` が終了です。
`audio_level` は `0.0` から `1.0` の口パク用音量です。

## 静止画プレビュー

動画を作らず、任意の画像だけで動作確認できます。

```powershell
python .\outputs\preview_puppet_engine.py --image pv_cut_07_takumi_closeup.png
python .\outputs\preview_puppet_engine.py --image pv_cut_08_mina_button.png
python .\outputs\preview_puppet_engine.py --image pv_cut_04_future_salaryman.png
python .\outputs\preview_puppet_engine.py --image pv_cut_07_takumi_closeup.png --contact-sheet
python .\outputs\preview_puppet_engine.py --image pv_cut_07_takumi_closeup.png --animated-gif --talk-demo
```

出力先:

```text
outputs/output_video/puppet_engine_previews/
```

## リグ一覧

現在エンジンに登録されている人物リグをCSVで確認できます。

```powershell
python .\outputs\inspect_puppet_engine.py
```

出力先:

```text
outputs/output_video/puppet_engine_rigs.csv
```

## JSONリグ

デフォルトリグをJSONに書き出せます。

```powershell
python .\outputs\export_puppet_rig_json.py
```

出力先:

```text
outputs/puppet_rigs/default_puppet_rigs.json
```

JSONリグを使ってプレビューできます。

```powershell
python .\outputs\preview_puppet_engine.py --rig-json .\outputs\puppet_rigs\default_puppet_rigs.json --image pv_cut_07_takumi_closeup.png
python .\outputs\preview_puppet_engine.py --rig-json .\outputs\puppet_rigs\default_puppet_rigs.json --image pv_cut_07_takumi_closeup.png --contact-sheet
python .\outputs\preview_puppet_engine.py --rig-json .\outputs\puppet_rigs\default_puppet_rigs.json --image pv_cut_07_takumi_closeup.png --animated-gif --talk-demo
python .\outputs\inspect_puppet_engine.py --rig-json .\outputs\puppet_rigs\default_puppet_rigs.json
```

調整の基本手順:

1. `outputs/puppet_rigs/default_puppet_rigs.json` の `box`, `motion_scale`, `left_eye`, `right_eye`, `mouth`, `highlight_box` を編集する
2. `preview_puppet_engine.py --rig-json ...` で静止画を確認する
3. 破綻がなければ `make_new_pv_video.py --rig-json ...` で同じJSONを動画生成側にも渡す

`motion_scale` はパッチの移動・回転・拡大の強さです。身体や胴体は `0.1` から `0.3`、手や小物は `0.4` から `0.7` くらいにすると、瞬きや口パク時に絵全体がずれる違和感を抑えやすくなります。

Vtuber感の調整は `face_rigs` 側の `gaze_strength`, `breath_strength`, `eye_light_strength`, `mouth_strength` を使います。タクミのように反応を出したいキャラは高め、ミナや未来の会社員のように抑えたいキャラは低めにします。

## 動画生成側で使う場合

```powershell
python .\outputs\make_new_pv_video.py --output-name sample.mp4 --textless --motion-effects --register-face --advanced-animation --puppet-animation --vtuber-motion
python .\outputs\make_new_pv_video.py --output-name sample.mp4 --textless --motion-effects --register-face --advanced-animation --puppet-animation --vtuber-motion --rig-json .\outputs\puppet_rigs\default_puppet_rigs.json
```

## 次の強化方針

- 座標をPython直書きからJSON/YAMLリグ定義に移す
- 透過パーツ素材に対応する
- 口形を `closed`, `small`, `wide`, `open` の複数形にする
- キャラごとの表情プリセットを追加する
- 顔パーツ、前髪、肩、手を親子関係で動かす階層リグを追加する
- 音素ベースの口形変化に対応する

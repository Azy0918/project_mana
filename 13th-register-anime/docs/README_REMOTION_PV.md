# Remotion PV 作業メモ

## 最新推奨動画

`remotion/out/13th_register_trailer.mp4`

## 目的

`第十三レジ` の1分宣伝PVを、字幕なし・紙芝居/ノベルゲーム風から一段進めて、Live2D/After Effects風の疑似パーツアニメとして構成する。

## 主要ファイル

- `remotion/src/NoSubtitleAnime.tsx`
  - 人物の呼吸、上下動、口パク、瞬き、レジ発光、スポット光、前景スライド影、終盤集合カット
- `remotion/src/trailerTimeline.ts`
  - PV台詞抜粋版のタイムライン
- `tools/build_remotion_trailer_assets.py`
  - 既存Aivis wavから `trailer_voice.wav` と `trailerTimeline.ts` を生成
- `tools/make_remotion_dialogue_sound_design.py`
  - 会話音声にBGM/効果音を合成し、MP4へmux

## 再生成コマンド

```powershell
python .\tools\build_remotion_trailer_assets.py

cd .\remotion
$env:PATH = 'C:\Users\qvf03\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
.\node_modules\.bin\tsc.cmd --noEmit
.\node_modules\.bin\remotion.cmd render .\src\index.ts TrailerAnimePV .\out\13th_register_trailer.mp4 --overwrite --codec=h264 --pixel-format=yuv420p

cd ..
python .\tools\make_remotion_dialogue_sound_design.py --video-in .\remotion\out\13th_register_trailer.mp4 --voice .\remotion\public\assets\13th-register\audio\trailer_voice.wav --output-video .\remotion\out\13th_register_trailer_sound.mp4 --design-gain 0.58 --duration-sec 60.05
```

## 現状の限界

- 本物のLive2Dのような腕・髪・顔の完全分解ではない
- 既存立ち絵を動かしているため、動きは呼吸・揺れ・口パク・瞬き・カメラワーク中心
- 常連のおじいさんは生成済み音声ログに台詞wavがないため、現版では映像参加のみ

## 次の改善候補

- 常連のおじいさんの短い一言を新規生成してPV音声に入れる
- 人物ごとに透過パーツを手作業で切り出し、頭・前髪・腕だけを独立レイヤー化する
- タクミの表情差分を追加し、ツッコミのときだけ目線と口形を強める
- レジの画面表情を数パターン増やす

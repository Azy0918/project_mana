# 第十三レジ PV 夜間作業サマリー

## 最新推奨版

- ローカル出力想定: `remotion/out/13th_register_trailer.mp4`

## 確認用

- コンタクトシート: `previews/*_contact_sheet.jpg`
- Vtuber風動き確認クリップ: `previews/*_vtuber_motion.mp4`

## 実装したこと

- Remotionに `TrailerAnimePV` コンポジションを追加
- 既存Aivis音声からPV用の台詞抜粋音声 `trailer_voice.wav` を生成
- `trailerTimeline.ts` を生成して、PV台詞に合わせて人物表示を切り替え
- タクミ、ミナ、未来の会社員、常連のおじいさん、第十三レジを1分内に登場
- 立ち絵に呼吸、上下動、微細な回転、口パク、瞬き、終盤集合カットを追加
- 第十三レジに発光、グリッチ、スキャンラインを追加
- 会話のタイミングに合わせてスポット光、レジ周辺の発光、前景スライド影を追加
- BGM/効果音を合成

## 検証

- `python -m py_compile .\tools\build_remotion_trailer_assets.py .\tools\make_remotion_dialogue_sound_design.py`
- `.\node_modules\.bin\tsc.cmd --noEmit`
- 音声: 60.05秒、peak 0.98、rms 0.1115

## 注意

- 常連のおじいさんは、現在の生成済み本編ログに台詞wavが見当たらないため、今回は映像参加のみ。
- 本物のLive2Dのような腕・髪・顔の完全分解ではなく、既存立ち絵をRemotionで疑似的に動かす方式。
- 自動頭部パーツ分解も試したが、顔のマスク境界が不自然だったため不採用。

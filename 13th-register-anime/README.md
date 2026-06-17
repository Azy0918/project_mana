# 13th Register Anime Project

`第十三レジ` のアニメPV化プロジェクトです。Remotion版の映像ソース、生成済み素材、Vtuber/Live2D風モーション確認ツールをGitHubで管理しやすい形に整理しています。

## 構成

- `remotion/`  
  Remotion本体。`src/`、`public/assets/13th-register/`、`package.json` を含みます。
- `tools/`  
  Python製の補助ツール。Puppet/Vtuber風モーションエンジン、プレビュー生成、素材生成補助を含みます。
- `puppet_rigs/`  
  人物パーツの動き・目・口・視線などを調整するJSONリグです。
- `previews/`  
  GitHub上でも確認しやすい軽量プレビューです。
- `docs/`  
  作業メモ、改善計画、モーションエンジン仕様です。

## セットアップ

```powershell
cd .\remotion
npm install
npm run lint
```

## Remotionプレビュー

```powershell
cd .\remotion
npm run dev
```

## Remotionレンダー

```powershell
cd .\remotion
npx remotion render .\src\index.ts TrailerAnimePV .\out\13th_register_trailer.mp4 --overwrite --codec=h264 --pixel-format=yuv420p
```

## Puppet/Vtuber風モーション確認

```powershell
python .\tools\preview_puppet_engine.py --rig-json .\puppet_rigs\default_puppet_rigs.json --image pv_cut_07_takumi_closeup.png --animated-gif --talk-demo --contact-sheet
```

出力先は `tools/output_video/puppet_engine_previews/` です。生成物は `.gitignore` で除外しています。

## GitHubで見られるプレビュー

このリポジトリを `Azy0918/13th-register-anime` としてGitHubへpushした場合、以下のリンクでGIFを確認できます。

- [タクミ Vtuber motion](https://github.com/Azy0918/13th-register-anime/blob/main/previews/takumi_vtuber_motion.gif)
- [ミナ Vtuber motion](https://github.com/Azy0918/13th-register-anime/blob/main/previews/mina_vtuber_motion.gif)
- [未来の会社員 Vtuber motion](https://github.com/Azy0918/13th-register-anime/blob/main/previews/salaryman_vtuber_motion.gif)

リポジトリ名を変える場合は、URL内の `13th-register-anime` を実際のリポジトリ名に置き換えます。

## GitHub運用方針

- Googleドライブ連携は使いません。
- `node_modules/`、`remotion/out/`、ログ、一時フレーム、完成動画の量産ファイルはコミットしません。
- ソース、リグ、軽量プレビュー、必要素材だけを管理します。
- 音声や画像で100MBを超えるファイルが出た場合は、Git LFSか外部配布を検討します。

## Bing Video Creator向け縦動画パック

`bing_video_creator/` に、Bing Video Creatorへ投入しやすい縦9:16用プロンプトと参考画像を用意しています。

- `bing_video_creator/bing_vertical_prompts.md`
- `bing_video_creator/bing_vertical_prompts.txt`
- `bing_video_creator/vertical_refs/*.jpg`

想定運用:

1. `bing_vertical_prompts.txt` から1カット分のプロンプトをコピーする
2. Bing Video Creatorに貼り付ける
3. 5秒程度の縦動画として生成する
4. 生成した動画をRemotionでつないでショートPVにする

## 現在の主な成果

- Remotionによる1分PV構成
- タクミ、ミナ、未来の会社員、第十三レジの表示制御
- Vtuber風の目パチ、視線揺れ、口パク、呼吸ハイライト
- JSONリグによる動き調整

## 現在の制作方針: 紙芝居風リアルイラスト版

人物アニメーションはいったん止め、リアル寄りのイラストを多数並べる紙芝居・ビジュアルノベル風の方向へ移行します。

- 設計書: `docs/KAMISHIBAI_REAL_ILLUSTRATION_PLAN.md`
- 画像生成用カットCSV: `tools/kamishibai_real_cut_prompts.csv`
- 目標: 1分で36カット前後
- 方針: 口パクや不自然な身体揺れを使わず、カット数、構図、音声演出で見せる

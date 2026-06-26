# PROJECT: 第十三レジ Anime / Kamishibai Project

> **📖 統合版（1冊）: [`docs/DESIGN_BIBLE_Ver1.1.md`](docs/DESIGN_BIBLE_Ver1.1.md)** — 全固定設定（世界観＋映像/字幕＋音声キャスト＋キャラ9＋舞台・設備＋12話構成）を1ファイルにまとめた読み物版。
> **共通固定設定（モジュール原本・最上位ルール）: [`docs/DESIGN_BIBLE.md`](docs/DESIGN_BIBLE.md)**
> 世界観・店舗・外観・ライティング・カメラ・画風・レシート・未来商品・演出・音・時間ルール・演技・禁止事項を一括固定。

## 目的

`第十三レジ` を、紙芝居・ビジュアルノベル風の縦型PVとして制作する。

現時点では、無理な人物アニメーションや不自然な口パクよりも、リアル寄りの高品質イラストを多数並べることを優先する。1枚ごとの絵の説得力、カット数、音声、BGM、効果音で映像として成立させる。

## 現在の制作方針

- 方向性: 紙芝居風、リアル寄りアニメイラスト、ビジュアルノベルのイベントCG調
- 画面: 縦9:16
- 長さ: まず1分PV
- カット数: 36カット前後
- 動き: 静止画ベース。使う場合は弱いズーム、フェード、光、雨、レジ画面の発光程度
- 音: ナレーション、BGM、効果音を重視
- 字幕: 基本なし。絵と音で伝える

## やらないこと

- 不自然な口パク
- キャラクター登場後の左右揺れ
- 瞬きのたびに身体がずれる処理
- 立ち絵を背景に貼っただけの画面
- レジ本体に不自然な四角枠を付けること
- Google Driveでの運用

## プロジェクトルート

ローカル作業場所:

```text
C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\anime-github-project
```

GitHub Pages公開用ワークツリー:

```text
C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages
```

既存GitHub連携先:

```text
C:\Users\qvf03\Documents\Codex\2026-05-27\ai-python-sqlite-streamlit-cards-csv
```

## 公開URL

紙芝居プレビュー:

```text
https://azy0918.github.io/project_mana/13th-register-kamishibai/?v=1
```

旧PVサウンド版:

```text
https://azy0918.github.io/project_mana/13th-register-pv/?v=sound3
```

## 主要フォルダ

```text
anime-github-project/
  docs/                         設計メモ、キャラクター資料
  docs/characters/              キャラクター設定と参照画像
  tools/                        生成補助、プレビュー作成スクリプト
  remotion/                     Remotion映像プロジェクト
  remotion/public/assets/       映像で使う画像素材
  previews/                     GitHubで見せやすい軽量プレビュー
  puppet_rigs/                  旧Live2D/Vtuber風検証用リグ
```

## 重要ファイル

- `README.md`: セットアップと全体説明
- `docs/KAMISHIBAI_REAL_ILLUSTRATION_PLAN.md`: 紙芝居風リアルイラスト版の設計
- `tools/kamishibai_real_cut_prompts.csv`: 36カット分の画像生成プロンプト
- `remotion/src/KamishibaiRealPV.tsx`: 紙芝居版PVのRemotion本体
- `remotion/src/kamishibaiCuts.ts`: カットタイムライン
- `previews/kamishibai_storyboard_preview.mp4`: 現在の紙芝居プレビュー動画
- `previews/kamishibai_storyboard_contact_sheet.jpg`: 36カット一覧
- `previews/kamishibai_opening_real_cuts_contact_sheet.jpg`: 実イラスト化済み冒頭カット一覧

## キャラクター

### タクミ

20代男性の新人バイト。ツッコミ役。困惑、呆れ、決意の表情を中心にする。女の子っぽくしない。

タクミは作品中で最も表情変化が大きいキャラクター。驚き・困惑・焦り・ツッコミ・呆れ・苦笑・安堵が頻繁に顔に表れる。基本的に感情を隠さず、リアクションが大きい。無表情やクールな主人公のように描かない。セリフごとに表情が変化する。

**固定設定（マスタープロンプト・全話/全カット共通の正本）: [`docs/characters/takumi/MASTER_PROMPT.md`](docs/characters/takumi/MASTER_PROMPT.md)**

### ミナ

20代前半女性（22〜24歳）。淡々、無表情、冷静。表情変化は小さく、視線と立ち位置で存在感を出す。

**固定設定（マスタープロンプト・全話/全カット共通の正本）: [`docs/characters/mina/MASTER_PROMPT.md`](docs/characters/mina/MASTER_PROMPT.md)**

### 第十三レジ

巨大装置ではなく、現代コンビニに現れる「13番目のPOSレジ」。卓上サイズ（目安35×45×55cm）で第12レジの隣に並び、午前2時17分だけ現れる。艶消しブラック＋細い青白LEDで店内に溶け込み、SF感は控えめ。通常はほぼ光らず、処理中だけ青白いラインが静かに流れる。**前面にネオンシアンの目二本＋小さな水平の口の「顔」を必ず持つ（必須・固定）**。「普通の新型レジに見えるが、レシート印字内容だけが異常」がコンセプト。

**固定設定（マスタープロンプト・全話/全カット共通の正本）: [`docs/characters/register13/MASTER_PROMPT.md`](docs/characters/register13/MASTER_PROMPT.md)**

### 未来の会社員（長谷山隆之）

40代前後の男性。2074年 食品流通管理課の会社員。くたびれた濃紺スーツ＋首元の記憶返品タグ。未来から来ているが派手なSF服ではなく、くたびれた現実感を優先する。

**固定設定: [`docs/characters/future_employee/MASTER_PROMPT.md`](docs/characters/future_employee/MASTER_PROMPT.md)**

> その他のキャラ（座木山辰哉／唐沢栄治／トラック運転手）の固定設定は [`docs/characters/README.md`](docs/characters/README.md) を参照。全キャラ共通ルールは [`docs/characters/COMMON_RULES.md`](docs/characters/COMMON_RULES.md)。

### 汗田竜司

54歳の自動車開発者。紫のサングラス、無精髭、ライディングジャケット、大型バイク。第2話候補の主軸。

**固定設定（マスタープロンプト・人物＋CB200X風バイク＋ライダー向きナビまで固定）: [`docs/characters/aseda_ryuji/MASTER_PROMPT.md`](docs/characters/aseda_ryuji/MASTER_PROMPT.md)**

## 舞台（コンビニ内装）

地方都市の国道沿いの24時間コンビニ。全12話を通して**同一店舗**で、レイアウト・棚/設備位置・照明・色調を固定する（カウンターは右奥、第12レジ＋第13レジ、コピー機は左奥＝次回予告装置、雑誌棚／おにぎり棚／冷蔵ケース／ホットスナック／コーヒーマシン／バックヤードの冷凍庫など位置固定）。色調は青/グレー/白/黒＋少し紫、暖色少なめのLED深夜感。未来感は出さず、異常なのは商品・レシート・第十三レジだけ。

**固定設定（マスタープロンプト・全話共通の正本）: [`docs/settings/store_interior/MASTER_PROMPT.md`](docs/settings/store_interior/MASTER_PROMPT.md)**

## 制作ルール

1. まず絵を増やす
2. 良いカットだけ残す
3. 顔が別人になったカットは再生成する
4. 動きは最後に足す
5. 音声とBGMは絵の完成度がある程度そろってから合わせる
6. 1つの動画に詰め込みすぎず、短い版を何度も更新する

## 画像生成ルール

基本プロンプトの方向性:

```text
vertical 9:16, realistic anime illustration, cinematic visual novel event CG,
late-night Japanese convenience store, rain, fluorescent lights, glass reflections,
subtle science fiction, high detail, grounded realism, no text, no subtitles, no logos
```

避ける要素:

```text
low quality, chibi, cartoonish, extra fingers, bad hands, distorted face,
text, subtitles, speech bubbles, logo, watermark, rectangular frame around register
```

## Remotion作業

開発プレビュー:

```powershell
cd .\remotion
npm run dev
```

型チェック:

```powershell
cd .\remotion
.\node_modules\.bin\tsc.cmd --noEmit
```

紙芝居PVレンダー:

```powershell
cd .\remotion
.\node_modules\.bin\remotion.cmd render .\src\index.ts KamishibaiRealPV .\out\13th_register_kamishibai_storyboard_preview.mp4 --overwrite --codec=h264 --pixel-format=yuv420p --crf=30 --timeout=120000 --concurrency=2
```

## Git運用

基本ブランチ:

```text
main
```

公開用GitHubブランチ:

```text
add-13th-register-anime-previews
```

GitHub Pages:

```text
gh-pages
```

コミットするもの:

- ソースコード
- 設計ドキュメント
- プロンプトCSV
- キャラクター参照資料
- 軽量プレビュー
- 採用済み画像素材

コミットしないもの:

- `node_modules/`
- `remotion/out/`
- 一時フレーム
- 大量の没画像
- ログ
- 100MBを超える動画ファイル

## 現在の到達点

- 紙芝居風リアルイラスト版の設計完了
- 第1話PV 36カット構成を作成済み
- 冒頭6カットを実イラスト化済み
- 36カットのRemotionタイムライン作成済み
- GitHub Pagesで紙芝居プレビューを公開済み
- 汗田竜司のキャラクター資料を追加済み

## 次にやること

1. `pv_007` から `pv_012` を実イラスト化する
2. タクミ、ミナ、未来の会社員の顔基準を固定する
3. 第十三レジの見た目をさらに印象的にする
4. 36カット中、最低18カットを実イラストに置き換える
5. 短編PV用ナレーションを紙芝居版に合わせて再調整する
6. BGM、雨音、入店音、レジ音、異常発光音を追加する
7. GitHub Pagesのプレビューを更新する

## 判断基準

迷ったら、次の順で優先する。

1. 絵として見たいか
2. キャラクターが別人になっていないか
3. 物語の状況が字幕なしで伝わるか
4. 1分PVとしてテンポがよいか
5. 音を入れたときに気持ちよく見られるか

このプロジェクトでは、まず「1分の完成した紙芝居PV」を作る。高度な人物アニメーションは、絵と音が揃ってから再検討する。

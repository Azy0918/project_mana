# Codex 引き継ぎ（作業場所をOneDrive外へ移設）

OneDrive同期がファイルを旧版へ巻き戻す事故が頻発したため、作業の正本を
OneDrive外へ完全移設しました。以下を厳守してください。

## 1. 正本（唯一の作業場所）
```
C:\Users\qvf03\Documents\Codex\2026-06-08\files-mentioned-by-the-user-13th\project_mana_gh_pages\
```
このリポジトリが github.io（gh-pages）の配信元です。ここだけを読み書きする。

## 2. 触ってはいけない場所（旧・OneDrive版＝破棄）
```
C:\Users\qvf03\OneDrive\ドキュメント\深夜二時の第十三レジ\   ← 読まない・書かない
```
古くて巻き戻る。ここを参照すると全部やり直しになる。

## 3. 画像差し替えの出力先（2コピー両方に置く）
リポジトリ直下の次の2フォルダ両方へ同じ画像を入れる：
```
project_mana_gh_pages\13th-register-kamishibai\   （プレイヤー本体）
project_mana_gh_pages\site\                        （配信用ミラー）
```

## 4. キャラ名は「エリ」（旧「ミナ」は全廃）
- 「ミナ」は「皆さん」と紛らわしいため **エリ** に統一済み。
- 画像ファイル名・プロンプト・メタ内の `mina`/`ミナ` は **eri/エリ** に直す。

## 5. 音声系ファイルは触らない（Claude/AivisSpeech管理）
次は私(Claude)がAivisSpeechで生成・管理する。Codexは上書きしないこと：
- `scene_manifest*.json`（`image`/`plannedImage` の画像名だけは更新可）
- `assets/*_full_voice_reading_*.wav`（連結音声）
- `assets/manifest_reading_*.json`
Codexの担当は **画像（plannedImage / assets内の画像）のみ**。

## 6. 公開
- 画像をリポジトリへ反映 → gh-pages へ push → github.io 配信。
- **ユーザーが「公開して」と言うまで公開はしない。**

## 補足（Claude側の構成・参考）
- 音声の中間クリップ: `C:\Users\qvf03\Documents\anime_clips\`（非OneDrive、Codex不要）
- 台本正本: `anime-github-project\ep01_revised.md`
- 声設定: `anime-github-project\tools\ep01_voice_cast.csv`（AivisSpeech）

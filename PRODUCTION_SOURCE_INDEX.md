# 深夜二時の第十三レジ 制作ソース索引

このファイルは、12話分のシナリオ本文と、画像・音声・紙芝居制作で参照する重要設定の置き場所を固定するための索引です。
作業を再開するときは、まずこのファイルを入口にする。

## 最優先で読むファイル

| 優先 | 用途 | ファイル |
|---:|---|---|
| 1 | 12話本文の一覧 | `_source_12episodes/00_索引.md` |
| 2 | キャラクター外見・シリーズ横断設定 | `13th-register-kamishibai/character_design_series.md` |
| 3 | 第十三レジの顔つき・筐体デザイン | `13th-register-kamishibai/register_design_reference.md` |
| 4 | 画像生成時のキャラ固定情報 | `13th-register-kamishibai/character_visual_locks.json` |
| 5 | 第1話紙芝居の場面manifest | `13th-register-kamishibai/scene_manifest.json` |
| 6 | 第1話音声キャスト確定表 | `anime-github-project/tools/ep01_voice_cast_selected.csv` |

## 12話シナリオ本文

シナリオ本文は `_source_12episodes/` に保管する。
各話の正式な参照順、タイトル、中心業務は `_source_12episodes/00_索引.md` を基準にする。

| 話数 | ファイル |
|---:|---|
| 1 | `_source_12episodes/01_未来のおにぎり_温めますか.md` |
| 2 | `_source_12episodes/02_ナビが未来を案内しました.md` |
| 3 | `_source_12episodes/03_昨日に溶けるアイスクリーム.md` |
| 4 | `_source_12episodes/04_未来レシートは先に謝る.md` |
| 5 | `_source_12episodes/05_昭和の伝票_まだ未処理です.md` |
| 6 | `_source_12episodes/06_賞味期限が生まれる前のパン.md` |
| 7 | `_source_12episodes/07_宇宙宅配便_店留めです.md` |
| 8 | `_source_12episodes/08_月面店_発注しすぎました.md` |
| 9 | `_source_12episodes/09_銀河ポイントカードはお持ちですか.md` |
| 10 | `_source_12episodes/10_あの会社員_返品済みです.md` |
| 11 | `_source_12episodes/11_第十二レジと第十四レジ.md` |
| 12 | `_source_12episodes/12_午前二時十七分_通常営業です.md` |

## キャラクター・世界観の決め事

| 用途 | ファイル |
|---|---|
| キャラクター外見・シリーズ横断設定 | `13th-register-kamishibai/character_design_series.md` |
| 第十三レジの顔つき・筐体デザイン | `13th-register-kamishibai/register_design_reference.md` |
| 画像生成時のキャラ固定情報 | `13th-register-kamishibai/character_visual_locks.json` |
| Gemini TTS検討用キャスト | `13th-register-kamishibai/assets/gemini_voice_cast_v1.json` |

### 現時点の重要整理

- 未来青年、座木山辰哉、汗田竜司は別人物として扱う。
- 汗田竜司は未来人ではない。現代の元・自動車研究開発者。
- 座木山辰哉は未来人ではない。近所の常連客で、日常側の変な人。
- 未来青年は第1話の未来の会社員本人で、第10話以降の縦軸に関わる。
- 第十三レジはマスコットではなく、黒いセルフレジ端末の画面に最小限のシアンの顔が出る存在。
- 生成画像内には字幕・UI・時計・SNSボタンを描き込まない。UIはHTML側で重ねる。

## 第1話制作データ

| 用途 | ファイル |
|---|---|
| 紙芝居プレイヤー用 scene manifest | `13th-register-kamishibai/scene_manifest.json` |
| 紙芝居プレイヤー用 visual cut plan | `13th-register-kamishibai/visual_cut_plan.json` |
| 第1話カット割りCSV | `13th-register-kamishibai/assets/ep01_visual_cut_plan.csv` |
| 第1話編集用セリフCSV | `13th-register-kamishibai/assets/ep01_dialogue_edit.csv` |
| 第1話読み・音声manifest | `13th-register-kamishibai/assets/manifest_reading_hiragana_mina_mao.json` |
| 第1話音声キャスト確定表 | `anime-github-project/tools/ep01_voice_cast_selected.csv` |
| 第1話音声生成計画 | `anime-github-project/tools/ep01_full_voice_generation_plan.csv` |
| 第1話本編台本CSV | `anime-github-project/tools/ep01_full_voice_script.csv` |
| 第1話可変紙芝居設計 | `anime-github-project/tools/ep01_full_variable_storyboard.csv` |
| 第1話カット割り | `anime-github-project/tools/ep01_full_cut_plan.csv` |
| 第1話キャラクター絵プロンプト | `anime-github-project/tools/ep01_character_art_prompts.csv` |
| 第1話音声候補 | `anime-github-project/tools/ep01_voice_casting_plan.csv` |

## 第2話以降の画像・紙芝居データ

| 用途 | ファイル |
|---|---|
| 第2話20カット公開画像 | `13th-register-kamishibai/assets/scenes/planned/ep02_vc01_company_parking_asada.png` から `ep02_vc20_night_shift_continues.png` |
| 第2話20カット再生成元 | `outputs/ep02_regenerated_20_20260619/` |
| 第2話20カット対応表 | `outputs/ep02_regenerated_20_20260619_mapping.json` |
| 第2話最新画像対応表 | `outputs/ep02_latest_20_image_mapping.json` |

## 公開ページ・配信先

| 用途 | ファイル |
|---|---|
| 公開紙芝居プレイヤー | `13th-register-kamishibai/index.html` |
| 互換用サイトプレイヤー | `site/index.html` |
| GitHub Pages用ルート | `index.html` |

公開URL:

- `https://azy0918.github.io/project_mana/13th-register-kamishibai/`

## 音声生成・キャスト関連

| 用途 | ファイル |
|---|---|
| Aivis話者一覧の保存版 | `anime-github-project/tools/aivis_speakers.json` |
| 第1話キャスト確定表 | `anime-github-project/tools/ep01_voice_cast_selected.csv` |
| 第1話音声生成スクリプト | `anime-github-project/tools/generate_ep01_full_voice.py` |
| 第1話最新合成音声の公開先 | `13th-register-kamishibai/assets/ep01_full_voice_reading_hiragana_mina_mao.wav` |
| 第1話最新合成音声の生成結果 | `outputs/ep01_voice_reading_hiragana_newcast_20260619/` |
| 第2話読み・音声manifest | `13th-register-kamishibai/assets/manifest_reading_hiragana_ep02.json` |
| 第2話音声生成スクリプト | `anime-github-project/tools/generate_ep02_full_voice.py`（manifest駆動・`synthesis_text`を合成。話者パラメータは `ep01_voice_cast_selected.csv` を `style_id` で参照） |
| 第2話最新合成音声の公開先 | `13th-register-kamishibai/assets/ep02_full_voice_reading_hiragana.wav`（`site/assets/` にも同梱） |
| 第2話最新合成音声の生成結果 | `outputs/ep02_voice_reading_hiragana/`（clips 63本＋連結wav＋timeline） |

## Git運用メモ

- この索引と、上記のシナリオ・設定ファイルは `gh-pages` ブランチで管理している。
- GitHub Pages公開対象は主に `13th-register-kamishibai/` と `site/`。
- 制作中の生成物は `outputs/` に残す。公開に必要なものだけ `13th-register-kamishibai/assets/` と `site/assets/` にコピーする。
- 一時的な話者一覧や検証キャッシュは、必要と判断したときだけGit管理に入れる。
